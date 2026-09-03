"""Tests for Market Nudge tools."""

from unittest.mock import AsyncMock

import httpx
import pytest
import respx

from components.market.nudges import (
    _extract_portfolio_identifiers,
    _slim_nudge,
    market_get_nudges,
    market_nudges_for_portfolio,
)

SAMPLE_NUDGES_DATA = [
    {
        "isin": "INE018A01030",
        "expireAt": "2026-08-10T18:29:59.999Z",
        "securityInfo": [
            {
                "scriptId": "2211483",
                "coCode": "348",
                "exchange": "NSE",
                "instrument": "Equity",
                "isinCode": "INE018A01030",
                "securityDescription": "LARSEN & TOUBRO LTD",
                "segment": "EQ",
                "symbol": "LT",
                "isin": "INE018A01030",
                "instrumentType": "Equity",
                "displayName": "LT",
            },
            {
                "scriptId": "11500510",
                "coCode": "348",
                "exchange": "BSE",
                "instrument": "Equity",
                "isinCode": "INE018A01030",
                "securityDescription": "LARSEN & TOUBRO LTD",
                "segment": "EQ",
                "symbol": "LT",
                "isin": "INE018A01030",
                "instrumentType": "Equity",
                "displayName": "LT",
            },
        ],
        "nudgesData": [
            {
                "label": "Order Win",
                "shortText": "L&T wins orders worth upto Rs 10,000 crore",
                "longText": "L&T hydrocarbon arm wins orders worth upto Rs 10,000 crore",
                "sentiment": "neutral",
                "createdAt": "2026-08-10T06:29:01.893Z",
            }
        ],
    },
    {
        "isin": "INE094A01015",
        "expireAt": "2026-08-10T18:29:59.999Z",
        "securityInfo": [
            {
                "scriptId": "221406",
                "coCode": "2305",
                "exchange": "NSE",
                "instrument": "Equity",
                "isinCode": "INE094A01015",
                "securityDescription": "HINDUSTAN PETROLEUM CORPORATION LTD",
                "segment": "EQ",
                "symbol": "HINDPETRO",
                "isin": "INE094A01015",
                "instrumentType": "Equity",
                "displayName": "HINDPETRO",
            }
        ],
        "nudgesData": [
            {
                "label": "Dividend",
                "shortText": "HPCL upcoming dividend of Rs 19.25",
                "longText": "HPCL has an upcoming dividend of Rs 19.25 per share",
                "sentiment": "positive",
                "createdAt": "2026-08-10T06:29:01.894Z",
            }
        ],
    },
]

SAMPLE_PORTFOLIO_DATA = {
    "statusCode": 200,
    "status": "OK",
    "data": [
        {
            "holdings": [
                {
                    "isin": "INE018A01030",
                    "symbol": "LT",
                    "quantity": 25,
                    "securityInfo": [{"scriptId": "2211483", "exchange": "NSE"}],
                }
            ]
        }
    ],
}


def make_ctx() -> AsyncMock:
    ctx = AsyncMock()

    async def get_state(key: str):
        return {"auth_token": "tok123", "sub_account_id": "sub456"}.get(key)

    ctx.get_state.side_effect = get_state
    return ctx


def test_slim_nudge():
    entry = SAMPLE_NUDGES_DATA[0]
    slim = _slim_nudge(entry)

    assert slim["isin"] == "INE018A01030"
    assert slim["symbol"] == "LT"
    assert slim["companyName"] == "LARSEN & TOUBRO LTD"
    assert "2211483" in slim["scriptIds"]
    assert "11500510" in slim["scriptIds"]
    assert "NSE" in slim["exchanges"]
    assert "BSE" in slim["exchanges"]
    assert len(slim["nudges"]) == 1
    assert slim["nudges"][0]["label"] == "Order Win"


def test_extract_portfolio_identifiers():
    held_isins, held_script_ids = _extract_portfolio_identifiers(SAMPLE_PORTFOLIO_DATA)
    assert "INE018A01030" in held_isins
    assert "2211483" in held_script_ids


@pytest.mark.asyncio
async def test_market_get_nudges_unfiltered(mock_env):
    ctx = make_ctx()
    with respx.mock(base_url="http://investor.test") as router:
        router.get("/markettracking/market-nudge/portfolio").mock(
            return_value=httpx.Response(200, json={"data": SAMPLE_NUDGES_DATA})
        )

        res = await market_get_nudges(ctx, limit=10, offset=0)
        assert res["count"] == 2
        assert res["total_returned"] == 2
        assert res["nudges"][0]["symbol"] == "LT"
        assert res["nudges"][1]["symbol"] == "HINDPETRO"


@pytest.mark.asyncio
async def test_market_get_nudges_filter_by_symbol(mock_env):
    ctx = make_ctx()
    with respx.mock(base_url="http://investor.test") as router:
        router.get("/markettracking/market-nudge/portfolio").mock(
            return_value=httpx.Response(200, json={"data": SAMPLE_NUDGES_DATA})
        )

        res = await market_get_nudges(ctx, symbol="HINDPETRO")
        assert res["count"] == 1
        assert res["nudges"][0]["symbol"] == "HINDPETRO"


@pytest.mark.asyncio
async def test_market_get_nudges_filter_by_label_and_sentiment(mock_env):
    ctx = make_ctx()
    with respx.mock(base_url="http://investor.test") as router:
        router.get("/markettracking/market-nudge/portfolio").mock(
            return_value=httpx.Response(200, json={"data": SAMPLE_NUDGES_DATA})
        )

        res_div = await market_get_nudges(ctx, label="dividend")
        assert res_div["count"] == 1
        assert res_div["nudges"][0]["symbol"] == "HINDPETRO"

        res_pos = await market_get_nudges(ctx, sentiment="positive")
        assert res_pos["count"] == 1
        assert res_pos["nudges"][0]["symbol"] == "HINDPETRO"


@pytest.mark.asyncio
async def test_market_nudges_for_portfolio(mock_env):
    ctx = make_ctx()
    with respx.mock(base_url="http://investor.test") as router:
        router.get("/trading/v2/portfolio/multi").mock(
            return_value=httpx.Response(200, json=SAMPLE_PORTFOLIO_DATA)
        )
        router.get("/markettracking/market-nudge/portfolio").mock(
            return_value=httpx.Response(200, json={"data": SAMPLE_NUDGES_DATA})
        )

        res = await market_nudges_for_portfolio(ctx, limit=50)
        assert res["held_securities_count"] >= 1
        assert res["matched_count"] == 1
        matched_item = res["matched"][0]
        assert matched_item["symbol"] == "LT"
        assert matched_item["held"] is True
        assert matched_item["nudges"][0]["label"] == "Order Win"
