/**
 * Cryptographic utilities for RSA-2048 key generation, signing, and hashing.
 * Uses the Web Crypto API (window.crypto.subtle).
 */
export declare class CryptoUtils {
    /**
     * Generate an RSA-2048 keypair.
     */
    generateKeyPair(): Promise<{
        publicKey: string;
        privateKey: string;
    }>;
    /**
     * Synchronous key generation — only works if keys were previously generated
     * and stored. Falls back to async generation.
     */
    generateKeyPairSync(): {
        publicKey: string;
        privateKey: string;
    };
    /**
     * Sign a message string with the given private key (base64 PKCS#8).
     */
    sign(privateKeyBase64: string, message: string): Promise<string>;
    /**
     * Verify a signed payload against a transaction ID (signature).
     */
    verify(publicKeyBase64: string, payload: string, signatureBase64: string): Promise<boolean>;
    /**
     * Compute the credential slug from a public key.
     * Returns: pk-<first 12 chars of SHA-256 hash, base64url-encoded>
     */
    publicKeyToSlug(publicKeyBase64: string): Promise<string>;
    static arrayBufferToBase64(buffer: ArrayBuffer): string;
    static base64ToArrayBuffer(base64: string): ArrayBuffer;
    static base64ToBase64Url(base64: string): string;
}
//# sourceMappingURL=crypto.d.ts.map