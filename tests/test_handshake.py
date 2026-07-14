from collections.abc import Generator

import pytest
import pytest_asyncio
import respx
from httpx import Response

from api.handshake import HandshakeClient
from utils.errors import HandshakeError

# Sample from be-middlewares/libs/apicrypto/handshake_test.go
# This is a placeholder; a real key would be much longer.
SAMPLE_PUBLIC_KEY = "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA..."
SAMPLE_CLIENT_ID = "test-client-id-123"
SAMPLE_AUTH = "test-auth-key"
HANDSHAKE_URL = "https://api.test.backend/handshake"


@pytest_asyncio.fixture
def mock_handshake() -> Generator[respx.MockRouter, None, None]:
    with respx.mock() as mock:
        yield mock


@pytest.fixture
def handshake_client() -> HandshakeClient:
    return HandshakeClient(url=HANDSHAKE_URL)


@pytest.mark.asyncio
async def test_get_public_key_success(
    mock_handshake: respx.MockRouter, handshake_client: HandshakeClient
):
    """Test successful public key retrieval."""
    mock_handshake.post(HANDSHAKE_URL).mock(
        return_value=Response(
            200, json={"statusCode": 200, "data": {"publicKey": SAMPLE_PUBLIC_KEY}}
        )
    )

    public_key = await handshake_client.get_public_key(SAMPLE_CLIENT_ID, SAMPLE_AUTH)
    assert public_key == SAMPLE_PUBLIC_KEY

    # Verify caching
    public_key_cached = await handshake_client.get_public_key(SAMPLE_CLIENT_ID, SAMPLE_AUTH)
    assert public_key_cached == SAMPLE_PUBLIC_KEY
    assert len(mock_handshake.calls) == 1


@pytest.mark.asyncio
async def test_get_public_key_http_error(
    mock_handshake: respx.MockRouter, handshake_client: HandshakeClient
):
    """Test that HTTP 5xx errors raise HandshakeError."""
    mock_handshake.post(HANDSHAKE_URL).mock(return_value=Response(503))

    with pytest.raises(HandshakeError, match="Handshake failed with status 503"):
        await handshake_client.get_public_key(SAMPLE_CLIENT_ID, SAMPLE_AUTH)


@pytest.mark.asyncio
async def test_get_public_key_missing_key(
    mock_handshake: respx.MockRouter, handshake_client: HandshakeClient
):
    """Test response missing the `data.publicKey` field raises HandshakeError."""
    mock_handshake.post(HANDSHAKE_URL).mock(
        return_value=Response(200, json={"statusCode": 200, "data": {}})
    )

    with pytest.raises(HandshakeError, match="Public key not found or invalid"):
        await handshake_client.get_public_key(SAMPLE_CLIENT_ID, SAMPLE_AUTH)


@pytest.mark.asyncio
async def test_get_public_key_malformed_response(
    mock_handshake: respx.MockRouter, handshake_client: HandshakeClient
):
    """Test non-JSON or malformed response raises HandshakeError."""
    mock_handshake.post(HANDSHAKE_URL).mock(return_value=Response(200, text="not-json"))

    with pytest.raises(HandshakeError, match="An unexpected error occurred"):
        await handshake_client.get_public_key(SAMPLE_CLIENT_ID, SAMPLE_AUTH)


@pytest.mark.asyncio
async def test_get_public_key_caching_clears(
    mock_handshake: respx.MockRouter, handshake_client: HandshakeClient
):
    """Verify the LRU cache can be cleared to re-fetch a key."""
    route = mock_handshake.post(HANDSHAKE_URL)
    route.mock(
        return_value=Response(200, json={"statusCode": 200, "data": {"publicKey": "KEY_V1"}})
    )

    # First call, should cache
    key1 = await handshake_client.get_public_key(SAMPLE_CLIENT_ID, SAMPLE_AUTH)
    assert key1 == "KEY_V1"
    assert len(mock_handshake.calls) == 1

    # Second call, should be cached
    key2 = await handshake_client.get_public_key(SAMPLE_CLIENT_ID, SAMPLE_AUTH)
    assert key2 == "KEY_V1"
    assert len(mock_handshake.calls) == 1

    # Clear cache and re-route for V2
    handshake_client.get_public_key.cache_clear()
    route.mock(
        return_value=Response(200, json={"statusCode": 200, "data": {"publicKey": "KEY_V2"}})
    )

    # Third call, should re-fetch
    key3 = await handshake_client.get_public_key(SAMPLE_CLIENT_ID, SAMPLE_AUTH)
    assert key3 == "KEY_V2"
    assert len(mock_handshake.calls) == 2
