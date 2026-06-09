/**
 * @truesight_dao/dao-client
 *
 * Zero-dependency browser library for TrueSight DAO identity management,
 * cryptographic signing, and Edgar submission.
 *
 * Usage:
 *   import { DaoClient } from '@truesight_dao/dao-client';
 *   const client = new DaoClient();
 *   await client.submit('CONTRIBUTION EVENT', { ... });
 */

import { CryptoUtils } from './crypto';
import { PayloadBuilder } from './payload';
import { EdgarClient, SubmitEventResponse, CheckRegistrationResponse } from './edgar';
import { StorageManager } from './storage';

export interface DaoClientOptions {
  edgarBase?: string;
  verifyUrl?: string;
  storagePrefix?: string;
  generationSource?: string;
}

export interface SubmitResult {
  json: Record<string, unknown>;
  txId: string;
}

export interface SignResult {
  payload: string;
  txId: string;
  shareText: string;
}

export interface SubmitEventOptions {
  /** The event type, e.g. 'CONTRIBUTION EVENT' */
  eventType: string;
  /** Key-value fields to include in the signed body */
  fields: Record<string, unknown>;
  /**
   * Override the generation source URL.
   * Defaults to window.location.origin + pathname in browser environments.
   * Required when window is undefined (Node.js).
   */
  generationSource?: string;
}

export { SubmitEventResponse, CheckRegistrationResponse };
export type { EmailRegistrationStatus } from './edgar';

export class DaoClient {
  public publicKey: string;
  public privateKey: string;

  private crypto: CryptoUtils;
  private payloadBuilder: PayloadBuilder;
  private edgar: EdgarClient;
  private storage: StorageManager;
  private generationSource: string;

  constructor(options: DaoClientOptions = {}) {
    const edgarBase = options.edgarBase || 'https://edgar.truesight.me';
    const verifyUrl = options.verifyUrl || 'https://dapp.truesight.me/verify_request.html';
    const storagePrefix = options.storagePrefix || 'truesight_dao_';

    this.crypto = new CryptoUtils();
    this.payloadBuilder = new PayloadBuilder();
    this.edgar = new EdgarClient(edgarBase, verifyUrl);
    this.storage = new StorageManager(storagePrefix);

    // generationSource: explicit param > window.location > fallback
    if (options.generationSource) {
      this.generationSource = options.generationSource;
    } else if (typeof window !== 'undefined') {
      this.generationSource = window.location.origin + window.location.pathname;
    } else {
      // In Node.js, generationSource must be provided explicitly
      this.generationSource = 'https://truesight.me';
    }

    // Load existing keys from storage (no async generation in constructor)
    const existing = this.storage.loadKeyPair();
    if (existing) {
      this.publicKey = existing.publicKey;
      this.privateKey = existing.privateKey;
    } else {
      // Placeholder — keys will be generated on first ensureKeys() or generateKeyPair() call
      this.publicKey = '';
      this.privateKey = '';
    }
  }

  /**
   * Static async factory. Creates a DaoClient and ensures a keypair exists
   * (loading from storage or generating a new one).
   *
   * Usage:
   *   const client = await DaoClient.create();
   */
  static async create(options: DaoClientOptions = {}): Promise<DaoClient> {
    const client = new DaoClient(options);
    await client.ensureKeys();
    return client;
  }

