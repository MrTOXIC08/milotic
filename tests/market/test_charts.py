"""Unit tests for market chart tools (Equity, Derivatives, Commodity)."""

import json
from unittest.mock import AsyncMock

import httpx
import pytest
import respx

from components.market.charts import (
    market_get_chart,
    market_get_commodity_chart,
    market_get_derivatives_chart,
    market_get_equity_chart,
)


def make_ctx() -> AsyncMock:
    ctx = AsyncMock()

    async def get_state(key: str):
        return {"auth_token": "tok123", "sub_account_id": "4433009"}.get(key)

    ctx.get_state.side_effect = get_state
    return ctx


SAMPLE_EQUITY_CHART_RESPONSE = {
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
                    "volume": "1250000",
                    "ISIN": "INE736A01011",
                }
            ]
        }
    },
}

SAMPLE_DERIVATIVES_CHART_RESPONSE = {
    "status": "OK",
    "response": {
        "data": {
            "candle": [
                {
                    "date": "10-Jan-2024",
                    "open": "210.00",
                    "high": "340.00",
                    "low": "180.00",
                    "close": "295.00",
                    "volume": "450000",
                    "oi": "120000",
                }
            ]
        }
    },
}

SAMPLE_COMMODITY_CHART_RESPONSE = {
    "status": "OK",
    "response": {
        "data": [
            {
                "date": "05-Feb-2024",
                "exp_date": "05-Feb-2024",
                "open_price": "62500",
                "high_price": "62800",
                "low_price": "62300",
                "ltp": "62650",
                "volume": "8500",
                "openinterest": "1200",
            }
        ]
    },
}


@pytest.mark.asyncio
async def test_market_get_equity_chart_with_co_code(mock_env):
    ctx = make_ctx()
    with respx.mock(base_url="http://investor.test") as router:
        route = router.post("/charts/equity").mock(
            return_value=httpx.Response(200, json=SAMPLE_EQUITY_CHART_RESPONSE)
        )
        res = await market_get_equity_chart(ctx, co_code="20139", period="W", count="1")
        assert res["status"] == "OK"
        assert "Stock-Detailedlist" in res["response"]["data"]

        assert route.called
        sent_body = json.loads(route.calls.last.request.content)
        assert sent_body == {
            "exchange": "NSE",
            "coCode": "20139",
            "period": "W",
            "count": "1",
        }
        sent_headers = route.calls.last.request.headers
        assert sent_headers["x-subAccountId"] == "4433009"
        assert sent_headers["x-authToken"] == "tok123"


@pytest.mark.asyncio
async def test_market_get_equity_chart_symbol_resolution(mock_env):
    ctx = make_ctx()
    with respx.mock(base_url="http://investor.test") as router:
        route = router.post("/charts/equity").mock(
            return_value=httpx.Response(200, json=SAMPLE_EQUITY_CHART_RESPONSE)
        )
        # Test mapped symbol (CDSL -> 20139)
        res1 = await market_get_equity_chart(ctx, symbol="CDSL", exchange="BSE")
        assert res1["status"] == "OK"
        sent_body1 = json.loads(route.calls.last.request.content)
        assert sent_body1["coCode"] == "20139"
        assert sent_body1["exchange"] == "BSE"

        # Test numeric symbol ("23040")
        res2 = await market_get_equity_chart(ctx, symbol="23040")
        assert res2["status"] == "OK"
        sent_body2 = json.loads(route.calls.last.request.content)
        assert sent_body2["coCode"] == "23040"


@pytest.mark.asyncio
async def test_market_get_equity_chart_missing_code_error(mock_env):
    ctx = make_ctx()
    res = await market_get_equity_chart(ctx)
    assert res["status"] == "error"
    assert "Company code 'co_code' is required" in res["message"]


@pytest.mark.asyncio
async def test_market_get_derivatives_chart_options(mock_env):
    ctx = make_ctx()
    with respx.mock(base_url="http://investor.test") as router:
        route = router.post("/charts/derivatives").mock(
            return_value=httpx.Response(200, json=SAMPLE_DERIVATIVES_CHART_RESPONSE)
        )
        res = await market_get_derivatives_chart(
            ctx,
            symbol="BANKNIFTY",
            expiry_date="10-jan-2024",
            instrument_type="OPTIDX",
            opt_type="CE",
            strike_price="47300",
            period="D1",
            sub_account_id="ASX555",
        )
        assert res["status"] == "OK"
        assert route.called
        sent_body = json.loads(route.calls.last.request.content)
        assert sent_body == {
            "instrumentType": "OPTIDX",
            "symbol": "BANKNIFTY",
            "expiryDate": "10-jan-2024",
            "period": "D1",
            "optType": "CE",
            "strikePrice": "47300",
        }
        sent_headers = route.calls.last.request.headers
        assert sent_headers["x-subAccountId"] == "ASX555"


