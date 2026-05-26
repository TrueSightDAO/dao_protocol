"""Runtime configuration for the dao_protocol server.

Settings are read from the environment (prefix ``DAO_PROTOCOL_``) or a local
``.env``. PR1 only needs the bind + metadata fields; later slices extend this
with the Sheets service-account path, Stripe / EasyPost / GitHub secrets, and
GAS shared secrets (kept here so there is one typed place to add them).
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # Service-account JSON for Google Sheets writes (newsletter/email-agent tracking, etc.).
    # On seni_ror_new this defaults to the same key Edgar's Rails app already uses, so no new
    # credential needs provisioning. Override with DAO_PROTOCOL_GOOGLE_SA_JSON.
    google_sa_json: str = "/home/ubuntu/sentiment_importer/config/edgar_dapp_listener_key.json"

    # EasyPost API key for USPS shipping rate quotes (PR4). NOT hardcoded — set
    # DAO_PROTOCOL_EASYPOST_API_KEY in the box's .env (gitignored). Empty → rate calc returns [].
    easypost_api_key: str = ""

    # Stripe secret key for the QR-code / meta-checkout flows (PR6). From DAO_PROTOCOL_STRIPE_SECRET_KEY
    # (box .env). Empty → MINTED-QR checkout returns an error (gate-off safe).
    stripe_secret_key: str = ""

    # Service-account keys for the QR-code tabs (different perms than the tracking key).
    google_sa_json_qr_lookup: str = "/home/ubuntu/sentiment_importer/config/cypher_defense_gdrive_key.json"
    google_sa_json_qr_sales: str = "/home/ubuntu/sentiment_importer/config/agroverse_qr_code_gdrive_key.json"

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


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()
