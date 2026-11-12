"""
Core HTTP client for all Go backend communications.

Implements the "Vortex" pattern for transparent encryption/decryption,
plus a per-category ClientRegistry with rate limiting and a circuit breaker.
"""

import asyncio
from typing import Any

import httpx

import config as _config
from api.handshake import HandshakeClient
from api.session import SessionKeyProvider
from utils.crypto import MiloticCipher
from utils.errors import (
    BackendConnectionError,
    CircuitBreakerOpenError,
    DecryptionError,
    HandshakeError,
    RateLimitError,
)
from utils.logging import logger
from utils.ssl_context import get_ssl_context

# Registry of one BaseClient instance per service category.
_instances: dict[str, "BaseClient"] = {}
_registry_lock = asyncio.Lock()


async def _log_request(request: httpx.Request) -> None:
    # ponytail: log request details at debug level
    logger.debug(
        "http_request", method=request.method, url=str(request.url), headers=dict(request.headers)
    )


async def _log_response(response: httpx.Response) -> None:
    # ponytail: load response content and log details
    await response.aread()
    logger.debug("http_response", status_code=response.status_code, content=response.text)


class BaseClient:
    """
    Per-category HTTP client that manages crypto bootstrap and transparently
    encrypts/decrypts JSON payloads. Use BaseClient.instance(category) to get
    or lazily create the client for a given service.
    """

    def __init__(self) -> None:
        raise RuntimeError("Call BaseClient.instance(category) instead.")

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    async def instance(cls, category: str) -> "BaseClient":
        """Return the singleton BaseClient for *category*, creating it if needed."""
        if category in _instances:
            return _instances[category]

        async with _registry_lock:
            if category in _instances:
                return _instances[category]

            new = cls.__new__(cls)
            new._category = category
            new._base_url = _config.settings.backend_url(category)
            new._http_client = httpx.AsyncClient(
                base_url=new._base_url,
                verify=get_ssl_context(),
                event_hooks={"request": [_log_request], "response": [_log_response]},
            )
            new._semaphore = asyncio.Semaphore(_config.settings.MAX_CONCURRENT_REQUESTS)
            new._consecutive_failures = 0
            new._circuit_open = False
            new._session_key_provider: SessionKeyProvider | None = None
            new._cipher: MiloticCipher | None = None
            new._encrypted_session_header: str | None = None
            new._handshake_client = HandshakeClient(
                url=_config.settings.HANDSHAKE_URL,
                client_authorization_header=_config.settings.CONST_AUTHORIZATION_HEADER_KEY,
                client_id_header=_config.settings.CONST_CLIENT_ID_HEADER_KEY,
            )

            if _config.settings.CRYPTO_ENABLED:
                await new._bootstrap_crypto()

            _instances[category] = new
            return new

    @classmethod
    def reset(cls, category: str | None = None) -> None:
        """Remove one or all cached instances (primarily for testing)."""
        if category:
            _instances.pop(category, None)
        else:
            _instances.clear()

    # ------------------------------------------------------------------
    # Crypto bootstrap
    # ------------------------------------------------------------------

    async def _bootstrap_crypto(self) -> None:
        logger.info("crypto_bootstrap_start", category=self._category)
        public_key = await self._handshake_client.get_public_key(
            _config.settings.API_CLIENT_ID,
            _config.settings.AUTHORIZATION,
        )
        self._session_key_provider = SessionKeyProvider(public_key)
        self._encrypted_session_header = self._session_key_provider.encrypt_session_for_header(
            _config.settings.API_SESSION_SECRET
        )
        self._cipher = MiloticCipher(_config.settings.API_SESSION_SECRET)
        logger.info("crypto_bootstrap_success", category=self._category)

    async def _refresh_crypto(self) -> None:
        """Clear the handshake cache and re-bootstrap (called on 401)."""
        logger.warning("crypto_refresh_triggered", category=self._category)
        self._handshake_client.get_public_key.cache_clear()
        await self._bootstrap_crypto()

    # ------------------------------------------------------------------
    # Circuit breaker helpers
    # ------------------------------------------------------------------

    def _record_success(self) -> None:
        self._consecutive_failures = 0
        self._circuit_open = False

    def _record_failure(self) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures >= _config.settings.CIRCUIT_BREAKER_THRESHOLD:
            if not self._circuit_open:
                logger.error(
                    "circuit_breaker_opened",
                    category=self._category,
                    failures=self._consecutive_failures,
                )
            self._circuit_open = True

    # ------------------------------------------------------------------
    # Core request
    # ------------------------------------------------------------------

    async def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        """
        Make an HTTP request to the category backend with optional transparent
        AES encryption. Enforces the circuit breaker and rate-limiting semaphore.
        """
        if self._circuit_open:
            raise CircuitBreakerOpenError(
                f"Circuit breaker open for '{self._category}'. "
                f"After {self._consecutive_failures} consecutive failures."
            )

        async with self._semaphore:
            return await self._do_request(method, path, **kwargs)

    async def _do_request(
        self, method: str, path: str, _retry_on_401: bool = True, **kwargs: Any
    ) -> dict[str, Any]:
        headers: dict[str, str] = kwargs.pop("headers", {})
        json_payload = kwargs.pop("json", None)

        if _config.settings.CRYPTO_ENABLED:
            if not self._cipher or not self._encrypted_session_header:
                raise BackendConnectionError(
                    "Crypto components not initialised. Bootstrap may have failed."
                )
            headers[_config.settings.CONST_CLIENT_ID_HEADER_KEY] = _config.settings.API_CLIENT_ID
            headers[_config.settings.CONST_AUTHORIZATION_HEADER_KEY] = (
                _config.settings.AUTHORIZATION
            )
            headers["X-API-Encryption-Key"] = self._encrypted_session_header
            if json_payload is not None:
                kwargs["json"] = self._cipher.encrypt_json(json_payload)
        elif json_payload is not None:
            kwargs["json"] = json_payload

        try:
            response = await self._http_client.request(method, path, headers=headers, **kwargs)

            # Handle key rotation: refresh and retry once
            if response.status_code == 401 and _retry_on_401 and _config.settings.CRYPTO_ENABLED:
                logger.warning("auth_401_refreshing_key", category=self._category, path=path)
                await self._refresh_crypto()
                return await self._do_request(method, path, _retry_on_401=False, **kwargs)

            if response.status_code == 429:
                self._record_failure()
                raise RateLimitError()

            response.raise_for_status()

            self._record_success()

            if not response.content:
                return {}

            response_data = response.json()

            if _config.settings.CRYPTO_ENABLED and response_data:
                return self._cipher.decrypt_json(response_data)

            return response_data

        except (RateLimitError, DecryptionError, HandshakeError, CircuitBreakerOpenError):
            raise
        except httpx.HTTPStatusError as e:
            self._record_failure()
            raise BackendConnectionError(
                f"Request to '{self._category}' failed with status {e.response.status_code}."
            ) from e
        except Exception as e:
            self._record_failure()
            raise BackendConnectionError(
                f"Unexpected error communicating with '{self._category}' backend."
            ) from e

    # ------------------------------------------------------------------
    # Convenience methods
    # ------------------------------------------------------------------

    async def get(self, path: str, **kwargs: Any) -> dict[str, Any]:
        return await self.request("GET", path, **kwargs)

    async def post(self, path: str, **kwargs: Any) -> dict[str, Any]:
        return await self.request("POST", path, **kwargs)

    async def put(self, path: str, **kwargs: Any) -> dict[str, Any]:
        return await self.request("PUT", path, **kwargs)

    async def delete(self, path: str, **kwargs: Any) -> dict[str, Any]:
        return await self.request("DELETE", path, **kwargs)