@pytest.mark.asyncio
async def test_market_get_derivatives_chart_futures(mock_env):
    ctx = make_ctx()
    with respx.mock(base_url="http://investor.test") as router:
        route = router.post("/charts/derivatives").mock(
            return_value=httpx.Response(200, json=SAMPLE_DERIVATIVES_CHART_RESPONSE)
        )
        res = await market_get_derivatives_chart(
            ctx,
            symbol="NIFTY",
            expiry_date="28-Nov-2024",
            instrument_type="FUTIDX",
            period="D",
            count="5",
        )
        assert res["status"] == "OK"
        sent_body = json.loads(route.calls.last.request.content)
        assert sent_body == {
            "instrumentType": "FUTIDX",
            "symbol": "NIFTY",
            "expiryDate": "28-Nov-2024",
            "period": "D",
            "count": "5",
        }
        assert "optType" not in sent_body
        assert "strikePrice" not in sent_body


@pytest.mark.asyncio
async def test_market_get_derivatives_chart_validation(mock_env):
    ctx = make_ctx()
    res1 = await market_get_derivatives_chart(ctx, symbol="", expiry_date="10-jan-2024")
    assert res1["status"] == "error"
    assert "'symbol' is required" in res1["message"]

    res2 = await market_get_derivatives_chart(ctx, symbol="NIFTY", expiry_date="")
    assert res2["status"] == "error"
    assert "'expiry_date' is required" in res2["message"]


@pytest.mark.asyncio
async def test_market_get_commodity_chart(mock_env):
    ctx = make_ctx()
    with respx.mock(base_url="http://investor.test") as router:
        route = router.post("/charts/commodity").mock(
            return_value=httpx.Response(200, json=SAMPLE_COMMODITY_CHART_RESPONSE)
        )
        res = await market_get_commodity_chart(
            ctx,
            symbol="gold",
            expiry_date="05-feb-2024",
            type="FUT",
            exchange="MCX",
            period="d",
            count="1",
        )
        assert res["status"] == "OK"
        sent_body = json.loads(route.calls.last.request.content)
        assert sent_body == {
            "type": "FUT",
            "exchange": "MCX",
            "symbol": "gold",
            "expiryDate": "05-feb-2024",
            "period": "d",
            "count": "1",
        }


@pytest.mark.asyncio
async def test_market_get_commodity_chart_validation(mock_env):
    ctx = make_ctx()
    res1 = await market_get_commodity_chart(ctx, symbol="", expiry_date="05-feb-2024")
    assert res1["status"] == "error"
    assert "'symbol' is required" in res1["message"]

    res2 = await market_get_commodity_chart(ctx, symbol="gold", expiry_date="")
    assert res2["status"] == "error"
    assert "'expiry_date' is required" in res2["message"]


@pytest.mark.asyncio
async def test_market_get_chart_unified_equity(mock_env):
    ctx = make_ctx()
    with respx.mock(base_url="http://investor.test") as router:
        route = router.post("/charts/equity").mock(
            return_value=httpx.Response(200, json=SAMPLE_EQUITY_CHART_RESPONSE)
        )
        res = await market_get_chart(
            ctx, asset_class="EQ", co_code="20139", exchange="NSE", period="W", count="1"
        )
        assert res["status"] == "OK"
        assert route.called


@pytest.mark.asyncio
async def test_market_get_chart_unified_derivatives(mock_env):
    ctx = make_ctx()
    with respx.mock(base_url="http://investor.test") as router:
        route = router.post("/charts/derivatives").mock(
            return_value=httpx.Response(200, json=SAMPLE_DERIVATIVES_CHART_RESPONSE)
        )
        res = await market_get_chart(
            ctx,
            asset_class="DERIVATIVES",
            symbol="BANKNIFTY",
            expiry_date="10-jan-2024",
            opt_type="CE",
            strike_price="47300",
        )
        assert res["status"] == "OK"
        assert route.called


@pytest.mark.asyncio
async def test_market_get_chart_unified_commodity(mock_env):
    ctx = make_ctx()
    with respx.mock(base_url="http://investor.test") as router:
        route = router.post("/charts/commodity").mock(
            return_value=httpx.Response(200, json=SAMPLE_COMMODITY_CHART_RESPONSE)
        )
        res = await market_get_chart(
            ctx,
            asset_class="COMMODITY",
            symbol="gold",
            expiry_date="05-feb-2024",
        )
        assert res["status"] == "OK"
        assert route.called


@pytest.mark.asyncio
async def test_market_get_chart_unified_errors(mock_env):
    ctx = make_ctx()
    res_inv = await market_get_chart(ctx, asset_class="CRYPTO")
    assert res_inv["status"] == "error"
    assert "Unsupported asset_class 'CRYPTO'" in res_inv["message"]

    res_fo_nosym = await market_get_chart(ctx, asset_class="FO")
    assert res_fo_nosym["status"] == "error"
    assert "'symbol' is required" in res_fo_nosym["message"]

    res_comm_nosym = await market_get_chart(ctx, asset_class="COMMODITY")
    assert res_comm_nosym["status"] == "error"
    assert "'symbol' is required" in res_comm_nosym["message"]
