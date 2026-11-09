"""
Comprehensive Integration Contract Tests for all Axis Direct API endpoints.

Verifies the cryptographic request payload, headers, and decrypted response schema
for every single integration point in the gateway.
"""

import importlib
import json
import uuid
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

import config
from api.handshake import HandshakeClient
from components.books.orders import (
    trading_cancel_order,
    trading_get_order,
    trading_place_order,
)
from components.books.portfolio import books_get_portfolio
from components.market.charts import (
    market_get_commodity_chart,
    market_get_derivatives_chart,
    market_get_equity_chart,
)
from components.system.system import system_connect_start, system_connect_verify
from utils.crypto import MiloticCipher


def make_ctx(auth_token="tok123", sub_account_id="sub456") -> AsyncMock:
    """Helper to mock FastMCP Context session state."""
    ctx = AsyncMock()

    async def get_state(key: str):
        return {"auth_token": auth_token, "sub_account_id": sub_account_id, "sso_id": "sso789"}.get(
            key
        )

    ctx.get_state.side_effect = get_state
    return ctx


@pytest.fixture
def test_cipher() -> MiloticCipher:
    return MiloticCipher("a" * 32)


# ---------------------------------------------------------------------------
# 1. HANDSHAKE CONTRACT (POST /handshake)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_contract_handshake():
    """Verify handshake POST request headers and public key return schema."""
    url = "https://api.test.backend/handshake"
    contract_response = {
        "statusCode": 200,
        "status": "OK",
        "data": {"publicKey": "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA..."},
    }

    with respx.mock() as mock:
        mock.post(url).mock(return_value=httpx.Response(200, json=contract_response))

        client = HandshakeClient(url=url)
        pub_key = await client.get_public_key("client-123", "auth-456")

        assert pub_key == contract_response["data"]["publicKey"]

        # Verify headers were built exactly as required by the Axis gateway
        sent_request = mock.calls.last.request
        assert sent_request.headers["x-api-client-id"] == "client-123"
        assert sent_request.headers["authorization"] == "auth-456"


# ---------------------------------------------------------------------------
# 2. SSO INITIATE CONTRACT (POST /sso/initiate)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("api.base.SessionKeyProvider")
@patch("api.handshake.HandshakeClient.get_public_key", new_callable=AsyncMock)
async def test_contract_sso_initiate(
    mock_get_pub_key: AsyncMock, mock_provider, respx_mock, monkeypatch, test_cipher
):
    """Verify SSO initiate sends expected payload and decrypts redirectURL correctly."""
    mock_get_pub_key.return_value = "mock-pub-key"
    mock_provider.return_value.encrypt_session_for_header.return_value = "session-header"

    monkeypatch.setenv("CRYPTO_ENABLED", "true")
    monkeypatch.setenv("LOGIN_BACKEND_URL", "https://api.test.backend")
    monkeypatch.setenv("API_CLIENT_ID", "test-client")
    monkeypatch.setenv("AUTHORIZATION", "test-auth")
    monkeypatch.setenv("API_SESSION_SECRET", "a" * 32)

    importlib.reload(config)

    # Expected decrypted response contract from Axis Direct
    decrypted_response = {
        "statusCode": 200,
        "status": "OK",
        "data": {
            "redirectURL": "https://auth.uat.asldt.com/sso/validate?ssoId=sso789",
        },
    }
    encrypted_response = test_cipher.encrypt_json(decrypted_response)

    # API response wrapping
    wrapper_response = {
        "statusCode": 200,
        "status": "OK",
        "data": encrypted_response,
    }

    respx_mock.post("/sso/initiate").mock(return_value=httpx.Response(200, json=wrapper_response))

    ctx = make_ctx()
    result = await system_connect_start(ctx)

    assert result["redirect_url"] == decrypted_response["data"]["redirectURL"]

    # Verify context is not awaited (since loopback server captures dynamically)
    ctx.set_state.assert_not_awaited()


