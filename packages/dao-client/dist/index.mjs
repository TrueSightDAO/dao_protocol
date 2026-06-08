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
   * Synchronous key generation — only works if keys were previously generated
   * and stored. Falls back to async generation.
   */
  generateKeyPairSync() {
    throw new Error("Use generateKeyPair() (async) or load from storage");
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
};

// src/edgar.ts
var EdgarClient = class {
  constructor(baseUrl, verifyUrl) {
    this.baseUrl = baseUrl.replace(/\/+$/, "");
    this.submitUrl = `${this.baseUrl}/dao/submit_contribution`;
    this.verifyUrl = verifyUrl;
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
};

// src/storage.ts
var StorageManager = class {
  constructor(prefix) {
    this.publicKeyKey = `${prefix}public_key`;
    this.privateKeyKey = `${prefix}private_key`;
  }
  /**
   * Load the keypair from localStorage.
   */
  loadKeyPair() {
    try {
      const publicKey = localStorage.getItem(this.publicKeyKey);
      const privateKey = localStorage.getItem(this.privateKeyKey);
      if (publicKey && privateKey) {
        return { publicKey, privateKey };
      }
      return null;
    } catch {
      return null;
    }
  }
  /**
   * Save the keypair to localStorage.
   */
  saveKeyPair(kp) {
    try {
      localStorage.setItem(this.publicKeyKey, kp.publicKey);
      localStorage.setItem(this.privateKeyKey, kp.privateKey);
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
    } catch {
    }
  }
};

// src/index.ts
var DaoClient = class {
  constructor(options = {}) {
    const edgarBase = options.edgarBase || "https://edgar.truesight.me";
    const verifyUrl = options.verifyUrl || "https://dapp.truesight.me/verify_request.html";
    const storagePrefix = options.storagePrefix || "truesight_dao_";
    this.crypto = new CryptoUtils();
    this.payloadBuilder = new PayloadBuilder();
    this.edgar = new EdgarClient(edgarBase, verifyUrl);
    this.storage = new StorageManager(storagePrefix);
    this.generationSource = typeof window !== "undefined" ? window.location.href.split("#")[0] : "https://truesight.me";
    const existing = this.storage.loadKeyPair();
    if (existing) {
      this.publicKey = existing.publicKey;
      this.privateKey = existing.privateKey;
    } else {
      const fresh = this.crypto.generateKeyPairSync();
      this.publicKey = fresh.publicKey;
      this.privateKey = fresh.privateKey;
      this.storage.saveKeyPair(fresh);
    }
  }
  /**
   * Build a canonical payload, sign it, and submit to Edgar.
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
