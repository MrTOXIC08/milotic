"""Application configuration using Pydantic Settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict

from utils.errors import BackendConnectionError


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Backend Service URLs ---
    ACCOUNT_BACKEND_URL: str = ""
    TRADING_BACKEND_URL: str = ""

    # --- Crypto Settings ---
    CRYPTO_ENABLED: bool = True

    # --- Need To Get From Environment Variable ---
    API_CLIENT_ID: str = ""
    API_SESSION_SECRET: str = ""
    AUTHORIZATION: str = ""

    API_RSA_PUBLIC_KEY: str | None = None

    # --- Handshake Configuration ---
    HANDSHAKE_PATH: str = "/handshake/get-public-key"
    HANDSHAKE_PUBLIC_KEY_TTL_SECONDS: int = 3600
    HANDSHAKE_CLIENT_ID_HEADER: str = "X-API-Client-Id"
    HANDSHAKE_AUTHORIZATION_HEADER: str = "Authorization"

    # --- Headers Configuration ---
    TRADING_AUTH_HEADER: str = "X-Auth-Token"
    TRADING_SUB_ACCOUNT_HEADER: str = "X-Sub-Account-Id"

    # --- Resilience ---
    MAX_CONCURRENT_REQUESTS: int = 20
    CIRCUIT_BREAKER_THRESHOLD: int = 5

    # --- Logging ---
    LOG_LEVEL: str = "INFO"

    def backend_url(self, category: str) -> str:
        mapping = {
            "account": self.ACCOUNT_BACKEND_URL,
            "trading": self.TRADING_BACKEND_URL,
        }
        url = mapping.get(category)
        if not url:
            raise BackendConnectionError(
                f"No backend URL configured for category '{category}'. "
                f"Set {category.upper()}_BACKEND_URL in your .env file."
            )
        return url


settings = Settings()
