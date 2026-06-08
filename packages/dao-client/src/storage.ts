/**
 * localStorage manager for DAO keypairs.
 */

export interface KeyPair {
  publicKey: string;
  privateKey: string;
}

export class StorageManager {
  private publicKeyKey: string;
  private privateKeyKey: string;

  constructor(prefix: string) {
    this.publicKeyKey = `${prefix}public_key`;
    this.privateKeyKey = `${prefix}private_key`;
  }

  /**
   * Load the keypair from localStorage.
   */
  loadKeyPair(): KeyPair | null {
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
  saveKeyPair(kp: KeyPair): void {
    try {
      localStorage.setItem(this.publicKeyKey, kp.publicKey);
      localStorage.setItem(this.privateKeyKey, kp.privateKey);
    } catch (e) {
      console.warn('Failed to save keypair to localStorage:', e);
    }
  }

  /**
   * Remove the keypair from localStorage.
   */
  clearKeyPair(): void {
    try {
      localStorage.removeItem(this.publicKeyKey);
      localStorage.removeItem(this.privateKeyKey);
    } catch {
      // ignore
    }
  }
}
