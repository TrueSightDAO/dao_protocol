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
export interface DaoClientOptions {
    edgarBase?: string;
    verifyUrl?: string;
    storagePrefix?: string;
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
export declare class DaoClient {
    publicKey: string;
    privateKey: string;
    private crypto;
    private payloadBuilder;
    private edgar;
    private storage;
    private generationSource;
    constructor(options?: DaoClientOptions);
    /**
     * Build a canonical payload, sign it, and submit to Edgar.
     */
    submit(eventName: string, attributes: Record<string, unknown>): Promise<SubmitResult>;
    /**
     * Build and sign a payload without submitting.
     */
    sign(eventName: string, attributes: Record<string, unknown>): Promise<SignResult>;
    /**
     * Get the credential slug: pk-<sha256-hash-prefix>
     */
    getSlug(): Promise<string>;
    /**
     * Verify a signed payload against a transaction ID.
     */
    verifyPayload(payload: string, txId: string): Promise<boolean>;
    /**
     * Generate a new keypair and store it.
     */
    generateKeyPair(): Promise<{
        publicKey: string;
        privateKey: string;
    }>;
    /**
     * Build the share text wrapper around a signed payload.
     */
    private buildShareText;
    static generateKeyPair(): Promise<{
        publicKey: string;
        privateKey: string;
    }>;
    static arrayBufferToBase64(buffer: ArrayBuffer): string;
    static base64ToArrayBuffer(base64: string): ArrayBuffer;
    static base64ToBase64Url(base64: string): string;
}
//# sourceMappingURL=index.d.ts.map