"""Runtime configuration for the dao_protocol server.

Settings are read from the environment (prefix ``DAO_PROTOCOL_``) or a local
``.env``. PR1 only needs the bind + metadata fields; later slices extend this
with the Sheets service-account path, Stripe / EasyPost / GitHub secrets, and
GAS shared secrets (kept here so there is one typed place to add them).
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Where the service-account JSONs were first provisioned: the Edgar web box.
# Kept as the final fallback so existing seni_ror deploys keep resolving even
# without any creds-dir configuration.
_LEGACY_CREDS_DIR = "/home/ubuntu/sentiment_importer/config"

# Other hosts that run this server keep the SAME filenames under a DIFFERENT
# directory (the autopilot EC2 ships them under config/google). We probe these
# in order so the server "just works" wherever it is deployed, instead of
# raising FileNotFoundError on a path that only exists on the Edgar box.
_BUILTIN_CREDS_DIRS = (
    "/opt/truesight_autopilot/config/google",
    _LEGACY_CREDS_DIR,
)

# Field name -> credential filename. The filename is stable across hosts; only
# the containing directory changes, which is what we resolve below.
_SA_FILENAMES = {
    "google_sa_json": "edgar_dapp_listener_key.json",
    "google_sa_json_qr_lookup": "cypher_defense_gdrive_key.json",
    "google_sa_json_qr_sales": "agroverse_qr_code_gdrive_key.json",
}


def _resolve_sa_path(filename: str, creds_dirs: list[str]) -> str:
    """Return the first ``{dir}/{filename}`` that exists.

    If none exist, fall back to the legacy Edgar-box path so error messages name
    a concrete location rather than an empty string.
    """
    for d in creds_dirs:
        if not d:
            continue
        candidate = Path(d) / filename
        if candidate.is_file():
            return str(candidate)
    return str(Path(_LEGACY_CREDS_DIR) / filename)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DAO_PROTOCOL_",
        env_file=".env",
        extra="ignore",
    )

    # --- service metadata ---------------------------------------------------
    service_name: str = "dao_protocol"
    environment: str = "development"  # development | production

    # --- bind --------------------------------------------------------------
    # Bind on all interfaces: the nginx reverse proxy (krake_ng) lives on a
    # SEPARATE host and reaches this service across the private network, the
    # same way it already proxies to the Rails app on :3002. The security
    # group — not a localhost bind — is what restricts who can hit :8010.
    host: str = "0.0.0.0"
    port: int = 8010

    log_level: str = "info"

    # Directory holding the service-account JSONs. Honors the autopilot's
    # ``GOOGLE_CREDS_DIR`` convention; ``DAO_PROTOCOL_GOOGLE_CREDS_DIR`` takes
    # precedence. When set, ``{dir}/<key>.json`` is preferred over the built-in
    # probe dirs. Leave empty to auto-resolve (see _resolve_google_sa_paths).
    google_creds_dir: str = ""

    # Service-account JSON paths. Leave UNSET to auto-resolve the filename from
    # google_creds_dir → GOOGLE_CREDS_DIR → built-in dirs (autopilot, then the
    # legacy Edgar box). Set DAO_PROTOCOL_GOOGLE_SA_JSON to pin an exact path
    # verbatim (operator override wins over auto-resolution).
    #   - google_sa_json          → Google Sheets writes (newsletter/email-agent tracking, etc.)
    #   - google_sa_json_qr_lookup → QR-code lookup tab (different perms)
    #   - google_sa_json_qr_sales  → QR-code sales tab (different perms)
    google_sa_json: str = ""
    google_sa_json_qr_lookup: str = ""
    google_sa_json_qr_sales: str = ""

    # EasyPost API key for USPS shipping rate quotes (PR4). NOT hardcoded — set
    # DAO_PROTOCOL_EASYPOST_API_KEY in the box's .env (gitignored). Empty → rate calc returns [].
    easypost_api_key: str = ""

    # Stripe secret key for the QR-code / meta-checkout flows (PR6). From DAO_PROTOCOL_STRIPE_SECRET_KEY
    # (box .env). Empty → MINTED-QR checkout returns an error (gate-off safe).
    stripe_secret_key: str = ""

    # GitHub PAT for /dao attachment uploads to TrueSightDAO repos (DAO_PROTOCOL_GITHUB_PAT).
    github_pat: str = ""

    # Agroverse inventory-snapshot GAS (ASSET RECEIPT dispatch → refresh inventory JSON). GET
    # ?action=&token=. From DAO_PROTOCOL_AGROVERSE_INVENTORY_{GAS_WEBAPP_URL,PUBLISH_SECRET,GAS_ACTION}.
    agroverse_inventory_gas_webapp_url: str = ""
    agroverse_inventory_publish_secret: str = ""
    agroverse_inventory_gas_action: str = "recalculateAndPublishInventory"

    # Email-onboarding GAS mailer ([EMAIL REGISTERED] → sendEmailVerification). From
    # DAO_PROTOCOL_EMAIL_VERIFICATION_{GAS_WEBHOOK_URL,GAS_SECRET}.
    email_verification_gas_webhook_url: str = ""
    email_verification_gas_secret: str = ""

    # Bugsnag error tracking (DAO_PROTOCOL_BUGSNAG_API_KEY). Empty → SDK not loaded, no
    # middleware, zero overhead. `release_stage` defaults to `environment` above.
    bugsnag_api_key: str = ""

    @model_validator(mode="after")
    def _resolve_google_sa_paths(self) -> "Settings":
        """Fill any unset service-account path by locating its filename on disk.

        Precedence per key: an explicit ``DAO_PROTOCOL_GOOGLE_SA_JSON*`` override
        (respected verbatim) → ``google_creds_dir`` → ``GOOGLE_CREDS_DIR`` env →
        built-in dirs (autopilot, then legacy Edgar box). This lets the same
        server boot on the Edgar box, the autopilot EC2, or the dao_protocol host
        without each one hardcoding a path that only exists somewhere else.
        """
        creds_dirs = [
            self.google_creds_dir,
            os.environ.get("GOOGLE_CREDS_DIR", ""),
            *_BUILTIN_CREDS_DIRS,
        ]
        for field, filename in _SA_FILENAMES.items():
            # An explicit, non-empty operator override is used as-is.
            if field in self.model_fields_set and getattr(self, field):
                continue
            setattr(self, field, _resolve_sa_path(filename, creds_dirs))
        return self

    @model_validator(mode="after")
    def _guard_sk_live_in_development(self) -> "Settings":
        """Safety backstop: refuse to boot in development mode with a live Stripe key."""
        if self.environment == "development" and self.stripe_secret_key.startswith("sk_live_"):
            raise ValueError(
                "REFUSED: environment=development but stripe_secret_key starts with sk_live_. "
                "Set DAO_PROTOCOL_STRIPE_SECRET_KEY to a test key (sk_test_...) or switch to "
                "environment=production."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()
