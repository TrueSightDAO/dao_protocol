# Kimi Moon — DAO Client Credentials

Registered on Edgar (TrueSight DAO) for AI agent identity.

| Field | Value |
|-------|-------|
| **Name** | Kimi Moon |
| **Email** | admin+kimi@truesight.me |
| **Status** | ACTIVE on Edgar |
| **Contributor Name** | Kimi Moon (resolved from Contributors contact information sheet) |
| **Public Key** | `MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAtXffJY0bbI7BVP/i3B5UEHJkvmG2Y1Jf/dS4lqNTVqwC/fb65P7NphrnTMxkTCbah2NjPJDNaQlQiYRIG69x677/+CckZr7ZeSvCvyVOqV6bEZpCc8dmKn8AkqW3K7EWenWkxTKBOBL3cVqS42SAsAY3bHLzcZqs/8H7DPDRJZKsTOkTUjS/en4kbHELmfnAjgYpARIuFOdhfeBWI3qys96xvGaMBOtDLhAyIlnmtACMXRwp3f2pU/+HMP1KfH5HBV/4QKeP9WF19gNhfmS43QufTd0hjfinb6KgCRSzs/z/8dZHyWc+2O4yJX0obvO11sx1sgpwHmNw5z4s4YYhzwIDAQAB` |

## Files

- `.env` — RSA-2048 keypair + email (permissions `0o600`, gitignored)
- `README.md` — this file

## Registration Log

- **Date**: 2026-06-18
- **Method**: `truesight-dao-auth login --email admin+kimi@truesight.me`
- **Verification email**: Read via Gmail API (`admin@truesight.me` mailbox)
- **Activation**: Verified via `truesight-dao-auth status` → `registered: true`

## Usage

From the `dao_client` repo root:

```bash
cd credentials/kimi-moon
../../.venv/bin/truesight-dao-auth status
```

Or load the client in Python:

```python
from truesight_dao_client import EdgarClient
client = EdgarClient.from_env(path="credentials/kimi-moon/.env")
```

---
**⚠️ Security**: The `.env` file contains an unencrypted private key. Keep permissions at `0o600`. Do not commit to git. Rotate immediately if leaked.
