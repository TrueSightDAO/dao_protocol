# @truesight_dao/dao-client

Zero-dependency browser library for TrueSight DAO identity management, cryptographic signing, and Edgar submission.

## Installation

### Browser (CDN)

```html
<script src="https://unpkg.com/@truesight_dao/dao-client@1.1.0-rc.1/dist/dao-client.min.js"></script>
<script>
  // window.DaoClient is the class itself
  const client = new DaoClient();
</script>
```

### Module (ESM / CJS)

```ts
import { DaoClient } from '@truesight_dao/dao-client';
const client = new DaoClient();
```

## Quick Start

```js
const client = new DaoClient();

// Submit any signed event to Edgar in one call
const result = await client.submitEvent({
  eventType: 'CONTRIBUTION EVENT',
  fields: {
    Type: 'Time (Minutes)',
    Amount: '30',
    Description: 'DAO standup and code review',
    'Contributor(s)': 'Your Name',
  },
});

console.log(result.status); // 'submitted'
console.log(result.slug);   // 'pk-a1b2c3d4e5f6'
```

## API Reference

### Constructor

```ts
const client = new DaoClient(options?: DaoClientOptions);
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `edgarBase` | `string` | `'https://edgar.truesight.me'` | Base URL for Edgar API |
| `verifyUrl` | `string` | `'https://dapp.truesight.me/verify_request.html'` | URL for signature verification UI |
| `storagePrefix` | `string` | `'truesight_dao_'` | localStorage key prefix for keypair persistence |
| `generationSource` | `string` | `window.location.origin + pathname` | Source URL embedded in signed payloads |

On construction, the client **auto-loads** an existing keypair from localStorage, or **auto-generates** a new RSA-2048 keypair if none exists. The keypair persists across page loads automatically.

---

### `client.submitEvent(options)` — **Recommended**

Submit any signed event to Edgar with safety features (auto-Timestamp injection, field value guarding).

```ts
const result = await client.submitEvent({
  eventType: 'PRACTICE EVENT',
  fields: {
    Program: 'capoeira-tribo-mirim',
    'Practice Type': 'training-session',
    'Captured At': new Date().toISOString(),
    'Source URL': window.location.href,
    Theme: 'ginga-basics',
    'Total Practice Minutes': '45',
  },
});
```

**Returns:** [`SubmitEventResponse`](#submiteventresponse)

---

### `client.registerEmail(email)`

Register an email address with the DAO identity system. Submits an `[EMAIL REGISTERED EVENT]`.

```ts
const result = await client.registerEmail('user@example.com');

if (result.emailRegistration?.status === 'pending_verification') {
  console.log('Check your inbox for the verification link.');
}
```

After calling this, the user must click the verification link sent to their email to complete registration. The link must be opened **in the same browser** where the keypair lives (the signing key is in localStorage).

**Returns:** [`SubmitEventResponse`](#submiteventresponse) with `emailRegistration` populated.

---

### `client.verifyEmail(email, verificationKey)`

Complete email verification using the key from the email link. Submits an `[EMAIL VERIFICATION EVENT]`.

```ts
// Call this when the user lands on your page with ?em=...&vk=... params
const params = new URLSearchParams(window.location.search);
const email = params.get('em');
const vk = params.get('vk');

if (email && vk) {
  const result = await client.verifyEmail(email, vk);
  if (result.ok) {
    console.log('Email verified!');
  }
}
```

**Returns:** [`SubmitEventResponse`](#submiteventresponse) with `emailRegistration` populated.

---

### `client.checkRegistration()`

Check the registration status of the current public key against Edgar. This is a **read-only GET** call (not a submission).

```ts
const status = await client.checkRegistration();

if (status.registered) {
  console.log(`Registered as ${status.contributor_name}`);
} else if (status.pending_verification) {
  console.log(`Pending verification for ${status.contributor_email}`);
} else {
  console.log('Not registered.');
}
```

**Returns:** [`CheckRegistrationResponse`](#checkregistrationresponse)

---

### `client.getSlug()`

Derive the public key slug — a `pk-` prefix followed by the first 12 characters of the SHA-256 hash of the public key.

```ts
const slug = await client.getSlug();
// e.g. 'pk-a1b2c3d4e5f6'

const cvUrl = `https://truesight.me/programs/truesight-grounding/credentials/#${slug}`;
```

This is used to build credential page URLs on truesight.me.

**Returns:** `string`

---

### `client.generateKeyPair()`

Generate a new RSA-2048 keypair, store it in localStorage, and update the client instance.

```ts
const kp = await client.generateKeyPair();
console.log(kp.publicKey);  // SPKI base64 string
console.log(kp.privateKey); // PKCS#8 base64 string
```

**Returns:** `{ publicKey: string, privateKey: string }`

---

### `client.verifyPayload(payload, txId)`

Verify a signed payload against a transaction ID (signature).

```ts
const isValid = await client.verifyPayload(payloadText, signatureBase64);
console.log(isValid); // true or false
```

**Returns:** `boolean`

---

### `client.submit(eventName, attributes)` — *Lower-level*

Build a canonical payload, sign it, and submit to Edgar. This is the v1.0.x compatible method (no Timestamp injection, no field guard).

```ts
const { json, txId } = await client.submit('CONTRIBUTION EVENT', {
  Type: 'Time (Minutes)',
  Amount: '30',
});
```

**Returns:** `{ json: Record<string, unknown>, txId: string }`

---

### `client.sign(eventName, attributes)` — *Lower-level*

Build and sign a payload **without** submitting. Useful for testing or manual workflows.

```ts
const { payload, txId, shareText } = await client.sign('CONTRIBUTION EVENT', {
  Type: 'Time (Minutes)',
  Amount: '30',
});

