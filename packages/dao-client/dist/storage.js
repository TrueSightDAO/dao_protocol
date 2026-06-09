/**
 * localStorage manager for DAO keypairs.
 */
const DEFAULT_PREFIX = 'truesight_dao_';
export class StorageManager {
    constructor(options = {}) {
        // Backwards compat: accept a plain string prefix
        if (typeof options === 'string') {
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
            // Try configured keys first
            let publicKey = localStorage.getItem(this.publicKeyKey);
            let privateKey = localStorage.getItem(this.privateKeyKey);
            if (publicKey && privateKey) {
                return { publicKey, privateKey };
            }
            // Fall back to legacy unprefixed keys
            publicKey = localStorage.getItem('publicKey');
            privateKey = localStorage.getItem('privateKey');
            if (publicKey && privateKey) {
                // Migrate to configured keys
                localStorage.setItem(this.publicKeyKey, publicKey);
                localStorage.setItem(this.privateKeyKey, privateKey);
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
     * Also writes to legacy bare `publicKey`/`privateKey` for backwards
     * compatibility with the dapp ecosystem.
     */
    saveKeyPair(kp) {
        try {
            localStorage.setItem(this.publicKeyKey, kp.publicKey);
            localStorage.setItem(this.privateKeyKey, kp.privateKey);
            // Backwards compat: also write bare keys for dapp pages
            localStorage.setItem('publicKey', kp.publicKey);
            localStorage.setItem('privateKey', kp.privateKey);
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
            localStorage.removeItem('publicKey');
            localStorage.removeItem('privateKey');
        }
        catch {
            // ignore
        }
    }
}
//# sourceMappingURL=storage.js.map