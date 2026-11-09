"""Tests for research recommendations tools."""

from unittest.mock import AsyncMock, patch

import pytest

from components.research.recommendations import (
    _held_script_ids,
    _script_id,
    _slim,
    research_for_portfolio,
    research_get_recommendations,
)


def make_ctx() -> AsyncMock:
    """Build an AsyncMock ctx whose get_state resolves auth_token/sub_account_id."""
    ctx = AsyncMock()

    async def get_state(key: str):
        return {"auth_token": "tok123", "sub_account_id": "sub456"}.get(key)

    ctx.get_state.side_effect = get_state
    return ctx


def test_script_id_extraction():
    entry_exchange = {"exchangeDetails": [{"scriptId": "2214366"}]}
    assert _script_id(entry_exchange) == "2214366"

    entry_security = {"securityInfo": [{"scriptId": "11532822"}]}
    assert _script_id(entry_security) == "11532822"

    entry_empty = {}
    assert _script_id(entry_empty) is None


def test_slim():
    entry = {
        "symbol": "ACC",
        "displayName": "ACC Ltd",
        "callType": "BUY",
        "callStatus": "OPEN",
        "targetPrice": 2500,
        "exchangeDetails": [{"ltp": 2300, "exchange": "NSE", "scriptId": "2222"}],
        "extraHugeField": "drop_me",
    }
    slimmed = _slim(entry)
    assert slimmed["symbol"] == "ACC"
    assert slimmed["displayName"] == "ACC Ltd"
    assert slimmed["ltp"] == 2300
    assert slimmed["exchange"] == "NSE"
    assert slimmed["scriptId"] == "2222"
    assert "extraHugeField" not in slimmed


def test_held_script_ids():
    portfolio = {
        "data": [
            {
                "holdings": [
                    {
                        "name": "IDEA",
                        "securityInfo": [{"scriptId": "2214366"}, {"scriptId": "11532822"}],
                    },
                    {"name": "ACC", "securityInfo": [{"scriptId": "2222"}]},
                ]
            }
        ]
    }
    held = _held_script_ids(portfolio)
    assert held == {"2214366", "11532822", "2222"}


@pytest.mark.asyncio
async def test_research_get_recommendations_success():
    ctx = make_ctx()
    mock_client = AsyncMock()

    mock_client.get.return_value = {
        "statusCode": 200,
        "status": "OK",
        "data": {"configTs": "2026-11-09T05:12:33Z"},
    }

    mock_client.post.return_value = {
        "statusCode": 200,
        "status": "OK",
        "data": {
            "entries": {
                "entry": [
                    {
                        "symbol": "ACC",
                        "segment": "EQ",
                        "subCategory": "Long Term",
                        "callType": "BUY",
                        "exchangeDetails": [{"ltp": 2300, "exchange": "NSE", "scriptId": "2222"}],
                    },
                    {
                        "symbol": "IDEA",
                        "segment": "FO",
                        "subCategory": "Intraday",
                        "callType": "SELL",
                        "exchangeDetails": [{"ltp": 12, "exchange": "NSE", "scriptId": "2214366"}],
                    },
                ]
            }
        },
    }

    with patch("components.research.recommendations.BaseClient.instance", return_value=mock_client):
        res = await research_get_recommendations(ctx, segment="EQ", sub_category="Long Term")
        assert res["count"] == 1
        assert res["config_ts"] == "2026-11-09T05:12:33Z"
        assert res["recommendations"][0]["symbol"] == "ACC"
        assert res["recommendations"][0]["scriptId"] == "2222"


@pytest.mark.asyncio
async def test_research_for_portfolio_success():
    ctx = make_ctx()
    mock_client = AsyncMock()

    # 1. Mock portfolio call
    mock_client.get.side_effect = [
        # First call: portfolio
        {
            "statusCode": 200,
            "status": "OK",
            "data": [
                {
                    "holdings": [
                        {
                            "name": "ACC",
                            "securityInfo": [{"scriptId": "2222"}],
                        }
                    ]
                }
            ],
        },
        # Second call: research config
        {
            "statusCode": 200,
            "status": "OK",
            "data": {"configTs": "2026-11-09T05:12:33Z"},
        },
    ]

    # Mock fetch POST call
    mock_client.post.return_value = {
        "statusCode": 200,
        "status": "OK",
        "data": {
            "entries": {
                "entry": [
                    {
                        "symbol": "ACC",
                        "exchangeDetails": [{"ltp": 2300, "exchange": "NSE", "scriptId": "2222"}],
                    },
                    {
                        "symbol": "TATA",
                        "exchangeDetails": [{"ltp": 900, "exchange": "NSE", "scriptId": "9999"}],
                    },
                ]
            }
        },
    }

    with patch("components.research.recommendations.BaseClient.instance", return_value=mock_client):
        res = await research_for_portfolio(ctx)
        assert res["held_count"] == 1
        assert res["matched_count"] == 1
        assert res["matched"][0]["symbol"] == "ACC"
        assert res["matched"][0]["held"] is True
