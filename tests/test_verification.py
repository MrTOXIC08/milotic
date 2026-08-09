"""End-to-end verification of the Vortex encryption layer."""

import importlib
import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

pytestmark = pytest.mark.asyncio


@patch("api.base.SessionKeyProvider")
@patch("api.handshake.HandshakeClient.get_public_key", new_callable=AsyncMock)
async def test_base_client_full_flow(
    mock_get_public_key: AsyncMock,
    mock_session_provider: patch,
    respx_mock,
    monkeypatch,
):
    """
    End-to-end test verifying the Vortex crypto flow: bootstrap (handshake + RSA),
    encrypted request body, and decrypted response — all for one category client.
    """
    # --- mocks ---
    mock_get_public_key.return_value = "mock-public-key"
    mock_provider_instance = mock_session_provider.return_value
    mock_provider_instance.encrypt_session_for_header.return_value = "encrypted-session-header"

    # --- env ---
    monkeypatch.setenv("CRYPTO_ENABLED", "true")
    monkeypatch.setenv("INVESTOR_BACKEND_URL", "https://test.backend.api")
    monkeypatch.setenv("API_CLIENT_ID", "test-client")
    monkeypatch.setenv("AUTHORIZATION", "test-auth")
    monkeypatch.setenv("API_SESSION_SECRET", "a-very-secure-32-byte-secret-key")

    import config

    importlib.reload(config)

    from api.base import BaseClient
    from config import settings
    from utils.crypto import MiloticCipher

    # --- bootstrap ---
    client = await BaseClient.instance("investor")

    mock_get_public_key.assert_awaited_once_with("test-client", "test-auth")
    mock_session_provider.assert_called_once_with("mock-public-key")
    mock_provider_instance.encrypt_session_for_header.assert_called_once_with(
        settings.API_SESSION_SECRET
    )

    # --- request/response ---
    test_cipher = MiloticCipher(settings.API_SESSION_SECRET)
    test_path = "/v1/test-order"
    request_payload = {"symbol": "BTC", "qty": 1}
    response_payload = {"orderId": "12345", "status": "FILLED"}
    encrypted_response_wrapper = test_cipher.encrypt_json(response_payload)

    respx_mock.post(test_path).mock(
        return_value=httpx.Response(200, json=encrypted_response_wrapper)
    )

    decrypted_response = await client.post(test_path, json=request_payload)

    # --- assertions ---
    assert decrypted_response == response_payload

    sent_request = respx_mock.calls.last.request
    decrypted_sent_payload = test_cipher.decrypt_json(json.loads(sent_request.content))
    assert decrypted_sent_payload == request_payload
    assert sent_request.headers["x-api-client-id"] == "test-client"
    assert sent_request.headers["x-api-encryption-key"] == "encrypted-session-header"
