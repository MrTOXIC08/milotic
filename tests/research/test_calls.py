"""Tests for research tools."""

from unittest.mock import AsyncMock, patch

import pytest

from components.research.calls import (
    _extract_prices,
    _format_call_summary,
    research_get_calls,
    research_get_config,
    research_get_portfolio_calls,
)


def make_ctx() -> AsyncMock:
    """Build an AsyncMock ctx whose get_state resolves auth_token/sub_account_id."""
    ctx = AsyncMock()

    async def get_state(key: str):
        return {"auth_token": "tok123", "sub_account_id": "sub456"}.get(key)

    ctx.get_state.side_effect = get_state
    return ctx


def test_extract_prices():
    assert _extract_prices(None) == []
    assert _extract_prices([]) == []
    assert _extract_prices([1360, 1385, 0]) == [1360.0, 1385.0]
    assert _extract_prices([0, 0, 0]) == []
    assert _extract_prices([950.5]) == [950.5]


def test_format_call_summary():
    entry = {
        "displayName": "HINDALCO",
        "segment": "EQ",
        "callType": "buy",
        "callStatus": "Open",
        "category": "Result Update (12-18 Months)",
        "subCategory": "Long Term",
        "entryPrice": [953, 0],
        "targetPrice": [1060, 0, 0],
        "stopLoss": [0, 0, 0],
        "targetPercentage": 11,
        "timeDurationOfInvestment": "553 days",
        "timeOfCall": "2026-11-09T04:54:44Z",
        "expiryDate": "2028-05-16",
        "marketCap": "Large Cap",
        "marketCategory": "Non Ferrous Metals",
        "exchangeDetails": [{"exchange": "NSE", "ltp": 938.55, "scriptId": "221363"}],
        "reportHeader": "HINDALCO Report",
        "reportAttachment": "report.pdf",
    }
    summary = _format_call_summary(entry)
    assert summary["symbol"] == "HINDALCO"
    assert summary["segment"] == "EQ"
    assert summary["call_type"] == "BUY"
    assert summary["call_status"] == "Open"
    assert summary["target_price"] == [1060.0]
    assert summary["stop_loss"] == []
    assert summary["entry_price"] == [953.0]
    assert summary["ltp"] == 938.55
    assert summary["script_id"] == "221363"


@pytest.mark.asyncio
async def test_research_get_config_success():
    ctx = make_ctx()
    mock_client = AsyncMock()
    mock_client.get.return_value = {
        "statusCode": 200,
        "status": "OK",
        "data": {
            "configTs": "2026-11-09T05:12:33Z",
            "lastUpdatedAt": "2026-11-09T10:40:00+05:30",
            "unifiedCounts": {
                "segmentCounts": [{"segment": "EQ", "count": 450}],
                "subCategoryCounts": [{"subCategory": "Long Term", "count": 396}],
            },
        },
    }

    with patch("components.research.calls.BaseClient.instance", return_value=mock_client):
        res = await research_get_config(ctx)
        assert res["status"] == "OK"
        assert res["configTs"] == "2026-11-09T05:12:33Z"
        assert len(res["segmentCounts"]) == 1
        assert len(res["subCategories"]) == 1
        mock_client.get.assert_awaited_once_with(
            "markettracking/research-and-recommendations/config",
            headers={"x-authToken": "tok123", "x-subAccountId": "sub456"},
        )


@pytest.mark.asyncio
async def test_research_get_calls_auto_config():
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
                        "displayName": "ZYDUSLIFE",
                        "segment": "EQ",
                        "callType": "buy",
                        "callStatus": "Open",
                        "targetPrice": [1360, 1385, 0],
                        "stopLoss": [1130, 0, 0],
                    }
                ]
            }
        },
    }

    with patch("components.research.calls.BaseClient.instance", return_value=mock_client):
        res = await research_get_calls(ctx, sub_category="Positional", limit=5)
        assert res["status"] == "OK"
        assert res["configTs"] == "2026-11-09T05:12:33Z"
        assert res["total_calls"] == 1
        assert res["calls"][0]["symbol"] == "ZYDUSLIFE"

        # Verify POST payload sent to backend
        mock_client.post.assert_awaited_once()
        call_args = mock_client.post.call_args
        sent_path = call_args[0][0]
        sent_payload = call_args[1]["json"]
        assert "offset=0&limit=5&sort=desc&sortBy=timeOfCall" in sent_path
        assert sent_payload["configTS"] == "2026-11-09T05:12:33Z"
        assert sent_payload["subCategory"] == ["Positional"]
        assert sent_payload["callStatus"] == ["open"]


@pytest.mark.asyncio
async def test_research_get_calls_with_symbol_filter():
    ctx = make_ctx()
    mock_client = AsyncMock()

    mock_client.post.return_value = {
        "statusCode": 200,
        "status": "OK",
        "data": {
            "entries": {
                "entry": [
                    {"displayName": "HINDALCO", "callType": "buy"},
                    {"displayName": "TATAELXSI", "callType": "buy"},
                ]
            }
        },
    }

    with patch("components.research.calls.BaseClient.instance", return_value=mock_client):
        res = await research_get_calls(ctx, symbol="TATA", config_ts="2026-11-09T05:12:33Z")
        assert res["total_calls"] == 1
        assert res["calls"][0]["symbol"] == "TATAELXSI"


@pytest.mark.asyncio
async def test_research_get_portfolio_calls_match():
    ctx = make_ctx()

    mock_portfolio = {
        "data": [
            {
                "holdings": [
                    {
                        "name": "NTPC",
                        "quantity": 10,
                        "averagePrice": 320.0,
                        "unrealizedGain": 150.0,
                    },
                    {
                        "name": "IDEA",
                        "quantity": 5,
                        "averagePrice": 12.0,
                        "unrealizedGain": -1.0,
                    },
                ]
            }
        ]
    }

    mock_calls_result = {
        "status": "OK",
        "calls": [
            {
                "symbol": "NTPC",
                "call_type": "BUY",
                "target_price": [370.0],
                "category": "Result Update",
            },
            {
                "symbol": "BRITANNIA",
                "call_type": "BUY",
                "target_price": [5500.0],
                "category": "Top Pick",
            },
        ],
    }

    with (
        patch(
            "components.books.portfolio.books_get_portfolio",
            AsyncMock(return_value=mock_portfolio),
        ),
        patch(
            "components.research.calls.research_get_calls",
            AsyncMock(return_value=mock_calls_result),
        ),
    ):
        res = await research_get_portfolio_calls(ctx)
        assert res["status"] == "OK"
        assert res["total_holdings_analyzed"] == 2
        assert res["matching_research_calls_count"] == 1
        matched = res["matched_calls"][0]
        assert matched["holding_symbol"] == "NTPC"
        assert matched["holding_quantity"] == 10
        assert matched["call"]["target_price"] == [370.0]