console.log(shareText); // Full signed text ready for Edgar
```

**Returns:** `{ payload: string, txId: string, shareText: string }`

---

## Static Methods

### `DaoClient.generateKeyPair()`

Generate a new RSA-2048 keypair without instantiating a client.

```ts
const kp = await DaoClient.generateKeyPair();
// { publicKey: 'MIIB...', privateKey: 'MIIE...' }
```

**Returns:** `Promise<{ publicKey: string, privateKey: string }>`

---

### `DaoClient.arrayBufferToBase64(buffer)`

Convert an ArrayBuffer to a base64-encoded string.

```ts
const b64 = DaoClient.arrayBufferToBase64(new Uint8Array([72, 101, 108, 108, 111]).buffer);
// 'SGVsbG8='
```

**Returns:** `string`

---

### `DaoClient.base64ToArrayBuffer(base64)`

Convert a base64-encoded string to an ArrayBuffer.

```ts
const buf = DaoClient.base64ToArrayBuffer('SGVsbG8=');
```

**Returns:** `ArrayBuffer`

---

### `DaoClient.base64ToBase64Url(base64)`

Convert a standard base64 string to base64url format (replaces `+` with `-`, `/` with `_`, strips `=` padding).

```ts
const urlSafe = DaoClient.base64ToBase64Url('SGVsbG8=');
// 'SGVsbG8'
```

**Returns:** `string`

---

## Response Types

### `SubmitEventResponse`

Returned by `submitEvent()`, `registerEmail()`, and `verifyEmail()`.

```ts
interface SubmitEventResponse {
  ok: boolean;
  status: 'submitted' | 'server_error' | 'signature_verification_failed';
  txId: string;
  slug: string;
  httpStatus: number;
  error?: string;
  emailRegistration?: {
    status: 'activated' | 'pending_verification' | 'already_consumed' | 'pubkey_mismatch' | 'not_found' | 'not_applicable';
    contributorEmail?: string;
  };
}
```

| Field | Description |
|-------|-------------|
| `ok` | `true` if the submission was accepted by Edgar |
| `status` | High-level outcome string |
| `txId` | The RSA signature (transaction ID) |
| `slug` | The public key slug (`pk-...`) |
| `httpStatus` | The HTTP response status code |
| `error` | Error message if submission failed |
| `emailRegistration` | Present only for email-related events; describes the registration state |

### `CheckRegistrationResponse`

Returned by `checkRegistration()`.

```ts
interface CheckRegistrationResponse {
  registered: boolean;
  contributor_name?: string;
  contributor_email?: string;
  pending_verification?: boolean;
  error?: string;
}
```

---

## Complete Examples

### Email Registration Flow

```js
const client = new DaoClient();

// 1. Register
const regResult = await client.registerEmail('user@example.com');
console.log(regResult.emailRegistration?.status);
// → 'pending_verification' — check your inbox

// 2. User clicks email link, lands back on your page with ?em=&vk=
const params = new URLSearchParams(window.location.search);
const email = params.get('em');
const vk = params.get('vk');

if (email && vk) {
  const verifyResult = await client.verifyEmail(email, vk);
  if (verifyResult.ok) {
    console.log('✓ Email verified!');
  }
}

// 3. Check authoritative status
const status = await client.checkRegistration();
if (status.registered) {
  console.log(`Active as ${status.contributor_name}`);
}
```

### Submitting a Practice Session

```js
const client = new DaoClient();

const result = await client.submitEvent({
  eventType: 'PRACTICE EVENT',
  fields: {
    Program: 'capoeira-tribo-mirim',
    'Practice Type': 'training-session',
    'Captured At': new Date().toISOString(),
    'Source URL': window.location.href,
    Theme: 'ginga-basics',
    'Moves Practiced': JSON.stringify([
      { id: 'ginga', name_pt: 'Ginga', duration_seconds: 300 },
    ]),
    'Music Played': JSON.stringify(['berimbau-angola']),
    'Total Practice Minutes': '45',
  },
});

if (result.ok) {
  const cvUrl = `https://truesight.me/programs/capoeira-tribo-mirim/credentials/#${result.slug}`;
  console.log('Credential:', cvUrl);
}
```

### Submitting a Contribution

```js
const client = new DaoClient();

const result = await client.submitEvent({
  eventType: 'CONTRIBUTION EVENT',
  fields: {
    Type: 'Time (Minutes)',
    Amount: '120',
    Description: 'Built the new onboarding flow',
    'Contributor(s)': 'Your Name',
    'TDG Issued': '200.00',
  },
});
```

---

## Identity & Storage

- Keypairs are stored in **localStorage** under the configured prefix (`truesight_dao_` by default).
- The constructor auto-loads existing keys on every page load — no user action needed.
- Keys persist across sessions and page reloads automatically.
- To reset: `localStorage.removeItem('truesight_dao_public_key')` and `localStorage.removeItem('truesight_dao_private_key')`.

---

## Build

```bash
npm run build      # CJS + IIFE (browser)
npm run build:esm  # ESM
npm test           # Runtime smoke test on the built bundle
```

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

## License

MIT
