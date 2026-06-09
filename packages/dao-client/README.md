# @truesight_dao/dao-client

Zero-dependency browser library for **TrueSight DAO** identity management, cryptographic signing, and Edgar submission.

This library handles the browser side of the DAO's RSA-signed event system. It generates RSA-2048 keypairs (byte-identical to Web Crypto exports), builds canonical signed payloads, submits them to Edgar (`POST /dao/submit_contribution`), and manages email-based identity registration — all with zero external dependencies.

> **Looking for the Python equivalent?** See [`TrueSightDAO/dao_client`](https://github.com/TrueSightDAO/dao_client) — the terminal / automation counterpart.

---

## Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [API Reference](#api-reference)
  - [Constructor](#constructor)
  - [Instance Methods](#instance-methods)
  - [Static Methods](#static-methods)
  - [Lower-level Methods](#lower-level-methods)
  - [Storage](#storage)
- [Examples](#examples)
  - [Submit a PRACTICE EVENT](#example-1-submit-a-practice-event)
  - [Email Registration Flow](#example-2-email-registration-flow)
  - [Check Registration Status](#example-3-check-registration-status)
- [Build](#build)
- [Publishing (automatic)](#publishing-automatic)
- [License](#license)

---

## Installation

### Browser (CDN)

```html
<script src="https://unpkg.com/@truesight_dao/dao-client@1.1.0-rc.1/dist/dao-client.min.js"></script>
<script>
  // window.DaoClient is the class itself
  const client = new DaoClient();
  
  // Static helpers available directly
  const buf = DaoClient.base64ToArrayBuffer('SGVsbG8=');
  
  // Sign and submit
  client.submit('CONTRIBUTION EVENT', { key: 'value' })
    .then(result => console.log('Submitted:', result.txId));
</script>
```

### Module (ESM / CJS)

```bash
npm install @truesight_dao/dao-client
```

```ts
import { DaoClient } from '@truesight_dao/dao-client';
const client = new DaoClient();
```

---

## Quick Start

```ts
import { DaoClient } from '@truesight_dao/dao-client';

// 1. Create a client — auto-generates or loads a keypair from localStorage
const client = new DaoClient();

// 2. Submit a signed event to Edgar
const result = await client.submitEvent({
  eventType: 'PRACTICE EVENT',
  fields: {
    Message: 'Hello from the DAO client!',
    Category: 'Testing',
  },
});

console.log(result.status);   // 'submitted' | 'duplicate' | ...
console.log(result.txId);     // Transaction ID (the RSA signature)
console.log(result.slug);     // pk-<hash> — derived from your public key
```

---

## API Reference

### Constructor

#### `new DaoClient(options?)`

Creates a new DAO client instance. On construction it **automatically loads an existing keypair** from `localStorage` (under the prefix `truesight_dao_`), or **generates a fresh RSA-2048 keypair** if none is found.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `edgarBase` | `string` | `'https://edgar.truesight.me'` | Base URL for the Edgar submission server. |
| `verifyUrl` | `string` | `'https://dapp.truesight.me/verify_request.html'` | URL used in the share-text "Verify submission here:" line. |
| `storagePrefix` | `string` | `'truesight_dao_'` | localStorage key prefix for keypair persistence. |
| `generationSource` | `string` | `window.location.origin + pathname` | URL string embedded in the share text to identify the submission source. **Required in Node.js** (no `window`). |

```ts
// Default — uses production Edgar
const client = new DaoClient();

// Custom Edgar endpoint (e.g. local development)
const client = new DaoClient({
  edgarBase: 'http://localhost:3000',
  generationSource: 'https://my-app.com/contribute',
});
```

---

### Instance Methods

#### `client.submitEvent({ eventType, fields, generationSource? })` → `Promise<SubmitEventResponse>`

Submit any signed event to Edgar. This is the **primary method** for v1.1.0+. It:

- Auto-injects a `Timestamp` field (ISO 8601 UTC) to prevent HTTP 409 duplicate-submission errors from persistent keys.
- Guards field values against `[... EVENT]` substrings that would cause Edgar misdispatch.
- Builds the canonical payload, signs it with the stored private key, and POSTs to Edgar.
- Parses the response into a structured `SubmitEventResponse`.

**Parameters:**

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `eventType` | `string` | Yes | The event type, e.g. `'CONTRIBUTION EVENT'`, `'PRACTICE EVENT'`, `'EMAIL REGISTERED EVENT'`. |
| `fields` | `Record<string, unknown>` | Yes | Key-value fields to include in the signed body. |
| `generationSource` | `string` | No | Override the generation source URL for this submission. Defaults to the constructor value. |

**Returns:** `SubmitEventResponse`

```ts
interface SubmitEventResponse {
  ok: boolean;
  status: 'submitted' | 'duplicate' | 'signature_verification_failed' | 'validation_failed' | 'server_error';
  txId: string;        // The RSA signature (base64)
  slug: string;        // pk-<sha256-hash-prefix>
  httpStatus: number;  // The raw HTTP status code
  emailRegistration?: EmailRegistrationStatus;  // Present for email-related events
  error?: string;      // Human-readable error message
}
```

**`EmailRegistrationStatus`:**

```ts
interface EmailRegistrationStatus {
  status: 'activated' | 'already_consumed' | 'pending_verification' | 'pubkey_mismatch' | 'not_found' | 'not_applicable';
  contributorEmail?: string;
}
```

---

#### `client.registerEmail(email)` → `Promise<SubmitEventResponse>`

Register an email address with the DAO identity system. Submits an `[EMAIL REGISTERED EVENT]` with the given email.

After calling this, the user must click the verification link sent to their email to complete registration. The response includes `emailRegistration` with status details.

```ts
const result = await client.registerEmail('user@example.com');
// result.emailRegistration?.status === 'pending_verification'
```

---

#### `client.verifyEmail(email, verificationKey)` → `Promise<SubmitEventResponse>`

Verify an email registration using the verification key from the email link. Submits an `[EMAIL VERIFICATION EVENT]`.

Call this when the user lands on your page with `?em=...&vk=...` query parameters from the verification email.

```ts
const result = await client.verifyEmail('user@example.com', 'abc123def456');
// result.emailRegistration?.status === 'activated'
```

---

#### `client.checkRegistration()` → `Promise<CheckRegistrationResponse>`

Check the registration status of the current public key against Edgar. This is a **read-only GET** call (not a submission).

```ts
interface CheckRegistrationResponse {
  registered: boolean;
  pending_verification?: boolean;
  contributor_name?: string;
  contributor_email?: string;
  error?: string;
}
```

```ts
const status = await client.checkRegistration();

if (status.registered) {
  console.log(`Welcome back, ${status.contributor_name}!`);
} else if (status.pending_verification) {
  console.log('Check your email and click the verification link.');
} else {
  console.log('Not registered yet. Call registerEmail() first.');
}
```

---

#### `client.getSlug()` → `Promise<string>`

Derive the public key slug: `pk-<first 12 chars of SHA-256 hash, base64url-encoded>`.

```ts
const slug = await client.getSlug();
console.log(slug); // e.g. 'pk-AbCdEfGhIjKl'
```

---

#### `client.generateKeyPair()` → `Promise<{ publicKey, privateKey }>`

Generate a **new** RSA-2048 keypair, store it in localStorage (overwriting any existing keys), and update the client instance.

```ts
const kp = await client.generateKeyPair();
console.log(kp.publicKey);  // SPKI base64
console.log(kp.privateKey); // PKCS#8 base64
```

---

#### `client.verifyPayload(text, signature)` → `Promise<boolean>`

Verify a signed payload against a transaction ID (signature). Uses the client's public key.

```ts
const isValid = await client.verifyPayload(payloadString, signatureBase64);
console.log(isValid); // true or false
```

---

### Static Methods

#### `DaoClient.generateKeyPair()` → `Promise<{ publicKey, privateKey }>`

Static keypair generator. Does **not** store the keypair or affect any client instance.

```ts
const kp = await DaoClient.generateKeyPair();
```

#### `DaoClient.arrayBufferToBase64(buffer)` → `string`

Convert an `ArrayBuffer` to a base64 string.

```ts
const b64 = DaoClient.arrayBufferToBase64(new Uint8Array([72, 101, 108, 108, 111]).buffer);
// 'SGVsbG8='
```

#### `DaoClient.base64ToArrayBuffer(b64)` → `ArrayBuffer`

Convert a base64 string to an `ArrayBuffer`.

```ts
const buf = DaoClient.base64ToArrayBuffer('SGVsbG8=');
```

#### `DaoClient.base64ToBase64Url(b64)` → `string`

Convert a standard base64 string to base64url format (replaces `+` → `-`, `/` → `_`, strips `=` padding).

```ts
const urlSafe = DaoClient.base64ToBase64Url('a+b/c=');
// 'a-b_c'
```

---

### Lower-level Methods

These are the v1.0.x-compatible methods. They do **not** inject a `Timestamp` or guard field values — use `submitEvent()` for new code.

#### `client.submit(eventName, fields)` → `Promise<{ json, txId }>`

Lower-level submit. Builds the canonical payload, signs it, and POSTs to Edgar. Returns the raw JSON response and transaction ID.

```ts
const { json, txId } = await client.submit('CONTRIBUTION EVENT', {
  Type: 'Time (Minutes)',
  Amount: '30',
  Description: 'Worked on documentation',
});
```

#### `client.sign(eventName, fields)` → `Promise<{ payload, txId, shareText }>`

Sign without submitting. Returns the canonical payload string, the signature (txId), and the full share text (which can be pasted into the Edgar verification page manually).

```ts
const { payload, txId, shareText } = await client.sign('CONTRIBUTION EVENT', {
  Type: 'Time (Minutes)',
  Amount: '30',
});
console.log(shareText);
// [CONTRIBUTION EVENT]
// - Type: Time (Minutes)
// - Amount: 30
// --------
// My Digital Signature: MIIB...
// Request Transaction ID: abc123...
// This submission was generated using https://example.com/contribute
// Verify submission here: https://dapp.truesight.me/verify_request.html
```

---

### Storage

The constructor **automatically** manages keypair persistence:

- **Loads** an existing keypair from `localStorage` on construction (keys: `truesight_dao_public_key`, `truesight_dao_private_key`).
- **Generates and saves** a fresh keypair if none exists.
- **Persists across page loads** — the same keypair is reused until explicitly replaced via `client.generateKeyPair()`.

To clear stored keys (e.g. for testing):

```ts
localStorage.removeItem('truesight_dao_public_key');
localStorage.removeItem('truesight_dao_private_key');
```

---

## Examples

### Example 1: Submit a PRACTICE EVENT

```ts
import { DaoClient } from '@truesight_dao/dao-client';

const client = new DaoClient();

const result = await client.submitEvent({
  eventType: 'PRACTICE EVENT',
  fields: {
    Message: 'Testing the DAO client integration',
    Category: 'Onboarding',
    Notes: 'This is a practice submission to verify the flow works end-to-end.',
  },
});

if (result.ok) {
  console.log('✅ Practice event submitted successfully!');
  console.log('Transaction ID:', result.txId);
  console.log('Slug:', result.slug);
} else {
  console.error('❌ Submission failed:', result.error);
  console.log('Status:', result.status);
  console.log('HTTP:', result.httpStatus);
}
```

### Example 2: Email Registration Flow

```ts
import { DaoClient } from '@truesight_dao/dao-client';

const client = new DaoClient();

// Step 1: Register the email
const registerResult = await client.registerEmail('user@example.com');

if (!registerResult.ok) {
  console.error('Registration failed:', registerResult.error);
  // Handle emailRegistration?.status: 'already_consumed', 'pubkey_mismatch', etc.
}

console.log('📧 Verification email sent! Check your inbox.');
console.log('Status:', registerResult.emailRegistration?.status);

// Step 2: (On the verification page — capture ?em=...&vk=... from URL)
// Parse the URL query params after the user clicks the email link
const urlParams = new URLSearchParams(window.location.search);
const email = urlParams.get('em');
const vk = urlParams.get('vk');

if (email && vk) {
  const verifyResult = await client.verifyEmail(email, vk);

  if (verifyResult.emailRegistration?.status === 'activated') {
    console.log('✅ Email verified! Keypair is now ACTIVE on Edgar.');
  } else {
    console.log('Verification status:', verifyResult.emailRegistration?.status);
  }
}
```

### Example 3: Check Registration Status

```ts
import { DaoClient } from '@truesight_dao/dao-client';

const client = new DaoClient();

const status = await client.checkRegistration();

if (status.registered) {
  console.log(`✅ Registered as "${status.contributor_name}" (${status.contributor_email})`);
} else if (status.pending_verification) {
  console.log('⏳ Key is pending email verification. Check your inbox.');
} else {
  console.log('❌ Not registered. Call registerEmail() to start onboarding.');
  console.log('Error:', status.error);
}
```

---

## Build

```bash
npm run build      # CJS + IIFE (browser) — outputs dist/index.js + dist/dao-client.min.js
npm run build:esm  # ESM — outputs dist/index.mjs
npm test           # Runtime smoke test on the built bundle
```

---

## Publishing (automatic)

**Releasing is just: bump the version → merge.** On any push to `main` that
changes `packages/dao-client/package.json`, the `npm-publish-dao-client.yml`
workflow builds, runs the smoke test (`npm test`), and publishes **only if that
version is new** on npm. No manual step, no token handling.

```
# release flow
1. bump "version" in packages/dao-client/package.json (in a PR)
2. merge to main
3. CI publishes automatically (skips if the version already exists; a failing
   smoke test blocks the publish)
```

`workflow_dispatch` and `dao-client-v*` tags also trigger it, as escape hatches.

### npm token (it expires)

CI publishes with the **`NPM_TOKEN`** GitHub Actions secret on `dao_protocol`
(an npm Automation token for the `truesight_dao` org). **It expires (~2026-09-06)**
— when it does, publishes 401 and the **weekly `npm-token-health.yml` check**
fails loudly. Rotation is governor-only: regenerate an Automation token on
npmjs.com → update the `NPM_TOKEN` secret on `dao_protocol`. Tracked in
`agentic_ai_context/OPEN_FOLLOWUPS.md`. **Never put the token on a server or in
chat** — it only lives as the GH Actions secret.

---

## License

MIT
