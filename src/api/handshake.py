"""
Handshake client for fetching the backend's RSA public key.

This client uses a plain httpx client, NOT the BaseClient, to avoid a
circular dependency during the crypto bootstrap process.
"""

import httpx
from async_lru import alru_cache

from utils.errors import HandshakeError
from utils.logging import logger

# Default cache TTL for the public key (e.g., 1 hour)
DEFAULT_CACHE_TTL_SECONDS = 3600


async def _log_request(request: httpx.Request) -> None:
    logger.debug(
        "http_request", method=request.method, url=str(request.url), headers=dict(request.headers)
    )


async def _log_response(response: httpx.Response) -> None:
    await response.aread()
    logger.debug("http_response", status_code=response.status_code, content=response.text)


class HandshakeClient:
    """
    Handles the initial handshake to retrieve the RSA public key for creating
    the X-API-Encryption-Key header.
    """

    def __init__(
        self,
        url: str,
        client_authorization_header: str = "authorization",
        client_id_header: str = "x-api-client-id",
    ):
        self.url = url
        self.client_id_header = client_id_header
        self.client_authorization_header = client_authorization_header
        self._http_client = httpx.AsyncClient(
            event_hooks={"request": [_log_request], "response": [_log_response]}
        )

    @alru_cache(maxsize=1, ttl=DEFAULT_CACHE_TTL_SECONDS)
    async def get_public_key(self, client_id: str, authorization: str) -> str:
        """
        Fetches the RSA public key from the backend.

        The result is cached in memory to avoid repeated calls. The cache
        is cleared on a TTL or can be cleared manually if a 401/1200 error
        from the gateway suggests a key rotation.
        """
        headers = {
            self.client_id_header: client_id,
            self.client_authorization_header: authorization,
        }
        log_params = {"url": self.url, "client_id": client_id}
        logger.info("handshake_start", **log_params)

        try:
            response = await self._http_client.post(self.url, headers=headers)
            response.raise_for_status()

            data = response.json()

            # The Go backend wraps responses; we expect data.publicKey
            public_key = data.get("data", {}).get("publicKey")

            if not public_key or not isinstance(public_key, str):
                raise HandshakeError("Public key not found or invalid in backend response.")

            logger.info("handshake_success", **log_params)
            return public_key

        except HandshakeError:
            # Re-raise specific handshake errors to be caught correctly by tests
            raise
        except httpx.HTTPStatusError as e:
            logger.error(
                "handshake_http_error",
                status_code=e.response.status_code,
                response=e.response.text,
                **log_params,
            )
            raise HandshakeError(f"Handshake failed with status {e.response.status_code}.") from e
        except (TimeoutError, httpx.RequestError) as e:
            logger.error("handshake_connection_error", error=str(e), **log_params)
            raise HandshakeError("Could not connect to the backend for handshake.") from e
        except Exception as e:
            logger.exception("handshake_unexpected_error", error=str(e), **log_params)
            raise HandshakeError("An unexpected error occurred during handshake.") from e
