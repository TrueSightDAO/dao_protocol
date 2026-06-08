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

describe('dao-client browser bundle (dao-client.min.js)', () => {
  let bundleCode: string;

  beforeAll(() => {
    // Read the built bundle from dist
    bundleCode = readFileSync(
      resolve(__dirname, '..', 'dist', 'dao-client.min.js'),
      'utf-8'
    );
    // Execute it in the current global scope (happy-dom provides window, crypto, etc.)
    const script = document.createElement('script');
    script.textContent = bundleCode;
    document.head.appendChild(script);
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