# ---------------------------------------------------------------------------
# 3. SSO AUTHENTICATE CONTRACT (POST /sso/authenticate)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("api.base.SessionKeyProvider")
@patch("api.handshake.HandshakeClient.get_public_key", new_callable=AsyncMock)
async def test_contract_sso_verify(
    mock_get_pub_key: AsyncMock, mock_provider, respx_mock, monkeypatch, test_cipher
):
    """Verify SSO verify checks sso-status and extracts final auth keys."""
    mock_get_pub_key.return_value = "mock-pub-key"
    mock_provider.return_value.encrypt_session_for_header.return_value = "session-header"

    monkeypatch.setenv("CRYPTO_ENABLED", "true")
    monkeypatch.setenv("LOGIN_BACKEND_URL", "https://api.test.backend")
    monkeypatch.setenv("API_CLIENT_ID", "test-client")
    monkeypatch.setenv("AUTHORIZATION", "test-auth")
    monkeypatch.setenv("API_SESSION_SECRET", "a" * 32)

    importlib.reload(config)

    # Expected decrypted response containing our final login session credentials
    decrypted_response = {
        "statusCode": 200,
        "status": "OK",
        "data": {
            "authToken": {
                "token": "token-xyz-999",
                "expireAt": "2024-03-21T15:50:10.940184129+05:30",
            },
            "refreshToken": {
                "token": "refresh-xyz-888",
                "expireAt": "2024-03-21T23:59:59+05:30",
            },
            "accounts": [
                {
                    "subAccountId": "sub-acc-111",
                    "isPrimary": True,
                    "name": "Aman",
                    "accountType": "RCL",
                }
            ],
        },
    }
    encrypted_response = test_cipher.encrypt_json(decrypted_response)

    wrapper_response = {
        "statusCode": 200,
        "status": "OK",
        "data": encrypted_response,
    }

    respx_mock.post("/sso/authenticate").mock(
        return_value=httpx.Response(200, json=wrapper_response)
    )

    ctx = make_ctx()
    result = await system_connect_verify(ctx, redirect_url="https://google.com?ssoId=sso789")

    assert result == {"status": "connected", "sub_account_id": "sub-acc-111"}
    ctx.set_state.assert_any_await("auth_token", "token-xyz-999")
    ctx.set_state.assert_any_await("refresh_token", "refresh-xyz-888")
    ctx.set_state.assert_any_await("sub_account_id", "sub-acc-111")


# ---------------------------------------------------------------------------
# 5. TRADING ORDER CONTRACTS (POST, DELETE, GET /orders)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("api.base.SessionKeyProvider")
@patch("api.handshake.HandshakeClient.get_public_key", new_callable=AsyncMock)
async def test_contract_place_order(
    mock_get_pub_key: AsyncMock, mock_provider, respx_mock, monkeypatch, test_cipher
):
    """Verify order placement payload formatting, encryption, and reference UUID generation."""
    mock_get_pub_key.return_value = "mock-pub-key"
    mock_provider.return_value.encrypt_session_for_header.return_value = "session-header"

    monkeypatch.setenv("CRYPTO_ENABLED", "true")
    monkeypatch.setenv("INVESTOR_BACKEND_URL", "https://api.test.backend")
    monkeypatch.setenv("API_CLIENT_ID", "test-client")
    monkeypatch.setenv("AUTHORIZATION", "test-auth")
    monkeypatch.setenv("API_SESSION_SECRET", "a" * 32)

    importlib.reload(config)

    decrypted_response = {"order_id": "ord-8888-xyz", "status": "pending"}
    encrypted_response = test_cipher.encrypt_json(decrypted_response)

    respx_mock.post("/trading/orders/place-order").mock(
        return_value=httpx.Response(200, json=encrypted_response)
    )

    ctx = make_ctx()
    result = await trading_place_order(
        ctx, symbol="BTC", side="buy", quantity=1.5, order_type="market", confirmed=True
    )

    assert result["order_id"] == "ord-8888-xyz"

    sent_request = respx_mock.calls.last.request
    payload_wrapper = json.loads(sent_request.content)
    # Verify request body was transparently encrypted inside wrapper
    assert "payload" in payload_wrapper

    decrypted_payload = test_cipher.decrypt_json(payload_wrapper)
    assert decrypted_payload["symbol"] == "BTC"
    assert decrypted_payload["side"] == "buy"
    assert decrypted_payload["quantity"] == 1.5
    assert decrypted_payload["order_type"] == "market"
    # Verify a random reference UUID was injected automatically
    assert "reference_id" in decrypted_payload
    uuid.UUID(decrypted_payload["reference_id"])


