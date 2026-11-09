"""Tests for market data tools and Axis Direct search/get-all integration."""

from unittest.mock import AsyncMock

import httpx
import pytest
import respx

from components.market.ohlcv import market_get_ohlcv
from components.market.orderbook import market_get_depth
from components.market.quotes import market_get_ltp, market_get_quotes
from components.market.search import (
    market_search_instruments,
    search_security_id,
)


def make_ctx() -> AsyncMock:
    ctx = AsyncMock()

    async def get_state(key: str):
        return {"auth_token": "tok123", "sub_account_id": "sub456"}.get(key)

    ctx.get_state.side_effect = get_state
    return ctx


@pytest.mark.asyncio
async def test_market_search_instruments(mock_env):
    ctx = make_ctx()
    with respx.mock(base_url="http://investor.test") as router:
        router.get("/search/get-all").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "symbol": "INFY",
                            "name": "INFOSYS LIMITED",
                            "isin": "INE009A01021",
                            "securityInfo": [
                                {"exchange": "NSE", "scriptId": "221594", "segment": "EQ"}
                            ],
                            "ltp": 1600.0,
                        }
                    ]
                },
            )
        )
        res = await market_search_instruments(ctx, query="INFY")
        assert res["count"] >= 1
        matches = [r for r in res["results"] if r.get("symbol") == "INFY"]
        assert len(matches) > 0
        assert matches[0]["scriptId"] == "221594"


@pytest.mark.asyncio
async def test_market_search_instruments_nested_axis_payload(mock_env):
    ctx = make_ctx()
    with respx.mock(base_url="http://investor.test") as router:
        router.get("/search/get-all").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "entries": [
                            {
                                "symbol": "TATAMOTORS",
                                "name": "TATA MOTORS LIMITED",
                                "isin": "INE155A01022",
                                "securityInfo": [
                                    {"exchange": "NSE", "scriptId": "223456", "segment": "EQ"},
                                    {"exchange": "BSE", "scriptId": "11500570", "segment": "EQ"},
                                ],
                                "ltp": 980.5,
                            },
                            {
                                "symbol": "TATACHEM",
                                "name": "TATA CHEMICALS LIMITED",
                                "isin": "INE092A01019",
                                "securityInfo": [
                                    {"exchange": "NSE", "scriptId": "223457", "segment": "EQ"},
                                ],
                                "ltp": 1100.0,
                            },
                        ]
                    }
                },
            )
        )
        res = await market_search_instruments(ctx, query="TATA", exchange="BSE")
        matches = [r for r in res["results"] if r["symbol"] in ("TATAMOTORS", "TATACHEM")]
        assert len(matches) == 2
        tata_motors = next(r for r in res["results"] if r["symbol"] == "TATAMOTORS")
        assert tata_motors["scriptId"] == "11500570"
        assert tata_motors["exchange"] == "BSE"
        assert tata_motors["ltp"] == 980.5


@pytest.mark.asyncio
async def test_market_search_instruments_exchange_details_and_fallback(mock_env):
    ctx = make_ctx()
    with respx.mock(base_url="http://investor.test") as router:
        router.get("/search/get-all").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {
                        "tradingSymbol": "WIPRO",
                        "companyName": "WIPRO LTD",
                        "isin": "INE075A01022",
                        "exchangeDetails": [
                            {"exchange": "NSE", "scriptId": "221760", "ltp": 480.0},
                        ],
                    }
                ],
            )
        )
        res = await market_search_instruments(ctx, query="WIPRO")
        assert res["count"] == 1
        assert res["results"][0]["symbol"] == "WIPRO"
        assert res["results"][0]["scriptId"] == "221760"
        assert res["results"][0]["ltp"] == 480.0


@pytest.mark.asyncio
async def test_search_security_id_helper(mock_env):
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
        sid = await search_security_id(ctx, query="TATAMOTORS", exchange="NSE")
        assert sid == "223456"

        # When not found, returns None gracefully
        sid_missing = await search_security_id(ctx, query="NONEXISTENT", exchange="NSE")
        assert sid_missing is None


@pytest.mark.asyncio
async def test_market_get_quotes(mock_env):
    ctx = make_ctx()
    with respx.mock(base_url="http://investor.test") as router:
        router.post("/market/quotes").mock(
            return_value=httpx.Response(
                200, json={"status": "OK", "data": [{"symbol": "TCS", "ltp": 3850.5}]}
            )
        )
        res = await market_get_quotes(ctx, symbols=["TCS"])
        assert res["status"] == "OK"
        assert res["data"][0]["ltp"] == 3850.5


@pytest.mark.asyncio
async def test_market_get_ltp(mock_env):
    ctx = make_ctx()
    with respx.mock(base_url="http://investor.test") as router:
        router.get("/market/ltp/RELIANCE").mock(
            return_value=httpx.Response(
                200, json={"status": "OK", "symbol": "RELIANCE", "ltp": 2950.0}
            )
        )
        res = await market_get_ltp(ctx, symbol="RELIANCE")
        assert res["ltp"] == 2950.0


@pytest.mark.asyncio
async def test_market_get_ohlcv(mock_env):
    ctx = make_ctx()
    with respx.mock(base_url="http://investor.test") as router:
        router.get("/market/ohlcv/INFY").mock(
            return_value=httpx.Response(
                200, json={"status": "OK", "candles": [{"time": 1700000000, "close": 1500.0}]}
            )
        )
        res = await market_get_ohlcv(ctx, symbol="INFY", interval="1d", limit=10)
        assert res["status"] == "OK"
        assert len(res["candles"]) == 1


@pytest.mark.asyncio
async def test_market_get_depth(mock_env):
    ctx = make_ctx()
    with respx.mock(base_url="http://investor.test") as router:
        router.post("/feedbroadcast/best-five").mock(
            return_value=httpx.Response(
                200,
                json={
                    "status": "OK",
                    "data": {
                        "buy": [{"price": 750.0, "quantity": 100, "noOfOrders": 5}],
                        "sell": [],
                        "ltp": 750.0,
                    },
                },
            )
        )
        res = await market_get_depth(ctx, symbol="SBIN", depth=5)
        assert res["status"] == "OK"
        assert res["bids"][0]["price"] == 750.0
