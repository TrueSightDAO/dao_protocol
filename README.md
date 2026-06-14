> 📖 **New to the DAO? Start with the [Integration Guide →](INTEGRATION_GUIDE.md)** — a developer-friendly overview of all Edgar protocols, event types, and the digital signature system.

# dao_client

Python client library + CLI for **TrueSight DAO**'s contribution server, **Edgar** ([`edgar.truesight.me`](https://edgar.truesight.me), source: [`TrueSightDAO/dao_client`](https://github.com/TrueSightDAO/dao_client) (Python/FastAPI, formerly dao_protocol)).

Every public DAO action — contribution, inventory movement, notarization, QR update, tree planting, proposal vote, sale — is submitted as an **RSA-signed event payload** to Edgar's `POST /dao/submit_contribution` endpoint. The browser-side reference implementation lives in [`TrueSightDAO/dapp`](https://github.com/TrueSightDAO/dapp) (each HTML page under `dapp.truesight.me/`). This repo is the **terminal / script / automation** equivalent: same signing, same payload shape, same endpoint — just from Python instead of a browser tab.

## Contents

- [What this repo gives you](#what-this-repo-gives-you)
- [Installation](#installation)
- [Quick start (three commands)](#quick-start-three-commands)
- [Onboarding a key — `truesight_dao_client.auth`](#onboarding-a-key--truesight_dao_clientauth--truesight-dao-auth)
  - [How the loopback flow works](#how-the-loopback-flow-works)
  - [Subcommands](#subcommands)
  - [Constraints & troubleshooting](#constraints--troubleshooting)
- [Submitting signed events — `truesight_dao_client.modules/`](#submitting-signed-events--truesight_dao_clientmodules)
- [Reading DAO data — `truesight_dao_client.cache/`](#reading-dao-data--truesight_dao_clientcache)
- [AI-agent contributions — `report_ai_agent_contribution`](#ai-agent-contributions--truesight_dao_clientmodulesreport_ai_agent_contributionpy)
- [Using the library from your own Python](#using-the-library-from-your-own-python)
- [Environment variables (`.env`)](#environment-variables-env)
- [Architecture — one picture](#architecture--one-picture)
- [Security notes](#security-notes)
- [Related repos](#related-repos)

## What this repo gives you

| Location | Purpose |
|----------|---------|
| [`truesight_dao_client/edgar_client.py`](truesight_dao_client/edgar_client.py) | Core library. Key generation (RSA-2048, SPKI / PKCS#8 base64 — byte-identical to WebCrypto exports), canonical payload formatting, RSASSA-PKCS1-v1_5 / SHA-256 signing, the multipart `POST /dao/submit_contribution`, and `build_event_cli(...)` for zero-boilerplate per-event wrappers. Python port of [`dapp/scripts/edgar_payload_helper.js`](https://github.com/TrueSightDAO/dapp/blob/main/scripts/edgar_payload_helper.js). |
| [`truesight_dao_client/auth.py`](truesight_dao_client/auth.py) | OAuth-loopback CLI to onboard this machine's keypair. `login` signs `[EMAIL REGISTERED EVENT]` with a `127.0.0.1:<port>/verify` callback, spins up a one-shot listener, captures `em`+`vk` when the email link is clicked, auto-submits `[EMAIL VERIFICATION EVENT]`. Fallbacks: `verify`, `status`, `rotate`. Installed as `truesight-dao-auth`. |
| [`truesight_dao_client/modules/`](truesight_dao_client/modules) | Thin CLI wrappers, one per signed page on `dapp.truesight.me/`. Named flags for canonical attributes + `--attr 'Label=Value'` escape hatch + `--dry-run`. See [table](#submitting-signed-events--truesight_dao_clientmodules). |
| [`truesight_dao_client/cache/`](truesight_dao_client/cache) | Read-side wrappers over the DAO's four public data sources (treasury snapshot, freight lanes, repackaging receipts, contributor voting rights). Each module has a library API and `python -m truesight_dao_client.cache.<name>` (plus `truesight-dao-cache-*` console scripts). Swappable backends (`GithubRawBackend` / `GithubContentsBackend` / `GasBackend`) so GAS→GitHub flips are one-liners. |
| [`truesight_dao_client/modules/ping_sophia.py`](truesight_dao_client/modules/ping_sophia.py) | **Ping Sophia (the autopilot)** with a governor-signed one-shot message — the reusable trigger for the local-LLM → Sophia execution handoff (e.g. "open a Telegram topic for `<plan>` and post a kickoff"). Signs the RSA payload Sophia's `/chat-blocking` expects and POSTs with `X-Public-Key`. **Governor-only — enforced by Sophia** (non-governor keys get HTTP 403). Installed as `truesight-dao-ping-sophia`. Any LLM/CLI on a governor's machine (with that governor's `./.env` keys) can use it. |
| [`dapp_digital_signature_onboarding/`](dapp_digital_signature_onboarding/) | Operator read-mostly demo mirroring Edgar's Google-Sheets side of the onboarding flow (append `VERIFYING` row, call the mailer, flip to `ACTIVE`). Previously lived in [`TrueSightDAO/tokenomics`](https://github.com/TrueSightDAO/tokenomics) under `python_scripts/examples/`. |
| [`requirements.txt`](requirements.txt) | Mirrors runtime deps from [`pyproject.toml`](pyproject.toml) for `pip install -r` workflows. |
| [`pyproject.toml`](pyproject.toml) | **Installable package** `truesight-dao-client` (import name `truesight_dao_client`) and console entry points (`truesight-dao-auth`, per-event CLIs, cache readers). |
| `.env` | **Never committed** (0600, gitignored). Holds `EMAIL`, `PUBLIC_KEY` (SPKI base64), `PRIVATE_KEY` (PKCS#8 base64). Written by `truesight-dao-auth login` (or `python -m truesight_dao_client.auth login`). **Looked up from the current working directory** (`./.env`) unless you pass an explicit path to `EdgarClient.from_env(path=...)`. |
| [`auth.py`](auth.py), [`edgar_client.py`](edgar_client.py) (repo root) | Thin shims for older scripts; prefer `truesight_dao_client` imports or the `truesight-dao-*` commands after `pip install`. |

## Installation

**From PyPI** (once published):

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install truesight-dao-client
```

**From a git checkout** (editable install keeps `truesight-dao-*` on your `PATH`):

```bash
git clone git@github.com:TrueSightDAO/dao_client.git ~/Applications/dao_client
cd ~/Applications/dao_client
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
# or: pip install -r requirements.txt   # library only, no console scripts
```

Python **3.10+** (uses `list[str]`-style type hints in several modules).

## Quick start (three commands)

```bash
# 1. Generate a keypair, register it with Edgar, finalise via email click.
truesight-dao-auth login --email you@example.com

# 2. Confirm Edgar agrees you're active.
truesight-dao-auth status

# 3. Emit any signed event — e.g. log 30 min of contribution work.
truesight-dao-report-contribution \
    --type "Time (Minutes)" --amount 30 \
    --description "Closing out Townhall" \
    --contributors "Your Name" --tdg-issued "N/A"
```

Dry-run the third command with `--dry-run` first if you want to see the signed share text without hitting the wire.

## Onboarding a key — `truesight_dao_client.auth` / `truesight-dao-auth`

### How the loopback flow works

```text
  ┌─────────────┐                     ┌─────────────────────┐
  │  your CLI   │   [EMAIL REGISTERED │ Edgar (Python/FastAPI)       │
  │  auth.py    │──────── EVENT]─────▶│ edgar.truesight.me  │
  │             │   gen_src=127.0.0.1 │                     │
  │             │                     └──────────┬──────────┘
  │             │                                │
  │             │          ┌─────────────────────▼──────────┐
  │             │          │ GAS edgar_send_email_verif.gs │
  │             │          │ GmailApp.sendEmail(…&vk=…)    │
  │             │          └─────────────────────┬──────────┘
  │             │                                │
  │             │         (you receive an email) │
  │             │                                ▼
  │             │  ┌──────────────────────────────────────┐
  │ ◀────em,vk──┼──┤ browser: http://127.0.0.1:PORT/verify│
  │             │  │ ?em=…&vk=…                            │
  │             │  └──────────────────────────────────────┘
  │             │                     ┌─────────────────────┐
  │             │   [EMAIL VERIFICATION│ Edgar writes       │
  │             │─────── EVENT]──────▶│ Contributors Digital│
  │             │   vk + pubkey       │ Signatures row:    │
  │             │                     │ Status=ACTIVE,     │
  │             │                     │ col H = now         │
  │             │                     └─────────────────────┘
  └─────────────┘
```

The generation-source URL encoded in the signed payload is the **only** thing that tells the mailer where to point the link — the auth CLI exploits that by setting it to an ephemeral `127.0.0.1` port bound a moment before the `EMAIL REGISTERED EVENT` POST. The listener captures `em`+`vk` the instant you click, signs `[EMAIL VERIFICATION EVENT]` with the **same** keypair, and POSTs it to Edgar. Column H ("Verification Key Consumed", added in [`sentiment_importer#1024`](https://github.com/TrueSightDAO/sentiment_importer/pull/1024)) enforces single-use.

### Subcommands

```bash
truesight-dao-auth login  --email you@example.com   # loopback register+verify; default path
truesight-dao-auth verify --vk <value-from-email-url>  # manual fallback if you click on a phone
truesight-dao-auth status                            # GET /dao/check_digital_signature
truesight-dao-auth rotate --email you@example.com    # wipe .env keys + generate fresh
```

`truesight-dao-auth login` is **idempotent** — if the stored key is already `ACTIVE` on Edgar it exits with a short message. If the key is mid-verification it says so and points you at `verify` / `rotate`.

### Constraints & troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Gmail shows "preview this link" warning | Link is `http://127.0.0.1:…` (not HTTPS). | Click through — it's a local URL. |
| Email link opens but nothing happens in terminal | You clicked on a different device, or the listener timed out (10 min default). | `truesight-dao-auth verify --vk <value>` (paste the `vk=` query param from the URL). |
| `HTTP 422 … No matching pending verification row` | The vk already consumed, or the pub_key doesn't match the row the vk was minted for. | `truesight-dao-auth rotate --email you@example.com` then log in again. |
| `HTTP 200 … email_registration.skipped=true` | This browser key is already pending/active — Edgar won't re-send. | Click the previous email, or `rotate`. |
| `ReadTimeout` on status / contributors | GAS cold start. | Retry once; `GasBackend` default is 45 s. |

## Submitting signed events — `truesight_dao_client.modules/`

Every signed page on `dapp.truesight.me/` has a matching module under `truesight_dao_client/modules/`. Each one hardcodes the event name, exposes canonical attributes as named CLI flags (dashes; e.g. `--type`, `--amount`), and accepts `--attr 'Label=Value'` (repeatable) for anything not covered. All modules support `--dry-run` and `--generation-source <URL>`.

After `pip install -e .` or `pip install truesight-dao-client`, use the `truesight-dao-*` console commands (see [`pyproject.toml`](pyproject.toml) `[project.scripts]`). You can also run `python -m truesight_dao_client.modules.<name> …`.

```bash
truesight-dao-report-contribution \
    --type "Time (Minutes)" --amount 30 \
    --description "Closing out Townhall" \
    --contributors "Gary Teh" \
    --tdg-issued 50.00
# → HTTP 200, {"status":"success","signature_verification":"success",...}
```

Example when the contribution is **USD-denominated** under the **1 TDG per 1 USD** rule. The DApp maps the **USD** picker to payload **`- Type: USD`** ([`dapp/report_contribution.html`](https://github.com/TrueSightDAO/dapp/blob/main/report_contribution.html)); **`Amount`** is the USD number; **`TDG Issued`** should match it (e.g. **607.00** TDG for **607.00** USD).

```bash
truesight-dao-report-contribution \
    --type "USD" \
    --amount 607.00 \
    --description "Flight tickets for DAO logistics (USD 607.00)." \
    --contributors "Gary Teh" \
    --tdg-issued 607.00
```

### TDG Issued — match the scoring rubric (time **or** USD)

Do **not** use `N/A` for **`TDG Issued`** when a numeric rubric applies. Tokenomics TDG scoring encodes two headline rules in `google_app_scripts/tdg_scoring/grok_scoring_for_telegram_and_whatsapp_logs.gs` (`checkTdgIssued`): **100 TDG per 1 hour** of human effort, and **1 TDG per 1 USD** of contribution treated as **liquidity / dollar outlay**. The sheet **Intiatives Scoring Rubric** summarizes categories ([`tokenomics/SCHEMA.md` — *Intiatives Scoring Rubric*](https://github.com/TrueSightDAO/tokenomics/blob/main/SCHEMA.md)). Pass **`--tdg-issued`** so CLI rows stay consistent with Telegram-scored lines.

**Clock time (`Time (Minutes)`, human effort)**  
Classification analogue: *100TDG For every 1 hour of human effort*. Compute TDG as **`100 * <minutes> / 60`** (e.g. 30 minutes → **50.00** TDG).

**USD (dollar amount — liquidity injected / spend the rubric scores per-USD)**  
Classification analogue: *1TDG For every 1 USD of liquidity injected*. Use **`--type "USD"`** to mirror the DApp’s USD branch (not `Time (Minutes)`). Set **`--amount`** to the **USD** number and **`--tdg-issued` to the same numeric total** — e.g. **607.00** USD outlay → **`--tdg-issued 607.00`** (Grok example in the same `checkTdgIssued` string). Proof and context still go in **`--description`** (and attachments / destination fields when applicable).

**Other types** (capital injection events, inventory, AI-agent sessions, …) use the rubric line that applies to that **Type** / event. The AI-agent contribution CLI defaults `Amount` / TDG to **0** by convention; see [`agentic_ai_context/DAO_CLIENT_AI_AGENT_CONTRIBUTIONS.md`](https://github.com/TrueSightDAO/agentic_ai_context/blob/main/DAO_CLIENT_AI_AGENT_CONTRIBUTIONS.md). Capital and other dedicated events may use **`truesight-dao-report-capital-injection`** (or the matching module) instead of **`truesight-dao-report-contribution`** when that is the correct Edgar event.

| Module | Console script (examples) | Event tag | Browser equivalent |
|--------|---------------------------|-----------|--------------------|
| `truesight_dao_client/modules/batch_qr_generator.py` | `truesight-dao-batch-qr-generator` | `[BATCH QR CODE REQUEST]` | `batch_qr_generator.html` |
| `truesight_dao_client/modules/create_proposal.py` | `truesight-dao-create-proposal` | `[PROPOSAL CREATION]` | `create_proposal.html` |
| `truesight_dao_client/modules/notarize.py` | `truesight-dao-notarize` | `[NOTARIZATION EVENT]` | `notarize.html` |
| `truesight_dao_client/modules/register_farm.py` | `truesight-dao-register-farm` | `[FARM REGISTRATION]` | `register_farm.html` |
| `truesight_dao_client/modules/repackaging_planner.py` | `truesight-dao-repackaging-planner` | `[REPACKAGING BATCH EVENT]` | `repackaging_planner.html` |
| `truesight_dao_client/modules/report_capital_injection.py` | `truesight-dao-report-capital-injection` | `[CAPITAL INJECTION EVENT]` — **external investors wiring into AGL contracts only** | `report_capital_injection.html` |
| `truesight_dao_client/modules/report_contribution.py` | `truesight-dao-report-contribution` | `[CONTRIBUTION EVENT]` — time or out-of-pocket expenses | `report_contribution.html` |
| `truesight_dao_client/modules/report_ai_agent_contribution.py` | `truesight-dao-report-ai-agent-contribution` | `[CONTRIBUTION EVENT]` (AI agent — **PR URLs required**) | *Convention:* [`agentic_ai_context/DAO_CLIENT_AI_AGENT_CONTRIBUTIONS.md`](https://github.com/TrueSightDAO/agentic_ai_context/blob/main/DAO_CLIENT_AI_AGENT_CONTRIBUTIONS.md) |
| `truesight_dao_client/modules/report_dapp_permission_change.py` | `truesight-dao-report-dapp-permission-change` | `[DAPP PERMISSION CHANGE EVENT]` (governor-only — edits `permissions.json` on `treasury-cache`) | *Spec:* [`agentic_ai_context/DAPP_PERMISSION_CHANGE_FLOW.md`](https://github.com/TrueSightDAO/agentic_ai_context/blob/main/DAPP_PERMISSION_CHANGE_FLOW.md) |
| `truesight_dao_client/modules/report_dao_expenses.py` | `truesight-dao-report-dao-expenses` | `[DAO Inventory Expense Event]` | `report_dao_expenses.html` |
| `truesight_dao_client/modules/report_inventory_movement.py` | `truesight-dao-report-inventory-movement` | `[INVENTORY MOVEMENT]` | `report_inventory_movement.html` |
| `truesight_dao_client/modules/report_sales.py` | `truesight-dao-report-sales` | `[SALES EVENT]` | `report_sales.html` |
| `truesight_dao_client/modules/report_tree_planting.py` | `truesight-dao-report-tree-planting` | `[TREE PLANTING EVENT]` | `report_tree_planting.html` |
| `truesight_dao_client/modules/review_proposal.py` | `truesight-dao-review-proposal` | `[PROPOSAL VOTE]` | `review_proposal.html` |
| `truesight_dao_client/modules/scanner.py` | `truesight-dao-scanner` | `[QR CODE EVENT]` | `scanner.html` |
| `truesight_dao_client/modules/update_qr_code.py` | `truesight-dao-update-qr-code` | `[QR CODE UPDATE EVENT]` | `update_qr_code.html` |
| `truesight_dao_client/modules/withdraw_voting_rights.py` | `truesight-dao-withdraw-voting-rights` | `[VOTING RIGHTS WITHDRAWAL REQUEST]` | `withdraw_voting_rights.html` |

Read the browser-equivalent HTML for the canonical attribute list and value-format expectations (dates, coordinates, currency). Pages that don't emit a signed event (read-only dashboards — `index.html`, `stores_nearby.html`, `stores_by_status.html`, `store_interaction_history.html`, `submit_feedback.html`, `verify_request.html`, `view_open_proposals.html`, `restock_recommender.html`, `shipping_planner.html`) aren't mirrored here — they'd need a different client surface (GET helpers).

## Reading DAO data — `truesight_dao_client.cache/`

Four wrappers over the DAO's read-only data sources. Each one has a library API, `python -m truesight_dao_client.cache.<name>`, and a `truesight-dao-cache-*` console script.

| Module | Source | CLI example |
|--------|--------|-------------|
| `truesight_dao_client.cache.treasury` | [`TrueSightDAO/treasury-cache/dao_offchain_treasury.json`](https://raw.githubusercontent.com/TrueSightDAO/treasury-cache/main/dao_offchain_treasury.json) (GitHub raw) — DAO off-chain inventory snapshot, regenerated on every Telegram-logged inventory movement + safety-net cron. | `truesight-dao-cache-treasury --ledger AGL4` |
| `truesight_dao_client.cache.freight` | [`TrueSightDAO/agroverse-freight-audit/pointers/freight_lanes.json`](https://raw.githubusercontent.com/TrueSightDAO/agroverse-freight-audit/main/pointers/freight_lanes.json) (GitHub raw) — freight lane registry. | `truesight-dao-cache-freight --to "San Francisco"` |
| `truesight_dao_client.cache.compositions` | [`TrueSightDAO/agroverse-inventory/currency-compositions/{uuid}.json`](https://github.com/TrueSightDAO/agroverse-inventory/tree/main/currency-compositions) — per-UUID repackaging receipts (GitHub raw fetch + GitHub contents API for listing, rate-limited to 60/hr unauthenticated). | `truesight-dao-cache-compositions --list` |
| `truesight_dao_client.cache.contributors` | **GAS `assetVerify` (default) + GitHub-raw [`dao_members.json`](https://raw.githubusercontent.com/TrueSightDAO/treasury-cache/main/dao_members.json) (live)** — auto-detects shape, either works. See below. | `truesight-dao-cache-contributors` · `--github` · `--list` · `--totals` |

### `truesight_dao_client.cache.contributors` — two live backends

The snapshot shipped by [`tokenomics#237`](https://github.com/TrueSightDAO/tokenomics/pull/237)'s `dao_members_cache_publisher.gs` is **live now** at `raw.githubusercontent.com/TrueSightDAO/treasury-cache/main/dao_members.json`. Refresh triggers:

- [`sentiment_importer#1028`](https://github.com/TrueSightDAO/sentiment_importer/pull/1028) — Perch (Rails) enqueues `DaoMembersCacheRefreshWorker` (Sidekiq worker in sentiment_importer) on every successful `[EMAIL VERIFICATION EVENT]` activation. The worker GETs `?action=refresh_dao_members_cache&secret=…` on the publisher, which rebuilds the snapshot and commits to the treasury-cache repo.
- `installDaoMembersCacheDailyTrigger()` — safety-net daily cron in the GAS. Cache self-heals if a Sidekiq enqueue drops.
- Manual operator call: `publishDaoMembersCacheNow()` in the Apps Script editor.

Snapshot shape (`schema_version: 2`, contributor-keyed because one contributor has N simultaneously-active RSA keys — see `project_edgar_multiple_active_keys` memory):

```json
{
  "generated_at": "2026-04-22T…Z",
  "schema_version": 2,
  "dao_totals": {
    "voting_rights_circulated": 2341222.10,
    "total_assets": 15086.58,
    "asset_per_circulated_voting_right": 0.00644,
    "usd_provisions_for_cash_out": 32.42
  },
  "contributors": [
    { "name": "Gary Teh", "voting_rights": 955414.06,
      "public_keys": [{"public_key": "MIIB…", "status": "ACTIVE",
                       "created_at": "…", "last_active_at": "…"}] }
  ]
}
```

`Contributors.for_public_key(pk)` auto-detects which shape the backend returned (GAS ships a single `{contributor_name, voting_rights, …}` dict; GitHub ships the snapshot above and we scan `contributors[*].public_keys[*]` locally) and returns an identical-shaped record either way — just with `_source: "gas" | "github_cache"` appended so callers can tell which path answered. **Default remains GAS** for zero-surprise migration; flip to GitHub explicitly via `Contributors.from_github()` or the `--github` CLI flag, or globally by editing `_default_lookup_source` in [`truesight_dao_client/cache/contributors.py`](truesight_dao_client/cache/contributors.py).

### Library usage

```python
from truesight_dao_client.cache.treasury import TreasuryCache
tc = TreasuryCache.fetch()
print(tc.totals())                               # {item_types, total_units, total_value_usd, ...}
print(tc.manager("Gary Teh"))                    # one manager's holdings
print(tc.for_ledger("AGL4"))                     # contents of AGL4
print(tc.item("ceremonial-cacao-500g"))          # where a SKU lives

from truesight_dao_client.cache.contributors import Contributors
me = Contributors().for_self()                   # default GAS backend
print(me["voting_rights"])                        # e.g. 955414.06

me_fast = Contributors.from_github().for_self()  # fast path — ~50–150ms TTFB vs 2–5s GAS cold start
print(me_fast["_source"], me_fast["_generated_at"])

roster = Contributors.from_github().list_all()   # every contributor + their public keys
print(Contributors.from_github().dao_totals())   # DAO-wide aggregates block
```

### Backend-swappable architecture

Every cache module delegates reads to a `DataSource` in [`truesight_dao_client/cache/_source.py`](truesight_dao_client/cache/_source.py). Three implementations ship:

- `GithubRawBackend(raw_url)` — CDN-fast, auth-free, git-history audit trail. Default for treasury / freight / compositions; opt-in for contributors.
- `GithubContentsBackend(contents_url)` — for directory listings that `raw.githubusercontent.com` can't enumerate. Rate-limited to 60 req/hr per IP unauthenticated; surfaces a readable error when throttled.
- `GasBackend(exec_url, params=...)` — for GAS web apps. 45 s timeout so cold starts don't spuriously fail. Default for `truesight_dao_client.cache.contributors`.

### Downstream — dapp uses the same cache

[`TrueSightDAO/dapp`](https://github.com/TrueSightDAO/dapp) shares the same `dao_members.json` snapshot via [`scripts/dao_members_cache.js`](https://github.com/TrueSightDAO/dapp/blob/main/scripts/dao_members_cache.js):

- [`tdg_balance.js`](https://github.com/TrueSightDAO/dapp/blob/main/tdg_balance.js) renders the voting-rights badge from the cache (GAS fallback on miss) — typical 20× latency win vs GAS cold start ([dapp#170](https://github.com/TrueSightDAO/dapp/pull/170)).
- [`create_signature.html`](https://github.com/TrueSightDAO/dapp/blob/main/create_signature.html) renders "Welcome back" optimistically from the cache while Edgar's `check_digital_signature` call is in flight ([dapp#171](https://github.com/TrueSightDAO/dapp/pull/171)).

So a verification landing in Edgar propagates to: Sidekiq worker → GAS publisher → GitHub raw → **both** the dapp browser badge and any Python scripts using `truesight_dao_client.cache.contributors`. One snapshot, three consumers.

## AI-agent contributions — `truesight_dao_client/modules/report_ai_agent_contribution.py`

Special-cased wrapper for `[CONTRIBUTION EVENT]` submissions that record work done **by an AI agent on behalf of a contributor** (e.g. Claude Code pairing sessions). Requires at least one `https://github.com/TrueSightDAO/.../pull/N` URL and an explicit description so the ledger entry is verifiable against a merged PR.

Full convention, format, and review checklist: **[`agentic_ai_context/DAO_CLIENT_AI_AGENT_CONTRIBUTIONS.md`](https://github.com/TrueSightDAO/agentic_ai_context/blob/main/DAO_CLIENT_AI_AGENT_CONTRIBUTIONS.md)**.

## Using the library from your own Python

Every additional DAO event is a three-line call:

```python
from truesight_dao_client import EdgarClient

client = EdgarClient.from_env()
resp = client.submit(
    "CONTRIBUTION EVENT",
    {
        "Type": "Time (Minutes)",
        "Amount": "30",
        "Description": "Closing out Townhall",
        "Contributor(s)": "Gary Teh",
    },
)
print(resp.status_code, resp.text)
```

Or sign without sending (handy for testing or for pasting into a manual workflow):

```python
payload, request_txn_id, share_text = client.sign(
    "CONTRIBUTION EVENT",
    {"Type": "Time (Minutes)", "Amount": "30", "Description": "…", "Contributor(s)": "…"},
)
print(share_text)
```

The attribute dict matches the `-  Label: value` lines emitted by the browser-side `edgar_payload_helper.js` + each `dapp/*.html`, so read that file as the canonical event contract.

## Environment variables (`.env`)

| Key | Purpose | Set by |
|-----|---------|--------|
| `EMAIL` | The email address this identity registered with (used for `EMAIL REGISTERED` + `EMAIL VERIFICATION` events). | `truesight-dao-auth login / rotate` |
| `PUBLIC_KEY` | RSA-2048 SPKI base64, no PEM headers. Byte-identical to `crypto.subtle.exportKey('spki', ...)` + `btoa`. | `truesight-dao-auth login / rotate` |
| `PRIVATE_KEY` | RSA-2048 PKCS#8 base64, no PEM headers, unencrypted. Keep this file mode `0600`. | `truesight-dao-auth login / rotate` |

The `.gitignore` covers `.env`, `.env.*`, and an exception for an optional `.env.example`. If you ever commit a private key by mistake, **rotate immediately** (`truesight-dao-auth rotate`) — multiple active keys per contributor are fine; old leaked keys can be marked inactive in the sheet by an operator.

## Architecture — one picture

```text
 ┌───────────────────────────────────────────────────────────────────────┐
 │                          your shell / script                          │
 │                                                                       │
 │  auth.py                modules/*.py                cache/*.py        │
 │     │                       │                          │              │
 │     └─────signed POST───────┘                          │              │
 │                │                                       │              │
 │                ▼                                       ▼              │
 │    edgar_client.EdgarClient                 cache/_source.py          │
 │     (RSA-2048, PKCS1v15/SHA256,             ┌──────────┬───────────┐  │
 │     SPKI pub / PKCS8 priv)                  │ Github   │ Gas       │  │
 │                │                            │ Raw /    │ Backend   │  │
 │                │                            │ Contents │           │  │
 │                ▼                            └────┬─────┴─────┬─────┘  │
 │  POST https://edgar.truesight.me/                │           │        │
 │       dao/submit_contribution                    │           │        │
 │                │                                 │           │        │
 └────────────────┼─────────────────────────────────┼───────────┼────────┘
                  │                                 │           │
                  ▼                                 ▼           ▼
          ┌────────────────┐              ┌───────────────┐  ┌───────────┐
          │ sentiment_     │              │ TrueSightDAO/ │  │ script.   │
          │ importer (Rails│              │ treasury-cache│  │ google.   │
          │ on EC2)        │              │ /… JSON files │  │ com/macros│
          │ — Edgar        │              │ (GitHub raw)  │  │ /s/…/exec │
          └────────────────┘              └───────────────┘  └───────────┘
                  │
                  ▼
           Google Sheet tabs:
           Contributors Digital Signatures,
           Contributors voting weight,
           TDG ledger, etc.
```

## Security notes

- **Key storage.** `PRIVATE_KEY` lives in `.env` mode 0600, gitignored. Don't check it in. If a key leaks, `truesight-dao-auth rotate` — Edgar allows multiple active keys so revoking an old one is an operator action on the sheet, not a hard lockout.
- **Loopback URLs.** The email verification link is `http://127.0.0.1:<port>/verify?em=…&vk=…`. Anyone with network access to your loopback interface during the 10 min window could hit it; in practice that's you + anything else running on your laptop. Not a concern on a single-user machine.
- **Single-use verification keys.** Column H on *Contributors Digital Signatures* enforces single-use per ([`sentiment_importer#1024`](https://github.com/TrueSightDAO/sentiment_importer/pull/1024)): a second click with the same vk returns `already_consumed: true` if the same public key is signing, or a hard reject if a different key is.
- **No secrets in signed payloads.** Everything in the signed share text is world-readable (Edgar logs it to the Telegram raw-logs sheet). Don't put API keys, sensitive notes, or internal URLs in attribute values.
- **GitHub cache.** The forthcoming `dao_members.json` must publish only **governance-public** fields (name, public keys, voting weight). Emails from `Contributors contact information` (column D) are onboarding data and must not leak — the publisher script projects columns explicitly.

## Related repos

- [`TrueSightDAO/dapp`](https://github.com/TrueSightDAO/dapp) — browser-side reference implementation; one HTML page per signed event.
- [`TrueSightDAO/sentiment_importer`](https://github.com/TrueSightDAO/sentiment_importer) — the Rails Perch (sentiment_importer, formerly called "Edgar"). Signature verify + sheet write logic: `app/services/dao_email_registration_service.rb`, `app/models/gdrive/contributors_digital_signatures.rb`.
- [`TrueSightDAO/tokenomics`](https://github.com/TrueSightDAO/tokenomics) — canonical [`SCHEMA.md`](https://github.com/TrueSightDAO/tokenomics/blob/main/SCHEMA.md) + Apps Script projects (`tdg_identity_management`, `tdg_inventory_management`, etc.) that maintain the Google Sheets ledger and publish the GitHub JSON caches.
- [`TrueSightDAO/treasury-cache`](https://github.com/TrueSightDAO/treasury-cache) — pre-computed JSON snapshot of DAO off-chain treasury. Consumed by `cache.treasury`.
- [`TrueSightDAO/agroverse-freight-audit`](https://github.com/TrueSightDAO/agroverse-freight-audit) — freight lane registry consumed by `cache.freight` and `dapp/shipping_planner.html`.
- [`TrueSightDAO/agroverse-inventory`](https://github.com/TrueSightDAO/agroverse-inventory) — per-request repackaging receipts consumed by `cache.compositions` and `dapp/repackaging_planner.html`.
- [`TrueSightDAO/agentic_ai_context`](https://github.com/TrueSightDAO/agentic_ai_context) — AI-agent operating conventions, including [`DAO_CLIENT_AI_AGENT_CONTRIBUTIONS.md`](https://github.com/TrueSightDAO/agentic_ai_context/blob/main/DAO_CLIENT_AI_AGENT_CONTRIBUTIONS.md) and `PROJECT_INDEX.md`.