@pytest.mark.asyncio
@patch("api.base.SessionKeyProvider")
@patch("api.handshake.HandshakeClient.get_public_key", new_callable=AsyncMock)
async def test_contract_cancel_order(
    mock_get_pub_key: AsyncMock, mock_provider, respx_mock, monkeypatch, test_cipher
):
    """Verify /orders/{order_id} DELETE request routing and credentials."""
    mock_get_pub_key.return_value = "mock-pub-key"
    mock_provider.return_value.encrypt_session_for_header.return_value = "session-header"

    monkeypatch.setenv("CRYPTO_ENABLED", "true")
    monkeypatch.setenv("INVESTOR_BACKEND_URL", "https://api.test.backend")
    monkeypatch.setenv("API_CLIENT_ID", "test-client")
    monkeypatch.setenv("AUTHORIZATION", "test-auth")
    monkeypatch.setenv("API_SESSION_SECRET", "a" * 32)

    importlib.reload(config)

    decrypted_response = {"status": "cancelled"}
    encrypted_response = test_cipher.encrypt_json(decrypted_response)

    respx_mock.delete("/orders/ord-1234").mock(
        return_value=httpx.Response(200, json=encrypted_response)
    )

    ctx = make_ctx()
    result = await trading_cancel_order(ctx, order_id="ord-1234")

    assert result["status"] == "cancelled"


@pytest.mark.asyncio
@patch("api.base.SessionKeyProvider")
@patch("api.handshake.HandshakeClient.get_public_key", new_callable=AsyncMock)
async def test_contract_get_order(
    mock_get_pub_key: AsyncMock, mock_provider, respx_mock, monkeypatch, test_cipher
):
    """Verify /orders/{order_id} GET status retrieval routing and decryption."""
    mock_get_pub_key.return_value = "mock-pub-key"
    mock_provider.return_value.encrypt_session_for_header.return_value = "session-header"

    monkeypatch.setenv("CRYPTO_ENABLED", "true")
    monkeypatch.setenv("INVESTOR_BACKEND_URL", "https://api.test.backend")
    monkeypatch.setenv("API_CLIENT_ID", "test-client")
    monkeypatch.setenv("AUTHORIZATION", "test-auth")
    monkeypatch.setenv("API_SESSION_SECRET", "a" * 32)

    importlib.reload(config)

    decrypted_response = {
        "order_id": "ord-1234",
        "symbol": "BTC",
        "side": "buy",
        "quantity": 1.5,
        "status": "filled",
    }
    encrypted_response = test_cipher.encrypt_json(decrypted_response)

    respx_mock.get("/orders/ord-1234").mock(
        return_value=httpx.Response(200, json=encrypted_response)
    )

    ctx = make_ctx()
    result = await trading_get_order(ctx, order_id="ord-1234")

    assert result["order_id"] == "ord-1234"
    assert result["status"] == "filled"
    assert result["symbol"] == "BTC"


