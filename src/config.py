"""Application configuration using Pydantic Settings."""

import secrets

from pydantic_settings import BaseSettings, SettingsConfigDict

from utils.errors import BackendConnectionError


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    API_CLIENT_ID: str = "GALAXY_WEBAPP"
    AUTHORIZATION: str = "CAOsBGMOSvj19jGNIRZpLY62Hd6yLA1r77H9MnQ4UyjaOsdo"

    # --- Backend Service URLs ---
    LOGIN_BACKEND_URL: str = "https://welcome-api.axisdirect.in"
    INVESTOR_BACKEND_URL: str = "https://invest-api.axisdirect.in"

    # --- Crypto Settings ---
    CRYPTO_ENABLED: bool = True
    API_SESSION_SECRET: str = ""

    API_RSA_PUBLIC_KEY: str | None = None

    # --- Handshake Configuration ---
    HANDSHAKE_URL: str = "https://welcome-api.axisdirect.in/handshake"
    HANDSHAKE_PUBLIC_KEY_TTL_SECONDS: int = 3600

    # --- Headers Configuration ---
    CONST_AUTHORIZATION_HEADER_KEY: str = "authorization"
    CONST_AUTH_HEADER_KEY: str = "x-authToken"
    CONST_SUB_ACCOUNT_HEADER_KEY: str = "x-subAccountId"
    CONST_CLIENT_ID_HEADER_KEY: str = "x-api-client-id"

    # --- Resilience ---
    MAX_CONCURRENT_REQUESTS: int = 20
    CIRCUIT_BREAKER_THRESHOLD: int = 5

    # --- Logging ---
    LOG_LEVEL: str = "INFO"

    def model_post_init(self, __context) -> None:
        if not self.API_SESSION_SECRET:
            self.API_SESSION_SECRET = secrets.token_hex(16)

    def backend_url(self, category: str) -> str:
        mapping = {
            "login": self.LOGIN_BACKEND_URL,
            "investor": self.INVESTOR_BACKEND_URL,
            "research": self.INVESTOR_BACKEND_URL,
            "trading": self.INVESTOR_BACKEND_URL,
            "account": self.INVESTOR_BACKEND_URL,
            "market": self.INVESTOR_BACKEND_URL,
            "books": self.INVESTOR_BACKEND_URL,
        }
        url = mapping.get(category, self.INVESTOR_BACKEND_URL)
        if not url:
            raise BackendConnectionError(
                f"No backend URL configured for category '{category}'. "
                f"Set {category.upper()}_BACKEND_URL in your .env file."
            )
        return url


settings = Settings()
