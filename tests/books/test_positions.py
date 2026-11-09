"""Tests for positions tools."""

from unittest.mock import AsyncMock

import httpx
import pytest
import respx

from components.books.positions import books_get_positions, trading_convert_position
from utils.constants import SECURITY_INFO_PROJECTION_POSITIONS


def make_ctx() -> AsyncMock:
    ctx = AsyncMock()

    async def get_state(key: str):
        return {"auth_token": "tok123", "sub_account_id": "sub456"}.get(key)

    ctx.get_state.side_effect = get_state
    return ctx


@pytest.mark.asyncio
async def test_books_get_positions(mock_env):
    ctx = make_ctx()
    with respx.mock(base_url="http://investor.test") as router:
        route = router.post("/trading/portfolio/get-positions").mock(
            return_value=httpx.Response(
                200, json={"status": "OK", "data": [{"symbol": "INFY", "netQty": 10}]}
            )
        )
        # Default position_type="all" fetches both daily and expiry concurrently
        res = await books_get_positions(ctx, segment="EQ")
        assert res["status"] == "OK"
        assert res["data"]["daily"][0]["symbol"] == "INFY"
        assert res["data"]["expiry"][0]["symbol"] == "INFY"
        assert res["summary"]["dailyCount"] == 1
        assert res["summary"]["expiryCount"] == 1

        # Verify request headers on route call
        last_request = route.calls.last.request
        assert (
            last_request.headers.get("x-securityinfoprojection")
            == SECURITY_INFO_PROJECTION_POSITIONS
        )

        import json

        # Verify targeted daily query
        await books_get_positions(ctx, segment="EQ", position_type="daily")
        body_daily = json.loads(route.calls.last.request.content)
        assert body_daily == {"interop": True, "segment": "EQ", "type": "daily"}

        # Verify targeted expiry query
        await books_get_positions(ctx, segment="EQ", position_type="expiry")
        body_expiry = json.loads(route.calls.last.request.content)
        assert body_expiry == {"interop": True, "segment": "EQ", "type": "expiry"}

        # Verify COMM overrides
        await books_get_positions(ctx, segment="COMM", position_type="expiry")
        body_comm = json.loads(route.calls.last.request.content)
        assert body_comm == {"interop": False, "segment": "COMM", "type": "expiry"}


@pytest.mark.asyncio
async def test_trading_convert_position_preview(mock_env):
    ctx = make_ctx()
    res = await trading_convert_position(
        ctx,
        symbol="RELIANCE",
        quantity=5,
        from_product="MIS",
        to_product="MTF",
        confirmed=False,
    )
    assert res.get("preview") is True
    assert res["symbol"] == "RELIANCE"
    assert res["from_product"] == "MIS"
    assert res["to_product"] == "MTF"


@pytest.mark.asyncio
async def test_trading_convert_position_execute(mock_env):
    ctx = make_ctx()
    with respx.mock(base_url="http://investor.test") as router:
        router.post("/trading/orders/convert-position").mock(
            return_value=httpx.Response(200, json={"status": "OK", "message": "Converted"})
        )
        res = await trading_convert_position(
            ctx,
            symbol="RELIANCE",
            quantity=5,
            from_product="MIS",
            to_product="MTF",
            confirmed=True,
        )
        assert res["status"] == "OK"
