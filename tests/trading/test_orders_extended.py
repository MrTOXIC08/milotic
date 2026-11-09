"""Tests for extended trading order tools (trigger_price, trades, order history)."""

import json
from unittest.mock import AsyncMock

import httpx
import pytest
import respx

from components.books.orders import (
    resolve_script_id_async,
    trading_get_order_history,
    trading_get_trades,
    trading_modify_order,
    trading_place_order,
)


def make_ctx() -> AsyncMock:
    ctx = AsyncMock()

    async def get_state(key: str):
        return {"auth_token": "tok123", "sub_account_id": "sub456"}.get(key)

    ctx.get_state.side_effect = get_state
    return ctx


@pytest.mark.asyncio
async def test_trading_place_order_trigger_price_preview(mock_env):
    ctx = make_ctx()
    res = await trading_place_order(
        ctx,
        symbol="ACC",
        side="buy",
        quantity=10,
        order_type="stop_limit",
        price=2200.0,
        trigger_price=2190.0,
        confirmed=False,
    )
    assert res.get("preview") is True
    assert res.get("trigger_price") == 2190.0


@pytest.mark.asyncio
async def test_trading_place_order_stop_loss_missing_trigger(mock_env):
    ctx = make_ctx()
    res = await trading_place_order(
        ctx,
        symbol="ACC",
        side="buy",
        quantity=10,
        order_type="stop_limit",
        price=2200.0,
        trigger_price=None,
        confirmed=False,
    )
    assert "error" in res
    assert "trigger_price is required" in res["error"]


@pytest.mark.asyncio
async def test_trading_place_order_with_trigger_price_execution(mock_env):
    ctx = make_ctx()
    with respx.mock(base_url="http://investor.test") as router:
        router.post("/trading/orders/place-order").mock(
            return_value=httpx.Response(
                200, json={"status": "OK", "data": {"omsOrderId": "ord123"}}
            )
        )
        res = await trading_place_order(
            ctx,
            symbol="ACC",
            side="buy",
            quantity=10,
            order_type="stop_limit",
            price=2200.0,
            trigger_price=2190.0,
            confirmed=True,
        )
        assert res["status"] == "OK"
        assert res["data"]["omsOrderId"] == "ord123"


@pytest.mark.asyncio
async def test_trading_modify_order_with_trigger_price(mock_env):
    ctx = make_ctx()
    with respx.mock(base_url="http://investor.test") as router:
        router.post("/trading/orders/get-order-book").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "omsOrderId": "20261109054126",
                            "openQty": 10,
                            "orderPrice": 2200.0,
                            "triggerPrice": 2180.0,
                            "orderType": "SL",
                            "product": "MTF",
                            "transactionType": "BUY",
                            "exchange": "NSE",
                            "segment": "EQ",
                            "scriptId": "2222",
                            "symbol": "ACC",
                        }
                    ]
                },
            )
        )
        router.post("/trading/orders/modify-order").mock(
            return_value=httpx.Response(200, json={"status": "OK", "message": "Modified"})
        )

        # 1. Preview
        preview = await trading_modify_order(
            ctx,
            order_id="20261109054126",
            price=2210.0,
            trigger_price=2200.0,
            confirmed=False,
        )
        assert preview.get("preview") is True
        assert preview.get("new_trigger_price") == 2200.0

        # 2. Confirmed
        mod = await trading_modify_order(
            ctx,
            order_id="20261109054126",
            price=2210.0,
            trigger_price=2200.0,
            confirmed=True,
        )
        assert mod["status"] == "OK"


@pytest.mark.asyncio
async def test_trading_get_trades(mock_env):
    ctx = make_ctx()
    with respx.mock(base_url="http://investor.test") as router:
        router.post("/trading/orders/get-trade-book").mock(
            return_value=httpx.Response(
                200, json={"status": "OK", "data": [{"tradeId": "trd999", "symbol": "INFY"}]}
            )
        )
        res = await trading_get_trades(ctx, segment="EQ")
        assert res["status"] == "OK"
        assert res["data"][0]["tradeId"] == "trd999"


@pytest.mark.asyncio
async def test_trading_get_order_history(mock_env):
    ctx = make_ctx()
    with respx.mock(base_url="http://investor.test") as router:
        router.post("/trading/orders/order-history").mock(
            return_value=httpx.Response(
                200, json={"status": "OK", "data": [{"status": "ORDER_PLACED"}]}
            )
        )
        res = await trading_get_order_history(ctx, order_id="ord123", segment="EQ")
        assert res["status"] == "OK"


@pytest.mark.asyncio
async def test_trading_place_order_auto_resolves_script_id_via_search(mock_env):
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
        place_route = router.post("/trading/orders/place-order").mock(
            return_value=httpx.Response(
                200, json={"status": "OK", "data": {"omsOrderId": "ord_tata"}}
            )
        )
        res = await trading_place_order(
            ctx,
            symbol="TATAMOTORS",
            side="buy",
            quantity=5,
            order_type="market",
            confirmed=True,
        )
        assert res["status"] == "OK"
        assert place_route.called
        last_request = place_route.calls.last.request
        body = json.loads(last_request.content)
        assert body["scriptId"] == "223456"
        assert body["symbol"] == "TATAMOTORS"


@pytest.mark.asyncio
async def test_resolve_script_id_async_scenarios(mock_env):
    ctx = make_ctx()

    # 1. Numeric already
    assert await resolve_script_id_async(ctx, "2214366") == "2214366"

    # 2. Known scrips local check (sync)
    assert await resolve_script_id_async(ctx, "IDEA", exchange="NSE") == "2214366"

    # 3. Dynamic lookup via /search/get-all
    with respx.mock(base_url="http://investor.test") as router:
        router.get("/search/get-all").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "symbol": "BHARTIARTL",
                            "securityInfo": [{"exchange": "NSE", "scriptId": "221061"}],
                        }
                    ]
                },
            )
        )
        resolved = await resolve_script_id_async(ctx, "BHARTIARTL", exchange="NSE")
        assert resolved == "221061"

    # 4. Fallback to raw symbol when not found
    with respx.mock(base_url="http://investor.test") as router:
        router.get("/search/get-all").mock(return_value=httpx.Response(200, json={"data": []}))
        fallback = await resolve_script_id_async(ctx, "UNKNOWNCO", exchange="NSE")
        assert fallback == "UNKNOWNCO"
