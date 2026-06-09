/**
 * Cryptographic utilities for RSA-2048 key generation, signing, and hashing.
 * Uses the Web Crypto API (window.crypto.subtle).
 */

export class CryptoUtils {
  /**
   * Generate an RSA-2048 keypair.
   */
  async generateKeyPair(): Promise<{ publicKey: string; privateKey: string }> {
    const keyPair = await window.crypto.subtle.generateKey(
      {
        name: 'RSASSA-PKCS1-v1_5',
        modulusLength: 2048,
        publicExponent: new Uint8Array([1, 0, 1]),
        hash: 'SHA-256',
      },
      true,
      ['sign', 'verify']
    );

    const publicKey = await window.crypto.subtle.exportKey('spki', keyPair.publicKey);
    const privateKey = await window.crypto.subtle.exportKey('pkcs8', keyPair.privateKey);

    return {
      publicKey: CryptoUtils.arrayBufferToBase64(publicKey),
      privateKey: CryptoUtils.arrayBufferToBase64(privateKey),
    };
  }

  /**
   * Sign a message string with the given private key (base64 PKCS#8).
   */
  async sign(privateKeyBase64: string, message: string): Promise<string> {
    const key = await window.crypto.subtle.importKey(
      'pkcs8',
      CryptoUtils.base64ToArrayBuffer(privateKeyBase64),
      { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' },
      false,
      ['sign']
    );

    const signature = await window.crypto.subtle.sign(
      'RSASSA-PKCS1-v1_5',
      key,
      new TextEncoder().encode(message)
    );

    return CryptoUtils.arrayBufferToBase64(signature);
  }

  /**
   * Verify a signed payload against a transaction ID (signature).
   */
  async verify(publicKeyBase64: string, payload: string, signatureBase64: string): Promise<boolean> {
    const key = await window.crypto.subtle.importKey(
      'spki',
      CryptoUtils.base64ToArrayBuffer(publicKeyBase64),
      { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' },
      false,
      ['verify']
    );

    return window.crypto.subtle.verify(
      'RSASSA-PKCS1-v1_5',
      key,
      CryptoUtils.base64ToArrayBuffer(signatureBase64),
      new TextEncoder().encode(payload)
    );
  }

  /**
   * Compute the credential slug from a public key.
   * Returns: pk-<first 12 chars of SHA-256 hash, base64url-encoded>
   */
  async publicKeyToSlug(publicKeyBase64: string): Promise<string> {
    const keyBytes = CryptoUtils.base64ToArrayBuffer(publicKeyBase64);
    const hashBuffer = await window.crypto.subtle.digest('SHA-256', keyBytes);
    const hashBase64 = CryptoUtils.arrayBufferToBase64(hashBuffer);
    const hashBase64Url = CryptoUtils.base64ToBase64Url(hashBase64);
    return 'pk-' + hashBase64Url.substring(0, 12);
  }

  // ---- Static helpers ----

  static arrayBufferToBase64(buffer: ArrayBuffer): string {
    const bytes = new Uint8Array(buffer);
    let binary = '';
    for (let i = 0; i < bytes.byteLength; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary);
  }

  static base64ToArrayBuffer(base64: string): ArrayBuffer {
    const binary = atob(base64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) {
      bytes[i] = binary.charCodeAt(i);
    }
    return bytes.buffer;
  }

  static base64ToBase64Url(base64: string): string {
    return base64.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  }
}