@pytest.mark.asyncio
@patch("api.base.SessionKeyProvider")
@patch("api.handshake.HandshakeClient.get_public_key", new_callable=AsyncMock)
async def test_contract_get_portfolio(
    mock_get_pub_key: AsyncMock, mock_provider, respx_mock, monkeypatch, test_cipher
):
    """Verify /v2/portfolio/multi GET portfolio holdings schema and projection header."""
    mock_get_pub_key.return_value = "mock-pub-key"
    mock_provider.return_value.encrypt_session_for_header.return_value = "session-header"

    monkeypatch.setenv("CRYPTO_ENABLED", "true")
    monkeypatch.setenv("INVESTOR_BACKEND_URL", "https://api.test.backend")
    monkeypatch.setenv("API_CLIENT_ID", "test-client")
    monkeypatch.setenv("AUTHORIZATION", "test-auth")
    monkeypatch.setenv("API_SESSION_SECRET", "a" * 32)

    importlib.reload(config)

    decrypted_response = {
        "statusCode": 200,
        "status": "OK",
        "data": [
            {
                "holdings": [
                    {
                        "name": "Clean Science",
                        "isin": "INE227W01023",
                        "quantity": "10.00",
                    }
                ],
                "holdingType": "Equity",
                "subAccountId": "sub-acc-111",
            }
        ],
    }
    encrypted_response = test_cipher.encrypt_json(decrypted_response)

    wrapper_response = {
        "statusCode": 200,
        "status": "OK",
        "data": encrypted_response,
    }

    respx_mock.get("/trading/v2/portfolio/multi").mock(
        return_value=httpx.Response(200, json=wrapper_response)
    )

    ctx = make_ctx(sub_account_id="sub-acc-111")
    result = await books_get_portfolio(ctx)

    assert result["data"][0]["subAccountId"] == "sub-acc-111"
    assert result["data"][0]["holdings"][0]["name"] == "Clean Science"

    sent_request = respx_mock.calls.last.request
    assert sent_request.headers["X-SecurityInfoProjection"] == "scriptId"
    assert sent_request.headers["x-subAccountId"] == "sub-acc-111"


# ---------------------------------------------------------------------------
# 11. CHARTS CONTRACTS (POST /charts/equity, /charts/derivatives, /charts/commodity)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("api.base.SessionKeyProvider")
@patch("api.handshake.HandshakeClient.get_public_key", new_callable=AsyncMock)
async def test_contract_charts_equity(
    mock_get_pub_key: AsyncMock, mock_provider, respx_mock, monkeypatch, test_cipher
):
    """Verify POST /charts/equity encrypted payload and decrypted candlestick response."""
    mock_get_pub_key.return_value = "mock-pub-key"
    mock_provider.return_value.encrypt_session_for_header.return_value = "session-header"

    monkeypatch.setenv("CRYPTO_ENABLED", "true")
    monkeypatch.setenv("INVESTOR_BACKEND_URL", "https://api.test.backend")
    monkeypatch.setenv("API_CLIENT_ID", "test-client")
    monkeypatch.setenv("AUTHORIZATION", "test-auth")
    monkeypatch.setenv("API_SESSION_SECRET", "a" * 32)

    importlib.reload(config)

    decrypted_response = {
        "status": "OK",
        "response": {
            "data": {
                "Stock-Detailedlist": [
                    {
                        "Companyname": "CENTRAL DEPOSITORY SERVICES (INDIA) LIMITED",
                        "DayHigh": "1520.00",
                        "DayLow": "1480.00",
                        "DayOpen": "1490.00",
                        "last_price": "1510.50",
                    }
                ]
            }
        },
    }
    encrypted_response = test_cipher.encrypt_json(decrypted_response)

    respx_mock.post("/charts/equity").mock(
        return_value=httpx.Response(200, json=encrypted_response)
    )

    ctx = make_ctx(auth_token="tok-chart", sub_account_id="4433009")
    result = await market_get_equity_chart(ctx, co_code="20139", period="W", count="1")

    assert result["status"] == "OK"
    assert "Stock-Detailedlist" in result["response"]["data"]

    sent_request = respx_mock.calls.last.request
    assert sent_request.headers["x-authToken"] == "tok-chart"
    assert sent_request.headers["x-subAccountId"] == "4433009"
    assert sent_request.headers["x-api-encryption-key"] == "session-header"

    # Verify encrypted request payload decodes to expected JSON body
    decrypted_body = test_cipher.decrypt_json(json.loads(sent_request.content))
    assert decrypted_body == {
        "exchange": "NSE",
        "coCode": "20139",
        "period": "W",
        "count": "1",
    }


