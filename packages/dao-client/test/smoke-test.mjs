/**
 * smoke-test.mjs — runtime smoke test for the browser IIFE bundle.
 *
 * Loads the built dist/dao-client.min.js in Node via vm.Script and
 * asserts the global shape matches what consumers expect:
 *   window.DaoClient IS the class (not a namespace object)
 *   DaoClient.base64ToArrayBuffer, .arrayBufferToBase64, .base64ToBase64Url
 *   are all functions
 *   A round-trip encode/decode works
 *
 * Run: node test/smoke-test.mjs
 * (Called automatically by prepublishOnly.)
 */

import { readFileSync } from 'fs';
import { Script } from 'vm';

const bundlePath = new URL('../dist/dao-client.min.js', import.meta.url);
const code = readFileSync(bundlePath, 'utf8');

// Evaluate the IIFE in a sandbox with a mock window/self
const sandbox = {
  window: {},
  self: {},
  crypto: {
    subtle: {
      // Stub — we're testing global shape, not actual crypto
      generateKey: () => {},
      importKey: () => {},
      exportKey: () => {},
      sign: () => {},
      verify: () => {},
      digest: () => {},
    },
  },
  TextEncoder: class {
    encode(s) { return Buffer.from(s); }
  },
  btoa: (s) => Buffer.from(s, 'binary').toString('base64'),
  atob: (s) => Buffer.from(s, 'base64').toString('binary'),
  Uint8Array,
  ArrayBuffer,
  console,
  // The IIFE assigns to var DaoClient on the global scope
  DaoClient: undefined,
};

const ctx = { ...sandbox };

// Run the IIFE — it assigns to `var DaoClient` which we catch via
// the sandbox's DaoClient property
const script = new Script(code);
script.runInNewContext(ctx);

const DaoClient = ctx.DaoClient;

let failures = 0;

function assert(condition, msg) {
  if (!condition) {
    console.error('FAIL:', msg);
    failures++;
  } else {
    console.log('  OK:', msg);
  }
}

console.log('\n=== dao-client smoke test ===\n');

// 1. DaoClient is the class, not a namespace
assert(typeof DaoClient === 'function', 'DaoClient is a function (class)');
assert(typeof DaoClient.DaoClient === 'undefined', 'DaoClient.DaoClient is undefined (namespace flattened)');

// 2. Static methods are directly on DaoClient
assert(typeof DaoClient.base64ToArrayBuffer === 'function', 'DaoClient.base64ToArrayBuffer is a function');
assert(typeof DaoClient.arrayBufferToBase64 === 'function', 'DaoClient.arrayBufferToBase64 is a function');
assert(typeof DaoClient.base64ToBase64Url === 'function', 'DaoClient.base64ToBase64Url is a function');
assert(typeof DaoClient.generateKeyPair === 'function', 'DaoClient.generateKeyPair is a function (static)');

// 3. Round-trip base64 encode/decode
const original = 'Hello World! Test 123 🎉';
const encoded = btoa(unescape(encodeURIComponent(original)));
const bytes = DaoClient.base64ToArrayBuffer(encoded);
assert(bytes instanceof ArrayBuffer, 'base64ToArrayBuffer returns ArrayBuffer');
const decoded = DaoClient.arrayBufferToBase64(bytes);
assert(decoded === encoded, `Round-trip: "${original}" → encode → decode → matches`);

// 4. base64ToBase64Url
const b64 = 'a+b/c=d';
const b64url = DaoClient.base64ToBase64Url(b64);
assert(b64url === 'a-b_c=d', `base64ToBase64Url: "${b64}" → "${b64url}"`);

console.log(`\n${failures === 0 ? '✓ ALL PASSED' : '✗ ' + failures + ' FAILED'}\n`);
process.exit(failures > 0 ? 1 : 0);
