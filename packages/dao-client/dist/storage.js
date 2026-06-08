/**
 * localStorage manager for DAO keypairs.
 */
export class StorageManager {
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
        }
        catch {
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
        }
        catch (e) {
            console.warn('Failed to save keypair to localStorage:', e);
        }
    }
    /**
     * Remove the keypair from localStorage.
     */
    clearKeyPair() {
        try {
            localStorage.removeItem(this.publicKeyKey);
            localStorage.removeItem(this.privateKeyKey);
        }
        catch {
            // ignore
        }
    }
}
//# sourceMappingURL=storage.js.map