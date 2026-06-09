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

const DEFAULT_PREFIX = 'truesight_dao_';

export class StorageManager {
  private publicKeyKey: string;
  private privateKeyKey: string;

  constructor(options: StorageOptions | string = {}) {
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
  loadKeyPair(): KeyPair | null {
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
    } catch {
      return null;
    }
  }

  /**
   * Save the keypair to localStorage.
   * Also writes to legacy bare `publicKey`/`privateKey` for backwards
   * compatibility with the dapp ecosystem.
   */
  saveKeyPair(kp: KeyPair): void {
    try {
      localStorage.setItem(this.publicKeyKey, kp.publicKey);
      localStorage.setItem(this.privateKeyKey, kp.privateKey);
      // Backwards compat: also write bare keys for dapp pages
      localStorage.setItem('publicKey', kp.publicKey);
      localStorage.setItem('privateKey', kp.privateKey);
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
      localStorage.removeItem('publicKey');
      localStorage.removeItem('privateKey');
    } catch {
      // ignore
    }
  }
}
