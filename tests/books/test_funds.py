"""Tests for funds and margin tools."""

from unittest.mock import AsyncMock

import httpx
import pytest
import respx

from components.books.funds import books_get_funds, trading_calculate_margin


def make_ctx() -> AsyncMock:
    ctx = AsyncMock()

    async def get_state(key: str):
        return {"auth_token": "tok123", "sub_account_id": "sub456"}.get(key)

    ctx.get_state.side_effect = get_state
    return ctx


@pytest.mark.asyncio
async def test_books_get_funds(mock_env):
    ctx = make_ctx()
    with respx.mock(base_url="http://investor.test") as router:
        router.get("/trading/v2/funds").mock(
            return_value=httpx.Response(
                200, json={"status": "OK", "data": {"availableCash": 100000.0}}
            )
        )
        res = await books_get_funds(ctx, segment="EQ")
        assert res["status"] == "OK"
        assert res["data"]["availableCash"] == 100000.0


@pytest.mark.asyncio
async def test_trading_calculate_margin(mock_env):
    ctx = make_ctx()
    with respx.mock(base_url="http://investor.test") as router:
        router.post("/trading/orders/margin-calculator").mock(
            return_value=httpx.Response(
                200, json={"status": "OK", "data": {"requiredMargin": 2500.0}}
            )
        )
        res = await trading_calculate_margin(
            ctx,
            symbol="INFY",
            quantity=10,
            side="buy",
            product_type="MTF",
            order_type="limit",
            price=1500.0,
        )
        assert res["status"] == "OK"
        assert res["data"]["requiredMargin"] == 2500.0
