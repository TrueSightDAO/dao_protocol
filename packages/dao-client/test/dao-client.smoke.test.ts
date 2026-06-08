/**
 * Runtime smoke test for @truesight_dao/dao-client browser bundle.
 *
 * Loads the ACTUAL built/minified IIFE bundle and asserts the global shape.
 * This catches the exact bug that broke oracle prod twice: esbuild
 * --global-name wraps the module namespace, so window.DaoClient was
 * {DaoClient: <class>} instead of the class itself.
 *
 * node --check cannot catch this — the syntax is valid, the runtime shape
 * is wrong. Only loading the real bundle and asserting the global works.
 *
 * Generated-by: Sophia (TrueSight Autopilot)
 */

import { readFileSync } from 'fs';
import { resolve } from 'path';
import { describe, it, expect, beforeAll } from 'vitest';

// A real RSA-2048 keypair (SPKI/PKCS#8 base64) for testing the sign path.
// The DaoClient constructor loads from localStorage; if no keys exist it
// calls generateKeyPairSync() which throws (it's a placeholder that requires
// pre-existing keys). We seed localStorage so the constructor path works.
const TEST_PUBLIC_KEY =
  'MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAlB5UmQJECz/BAHNROjgg' +
  'ADvyn91CVC6kR5F7r+h+OtOS/wziC+sS1xdphh2ms+jULbDuVEsTzPQPkTOrGqWAY/VF' +
  'DJV6KtMD1Txvm3m6BBmhvZTRKx3rCWcDXFDlsyu5HyTli6rUFRXkLse6oEdhd1ScFU72' +
  'Fyt3JoFju9d0/3n/GaRiojHJFtiCL8uBuubCUJi9ee3K3YcNGtjpLb9jaRLLvPAjmXIT' +
  'Kr8i2XMIwN1bJjbFtAg89A5cz6U3+gT2WG4ncj3dnmLq3MLW97TV96BsZTYvJWrsfYlf' +
  'AzSqxNCLs/0Hsgg59wChVrWpcgWmBz6/tG+a4qoGRIxMNVLtUQIDAQAB';
const TEST_PRIVATE_KEY =
  'MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQCUHlSZAkQLP8EA' +
  'c1E6OCAAO/Kf3UJULqRHkXuv6H4605L/DOIL6xLXF2mGHaaz6NQtsO5USxPM9A+RM6sa' +
  'pYBj9UUMlXoq0wPVPG+beboEGaG9lNErHesJZwNcUOWzK7kfJOWLqtQVFeQux7qgR2F3' +
  'VJwVTvYXK3cmgWO713T/ef8ZpGKiMckW2IIvy4G65sJQmL157crdhw0a2Oktv2NpEsu8' +
  '8COZchMqvyLZcwjA3VsmNsW0CDz0DlzPpTf6BPZYbidyPd2eYurcwtb3tNX3oGxlNi8l' +
  'aux9iV8DNKrE0Iuz/QeyCDn3AKFWtalyBaYHPr+0b5riqgZEjEw1Uu1RAgMBAAECggEA' +
  'KAQHs+y2SFm5gS8mZzWpg5auhj0HAeo17LXjthL4I1lskaY/3ZttFBoZoqeZFWrWA+AU' +
  'i0ZbO5hGKmLMm57R0G9/b5ZkknQ+yVmSB2178UaheS/e0Ki9CmW/tS2P2Pd7hGv57eFB' +
  'ec7XvkGsbEfMj6oWnvUdrAXMo2T6dlGPpMM94r8bU34nbVyH7dCjluRuGQF/rYYF0ecH' +
  'XE5nSyB1W+DKl16Dr1VpLxaRf04lYCOiMTQP3yc4vtEFROuyMQseVqOTn7TfW2khTTSb' +
  'jJC4l3wEINlXH1PsHd7i7N1w5pUIZn2TSbz2nyuzPMdiPqeA8nLW+9/UhkQdh33PGf1f' +
  'NwKBgQDOGbzwCyGrb5OxBqdPztXjPWas/8tb4wtMzsthbrOaiI9Is0dbd+610s9prSNi' +
  '8tFYJgNCc9aW8KF836IDDqVync/TzOTIdC1e6A1EEbpgfeoLrVAqoUyd3tTIxT19rE5S' +
  'MfubEIrmNQ+hcMBwD5obxzEBdg6snhS6es+Ih1pn9wKBgQC3+tJqkGP4gFbSPXguJAVn' +
  '3Pz57aSQmKDoC/IuFkAj4C+sTP/jTvLQC4hVpdtYiHMN/8Gtd6CoQtv/GrPczdu1wodV' +
  'Xp91uyMQuAUUOPI460jbrYR+WcDlnbNTHuj1lo+zUp/d7OGZ0qpiXOa+S9iotVT7iAby' +
  'rSs1KmzzVrDS9wKBgQCo3O2wv24WyJR5trne6djVFrnJhMtZvezEQarhaZI+SyUaq8kL' +
  'aHhtAQxvySv1Jn3fe0WwbLilcwLdDV3wo09rWWGuZ3ILyyRhXj+ARgYuiPv6FUZZp07f' +
  'CnPNC84V6ddCATHlGuizNUZZP8hsCFx75fiA+fmL9PmG0Ji5hCzOgQKBgQCt0I3Sl6+b' +
  'KsTbw68zCF0DD0kBZn6/DTOXhxG6cNMQEdF4Wxa1zfSgkQSwxg1Ay0jHxQVZuVdTIDdv' +
  '/+5FgUc9pRbulILaW355YSGLRXGyTLd8s6YlKO6RADhXIzC8NQ52QG1A4XcSOHE4lMR6' +
  'rHV4jjhHmu/Vfb0AcaCVFSXhaQKBgHniVzIqRKvAl1Rty3+9tca6m0gbBvBsuY+h7v8X' +
  'rVNc+mjzzNlCu4Bk4AYDSucOEaVb1hVUUA4qcG0zUMgBXR3qr26NbWlHNTHJGXC7Z8/g' +
  'yBWCWs8NaPrxI5Us8YHjbBoZt1WCoX93I/WV5u4FfPu8jN+QXsG2+G3yw+uWQEW4';