@pytest.mark.asyncio
@patch("api.base.SessionKeyProvider")
@patch("api.handshake.HandshakeClient.get_public_key", new_callable=AsyncMock)
async def test_contract_charts_derivatives(
    mock_get_pub_key: AsyncMock, mock_provider, respx_mock, monkeypatch, test_cipher
):
    """Verify POST /charts/derivatives encrypted payload and options contract schema."""
    mock_get_pub_key.return_value = "mock-pub-key"
    mock_provider.return_value.encrypt_session_for_header.return_value = "session-header"

    monkeypatch.setenv("CRYPTO_ENABLED", "true")
    monkeypatch.setenv("INVESTOR_BACKEND_URL", "https://api.test.backend")
    monkeypatch.setenv("API_CLIENT_ID", "test-client")
    monkeypatch.setenv("AUTHORIZATION", "test-auth")
    monkeypatch.setenv("API_SESSION_SECRET", "a" * 32)

    importlib.reload(config)

    decrypted_response = {
        "status": "OK",
        "response": {"data": {"candle": [{"close": "295.00"}]}},
    }
    encrypted_response = test_cipher.encrypt_json(decrypted_response)

    respx_mock.post("/charts/derivatives").mock(
        return_value=httpx.Response(200, json=encrypted_response)
    )

    ctx = make_ctx(auth_token="tok-chart", sub_account_id="4433009")
    result = await market_get_derivatives_chart(
        ctx,
        symbol="BANKNIFTY",
        expiry_date="10-jan-2024",
        instrument_type="OPTIDX",
        opt_type="CE",
        strike_price="47300",
        period="D1",
        sub_account_id="ASX555",
    )

    assert result["status"] == "OK"
    sent_request = respx_mock.calls.last.request
    assert sent_request.headers["x-subAccountId"] == "ASX555"

    decrypted_body = test_cipher.decrypt_json(json.loads(sent_request.content))
    assert decrypted_body == {
        "instrumentType": "OPTIDX",
        "symbol": "BANKNIFTY",
        "expiryDate": "10-jan-2024",
        "period": "D1",
        "optType": "CE",
        "strikePrice": "47300",
    }


@pytest.mark.asyncio
@patch("api.base.SessionKeyProvider")
@patch("api.handshake.HandshakeClient.get_public_key", new_callable=AsyncMock)
async def test_contract_charts_commodity(
    mock_get_pub_key: AsyncMock, mock_provider, respx_mock, monkeypatch, test_cipher
):
    """Verify POST /charts/commodity encrypted payload and commodity contract schema."""
    mock_get_pub_key.return_value = "mock-pub-key"
    mock_provider.return_value.encrypt_session_for_header.return_value = "session-header"

    monkeypatch.setenv("CRYPTO_ENABLED", "true")
    monkeypatch.setenv("INVESTOR_BACKEND_URL", "https://api.test.backend")
    monkeypatch.setenv("API_CLIENT_ID", "test-client")
    monkeypatch.setenv("AUTHORIZATION", "test-auth")
    monkeypatch.setenv("API_SESSION_SECRET", "a" * 32)

    importlib.reload(config)

    decrypted_response = {
        "status": "OK",
        "response": {"data": [{"ltp": "62650"}]},
    }
    encrypted_response = test_cipher.encrypt_json(decrypted_response)

    respx_mock.post("/charts/commodity").mock(
        return_value=httpx.Response(200, json=encrypted_response)
    )

    ctx = make_ctx(auth_token="tok-chart", sub_account_id="4433009")
    result = await market_get_commodity_chart(
        ctx,
        symbol="gold",
        expiry_date="05-feb-2024",
        type="FUT",
        exchange="MCX",
        period="d",
        count="1",
    )

    assert result["status"] == "OK"
    sent_request = respx_mock.calls.last.request
    decrypted_body = test_cipher.decrypt_json(json.loads(sent_request.content))
    assert decrypted_body == {
        "type": "FUT",
        "exchange": "MCX",
        "symbol": "gold",
        "expiryDate": "05-feb-2024",
        "period": "d",
        "count": "1",
    }
