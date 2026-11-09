"""Tests for market best-five order book and depth tools."""

from unittest.mock import AsyncMock

import httpx
import pytest
import respx

from components.market.orderbook import market_get_best_five, market_get_depth


def make_ctx() -> AsyncMock:
    ctx = AsyncMock()

    async def get_state(key: str):
        return {"auth_token": "tok123", "sub_account_id": "4433009"}.get(key)

    ctx.get_state.side_effect = get_state
    return ctx


SAMPLE_BEST_FIVE_PAYLOAD = {
    "statusCode": 200,
    "message": "Success",
    "data": {
        "buy": [
            {"price": 7.15, "quantity": "25000", "noOfOrders": "12"},
            {"price": 7.10, "quantity": "50000", "noOfOrders": "20"},
            {"price": 7.05, "quantity": "100000", "noOfOrders": "35"},
            {"price": 7.00, "quantity": "75000", "noOfOrders": "18"},
            {"price": 6.95, "quantity": "60000", "noOfOrders": "10"},
        ],
        "sell": [
            {"price": 7.20, "quantity": "30000", "noOfOrders": "15"},
            {"price": 7.25, "quantity": "45000", "noOfOrders": "22"},
            {"price": 7.30, "quantity": "80000", "noOfOrders": "28"},
            {"price": 7.35, "quantity": "40000", "noOfOrders": "14"},
            {"price": 7.40, "quantity": "90000", "noOfOrders": "30"},
        ],
        "ltp": 7.15,
        "lastTradeQuantity": 500,
        "lastTradeTime": "09-Nov-2026 14:15:00",
        "lastUpdateTime": "09-Nov-2026 14:15:30",
        "openInterest": 0,
        "netChangeFromPrevClose": 0.05,
        "closePrice": 7.10,
        "openPrice": 7.10,
        "highPrice": 7.25,
        "lowPrice": 7.05,
        "volume": 154200000,
        "averageTradedPrice": 7.14,
        "totalBuyQty": 310000,
        "totalSellQty": 285000,
        "lifeTimeHigh": 16.80,
        "lifeTimeLow": 5.70,
    },
}


@pytest.mark.asyncio
async def test_market_get_best_five_by_script_id(mock_env):
    ctx = make_ctx()
    with respx.mock(base_url="http://investor.test") as router:
        router.post("/feedbroadcast/best-five").mock(
            return_value=httpx.Response(200, json=SAMPLE_BEST_FIVE_PAYLOAD)
        )
        res = await market_get_best_five(ctx, script_id="2214366")
        assert res["status"] == "OK"
        assert res["scriptId"] == "2214366"
        assert res["ltp"] == 7.15
        assert len(res["bids"]) == 5
        assert len(res["asks"]) == 5
        assert res["bids"][0]["price"] == 7.15
        assert res["bids"][0]["quantity"] == 25000
        assert res["bids"][0]["orders"] == 12
        assert res["asks"][0]["price"] == 7.20
        assert res["totalBuyQty"] == 310000
        assert res["totalSellQty"] == 285000
        assert res["averageTradedPrice"] == 7.14
        assert res["open"] == 7.10
        assert res["high"] == 7.25
        assert res["low"] == 7.05
        assert res["close"] == 7.10


@pytest.mark.asyncio
async def test_market_get_best_five_by_symbol_known(mock_env):
    ctx = make_ctx()
    with respx.mock(base_url="http://investor.test") as router:
        route = router.post("/feedbroadcast/best-five").mock(
            return_value=httpx.Response(200, json=SAMPLE_BEST_FIVE_PAYLOAD)
        )
        res = await market_get_best_five(ctx, symbol="IDEA", exchange="NSE")
        assert res["status"] == "OK"
        assert res["symbol"] == "IDEA"
        assert res["scriptId"] == "2214366"
        assert res["exchange"] == "NSE"
        assert route.called
        import json

        assert json.loads(route.calls.last.request.content) == {"scriptId": "2214366"}


@pytest.mark.asyncio
async def test_market_get_best_five_by_symbol_search_fallback(mock_env):
    ctx = make_ctx()
    with respx.mock(base_url="http://investor.test") as router:
        router.get("/search/get-all").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "symbol": "TATAMOTORS",
                            "securityInfo": [{"exchange": "NSE", "scriptId": "223456"}],
                        }
                    ]
                },
            )
        )
        router.post("/feedbroadcast/best-five").mock(
            return_value=httpx.Response(200, json=SAMPLE_BEST_FIVE_PAYLOAD)
        )
        res = await market_get_best_five(ctx, symbol="TATAMOTORS", exchange="NSE")
        assert res["status"] == "OK"
        assert res["scriptId"] == "223456"
        assert res["symbol"] == "TATAMOTORS"


@pytest.mark.asyncio
async def test_market_get_depth_slicing(mock_env):
    ctx = make_ctx()
    with respx.mock(base_url="http://investor.test") as router:
        router.post("/feedbroadcast/best-five").mock(
            return_value=httpx.Response(200, json=SAMPLE_BEST_FIVE_PAYLOAD)
        )
        res = await market_get_depth(ctx, script_id="2214366", depth=2)
        assert res["status"] == "OK"
        assert len(res["bids"]) == 2
        assert len(res["asks"]) == 2
        assert res["bids"][0]["price"] == 7.15
        assert res["bids"][1]["price"] == 7.10


@pytest.mark.asyncio
async def test_market_get_depth_missing_args(mock_env):
    ctx = make_ctx()
    res = await market_get_depth(ctx)
    assert res["status"] == "error"
    assert "Either 'symbol' or 'script_id' must be provided" in res["message"]


@pytest.mark.asyncio
async def test_market_get_depth_unresolvable_symbol(mock_env):
    ctx = make_ctx()
    with respx.mock(base_url="http://investor.test") as router:
        router.get("/search/get-all").mock(return_value=httpx.Response(200, json={"data": []}))
        res = await market_get_depth(ctx, symbol="NONEXISTENTXYZ")
        assert res["status"] == "error"
        assert "Could not resolve numeric scriptId" in res["message"]


@pytest.mark.asyncio
async def test_market_get_best_five_backend_error(mock_env):
    ctx = make_ctx()
    with respx.mock(base_url="http://investor.test") as router:
        router.post("/feedbroadcast/best-five").mock(
            return_value=httpx.Response(502, json={"message": "entry not found in security master"})
        )
        res = await market_get_best_five(ctx, script_id="9999999999")
        assert res["status"] == "error"
        assert "Failed to fetch market depth" in res["message"]
