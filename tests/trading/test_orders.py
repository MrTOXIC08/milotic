"""Tests for trading order tools."""

import uuid
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

from api.base import BaseClient
from components.trading.orders import (
    trading_cancel_order,
    trading_get_order,
    trading_place_order,
)
from utils.errors import BackendConnectionError, RateLimitError


def make_ctx() -> AsyncMock:
    """Build an AsyncMock ctx whose get_state resolves auth_token/sub_account_id."""
    ctx = AsyncMock()

    async def get_state(key: str):
        return {"auth_token": "tok123", "sub_account_id": "sub456"}.get(key)

    ctx.get_state.side_effect = get_state
    return ctx


# ---------------------------------------------------------------------------
# Low-level BaseClient sanity checks (kept from original suite)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trading_place_order_success(mock_env):
    with respx.mock(base_url="http://trading.test") as router:
        router.post("/orders").mock(
            return_value=httpx.Response(200, json={"order_id": "abc123", "status": "pending"})
        )
        client = await BaseClient.instance("trading")
        result = await client.post(
            "/orders",
            json={"symbol": "AAPL", "side": "buy", "quantity": 10, "order_type": "market"},
        )
        assert result["order_id"] == "abc123"


@pytest.mark.asyncio
async def test_trading_rate_limit_raises(mock_env):
    with respx.mock(base_url="http://trading.test") as router:
        router.post("/orders").mock(return_value=httpx.Response(429))
        client = await BaseClient.instance("trading")
        with pytest.raises(RateLimitError):
            await client.post("/orders", json={})


# ---------------------------------------------------------------------------
# trading_place_order — validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trading_place_order_invalid_side(mock_env):
    with patch("api.base.BaseClient.instance", new_callable=AsyncMock) as mock_instance:
        ctx = make_ctx()
        result = await trading_place_order(
            ctx, symbol="AAPL", side="hold", quantity=10, order_type="market"
        )
    assert "error" in result
    mock_instance.assert_not_awaited()


@pytest.mark.asyncio
async def test_trading_place_order_invalid_order_type(mock_env):
    with patch("api.base.BaseClient.instance", new_callable=AsyncMock) as mock_instance:
        ctx = make_ctx()
        result = await trading_place_order(
            ctx, symbol="AAPL", side="buy", quantity=10, order_type="bogus"
        )
    assert "error" in result
    mock_instance.assert_not_awaited()


@pytest.mark.asyncio
async def test_trading_place_order_invalid_quantity(mock_env):
    with patch("api.base.BaseClient.instance", new_callable=AsyncMock) as mock_instance:
        ctx = make_ctx()
        result = await trading_place_order(
            ctx, symbol="AAPL", side="buy", quantity=0, order_type="market"
        )
    assert "error" in result
    mock_instance.assert_not_awaited()


@pytest.mark.asyncio
async def test_trading_place_order_negative_quantity(mock_env):
    with patch("api.base.BaseClient.instance", new_callable=AsyncMock) as mock_instance:
        ctx = make_ctx()
        result = await trading_place_order(
            ctx, symbol="AAPL", side="buy", quantity=-5, order_type="market"
        )
    assert "error" in result
    mock_instance.assert_not_awaited()


@pytest.mark.asyncio
async def test_trading_place_order_missing_price_for_limit(mock_env):
    with patch("api.base.BaseClient.instance", new_callable=AsyncMock) as mock_instance:
        ctx = make_ctx()
        result = await trading_place_order(
            ctx, symbol="AAPL", side="buy", quantity=10, order_type="limit"
        )
    assert "error" in result
    mock_instance.assert_not_awaited()


@pytest.mark.asyncio
async def test_trading_place_order_missing_price_for_stop_limit(mock_env):
    with patch("api.base.BaseClient.instance", new_callable=AsyncMock) as mock_instance:
        ctx = make_ctx()
        result = await trading_place_order(
            ctx, symbol="AAPL", side="sell", quantity=10, order_type="stop_limit"
        )
    assert "error" in result
    mock_instance.assert_not_awaited()


