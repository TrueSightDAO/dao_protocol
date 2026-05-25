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


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()
