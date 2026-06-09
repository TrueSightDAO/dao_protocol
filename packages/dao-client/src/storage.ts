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
   * Falls back to legacy unprefixed keys (`publicKey`/`privateKey`) and
   * migrates them to the new prefixed keys on read.
   */
  loadKeyPair(): KeyPair | null {
    try {
      // Try prefixed keys first
      let publicKey = localStorage.getItem(this.publicKeyKey);
      let privateKey = localStorage.getItem(this.privateKeyKey);
      if (publicKey && privateKey) {
        return { publicKey, privateKey };
      }

      // Fall back to legacy unprefixed keys
      publicKey = localStorage.getItem('publicKey');
      privateKey = localStorage.getItem('privateKey');
      if (publicKey && privateKey) {
        // Migrate to new prefixed keys
        localStorage.setItem(this.publicKeyKey, publicKey);
        localStorage.setItem(this.privateKeyKey, privateKey);
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
