/**
 * @truesight/dao-client
 *
 * Zero-dependency browser library for TrueSight DAO identity management,
 * cryptographic signing, and Edgar submission.
 *
 * Usage:
 *   import { DaoClient } from '@truesight/dao-client';
 *   const client = new DaoClient();
 *   await client.submit('CONTRIBUTION EVENT', { ... });
 */
import { CryptoUtils } from './crypto';
import { PayloadBuilder } from './payload';
import { EdgarClient } from './edgar';
import { StorageManager } from './storage';
export class DaoClient {
    constructor(options = {}) {
        const edgarBase = options.edgarBase || 'https://edgar.truesight.me';
        const verifyUrl = options.verifyUrl || 'https://dapp.truesight.me/verify_request.html';
        const storagePrefix = options.storagePrefix || 'truesight_dao_';
        this.crypto = new CryptoUtils();
        this.payloadBuilder = new PayloadBuilder();
        this.edgar = new EdgarClient(edgarBase, verifyUrl);
        this.storage = new StorageManager(storagePrefix);
        this.generationSource = typeof window !== 'undefined'
            ? window.location.href.split('#')[0]
            : 'https://truesight.me';
        // Load existing keys or generate new ones
        const existing = this.storage.loadKeyPair();
        if (existing) {
            this.publicKey = existing.publicKey;
            this.privateKey = existing.privateKey;
        }
        else {
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
}
//# sourceMappingURL=index.js.map