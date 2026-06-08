# @truesight/dao-client

Zero-dependency browser library for TrueSight DAO identity management, cryptographic signing, and Edgar submission.

## Installation

```bash
npm install @truesight/dao-client
```

Or include via CDN in a static HTML file:

```html
<script src="https://unpkg.com/@truesight/dao-client"></script>
<!-- or -->
<script src="https://cdn.jsdelivr.net/npm/@truesight/dao-client"></script>
```

When loaded via CDN, the library is available as the global `DaoClient` object.

## Quick Start

```js
import { DaoClient } from '@truesight/dao-client';

// Create a client — keypair is auto-generated if missing
const client = new DaoClient();

// Submit any event type to Edgar
await client.submit('PRACTICE EVENT', {
  'Program': 'truesight-grounding',
  'Practice Type': 'oracle-consultation',
  'Practitioner Public Key': client.publicKey,
});

// Get the credential slug (pk-xxxxxxxxxxxx)
const slug = await client.getSlug();
```

## API

### `new DaoClient(options?)`

Creates a new DAO client. If no keypair exists in localStorage, one is generated automatically.

Options:
- `edgarBase` (string) — Edgar API base URL. Default: `https://edgar.truesight.me`
- `verifyUrl` (string) — Verification page URL. Default: `https://dapp.truesight.me/verify_request.html`
- `storagePrefix` (string) — localStorage key prefix. Default: `'truesight_dao_'`

### Properties

- `client.publicKey` — The base64-encoded SPKI public key
- `client.privateKey` — The base64-encoded PKCS#8 private key (kept in memory only)

### Methods

#### `client.submit(eventName, attributes)`

Builds a canonical payload, signs it with the private key, and POSTs it to Edgar's `/dao/submit_contribution` endpoint.

Returns `{ json, txId }` where `txId` is the base64 signature (Request Transaction ID).

#### `client.sign(eventName, attributes)`

Builds and signs a payload without submitting. Returns `{ payload, txId, shareText }`.

#### `client.getSlug()`

Returns the credential slug: `pk-` + first 12 chars of the SHA-256 hash of the public key (base64url-encoded).

#### `client.verifyPayload(payload, txId)`

Verifies a signed payload against a transaction ID using the stored public key. Returns `true`/`false`.

#### `client.generateKeyPair()`

Generates a new RSA-2048 keypair, stores it in localStorage, and updates the client instance. Returns `{ publicKey, privateKey }`.

## Static Methods

#### `DaoClient.generateKeyPair()`

Static version — generates a keypair without creating a client instance.

#### `DaoClient.arrayBufferToBase64(buffer)`

#### `DaoClient.base64ToArrayBuffer(base64)`

#### `DaoClient.base64ToBase64Url(base64)`

## Browser Support

Requires `window.crypto.subtle` (Web Crypto API), available in all modern browsers (Chrome 37+, Firefox 34+, Safari 11+, Edge 79+).

## Development

```bash
# Build
npm run build

# Build ESM
npm run build:esm

# Test
npm test
```
