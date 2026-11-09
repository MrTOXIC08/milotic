"""Tests for trade book tools."""

import json
from unittest.mock import AsyncMock

import httpx
import pytest
import respx

from components.books.tradebook import books_get_trade_book, books_get_trades


def make_ctx() -> AsyncMock:
    ctx = AsyncMock()

    async def get_state(key: str):
        return {"auth_token": "tok123", "sub_account_id": "4433009"}.get(key)

    ctx.get_state.side_effect = get_state
    return ctx


SAMPLE_TRADE_BOOK_PAYLOAD = {
    "statusCode": 200,
    "status": "OK",
    "message": "Success",
    "data": [
        {
            "omsOrderId": "20261109054126",
            "tradeId": "TRD987654",
            "symbol": "IDEA",
            "exchange": "NSE",
            "segment": "EQ",
            "product": "MTF",
            "transactionType": "BUY",
            "tradeQty": 1000,
            "tradePrice": 7.15,
            "tradeValue": 7150.0,
            "tradeExecutionTime": "2026-11-09T09:15:30Z",
            "orderPrice": 7.15,
            "totalQty": 1000,
        }
    ],
}


@pytest.mark.asyncio
async def test_books_get_trade_book_default(mock_env):
    ctx = make_ctx()
    with respx.mock(base_url="http://investor.test") as router:
        route = router.post("/trading/books/get-trade-book").mock(
            return_value=httpx.Response(200, json=SAMPLE_TRADE_BOOK_PAYLOAD)
        )
        res = await books_get_trade_book(ctx)
        assert res["statusCode"] == 200
        assert res["status"] == "OK"
        assert len(res["data"]) == 1
        assert res["data"][0]["tradeId"] == "TRD987654"

        # Verify outgoing request payload and headers
        assert route.called
        sent_body = json.loads(route.calls.last.request.content)
        assert sent_body == {
            "segment": "EQ",
            "orderDetails": [{"omsOrderId": ""}],
        }
        sent_headers = route.calls.last.request.headers
        assert sent_headers["x-subAccountId"] == "4433009"
        assert sent_headers["x-authToken"] == "tok123"


@pytest.mark.asyncio
async def test_books_get_trade_book_with_oms_order_id(mock_env):
    ctx = make_ctx()
    with respx.mock(base_url="http://investor.test") as router:
        route = router.post("/trading/books/get-trade-book").mock(
            return_value=httpx.Response(200, json=SAMPLE_TRADE_BOOK_PAYLOAD)
        )
        res = await books_get_trade_book(ctx, segment="FO", oms_order_id="20261109054126")
        assert res["statusCode"] == 200
        sent_body = json.loads(route.calls.last.request.content)
        assert sent_body == {
            "segment": "FO",
            "orderDetails": [{"omsOrderId": "20261109054126"}],
        }


@pytest.mark.asyncio
async def test_books_get_trade_book_with_order_details(mock_env):
    ctx = make_ctx()
    with respx.mock(base_url="http://investor.test") as router:
        route = router.post("/trading/books/get-trade-book").mock(
            return_value=httpx.Response(200, json=SAMPLE_TRADE_BOOK_PAYLOAD)
        )
        custom_details = [
            {"omsOrderId": "11111"},
            {"omsOrderId": "22222"},
        ]
        res = await books_get_trade_book(ctx, segment="EQ", order_details=custom_details)
        assert res["statusCode"] == 200
        sent_body = json.loads(route.calls.last.request.content)
        assert sent_body == {
            "segment": "EQ",
            "orderDetails": custom_details,
        }


@pytest.mark.asyncio
async def test_books_get_trade_book_invalid_segment(mock_env):
    ctx = make_ctx()
    res = await books_get_trade_book(ctx, segment="INVALID")
    assert res["status"] == "error"
    assert "Invalid segment 'INVALID'" in res["message"]


@pytest.mark.asyncio
async def test_books_get_trades_alias(mock_env):
    ctx = make_ctx()
    with respx.mock(base_url="http://investor.test") as router:
        router.post("/trading/books/get-trade-book").mock(
            return_value=httpx.Response(200, json=SAMPLE_TRADE_BOOK_PAYLOAD)
        )
        res = await books_get_trades(ctx, segment="EQ", oms_order_id="20261109054126")
        assert res["statusCode"] == 200
        assert res["data"][0]["symbol"] == "IDEA"
