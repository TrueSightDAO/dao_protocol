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

    // Load existing keys or generate new ones
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