  /**
   * Ensure a keypair exists — loads from storage or generates a new one.
   * Safe to call multiple times; no-op if keys already loaded.
   */
  async ensureKeys(): Promise<void> {
    if (this.publicKey && this.privateKey) {
      return; // already have keys
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
  async submit(eventName: string, attributes: Record<string, unknown>): Promise<SubmitResult> {
    const { payload, txId } = await this.sign(eventName, attributes);
    const shareText = this.buildShareText(payload, txId);

    const formData = new FormData();
    formData.append('text', shareText);

    const response = await fetch(this.edgar.submitUrl, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      const errorText = await response.text().catch(() => '');
      throw new Error(`Edgar submit failed: ${response.status} ${errorText}`);
    }

    const json = await response.json();
    return { json, txId };
  }

  /**
   * Build and sign a payload without submitting.
   */
  async sign(eventName: string, attributes: Record<string, unknown>): Promise<SignResult> {
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
  async submitEvent(options: SubmitEventOptions): Promise<SubmitEventResponse> {
    const source = options.generationSource || this.generationSource;

    // Build the canonical payload with Timestamp + field guard
    const payload = this.payloadBuilder.buildSubmitEvent(options.eventType, options.fields);

    // Sign the payload
    const txId = await this.crypto.sign(this.privateKey, payload);

    // Build the share text wrapper
    const shareText = this.edgar.buildShareText(payload, txId, this.publicKey, source);

    // Compute slug
    const slug = await this.crypto.publicKeyToSlug(this.publicKey);

    // Submit to Edgar
    const formData = new FormData();
    formData.append('text', shareText);

    let response: Response;
    try {
      response = await fetch(this.edgar.submitUrl, {
        method: 'POST',
        body: formData,
      });
    } catch (err) {
      return {
        ok: false,
        status: 'server_error',
        txId,
        slug,
        httpStatus: 0,
        error: `Network error: ${err instanceof Error ? err.message : String(err)}`,
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
  async submitAttestation(options: {
    /** Program slug, e.g. 'butterfly-effect' or 'tribomirim' */
    program: string;
    /** Type of attestation, e.g. 'program-completion', 'program-admission' */
    attestationType: string;
    /** The participant's public key (base64 SPKI) */
    attesteePublicKey: string;
    /** The participant's display name */
    attesteeName: string;
    /** ISO 8601 timestamp of when the attestation was captured */
    capturedAt?: string;
    /** Program year, e.g. '2025-2026' */
    programYear?: string;
    /** URL of the source program/roster */
    sourceUrl?: string;
    /** Optional JSON payload with additional metadata */
    payload?: Record<string, unknown>;
    /** Override the generation source URL */
    generationSource?: string;
  }): Promise<SubmitEventResponse> {
    const fields: Record<string, unknown> = {
      Program: options.program,
      'Attestation Type': options.attestationType,
      'Attestor Public Key': this.publicKey,
      'Attestee Public Key': options.attesteePublicKey,
      'Attestee Name': options.attesteeName,
    };

    if (options.capturedAt) {
      fields['Captured At'] = options.capturedAt;
    }
    if (options.programYear) {
      fields['Program Year'] = options.programYear;
    }
    if (options.sourceUrl) {
      fields['Source URL'] = options.sourceUrl;
    }
    if (options.payload) {
      fields['Payload JSON'] = JSON.stringify(options.payload, null, 2);
    }

    return this.submitEvent({
      eventType: 'CREDENTIALING ATTESTATION EVENT',
      fields,
      generationSource: options.generationSource,
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
  async submitQualification(options: {
    /** Program slug, e.g. 'butterfly-effect' or 'tribomirim' */
    program: string;
    /** The participant's public key (base64 SPKI) */
    participantPublicKey: string;
    /** The participant's display name */
    participantName: string;
    /** ISO 8601 timestamp */
    capturedAt?: string;
    /** Program year, e.g. '2025-2026' */
    programYear?: string;
    /** URL of the source program/roster */
    sourceUrl?: string;
    /** Optional JSON payload with additional metadata */
    payload?: Record<string, unknown>;
    /** Override the generation source URL */
    generationSource?: string;
  }): Promise<SubmitEventResponse> {
    const fields: Record<string, unknown> = {
      Program: options.program,
      'Practitioner Public Key': options.participantPublicKey,
      'Practitioner Name': options.participantName,
    };

    if (options.capturedAt) {
      fields['Captured At'] = options.capturedAt;
    }
    if (options.programYear) {
      fields['Program Year'] = options.programYear;
    }
    if (options.sourceUrl) {
      fields['Source URL'] = options.sourceUrl;
    }
    if (options.payload) {
      fields['Payload JSON'] = JSON.stringify(options.payload, null, 2);
    }

    return this.submitEvent({
      eventType: 'CREDENTIALING QUALIFICATION EVENT',
      fields,
      generationSource: options.generationSource,
    });
  }

  /**
   * Register an email address with the DAO identity system.
   * Submits an [EMAIL REGISTERED EVENT] and returns the registration status.
   *
   * After calling this, the user must click the verification link sent to
   * their email to complete registration.
   */
  async registerEmail(email: string): Promise<SubmitEventResponse> {
    return this.submitEvent({
      eventType: 'EMAIL REGISTERED EVENT',
      fields: {
        Email: email,
      },
    });
  }

  /**
   * Verify an email registration using the verification key from the
   * email link. Submits an [EMAIL VERIFICATION EVENT].
   *
   * Call this when the user lands on your page with ?em=...&vk=... params.
   */
  async verifyEmail(email: string, verificationKey: string): Promise<SubmitEventResponse> {
    return this.submitEvent({
      eventType: 'EMAIL VERIFICATION EVENT',
      fields: {
        Email: email,
        'Verification Key': verificationKey,
      },
    });
  }

  /**
   * Check the registration status of the current public key against Edgar.
   * This is a read-only GET call (not a submission).
   *
   * Returns the authoritative registration status including whether the
   * key is registered, pending verification, or not found.
   */
  async checkRegistration(): Promise<CheckRegistrationResponse> {
    return this.edgar.checkRegistration(this.publicKey);
  }

  /**
   * Get the credential slug: pk-<sha256-hash-prefix>
   */
  async getSlug(): Promise<string> {
    return this.crypto.publicKeyToSlug(this.publicKey);
  }

  /**
   * Verify a signed payload against a transaction ID.
   */
  async verifyPayload(payload: string, txId: string): Promise<boolean> {
    return this.crypto.verify(this.publicKey, payload, txId);
  }

  /**
   * Generate a new keypair and store it.
   */
  async generateKeyPair(): Promise<{ publicKey: string; privateKey: string }> {
    const kp = await this.crypto.generateKeyPair();
    this.publicKey = kp.publicKey;
    this.privateKey = kp.privateKey;
    this.storage.saveKeyPair(kp);
    return kp;
  }

  /**
   * Build the share text wrapper around a signed payload.
   */
  private buildShareText(payload: string, txId: string): string {
    return this.edgar.buildShareText(payload, txId, this.publicKey, this.generationSource);
  }

  // ---- Static helpers ----

  static async generateKeyPair(): Promise<{ publicKey: string; privateKey: string }> {
    const crypto = new CryptoUtils();
    return crypto.generateKeyPair();
  }

  static arrayBufferToBase64(buffer: ArrayBuffer): string {
    return CryptoUtils.arrayBufferToBase64(buffer);
  }

  static base64ToArrayBuffer(base64: string): ArrayBuffer {
    return CryptoUtils.base64ToArrayBuffer(base64);
  }

  static base64ToBase64Url(base64: string): string {
    return CryptoUtils.base64ToBase64Url(base64);
  }
}