# ---------------------------------------------------------------------------
# trading_place_order — preview (confirmed=False)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trading_place_order_preview_does_not_call_backend(mock_env):
    with patch("api.base.BaseClient.instance", new_callable=AsyncMock) as mock_instance:
        ctx = make_ctx()
        result = await trading_place_order(
            ctx,
            symbol="aapl",
            side="buy",
            quantity=10,
            order_type="market",
            confirmed=False,
        )

    assert result["preview"] is True
    assert result["symbol"] == "AAPL"
    assert result["side"] == "buy"
    assert result["order_type"] == "market"
    mock_instance.assert_not_awaited()


# ---------------------------------------------------------------------------
# trading_place_order — confirmed=True
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("api.base.BaseClient.post", new_callable=AsyncMock)
async def test_trading_place_order_confirmed_calls_backend_with_reference_id(
    mock_post: AsyncMock, mock_env
):
    mock_post.return_value = {"order_id": "abc123", "status": "pending"}
    ctx = make_ctx()

    result = await trading_place_order(
        ctx,
        symbol="AAPL",
        side="buy",
        quantity=10,
        order_type="market",
        confirmed=True,
    )

    assert result["order_id"] == "abc123"
    mock_post.assert_awaited_once()
    _, kwargs = mock_post.call_args
    payload = kwargs["json"]
    assert "reference_id" in payload
    # must be a valid UUID
    uuid.UUID(payload["reference_id"])
    assert kwargs["headers"]["x-authToken"] == "tok123"


@pytest.mark.asyncio
@patch("api.base.BaseClient.post", new_callable=AsyncMock)
async def test_trading_place_order_confirmed_timeout_returns_unknown(
    mock_post: AsyncMock, mock_env
):
    mock_post.side_effect = BackendConnectionError("timed out")
    ctx = make_ctx()

    result = await trading_place_order(
        ctx,
        symbol="AAPL",
        side="buy",
        quantity=10,
        order_type="market",
        confirmed=True,
    )

    assert result["status"] == "unknown"
    assert "reference_id" in result
    uuid.UUID(result["reference_id"])
    mock_post.assert_awaited_once()  # never retried


# ---------------------------------------------------------------------------
# trading_cancel_order / trading_get_order
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("api.base.BaseClient.delete", new_callable=AsyncMock)
async def test_trading_cancel_order_uses_session_headers(mock_delete: AsyncMock, mock_env):
    mock_delete.return_value = {"status": "cancelled"}
    ctx = make_ctx()

    result = await trading_cancel_order(ctx, order_id="order-1")

    assert result == {"status": "cancelled"}
    mock_delete.assert_awaited_once()
    args, kwargs = mock_delete.call_args
    assert args[0] == "/orders/order-1"
    assert kwargs["headers"]["x-authToken"] == "tok123"


@pytest.mark.asyncio
@patch("api.base.BaseClient.get", new_callable=AsyncMock)
async def test_trading_get_order_uses_session_headers(mock_get: AsyncMock, mock_env):
    mock_get.return_value = {"order_id": "order-1", "status": "open"}
    ctx = make_ctx()

    result = await trading_get_order(ctx, order_id="order-1")

    assert result["status"] == "open"
    mock_get.assert_awaited_once()
    args, kwargs = mock_get.call_args
    assert args[0] == "/orders/order-1"
    assert kwargs["headers"]["x-authToken"] == "tok123"


@pytest.mark.asyncio
async def test_trading_get_order_not_connected_returns_error(mock_env):
    ctx = AsyncMock()
    ctx.get_state.return_value = None

    with patch("api.base.BaseClient.instance", new_callable=AsyncMock) as mock_instance:
        result = await trading_get_order(ctx, order_id="order-1")

    assert "error" in result
    mock_instance.assert_not_awaited()
