/**
 * localStorage manager for DAO keypairs.
 */
export interface KeyPair {
    publicKey: string;
    privateKey: string;
}
export interface StorageOptions {
    /** Explicit localStorage key for the public key (takes precedence over prefix). */
    publicKeyKey?: string;
    /** Explicit localStorage key for the private key (takes precedence over prefix). */
    privateKeyKey?: string;
    /** Prefix used to derive key names when publicKeyKey/privateKeyKey are not set. */
    prefix?: string;
}
export declare class StorageManager {
    private publicKeyKey;
    private privateKeyKey;
    constructor(options?: StorageOptions | string);
    /**
     * Load the keypair from localStorage.
     * Falls back to legacy unprefixed keys (`publicKey`/`privateKey`) and
     * migrates them to the configured keys on read.
     */
    loadKeyPair(): KeyPair | null;
    /**
     * Save the keypair to localStorage.
     * Also writes to legacy bare `publicKey`/`privateKey` for backwards
     * compatibility with the dapp ecosystem.
     */
    saveKeyPair(kp: KeyPair): void;
    /**
     * Remove the keypair from localStorage.
     */
    clearKeyPair(): void;
}
//# sourceMappingURL=storage.d.ts.map