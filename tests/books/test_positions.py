"""Tests for positions tools."""

from unittest.mock import AsyncMock

import httpx
import pytest
import respx

from components.books.positions import books_get_positions, trading_convert_position


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
        router.post("/trading/orders/get-positions").mock(
            return_value=httpx.Response(
                200, json={"status": "OK", "data": [{"symbol": "INFY", "netQty": 10}]}
            )
        )
        res = await books_get_positions(ctx, segment="EQ")
        assert res["status"] == "OK"
        assert res["data"][0]["symbol"] == "INFY"


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
