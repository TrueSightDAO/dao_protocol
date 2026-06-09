// src/crypto.ts
var CryptoUtils = class _CryptoUtils {
  /**
   * Generate an RSA-2048 keypair.
   */
  async generateKeyPair() {
    const keyPair = await window.crypto.subtle.generateKey(
      {
        name: "RSASSA-PKCS1-v1_5",
        modulusLength: 2048,
        publicExponent: new Uint8Array([1, 0, 1]),
        hash: "SHA-256"
      },
      true,
      ["sign", "verify"]
    );
    const publicKey = await window.crypto.subtle.exportKey("spki", keyPair.publicKey);
    const privateKey = await window.crypto.subtle.exportKey("pkcs8", keyPair.privateKey);
    return {
      publicKey: _CryptoUtils.arrayBufferToBase64(publicKey),
      privateKey: _CryptoUtils.arrayBufferToBase64(privateKey)
    };
  }
  /**
   * Sign a message string with the given private key (base64 PKCS#8).
   */
  async sign(privateKeyBase64, message) {
    const key = await window.crypto.subtle.importKey(
      "pkcs8",
      _CryptoUtils.base64ToArrayBuffer(privateKeyBase64),
      { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
      false,
      ["sign"]
    );
    const signature = await window.crypto.subtle.sign(
      "RSASSA-PKCS1-v1_5",
      key,
      new TextEncoder().encode(message)
    );
    return _CryptoUtils.arrayBufferToBase64(signature);
  }
  /**
   * Verify a signed payload against a transaction ID (signature).
   */
  async verify(publicKeyBase64, payload, signatureBase64) {
    const key = await window.crypto.subtle.importKey(
      "spki",
      _CryptoUtils.base64ToArrayBuffer(publicKeyBase64),
      { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
      false,
      ["verify"]
    );
    return window.crypto.subtle.verify(
      "RSASSA-PKCS1-v1_5",
      key,
      _CryptoUtils.base64ToArrayBuffer(signatureBase64),
      new TextEncoder().encode(payload)
    );
  }
  /**
   * Compute the credential slug from a public key.
   * Returns: pk-<first 12 chars of SHA-256 hash, base64url-encoded>
   */
  async publicKeyToSlug(publicKeyBase64) {
    const keyBytes = _CryptoUtils.base64ToArrayBuffer(publicKeyBase64);
    const hashBuffer = await window.crypto.subtle.digest("SHA-256", keyBytes);
    const hashBase64 = _CryptoUtils.arrayBufferToBase64(hashBuffer);
    const hashBase64Url = _CryptoUtils.base64ToBase64Url(hashBase64);
    return "pk-" + hashBase64Url.substring(0, 12);
  }
  // ---- Static helpers ----
  static arrayBufferToBase64(buffer) {
    const bytes = new Uint8Array(buffer);
    let binary = "";
    for (let i = 0; i < bytes.byteLength; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary);
  }
  static base64ToArrayBuffer(base64) {
    const binary = atob(base64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) {
      bytes[i] = binary.charCodeAt(i);
    }
    return bytes.buffer;
  }
  static base64ToBase64Url(base64) {
    return base64.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }
};

// src/payload.ts
var PayloadBuilder = class {
  /**
   * Build a canonical payload string from an event name and attributes.
   * (v1.0.x compatible — no Timestamp injection, no field guard)
   */
  build(eventName, attributes) {
    if (!eventName) {
      throw new Error("eventName is required");
    }
    const lines = [];
    for (const [key, rawValue] of Object.entries(attributes)) {
      if (rawValue === void 0 || rawValue === null)
        continue;
      let value;
      if (Array.isArray(rawValue)) {
        value = rawValue.join(", ");
      } else if (typeof rawValue === "object") {
        try {
          value = JSON.stringify(rawValue);
        } catch {
          value = String(rawValue);
        }
      } else {
        value = String(rawValue);
      }
      if (value.includes("\n")) {
        value = value.replace(/\r?\n/g, "\n  ");
      }
      lines.push(`- ${key}: ${value}`);
    }
    return `[${eventName.trim()}]
${lines.join("\n")}
--------`;
  }
  /**
   * Build a canonical payload with v1.1.0 safety features:
   *   - Auto-injects Timestamp as the first field (ISO 8601 UTC)
   *   - Rejects field values containing [... EVENT] substrings
   *
   * The Timestamp is INSIDE the signed body (before --------), so it
   * varies the signature on each call — preventing HTTP 409 "Duplicate
   * submission" errors from persistent keys.
   */
  buildSubmitEvent(eventName, fields, timestamp) {
    if (!eventName) {
      throw new Error("eventName is required");
    }
    this.validateFieldValues(fields);
    const ts = timestamp || (/* @__PURE__ */ new Date()).toISOString();
    const augmented = {
      Timestamp: ts,
      ...fields
    };
    return this.build(eventName, augmented);
  }
  /**
   * Validate that no field value contains a bracketed event tag like
   * [CONTRIBUTION EVENT] or [PRACTICE EVENT]. Edgar dispatches by
   * substring matching on the event name — a bracketed tag inside a
   * value causes a 422 misdispatch.
   *
   * Throws an error with the offending field name if found.
   */
  validateFieldValues(fields) {
    const eventTagPattern = /\[[A-Za-z]+(?:\s+[A-Za-z]+)*\s+EVENT\]/i;
    for (const [key, rawValue] of Object.entries(fields)) {
      if (rawValue === void 0 || rawValue === null)
        continue;
      let value;
      if (Array.isArray(rawValue)) {
        value = rawValue.join(", ");
      } else if (typeof rawValue === "object") {
        try {
          value = JSON.stringify(rawValue);
        } catch {
          value = String(rawValue);
        }
      } else {
        value = String(rawValue);
      }
      if (eventTagPattern.test(value)) {
        throw new Error(
          `Field '${key}' contains a bracketed event tag which would cause Edgar misdispatch. Value: "${value.slice(0, 100)}". Remove or escape the bracketed tag.`
        );
      }
    }
  }
};

// src/edgar.ts
var EdgarClient = class {
  constructor(baseUrl, verifyUrl) {
    this.baseUrl = baseUrl.replace(/\/+$/, "");
    this.submitUrl = `${this.baseUrl}/dao/submit_contribution`;
    this.verifyUrl = verifyUrl;
    this.checkSignatureUrl = `${this.baseUrl}/dao/check_digital_signature`;
  }
  /**
   * Build the share text wrapper around a signed payload.
   */
  buildShareText(payload, txId, publicKey, generationSource) {
    return [
      payload,
      "",
      `My Digital Signature: ${publicKey}`,
      "",
      `Request Transaction ID: ${txId}`,
      "",
      `This submission was generated using ${generationSource}`,
      "",
      `Verify submission here: ${this.verifyUrl}`
    ].join("\n");
  }
  /**
   * Parse Edgar's submit_contribution response into a structured outcome.
   *
   * Edgar response shapes:
   *   200: { status: 'success', signature_verification: 'success', email_registration?: {...} }
   *   409: { status: 'error', error: 'Duplicate submission...' }
   *   422: { status: 'error', error: 'Email onboarding failed', email_registration: {ok: false, ...} }
   *   500: { status: 'error', error: '...' }
   */
  async parseSubmitResponse(response, txId, slug) {
    const httpStatus = response.status;
    let body = {};
    try {
      body = await response.json();
    } catch {
    }
    const base = {
      ok: false,
      txId,
      slug,
      httpStatus
    };
    if (httpStatus === 409) {
      return {
        ...base,
        status: "duplicate",
        error: body.error || "Duplicate submission"
      };
    }
    if (httpStatus === 422) {
      const emailReg = this.parseEmailRegistration(body);
      return {
        ...base,
        status: "validation_failed",
        error: body.error || "Validation failed",
        emailRegistration: emailReg
      };
    }
    if (httpStatus >= 500) {
      return {
        ...base,
        status: "server_error",
        error: body.error || `Server error (${httpStatus})`
      };
    }
    if (httpStatus === 200) {
      const sigVerification = body.signature_verification;
      if (sigVerification === "failed" || sigVerification === "error") {
        return {
          ...base,
          status: "signature_verification_failed",
          error: "Signature verification failed on Edgar"
        };
      }
      const emailReg = this.parseEmailRegistration(body);
      return {
        ...base,
        ok: true,
        status: "submitted",
        emailRegistration: emailReg
      };
    }
    return {
      ...base,
      status: "server_error",
      error: `Unexpected HTTP ${httpStatus}`
    };
  }
  /**
   * Parse the email_registration field from Edgar's response body.
   */
  parseEmailRegistration(body) {
    const er = body.email_registration;
    if (!er || !er.applicable) {
      return void 0;
    }
    let status = "not_applicable";
    if (er.ok === true) {
      if (er.activated === true) {
        status = "activated";
      } else if (er.already_consumed === true) {
        status = "already_consumed";
      } else if (er.pending_verification === true) {
        status = "pending_verification";
      }
    } else if (er.ok === false) {
      if (er.pubkey_mismatch === true) {
        status = "pubkey_mismatch";
      } else if (er.not_found === true) {
        status = "not_found";
      }
    }
    return {
      status,
      contributorEmail: er.contributor_email
    };
  }
  /**
   * Call Edgar's check_digital_signature endpoint.
   * Returns the authoritative registration status for a public key.
   */
  async checkRegistration(publicKey) {
    const url = `${this.checkSignatureUrl}?signature=${encodeURIComponent(publicKey)}`;
    try {
      const response = await fetch(url, {
        method: "GET",
        cache: "no-store"
      });
      if (!response.ok) {
        if (response.status === 404) {
          return { registered: false, error: "No matching contributor digital signature" };
        }
        const text = await response.text().catch(() => "");
        return { registered: false, error: `HTTP ${response.status}: ${text.slice(0, 200)}` };
      }
      const body = await response.json();
      if (body.registered === true) {
        return {
          registered: true,
          contributor_name: body.contributor_name,
          contributor_email: body.contributor_email
        };
      }
      if (body.pending_verification === true) {
        return {
          registered: false,
          pending_verification: true,
          contributor_email: body.contributor_email
        };
      }
      return {
        registered: false,
        error: body.error || "Unknown response"
      };
    } catch (err) {
      return {
        registered: false,
        error: `Network error: ${err instanceof Error ? err.message : String(err)}`
      };
    }
  }
};

// src/storage.ts
var DEFAULT_PREFIX = "truesight_dao_";
var StorageManager = class {
  constructor(options = {}) {
    if (typeof options === "string") {
      options = { prefix: options };
    }
    const prefix = options.prefix || DEFAULT_PREFIX;
    this.publicKeyKey = options.publicKeyKey || `${prefix}public_key`;
    this.privateKeyKey = options.privateKeyKey || `${prefix}private_key`;
  }
  /**
   * Load the keypair from localStorage.
   * Falls back to legacy unprefixed keys (`publicKey`/`privateKey`) and
   * migrates them to the configured keys on read.
   */
  loadKeyPair() {
    try {
      let publicKey = localStorage.getItem(this.publicKeyKey);
      let privateKey = localStorage.getItem(this.privateKeyKey);
      if (publicKey && privateKey) {
        return { publicKey, privateKey };
      }
      publicKey = localStorage.getItem("publicKey");
      privateKey = localStorage.getItem("privateKey");
      if (publicKey && privateKey) {
        localStorage.setItem(this.publicKeyKey, publicKey);
        localStorage.setItem(this.privateKeyKey, privateKey);
        return { publicKey, privateKey };
      }
      return null;
    } catch {
      return null;
    }
  }
  /**
   * Save the keypair to localStorage.
   * Also writes to legacy bare `publicKey`/`privateKey` for backwards
   * compatibility with the dapp ecosystem.
   */
  saveKeyPair(kp) {
    try {
      localStorage.setItem(this.publicKeyKey, kp.publicKey);
      localStorage.setItem(this.privateKeyKey, kp.privateKey);
      localStorage.setItem("publicKey", kp.publicKey);
      localStorage.setItem("privateKey", kp.privateKey);
    } catch (e) {
      console.warn("Failed to save keypair to localStorage:", e);
    }
  }
  /**
   * Remove the keypair from localStorage.
   */
  clearKeyPair() {
    try {
      localStorage.removeItem(this.publicKeyKey);
      localStorage.removeItem(this.privateKeyKey);
      localStorage.removeItem("publicKey");
      localStorage.removeItem("privateKey");
    } catch {
    }
  }
};

// src/index.ts
var DaoClient = class _DaoClient {
  constructor(options = {}) {
    const edgarBase = options.edgarBase || "https://edgar.truesight.me";
    const verifyUrl = options.verifyUrl || "https://dapp.truesight.me/verify_request.html";
    this.crypto = new CryptoUtils();
    this.payloadBuilder = new PayloadBuilder();
    this.edgar = new EdgarClient(edgarBase, verifyUrl);
    this.storage = new StorageManager({
      publicKeyKey: options.publicKeyKey,
      privateKeyKey: options.privateKeyKey,
      prefix: options.storagePrefix
    });
    if (options.generationSource) {
      this.generationSource = options.generationSource;
    } else if (typeof window !== "undefined") {
      this.generationSource = window.location.origin + window.location.pathname;
    } else {
      this.generationSource = "https://truesight.me";
    }
    const existing = this.storage.loadKeyPair();
    if (existing) {
      this.publicKey = existing.publicKey;
      this.privateKey = existing.privateKey;
    } else {
      this.publicKey = "";
      this.privateKey = "";
    }
  }
  /**
   * Static async factory. Creates a DaoClient and ensures a keypair exists
   * (loading from storage or generating a new one).
   *
   * Usage:
   *   const client = await DaoClient.create();
   */
  static async create(options = {}) {
    const client = new _DaoClient(options);
    await client.ensureKeys();
    return client;
  }
  /**
   * Ensure a keypair exists — loads from storage or generates a new one.
   * Safe to call multiple times; no-op if keys already loaded.
   */
  async ensureKeys() {
    if (this.publicKey && this.privateKey) {
      return;
    }
    const existing = this.storage.loadKeyPair();
    if (existing) {
      this.publicKey = existing.publicKey;
      this.privateKey = existing.privateKey;
    } else {
      const kp = await this.crypto.generateKeyPair();
      this.publicKey = kp.publicKey;
      this.privateKey = kp.privateKey;
      this.storage.saveKeyPair(kp);
    }
  }
  /**
   * Build a canonical payload, sign it, and submit to Edgar.
   * (v1.0.x compatible — no Timestamp injection, no field guard)
   */
  async submit(eventName, attributes) {
    const { payload, txId } = await this.sign(eventName, attributes);
    const shareText = this.buildShareText(payload, txId);
    const formData = new FormData();
    formData.append("text", shareText);
    const response = await fetch(this.edgar.submitUrl, {
      method: "POST",
      body: formData
    });
    if (!response.ok) {
      const errorText = await response.text().catch(() => "");
      throw new Error(`Edgar submit failed: ${response.status} ${errorText}`);
    }
    const json = await response.json();
    return { json, txId };
  }
  /**
   * Build and sign a payload without submitting.
   */
  async sign(eventName, attributes) {
    const payload = this.payloadBuilder.build(eventName, attributes);
    const txId = await this.crypto.sign(this.privateKey, payload);
    const shareText = this.buildShareText(payload, txId);
    return { payload, txId, shareText };
  }
  /**
   * Submit an event with v1.1.0 safety features:
   *   - Auto-injects Timestamp (prevents 409 duplicates from persistent keys)
   *   - Guards field values against [... EVENT] substrings (prevents misdispatch)
   *   - Parses Edgar's response into structured outcomes
   *
   * Returns a structured result with status, txId, slug, and optional
   * email registration details.
   */
  async submitEvent(options) {
    const source = options.generationSource || this.generationSource;
    const payload = this.payloadBuilder.buildSubmitEvent(options.eventType, options.fields);
    const txId = await this.crypto.sign(this.privateKey, payload);
    const shareText = this.edgar.buildShareText(payload, txId, this.publicKey, source);
    const slug = await this.crypto.publicKeyToSlug(this.publicKey);
    const formData = new FormData();
    formData.append("text", shareText);
    let response;
    try {
      response = await fetch(this.edgar.submitUrl, {
        method: "POST",
        body: formData
      });
    } catch (err) {
      return {
        ok: false,
        status: "server_error",
        txId,
        slug,
        httpStatus: 0,
        error: `Network error: ${err instanceof Error ? err.message : String(err)}`
      };
    }
    return this.edgar.parseSubmitResponse(response, txId, slug);
  }
  /**
   * Submit a [CREDENTIALING ATTESTATION EVENT] — used by credentialing
   * programs (Butterfly Effect Club, capoeira Tribo Mirim Bahia, etc.)
   * to attest that a participant has completed a program milestone.
   *
   * The attestor (admin/teacher) signs this event with their own key.
   * The tokenomics GAS handler picks it up, verifies the attestor is
   * authorized (sheet editor), and commits identity.json +
   * attestations/<ts>.json to lineage-credentials.
   *
   * @see CREDENTIALING_PLATFORM.md §4c for the event spec
   * @see butterfly-effect-club/PROPOSAL.md §6.1 for payload format
   */
  async submitAttestation(options) {
    const fields = {
      Program: options.program,
      "Attestation Type": options.attestationType,
      "Attestor Public Key": this.publicKey,
      "Attestee Public Key": options.attesteePublicKey,
      "Attestee Name": options.attesteeName
    };
    if (options.capturedAt) {
      fields["Captured At"] = options.capturedAt;
    }
    if (options.programYear) {
      fields["Program Year"] = options.programYear;
    }
    if (options.sourceUrl) {
      fields["Source URL"] = options.sourceUrl;
    }
    if (options.payload) {
      fields["Payload JSON"] = JSON.stringify(options.payload, null, 2);
    }
    return this.submitEvent({
      eventType: "CREDENTIALING ATTESTATION EVENT",
      fields,
      generationSource: options.generationSource
    });
  }
  /**
   * Submit a [CREDENTIALING QUALIFICATION EVENT] — used for live-cohort
   * admission (the first of a two-event path: qualification then attestation).
   *
   * For alumni (graduation_date in the past), use submitAttestation() directly.
   * For live cohorts, call submitQualification() on admission and
   * submitAttestation() on completion.
   *
   * @see CREDENTIALING_PLATFORM.md §4b for the event spec
   */
  async submitQualification(options) {
    const fields = {
      Program: options.program,
      "Practitioner Public Key": options.participantPublicKey,
      "Practitioner Name": options.participantName
    };
    if (options.capturedAt) {
      fields["Captured At"] = options.capturedAt;
    }
    if (options.programYear) {
      fields["Program Year"] = options.programYear;
    }
    if (options.sourceUrl) {
      fields["Source URL"] = options.sourceUrl;
    }
    if (options.payload) {
      fields["Payload JSON"] = JSON.stringify(options.payload, null, 2);
    }
    return this.submitEvent({
      eventType: "CREDENTIALING QUALIFICATION EVENT",
      fields,
      generationSource: options.generationSource
    });
  }
  /**
   * Register an email address with the DAO identity system.
   * Submits an [EMAIL REGISTERED EVENT] and returns the registration status.
   *
   * After calling this, the user must click the verification link sent to
   * their email to complete registration.
   */
  async registerEmail(email) {
    return this.submitEvent({
      eventType: "EMAIL REGISTERED EVENT",
      fields: {
        Email: email
      }
    });
  }
  /**
   * Verify an email registration using the verification key from the
   * email link. Submits an [EMAIL VERIFICATION EVENT].
   *
   * Call this when the user lands on your page with ?em=...&vk=... params.
   */
  async verifyEmail(email, verificationKey) {
    return this.submitEvent({
      eventType: "EMAIL VERIFICATION EVENT",
      fields: {
        Email: email,
        "Verification Key": verificationKey
      }
    });
  }
  /**
   * Check the registration status of the current public key against Edgar.
   * This is a read-only GET call (not a submission).
   *
   * Returns the authoritative registration status including whether the
   * key is registered, pending verification, or not found.
   */
  async checkRegistration() {
    return this.edgar.checkRegistration(this.publicKey);
  }
  /**
   * Get the credential slug: pk-<sha256-hash-prefix>
   */
  async getSlug() {
    return this.crypto.publicKeyToSlug(this.publicKey);
  }
  /**
   * Verify a signed payload against a transaction ID.
   */
  async verifyPayload(payload, txId) {
    return this.crypto.verify(this.publicKey, payload, txId);
  }
  /**
   * Generate a new keypair and store it.
   */
  async generateKeyPair() {
    const kp = await this.crypto.generateKeyPair();
    this.publicKey = kp.publicKey;
    this.privateKey = kp.privateKey;
    this.storage.saveKeyPair(kp);
    return kp;
  }
  /**
   * Build the share text wrapper around a signed payload.
   */
  buildShareText(payload, txId) {
    return this.edgar.buildShareText(payload, txId, this.publicKey, this.generationSource);
  }
  // ---- Static helpers ----
  static async generateKeyPair() {
    const crypto = new CryptoUtils();
    return crypto.generateKeyPair();
  }
  static arrayBufferToBase64(buffer) {
    return CryptoUtils.arrayBufferToBase64(buffer);
  }
  static base64ToArrayBuffer(base64) {
    return CryptoUtils.base64ToArrayBuffer(base64);
  }
  static base64ToBase64Url(base64) {
    return CryptoUtils.base64ToBase64Url(base64);
  }
};
export {
  DaoClient
};
