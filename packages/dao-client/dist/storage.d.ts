/**
 * localStorage manager for DAO keypairs.
 */
export interface KeyPair {
    publicKey: string;
    privateKey: string;
}
export declare class StorageManager {
    private publicKeyKey;
    private privateKeyKey;
    constructor(prefix: string);
    /**
     * Load the keypair from localStorage.
     */
    loadKeyPair(): KeyPair | null;
    /**
     * Save the keypair to localStorage.
     */
    saveKeyPair(kp: KeyPair): void;
    /**
     * Remove the keypair from localStorage.
     */
    clearKeyPair(): void;
}
//# sourceMappingURL=storage.d.ts.map