# TrueSight DAO — Integration Guide

A language-agnostic overview for developers who want to integrate with the
TrueSight DAO credentialing layer. This guide describes the API surface,
cryptographic primitives, and registration flow — no internal DAO jargon,
no platform internals.

**Base URL (Edgar):** `https://edgar.truesight.me`  
**DApp (reference UI):** `https://dapp.truesight.me`

---

## 1. Overview

The TrueSight DAO credentialing layer lets any contributor prove their identity
and submit signed records of DAO-relevant actions — contributions, inventory
movements, sales, notarizations, proposals, votes, and more.

Every action is an **RSA-2048 signed event payload** submitted to Edgar's
`POST /dao/submit_contribution` endpoint. The signature proves authorship;
the payload is a plain-text, human-readable format that any system can
verify independently.

**Key properties:**

- **Asymmetric keys.** Each contributor generates an RSA-2048 keypair.
  The public key (SPKI, base64) is their on-chain identity.
- **No tokens, no JWTs.** Authentication is cryptographic: you sign what you
  say, and Edgar verifies the signature against the registered public key.
- **Email-bound identity.** A contributor's public key is bound to an email
  address through a verification flow (see [Registration flow](#3-registration-flow)).
- **Language-agnostic.** The wire format is plain text + multipart form POST.
  Any language with RSA-SHA256 signing can participate.

---

## 2. Core Concepts

### 2.1 Keypair Generation

Generate an **RSA-2048** keypair with a 65537 public exponent. Export the keys
in the following formats (byte-identical to what the browser's
`crypto.subtle.exportKey()` produces):

| Key | Format | Encoding |
|-----|--------|----------|
| **Public key** | SubjectPublicKeyInfo (SPKI) DER | Base64 (no PEM headers) |
| **Private key** | PKCS#8 DER, unencrypted | Base64 (no PEM headers) |

**Example (Python, using `cryptography`):**

```python
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import base64

priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)

pub_b64 = base64.b64encode(
    priv.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
).decode("ascii")

priv_b64 = base64.b64encode(
    priv.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
).decode("ascii")
```

**Example (JavaScript — browser):**

```js
const keypair = await crypto.subtle.generateKey(
  { name: "RSA-PSS", modulusLength: 2048, publicExponent: new Uint8Array([1,0,1]), hash: "SHA-256" },
  true,
  ["sign", "verify"]
);
const pubDer = await crypto.subtle.exportKey("spki", keypair.publicKey);
const privDer = await crypto.subtle.exportKey("pkcs8", keypair.privateKey);
const pubB64 = btoa(String.fromCharCode(...new Uint8Array(pubDer)));
const privB64 = btoa(String.fromCharCode(...new Uint8Array(privDer)));
```

> **Note:** The keys use **RSA-PSS** in the browser's `crypto.subtle.generateKey`
> call, but the signing scheme is **RSASSA-PKCS1-v1_5** (see below). The
> `generateKey` algorithm name is a browser API quirk — the exported key
> material is standard RSA-2048 and works with both schemes.

### 2.2 Canonical Payload Format

Every event follows this plain-text structure:

```
[EVENT NAME]
- Label: value
- Label: value
--------
```

Rules:

- The event name is enclosed in square brackets on the first line.
- Each attribute is a line starting with `- ` (dash, space), followed by
  `Label: value`.
- The payload ends with a line containing exactly eight dashes (`--------`).
- Multi-line values are indented with two spaces on continuation lines.

**Example payload:**

```
[CONTRIBUTION EVENT]
- Type: Time (Minutes)
- Amount: 30
- Description: Closing out Townhall
- Contributor(s): Gary Teh
- TDG Issued: 50.00
--------
```

### 2.3 Signing

Sign the canonical payload using **RSASSA-PKCS1-v1_5** with **SHA-256**.

The signature is base64-encoded and becomes the **Request Transaction ID**.

**Verification check:** Given the public key (SPKI base64), the payload text,
and the signature (base64), any system can verify that the payload was signed
by the holder of the private key.

### 2.4 Submission

Send the signed payload to Edgar as a **multipart form POST**:

```
POST https://edgar.truesight.me/dao/submit_contribution
Content-Type: multipart/form-data

text: <the full share text (see below)>
```

The **share text** is the complete signed artifact. It includes the payload,
the public key, the signature, and metadata:

```
[CONTRIBUTION EVENT]
- Type: Time (Minutes)
- Amount: 30
- Description: Closing out Townhall
- Contributor(s): Gary Teh
- TDG Issued: 50.00
--------

My Digital Signature: MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA...

Request Transaction ID: aB3x... (base64 signature)

This submission was generated using https://dapp.truesight.me/create_signature.html

Verify submission here: https://dapp.truesight.me/verify_request.html
```

**Optional attachment:** You can include a file as a second multipart field
named `attachment`. Edgar will parse the payload for a
`Destination Contribution File Location` URL and upload the file to the
corresponding GitHub repository.

**Response (success):**

```json
{
  "status": "success",
  "signature_verification": "success",
  "email_registration": { ... }
}
```

---

## 3. Registration Flow

Before a public key can sign events, it must be bound to an email address.
The flow has three steps:

### Step 1: Generate keypair + submit EMAIL REGISTERED EVENT

1. Generate an RSA-2048 keypair (see [§2.1](#21-keypair-generation)).
2. Construct a payload with event name `EMAIL REGISTERED EVENT` and attribute
   `Email: <your-email>`.
3. Sign the payload and POST it to `/dao/submit_contribution`.

The `generation source` URL in the share text tells Edgar where to send the
verification link. For the browser flow, this is
`https://dapp.truesight.me/create_signature.html`. For CLI/automation flows,
it can be a loopback URL like `http://127.0.0.1:<port>/verify`.

### Step 2: Click the verification link

Edgar sends an email containing a link with query parameters:

```
http://127.0.0.1:<port>/verify?em=<email>&vk=<verification_key>
```

Clicking this link signals that the email address is controlled by the person
who initiated registration.

### Step 3: Submit EMAIL VERIFICATION EVENT

After the link is clicked, construct and sign an `EMAIL VERIFICATION EVENT`
payload with attributes:

- `Verification Key: <vk>` (from the email URL)
- `Email: <email>`

Submit this to `/dao/submit_contribution`. Edgar marks the public key as
**ACTIVE**, and it can now be used to sign all other event types.

**Verification key single-use:** Each verification key (`vk`) can only be
consumed once. If you need to re-register, generate a fresh keypair and
start again.

### Checking registration status

To check whether a public key is registered and active:

```
GET https://edgar.truesight.me/dao/check_digital_signature?signature=<base64-public-key>
```

**Response:**

```json
{
  "registered": true,
  "contributor_email": "you@example.com",
  "status": "ACTIVE"
}
```

Possible statuses: `ACTIVE`, `VERIFYING` (email sent but not yet confirmed),
or `UNKNOWN`.

---

## 4. Verification

Any third party can verify a signed event without contacting Edgar:

1. Parse the share text to extract:
   - The **payload** (everything from `[EVENT NAME]` to `--------`)
   - The **public key** (the base64 string after `My Digital Signature:`)
   - The **signature** (the base64 string after `Request Transaction ID:`)
2. Decode the public key from base64 SPKI DER.
3. Decode the signature from base64.
4. Verify the payload bytes against the signature using
   **RSASSA-PKCS1-v1_5 / SHA-256**.

To also confirm the key is currently registered with the DAO, call the
`check_digital_signature` endpoint (see [§3](#3-registration-flow)).

---

## 5. Event Types

The following event types are supported. Each has a canonical set of
attributes. The exact attribute list for each event is defined by the
corresponding HTML page on `dapp.truesight.me`.

| Event Name | Key Attributes | Purpose |
|------------|---------------|---------|
| `CONTRIBUTION EVENT` | `Type`, `Amount`, `Description`, `Contributor(s)`, `TDG Issued` | Log human effort (minutes) or USD outlay |
| `INVENTORY MOVEMENT` | `SKU`, `Quantity`, `From Location`, `To Location`, `Contributor(s)` | Record inventory transfers |
| `SALES EVENT` | `SKU`, `Quantity`, `Unit Price`, `Currency`, `Buyer`, `Contributor(s)` | Record a sale |
| `NOTARIZATION EVENT` | `Document`, `Notary`, `Contributor(s)` | Notarize a document or record |
| `CAPITAL INJECTION EVENT` | `Amount`, `Currency`, `Investor`, `Contributor(s)` | Record external capital injection |
| `PROPOSAL CREATION` | `Title`, `Summary`, `Proposed By`, `Contributor(s)` | Create a DAO proposal |
| `PROPOSAL VOTE` | `Proposal ID`, `Vote`, `Voter`, `Contributor(s)` | Cast a vote on a proposal |
| `TREE PLANTING EVENT` | `Species`, `Quantity`, `Location`, `Contributor(s)` | Record tree planting |
| `FARM REGISTRATION` | `Farm Name`, `Location`, `Owner`, `Contributor(s)` | Register a farm |
| `REPACKAGING BATCH EVENT` | `Input SKU`, `Output SKU`, `Quantity`, `Contributor(s)` | Record repackaging |
| `QR CODE EVENT` | `QR ID`, `Action`, `Location`, `Contributor(s)` | QR code scan event |
| `QR CODE UPDATE EVENT` | `QR ID`, `Field`, `New Value`, `Contributor(s)` | Update QR code data |
| `BATCH QR CODE REQUEST` | `Count`, `Purpose`, `Contributor(s)` | Request batch QR codes |
| `DAO Inventory Expense Event` | `SKU`, `Quantity`, `Cost`, `Contributor(s)` | Record DAO expenses |
| `DAPP PERMISSION CHANGE EVENT` | `Target`, `Permission`, `Action`, `Contributor(s)` | Change dApp permissions |
| `VOTING RIGHTS WITHDRAWAL REQUEST` | `Amount`, `Reason`, `Contributor(s)` | Request voting rights withdrawal |
| `EMAIL REGISTERED EVENT` | `Email` | Begin registration (see §3) |
| `EMAIL VERIFICATION EVENT` | `Verification Key`, `Email` | Complete registration (see §3) |

> **Note:** `Contributor(s)` is present on most events and identifies who
> performed the action. The signing key proves cryptographic authorship;
> the `Contributor(s)` field records the human-readable name.

---

## 6. Reference Implementations

| Resource | Language | Description |
|----------|----------|-------------|
| [`dao_client`](https://github.com/TrueSightDAO/dao_protocol) | Python | Full-featured client library. Key generation, payload construction, signing, submission, and CLI tools for every event type. Install via `pip install truesight-dao-client`. |
| [`dapp.truesight.me`](https://dapp.truesight.me) | JavaScript (browser) | Reference UI. Each event type has its own HTML page that generates and submits signed payloads from the browser. |
| [`edgar_payload_helper.js`](https://github.com/TrueSightDAO/dapp/blob/main/scripts/edgar_payload_helper.js) | JavaScript | Canonical payload builder used by all dApp pages. The Python `edgar_client.py` is a direct port. |

### Quick start (Python)

```bash
pip install truesight-dao-client

# Register a keypair
truesight-dao-auth login --email you@example.com

# Check status
truesight-dao-auth status

# Submit a contribution
truesight-dao-report-contribution \
    --type "Time (Minutes)" --amount 30 \
    --description "Integration work" \
    --contributors "Your Name" --tdg-issued 50.00
```

### Quick start (any language)

```python
# Pseudocode — adapt to your language
import rsa, base64, requests

# 1. Generate RSA-2048 keypair
priv = rsa.generate_private_key(2048)
pub_b64 = base64_encode(spki_der(priv.public_key()))
priv_b64 = base64_encode(pkcs8_der(priv))

# 2. Build payload
payload = "[CONTRIBUTION EVENT]\n- Type: Time (Minutes)\n- Amount: 30\n--------"

# 3. Sign
signature = base64_encode(rsassa_pkcs1_v15_sign(priv, sha256(payload)))

# 4. Build share text
share_text = f"{payload}\n\nMy Digital Signature: {pub_b64}\n\nRequest Transaction ID: {signature}\n\n..."

# 5. Submit
requests.post("https://edgar.truesight.me/dao/submit_contribution",
              files={"text": (None, share_text)})
```

---

## 7. Getting Help

- **Documentation:** [`TrueSightDAO/dao_protocol`](https://github.com/TrueSightDAO/dao_protocol) — this repo contains the Python client library, the auth CLI, and integration docs.
- **Source code:** [`github.com/TrueSightDAO`](https://github.com/TrueSightDAO) — all DAO repos are open source.
- **Browser reference:** [`dapp.truesight.me`](https://dapp.truesight.me) — each event type has a working HTML page you can inspect.
- **Issues:** Open a GitHub issue in the relevant repo for bugs or feature requests.

---

*Last updated: 2026-05-20*