describe('dao-client browser bundle (dao-client.min.js)', () => {
  beforeAll(() => {
    // Read the built bundle from dist
    const bundleCode = readFileSync(
      resolve(__dirname, '..', 'dist', 'dao-client.min.js'),
      'utf-8'
    );
    // Execute the IIFE in the global scope so window.DaoClient is populated.
    // eval() is used because new Function() creates a scope that doesn't
    // inherit happy-dom's window/localStorage/crypto globals.
    eval(bundleCode);

    // Pre-seed localStorage with a real RSA-2048 keypair so the DaoClient
    // constructor can load keys instead of calling generateKeyPairSync()
    // (which throws — it's a placeholder that requires pre-existing keys).
    // In production, keys are generated on first visit and persisted.
    localStorage.setItem('truesight_dao_public_key', TEST_PUBLIC_KEY);
    localStorage.setItem('truesight_dao_private_key', TEST_PRIVATE_KEY);
  });

  it('window.DaoClient is defined and is the class itself (not a namespace wrapper)', () => {
    expect(window.DaoClient).toBeDefined();
    // The class constructor should be a function
    expect(typeof window.DaoClient).toBe('function');
    // The static helpers should be directly on the class
    expect(typeof window.DaoClient.base64ToArrayBuffer).toBe('function');
    expect(typeof window.DaoClient.arrayBufferToBase64).toBe('function');
    expect(typeof window.DaoClient.base64ToBase64Url).toBe('function');
    expect(typeof window.DaoClient.generateKeyPair).toBe('function');
  });

  it('base64 round-trip works via static helpers on the global', () => {
    const original = 'Hello DAO!';
    const encoded = new TextEncoder().encode(original);
    const b64 = window.DaoClient.arrayBufferToBase64(encoded.buffer);
    expect(typeof b64).toBe('string');
    expect(b64.length).toBeGreaterThan(0);

    const decoded = window.DaoClient.base64ToArrayBuffer(b64);
    const decodedText = new TextDecoder().decode(decoded);
    expect(decodedText).toBe(original);
  });

  it('base64ToBase64Url strips padding and replaces +/', () => {
    const result = window.DaoClient.base64ToBase64Url('a+b/c==');
    expect(result).toBe('a-b_c');
    expect(result).not.toContain('+');
    expect(result).not.toContain('/');
    expect(result).not.toContain('=');
  });

  it('can instantiate DaoClient and call sign (async)', async () => {
    const client = new window.DaoClient();
    expect(client).toBeInstanceOf(window.DaoClient);
    expect(typeof client.publicKey).toBe('string');
    expect(client.publicKey.length).toBeGreaterThan(0);
    expect(typeof client.privateKey).toBe('string');
    expect(client.privateKey.length).toBeGreaterThan(0);

    // Sign a test payload
    const result = await client.sign('TEST EVENT', { foo: 'bar' });
    expect(result).toHaveProperty('payload');
    expect(result).toHaveProperty('txId');
    expect(result).toHaveProperty('shareText');
    expect(typeof result.txId).toBe('string');
    expect(result.txId.length).toBeGreaterThan(0);
  });

  it('static generateKeyPair works', async () => {
    const kp = await window.DaoClient.generateKeyPair();
    expect(kp).toHaveProperty('publicKey');
    expect(kp).toHaveProperty('privateKey');
    expect(typeof kp.publicKey).toBe('string');
    expect(typeof kp.privateKey).toBe('string');
    expect(kp.publicKey.length).toBeGreaterThan(0);
  });
});
