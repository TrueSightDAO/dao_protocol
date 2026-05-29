# TrueSight DAO Integration Guide

A developer-friendly reference for integrating with the TrueSight DAO protocol via **Edgar** (`https://edgar.truesight.me`).

---

## Table of Contents

1. [Overview](#1-overview)
2. [Digital Signatures (Foundation)](#2-digital-signatures-foundation)
3. [Event Submission Protocol](#3-event-submission-protocol)
4. [Event Types Reference](#4-event-types-reference)
5. [Read APIs](#5-read-apis)
6. [Webhook / Processing Pipeline](#6-webhook--processing-pipeline)
7. [Reference Implementations](#7-reference-implementations)
8. [Getting Help](#8-getting-help)

---

## 1. Overview

**Edgar** is the TrueSight DAO's API server. It receives signed event payloads from contributors, verifies them cryptographically, logs them to Google Sheets, and triggers downstream processing (ledger updates, GitHub commits, email notifications).

Every interaction follows the same pattern:

1. **Generate an RSA-2048 keypair** (browser or client-side)
2. **Register the public key** with an email address (one-time)
3. **Sign event payloads** with the private key
4. **POST** the signed payload to Edgar
5. Edgar **verifies the signature**, logs the event, and triggers processing

No API key, no OAuth token, no session cookie — the digital signature **is** the authentication.

---

## 2. Digital Signatures (Foundation)

### 2.1 Keypair Generation

Generate an RSA-2048 keypair with SHA-256 hashing:

| Property | Value |
|----------|-------|
| Algorithm | RSA-2048 |
| Hash | SHA-256 |
| Padding | PKCS#1 v1.5 |
| Public Key Format | SPKI (SubjectPublicKeyInfo), base64-encoded |
| Private Key Format | PKCS#8, base64-encoded, unencrypted |

**JavaScript (browser, using Web Crypto API):**

```js
const keyPair = await crypto.subtle.generateKey(
  { name: 'RSASSA-PKCS1-v1_5', modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: 'SHA-256' },
  true,
  ['sign', 'verify']
);
const publicKey = btoa(String.fromCharCode(...new Uint8Array(await crypto.subtle.exportKey('spki', keyPair.publicKey))));
const privateKey = btoa(String.fromCharCode(...new Uint8Array(await crypto.subtle.exportKey('pkcs8', keyPair.privateKey))));
```

**Python (using `truesight-dao-client`):**

```python
from truesight_dao_client import EdgarClient
client = EdgarClient.generate()  # creates keypair, saves to .env
```

### 2.2 Canonical Payload Format

Every signed event follows this exact format:

```
[EVENT NAME]
- Label 1: Value 1
- Label 2: Value 2
- Label 3: Value 3

My Digital Signature: <base64 SPKI public key>

Request Transaction ID: <base64 RSA signature of the canonical payload>

This submission was generated using <source URL>
```

Key rules:
- Event name is in square brackets, all caps, with spaces: `[CONTRIBUTION EVENT]`
- Attributes are `- Label: value` (dash, space, label, colon, space, value)
- A blank line separates the attributes from the signature block
- `My Digital Signature:` is the **public key** (not a signature)
- `Request Transaction ID:` is the **RSA signature** of the entire payload above it (everything before `My Digital Signature:`)
- The signature covers the canonical text including the event name and all attribute lines

### 2.3 Signing

Sign the canonical payload text (everything before `My Digital Signature:`) using RSASSA-PKCS1-v1_5 with SHA-256.

**JavaScript:**

```js
const encoder = new TextEncoder();
const signature = await crypto.subtle.sign(
  { name: 'RSASSA-PKCS1-v1_5' },
  privateKey,
  encoder.encode(canonicalPayload)
);
const requestTxnId = btoa(String.fromCharCode(...new Uint8Array(signature)));
```

**Python:**

```python
from truesight_dao_client import EdgarClient
client = EdgarClient.from_env()
payload, request_txn_id, share_text = client.sign("CONTRIBUTION EVENT", {
    "Type": "Time (Minutes)",
    "Amount": "30",
    "Description": "Work description",
    "Contributor(s)": "Your Name",
})
```

### 2.4 Registration Flow

Before a public key can submit events, it must be bound to an email address. This is a one-time flow:

```
User generates keypair (browser/CLI)
  → submits [EMAIL REGISTERED EVENT] with their email
  → Edgar logs the event, GAS sends a verification email
  → User clicks the link (contains vk + em params)
  → Browser/CLI captures vk + em, signs [EMAIL VERIFICATION EVENT]
  → Edgar marks the public key as ACTIVE
```

**Browser:** Visit `https://dapp.truesight.me/create_signature.html`

**Python CLI:**

```bash
pip install truesight-dao-client
truesight-dao-auth login --email you@example.com
# Check email, click the link, the CLI auto-completes verification
truesight-dao-auth status  # should show registered: true
```

### 2.5 Checking Signature Status

```http
GET https://edgar.truesight.me/dao/check_digital_signature?signature=<base64 SPKI public key>
```

**Response (active):**

```json
{
  "registered": true,
  "contributor_name": "Your Name",
  "contributor_email": "you@example.com"
}
```

**Response (pending verification):**

```json
{
  "registered": false,
  "pending_verification": true,
  "contributor_email": "you@example.com"
}
```

**Response (not found):**

```json
{
  "registered": false,
  "error": "No matching contributor digital signature"
}
```

---

## 3. Event Submission Protocol

### 3.1 Main Submission Endpoint

```http
POST https://edgar.truesight.me/dao/submit_contribution
Content-Type: multipart/form-data
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `text` | string | yes | The full signed payload (canonical format) |
| `attachment` | file | no | File to upload (referenced in payload via GitHub URL) |

**Response (success):**

```json
{
  "status": "success",
  "fileUploadedToGithub": true,
  "googleSheetLogged": true,
  "signature_verification": "success"
}
```

**Response (duplicate):**

```json
{
  "status": "error",
  "error": "Duplicate submission (Request Transaction ID already processed)."
}
```

### 3.2 Express Submission Endpoint

```http
POST https://edgar.truesight.me/dao/express_submit_contribution
Content-Type: multipart/form-data
```

Used for invoice and UPC-linking workflows. Same `text` field, plus optional `contribution_type`.

### 3.3 Signature Verification

Edgar verifies every submission:
1. Parses the canonical payload from the text
2. Extracts the public key from `My Digital Signature:`
3. Verifies the `Request Transaction ID:` signature against the payload
4. Checks the public key is registered and ACTIVE
5. Checks for duplicate `Request Transaction ID` (prevents replay)

### 3.4 File Attachments

If the payload contains a GitHub URL (e.g., `Attachment GitHub URL: https://github.com/TrueSightDAO/.github/blob/main/assets/...`), Edgar will upload the attached file to that path automatically.

---

## 4. Event Types Reference

Every event follows the same submission protocol. Below is the complete catalog.

### Contribution & Finance

| Event Name | Purpose | Key Attributes | DApp Page |
|-----------|---------|---------------|-----------|
| `[CONTRIBUTION EVENT]` | Log time or USD contributions | Type, Amount, Description, Contributor(s), TDG Issued | `report_contribution.html` |
| `[CAPITAL INJECTION EVENT]` | External investment into AGL contracts | Investor Name, Amount, Currency, Ledger | `report_capital_injection.html` |
| `[CURRENCY CONVERSION EVENT]` | Multi-currency conversion between ledgers | Source Currency, Target Currency, Amount, Ledger | `currency_conversion.html` |
| `[VOTING RIGHTS WITHDRAWAL REQUEST]` | Request to cash out voting rights | Amount, Wallet Address | `withdraw_voting_rights.html` |
| `[INVOICE CONTRIBUTION]` | POS invoice via HelloCash integration | Date, Employee, Items (product, qty, price) | POS system |

### Inventory & Supply Chain

| Event Name | Purpose | Key Attributes | DApp Page |
|-----------|---------|---------------|-----------|
| `[INVENTORY MOVEMENT]` | Track inventory between managers/locations | Manager Name, Recipient Name, Inventory Item, Quantity, Location | `report_inventory_movement.html` |
| `[SALES EVENT]` | Record a QR-coded product sale | QR Code, Customer, Amount, Payment Method | `report_sales.html` |
| `[REPACKAGING BATCH EVENT]` | Record repackaging of bulk inventory | Input SKU, Output SKU, Quantity, Location | `repackaging_planner.html` |
| `[ASSET RECEIPT EVENT]` | Record receipt of a physical DAO asset | Currency, Amount, Fund Handler, Description | `report_asset_receipt.html` |
| `[DAO Inventory Expense Event]` | Record DAO operational expenses | Item, Cost, Category, Receipt | `report_dao_expenses.html` |

### QR Code Operations

| Event Name | Purpose | Key Attributes | DApp Page |
|-----------|---------|---------------|-----------|
| `[QR CODE EVENT]` | Scan/register a QR code | QR Code, Action, Location | `scanner.html` |
| `[QR CODE UPDATE EVENT]` | Update QR code metadata | QR Code, Field, New Value | `update_qr_code.html` |
| `[BATCH QR CODE REQUEST]` | Request batch QR code generation | Quantity, Prefix, Product | `batch_qr_generator.html` |
| `[DONATION MINT EVENT]` | Mint a donation pledge QR | Currency, Donor, Amount, Proof URL | Donation flow |

### Governance

| Event Name | Purpose | Key Attributes | DApp Page |
|-----------|---------|---------------|-----------|
| `[PROPOSAL CREATION]` | Submit a new DAO proposal | Title, Description, Options, Deadline | `create_proposal.html` |
| `[PROPOSAL VOTE]` | Cast a vote on a proposal | Proposal ID, Vote, Rationale | `review_proposal.html` |
| `[DAPP PERMISSION CHANGE EVENT]` | Governor-signed permission edits | Action, Target, Permission | Permission UI |

### Credentialing & Identity

| Event Name | Purpose | Key Attributes | DApp Page |
|-----------|---------|---------------|-----------|
| `[EMAIL REGISTERED EVENT]` | Begin key registration | Email, Generation Source URL | `create_signature.html` |
| `[EMAIL VERIFICATION EVENT]` | Complete key registration | Verification Key, Email | `create_signature.html` |
| `[CONTRIBUTOR ADD EVENT]` | Add a new DAO contributor | Name, Email, Role | Onboarding flow |
| `[CREDENTIALING ATTESTATION EVENT]` | Issue a lineage credential | Program, Attestor, Attestee, Credential Type | Credentialing UI |
| `[PRACTICE EVENT]` | Log a capoeira training session (Tribo Bahia Mirim) | Program, Practice Type, Practitioner Public Key, Moves Practiced, Total Practice Minutes | `capoeira.agroverse.shop/practice.html` |

### Outreach & Field Reports

| Event Name | Purpose | Key Attributes | DApp Page |
|-----------|---------|---------------|-----------|
| `[RETAIL FIELD REPORT EVENT]` | Log a store visit/check-in | Shop Name, Status, Remarks, Location | `store_interaction_history.html` |
| `[STORE ADD EVENT]` | Add a new store to the Hit List | Shop Name, Address, Contact, Type | Store add flow |
| `[PARTNER CHECK-IN EVENT]` | Partner restock check-in | Partner Name, SKU, Quantity, Notes | Partner UI |
| `[WARMUP SEND EVENT]` | Send a warm-up email draft | Draft ID, Recipient, Campaign | `warmup_review.html` |

### Other

| Event Name | Purpose | Key Attributes | DApp Page |
|-----------|---------|---------------|-----------|
| `[NOTARIZATION EVENT]` | Notarize a document | Document Hash, Description, Witnesses | `notarize.html` |
| `[TREE PLANTING EVENT]` | Record a tree planting | Tree Count, Location, Species, Planter | `report_tree_planting.html` |
| `[FARM REGISTRATION EVENT]` | Register a farm | Farm Name, Location, Owner, Acreage | `register_farm.html` |
| `[UPC LINKING CONTRIBUTION]` | Link a UPC barcode to a product | Product ID, UPC Code | POS system |

---

## 5. Read APIs

These endpoints do not require signatures — they are public read APIs.

### 5.1 Health Check

```http
GET https://edgar.truesight.me/ping
```

Returns `200 OK` with empty body if the server is healthy.

### 5.2 Signature Lookup

```http
GET https://edgar.truesight.me/dao/check_digital_signature?signature=<base64 SPKI public key>
```

See [Section 2.5](#25-checking-signature-status) for response format.

### 5.3 Shipping Rates (Agroverse)

```http
GET https://edgar.truesight.me/agroverse_shop/shipping_rates?origin=<zip>&destination=<zip>&weight=<oz>
```

Returns USPS shipping rates via EasyPost.

### 5.4 QR Code Lookup

```http
GET https://edgar.truesight.me/agroverse/qr-code-check?qr=<code>
```

Returns product/lot information for a scanned QR code.

### 5.5 Newsletter Tracking (Open Pixel)

```http
GET https://edgar.truesight.me/newsletter/open.gif?mid=<uuid>&r=<base64 recipient email>
```

Returns a 1×1 transparent GIF. Used for email open tracking. The `mid` is a unique message UUID, `r` is the base64-encoded recipient email for verification.

### 5.6 Newsletter Click Tracking

```http
GET https://edgar.truesight.me/newsletter/click?mid=<uuid>&r=<base64 recipient>&to=<base64 target URL>
```

302-redirects to the decoded `to` URL after logging the click.

### 5.7 GAS Proxy

```http
GET https://edgar.truesight.me/proxy/gas/<name>?<query params>
POST https://edgar.truesight.me/proxy/gas/<name>
```

Proxies requests to Google Apps Script endpoints. Used by the DApp in regions where `script.google.com` is blocked (e.g., China). The `<name>` maps to a configured GAS URL on the server.

---

## 6. Webhook / Processing Pipeline

After Edgar successfully receives and verifies a signed event, it triggers downstream processing via Google Apps Script webhooks. This happens asynchronously via Sidekiq background jobs.

### 6.1 Flow

```
Client → POST /dao/submit_contribution → Edgar
  → Signature verification
  → Log to Telegram Chat Logs (Google Sheet)
  → Enqueue WebhookTriggerWorker (Sidekiq)
  → Return success to client

Sidekiq worker → POST GAS webhook URL
  → GAS reads the new row from Telegram Chat Logs
  → Processes the event (update ledger, commit to GitHub, send email, etc.)
  → Returns status
```

### 6.2 Event → Webhook Mapping

| Event triggers | GAS action |
|---------------|------------|
| `[SALES EVENT]` | Parse Telegram Chat Logs → QR Code Sales → Offchain Transactions + Inventory Snapshot |
| `[INVENTORY MOVEMENT]` | Parse → Inventory Movement sheet → Ledgers + Inventory Snapshot |
| `[DAO Inventory Expense Event]` | Parse → Scored Expense Submissions → Ledgers + Inventory Snapshot |
| `[QR CODE UPDATE EVENT]` | Parse → Agroverse QR codes sheet |
| `[BATCH QR CODE REQUEST]` | Parse → QR Code Generation tab |
| `[PROPOSAL CREATION]` / `[PROPOSAL VOTE]` | Parse → GitHub proposals PR |
| `[REPACKAGING BATCH EVENT]` | Parse → Currency Creation → Currencies → GitHub compositions |
| `[CURRENCY CONVERSION EVENT]` | Parse → Currency Conversion → Managed AGL Transactions |
| `[RETAIL FIELD REPORT EVENT]` | Parse → Hit List + DApp Remarks + Stores Visits Field Reports |
| `[STORE ADD EVENT]` | Parse → Hit List row + Store Adds dedup log |
| `[DONATION MINT EVENT]` | Parse → Agroverse QR codes + Donation Mints dedup |
| `[CONTRIBUTOR ADD EVENT]` | Parse → Contributors contact information |
| `[DAPP PERMISSION CHANGE EVENT]` | Parse → permissions.json on treasury-cache + audit |
| `[WARMUP SEND EVENT]` | Parse → GmailApp.send + Warmup Sends audit |
| `[PARTNER CHECK-IN EVENT]` | Parse → Partner Check-ins on Main Ledger |
| `[ASSET RECEIPT EVENT]` | Parse → Currencies + Offchain Transactions |
| `[CREDENTIALING ATTESTATION EVENT]` | Parse → lineage-credentials commit + program roster back-fill |
| `[PRACTICE EVENT]` | Parse → lineage-credentials commit (capoeira-tribo-mirim program) + CV record |

### 6.3 Race Condition Prevention

Edgar uses a Redis-backed cache to prevent duplicate webhook triggers for the same `Request Transaction ID`. The cache key expires after 5 minutes, which covers the typical GAS processing window.

---

## 7. Reference Implementations

### 7.1 Python Client (`truesight-dao-client`)

The official Python library for interacting with Edgar.

```bash
pip install truesight-dao-client
```

**Repository:** `github.com/TrueSightDAO/dao_protocol`

Key capabilities:
- Key generation, registration, and verification
- Signed event submission for all event types
- Read APIs for DAO treasury, contributors, freight lanes, and compositions
- Console scripts: `truesight-dao-auth`, `truesight-dao-report-contribution`, etc.

### 7.2 Browser DApp

The browser-based reference implementation at `dapp.truesight.me`.

**Repository:** `github.com/TrueSightDAO/dapp_beta` (beta) / `github.com/TrueSightDAO/dapp_prod` (production)

Key files:
- `create_signature.html` — key registration flow
- `scripts/edgar_payload_helper.js` — JavaScript signing library
- `scripts/dao_members_cache.js` — contributor cache reader
- Each `report_*.html` — one per event type

### 7.3 JavaScript Signing Helper

`edgar_payload_helper.js` is the canonical reference for building and signing payloads in the browser. It handles:
- RSA keypair generation (Web Crypto API)
- Canonical payload formatting
- Signing with RSASSA-PKCS1-v1_5 / SHA-256
- Multipart form submission to Edgar

### 7.4 Capoeira Practice Platform

The capoeira practice platform at `capoeira.agroverse.shop` demonstrates anonymous keypair generation and `[PRACTICE EVENT]` submission without email registration — the keypair is generated client-side and stored in localStorage, and the practitioner slug is derived from a SHA-256 hash of the public key.

**Repository:** `github.com/TrueSightDAO/capoeira`

Key files:
- `assets/js/practice-event-submit.js` — key generation, payload building, signing, and Edgar submission
- `practice.html` — session generator and practice flow UI

### 7.5 Public Data Caches

The DAO publishes pre-computed JSON snapshots for fast read access:

| Data | URL | Description |
|------|-----|-------------|
| Treasury | `raw.githubusercontent.com/TrueSightDAO/treasury-cache/main/dao_offchain_treasury.json` | Off-chain inventory snapshot |
| Contributors | `raw.githubusercontent.com/TrueSightDAO/treasury-cache/main/dao_members.json` | Contributor names, voting rights, public keys |
| Freight Lanes | `raw.githubusercontent.com/TrueSightDAO/agroverse-freight-audit/main/pointers/freight_lanes.json` | Shipping lane registry |
| Compositions | `github.com/TrueSightDAO/agroverse-inventory/tree/main/currency-compositions/` | Repackaging receipts |

---

## 8. Getting Help

- **GitHub Organization:** `github.com/TrueSightDAO`
- **Documentation Repo:** `github.com/TrueSightDAO/documentation`
- **DAO Protocol Repo:** `github.com/TrueSightDAO/dao_protocol`
- **Edgar Endpoint:** `https://edgar.truesight.me`
- **DApp (Beta):** `https://beta.dapp.truesight.me`
- **DApp (Production):** `https://dapp.truesight.me`
- **Capoeira Practice:** `https://capoeira.agroverse.shop/practice.html`

For integration questions, open an issue on the `dao_protocol` or `documentation` repository.
