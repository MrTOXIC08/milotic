"""Trading order management tools."""

import json
import uuid
from pathlib import Path

from fastmcp import Context
from fastmcp.tools import tool

from api.base import BaseClient
from utils.decorators import milotic_tool
from utils.errors import BackendConnectionError
from utils.session import get_session_headers

VALID_SIDES = {"buy", "sell"}
VALID_ORDER_TYPES = {"market", "limit", "stop_limit", "rl-mkt", "rl", "sl", "sl-m"}


def resolve_script_id(symbol: str, exchange: str = "NSE") -> str:
    """Resolve an exchange-specific scriptId from symbol, portfolio, or known scrips."""
    sym = symbol.strip().upper()
    if sym.isdigit():
        return sym

    known_scrips: dict[str, dict[str, str]] = {
        "IDEA": {"NSE": "2214366", "BSE": "11532822"},
        "VODAFONE IDEA": {"NSE": "2214366", "BSE": "11532822"},
        "ACC": {"NSE": "2222", "BSE": "11500410"},
    }
    if sym in known_scrips and exchange in known_scrips[sym]:
        return known_scrips[sym][exchange]

    try:
        p = Path(".portfolio.json")
        if p.exists():
            data = json.loads(p.read_text())
            for h in data.get("data", [{}])[0].get("holdings", []):
                h_name = h.get("name", "").upper()
                if sym == h_name or sym in h_name:
                    sec_info = h.get("securityInfo", [])
                    prefix = "22" if exchange == "NSE" else "11"
                    for s in sec_info:
                        sid = str(s.get("scriptId", ""))
                        if sid.startswith(prefix):
                            return sid
                    if sec_info:
                        return str(sec_info[0].get("scriptId", ""))
    except Exception:
        pass
    return sym


async def resolve_script_id_async(ctx: Context, symbol: str, exchange: str = "NSE") -> str:
    """
    Resolve an exchange-specific scriptId asynchronously.
    First checks local static scrips & portfolio, then falls back to Axis Direct
    live search API (/search/get-all). Returns symbol unchanged if unresolvable.
    """
    sym = symbol.strip().upper()
    if sym.isdigit():
        return sym

    local_resolved = resolve_script_id(sym, exchange=exchange)
    if local_resolved != sym:
        return local_resolved

    try:
        from components.market.search import search_security_id

        api_resolved = await search_security_id(ctx, sym, exchange=exchange)
        if api_resolved:
            return api_resolved
    except Exception:
        pass

    return sym


# TODO(v2): add advisory rate throttle here once day-pass consent lands (fail-open,
# UX-only — server remains authoritative for the 10 orders/sec compliance cap).
@tool()
@milotic_tool
async def trading_place_order(
    ctx: Context,
    symbol: str,
    side: str,
    quantity: float,
    order_type: str,
    price: float | None = None,
    trigger_price: float | None = None,
    product_type: str = "MTF",
    exchange: str = "NSE",
    segment: str = "EQ",
    validity_type: str = "DAY",
    script_id: str | None = None,
    confirmed: bool = False,
) -> dict:
    """
    Place a new order. ALWAYS call with confirmed=False first to preview, then
    confirmed=True only after the user explicitly approves the previewed order.
    side: 'buy' or 'sell'.
    order_type: 'market', 'limit', 'stop_limit', 'rl-mkt', 'rl', 'sl', 'sl-m'.
    trigger_price: Required for stop-loss orders ('stop_limit', 'sl', 'sl-m').
    """
    symbol = symbol.strip().upper()
    side_norm = side.lower()
    order_type_norm = order_type.lower()

    if side_norm not in VALID_SIDES:
        return {"error": f"side must be 'buy' or 'sell', got '{side}'"}
    if order_type_norm not in VALID_ORDER_TYPES:
        return {
            "error": (
                "order_type must be 'market', 'limit', 'stop_limit', "
                "'rl-mkt', 'rl', 'sl', or 'sl-m'"
            )
        }
    if quantity <= 0:
        return {"error": "quantity must be positive"}
    if order_type_norm in ("limit", "stop_limit", "rl", "sl") and price is None:
        return {"error": f"price is required for {order_type_norm} orders"}
    if order_type_norm in ("stop_limit", "sl", "sl-m") and trigger_price is None:
        return {"error": f"trigger_price is required for {order_type_norm} orders"}

    if not confirmed:
        return {
            "preview": True,
            "symbol": symbol,
            "side": side_norm,
            "quantity": quantity,
            "order_type": order_type_norm,
            "price": price,
            "trigger_price": trigger_price,
            "product_type": product_type,
            "exchange": exchange,
            "segment": segment,
            "validity_type": validity_type,
            "message": "Call again with confirmed=True to place this order.",
        }

    headers = await get_session_headers(ctx)
    reference_id = str(uuid.uuid4())

    exchange_norm = exchange.upper() if exchange else "NSE"
    segment_norm = segment.upper() if segment else "EQ"
    validity_norm = validity_type.upper() if validity_type else "DAY"
    product_norm = product_type.upper() if product_type else "MTF"
    trans_norm = "BUY" if side_norm == "buy" else "SELL"

    if order_type_norm in ("market", "rl-mkt"):
        order_type_mapped = "RL-MKT"
    elif order_type_norm in ("limit", "rl"):
        order_type_mapped = "RL"
    else:
        order_type_mapped = order_type.upper()

    if script_id:
        script_id_resolved = script_id
    else:
        script_id_resolved = await resolve_script_id_async(ctx, symbol, exchange=exchange_norm)

    payload: dict = {
        # Go backend OMS DTO
        "validityType": validity_norm,
        "totalQty": int(quantity),
        "orderType": order_type_mapped,
        "productType": product_norm,
        "transactionType": trans_norm,
        "scriptId": script_id_resolved,
        "exchange": exchange_norm,
        "segment": segment_norm,
        # Legacy fields
        "symbol": symbol,
        "side": side_norm,
        "quantity": quantity,
        "order_type": order_type_norm,
        "reference_id": reference_id,
    }
    if price is not None:
        payload["price"] = price
        payload["orderPrice"] = price
    if trigger_price is not None:
        payload["triggerPrice"] = trigger_price

    client = await BaseClient.instance("investor")
    try:
        return await client.post("/trading/orders/place-order", json=payload, headers=headers)
    except BackendConnectionError:
        # Doc-mandated rule: never retry on timeout/unknown-outcome.
        return {
            "status": "unknown",
            "reference_id": reference_id,
            "message": (
                "Order status unknown due to a connection issue. "
                f"Check status with trading_get_order(order_id='{reference_id}')."
            ),
        }


@tool()
@milotic_tool
async def trading_cancel_order(ctx: Context, order_id: str) -> dict:
    """
    Cancel an open order by its ID.
    Use when the user wants to withdraw an unfilled order before execution.
    """
    headers = await get_session_headers(ctx)
    client = await BaseClient.instance("investor")

    try:
        existing = await trading_get_order(ctx, order_id=order_id)
        if existing and "error" not in existing and "omsOrderId" in existing:
            payload: dict = {
                "omsOrderId": str(existing.get("omsOrderId")),
                "omsOrderSerialNumber": str(existing.get("omsOrderSerialNumber", "1")),
                "openQty": int(existing.get("openQty") or existing.get("totalQty") or 1),
                "orderType": existing.get("orderType", "RL"),
                "productType": existing.get("product"),
                "transactionType": existing.get("transactionType"),
                "validityType": existing.get("validityType", "DAY"),
                "exchange": (
                    "NSE"
                    if "NSE" in str(existing.get("exchange", ""))
                    else str(existing.get("exchange"))
                ),
                "segment": existing.get("segment") or "EQ",
                "scriptId": str(existing.get("scriptId")),
            }
            return await client.post("/trading/orders/cancel-order", json=payload, headers=headers)
    except Exception:
        pass

    return await client.delete(f"/orders/{order_id}", headers=headers)


@tool()
@milotic_tool
async def trading_modify_order(
    ctx: Context,
    order_id: str,
    quantity: float | None = None,
    price: float | None = None,
    trigger_price: float | None = None,
    order_type: str | None = None,
    confirmed: bool = False,
) -> dict:
    """
    Modify an open order. ALWAYS call with confirmed=False first to preview, then
    confirmed=True only after the user explicitly approves the previewed modification.
    order_id: omsOrderId (e.g. '20261109054126').
    quantity: New quantity (must be positive).
    price: New limit price (optional).
    trigger_price: New stop-loss trigger price (optional).
    order_type: 'market', 'limit', 'rl-mkt', or 'rl' (optional).
    """
    existing = await trading_get_order(ctx, order_id=order_id)
    if not existing or "error" in existing or "omsOrderId" not in existing:
        return {"error": f"Could not find open order '{order_id}' to modify."}

    cur_qty = existing.get("openQty") or existing.get("totalQty") or 0
    new_qty = int(quantity) if quantity is not None else int(cur_qty)
    if new_qty <= 0:
        return {"error": "quantity must be positive"}

    cur_price = existing.get("orderPrice")
    new_price = price if price is not None else cur_price

    cur_trigger = existing.get("triggerPrice")
    new_trigger = trigger_price if trigger_price is not None else cur_trigger

    cur_type = existing.get("orderType", "RL").upper()
    if order_type:
        ot_norm = order_type.lower()
        if ot_norm in ("market", "rl-mkt"):
            new_type = "RL-MKT"
        elif ot_norm in ("limit", "rl"):
            new_type = "RL"
        else:
            new_type = order_type.upper()
    else:
        new_type = cur_type

    if not confirmed:
        return {
            "preview": True,
            "order_id": order_id,
            "symbol": existing.get("symbol"),
            "side": existing.get("transactionType"),
            "old_quantity": cur_qty,
            "new_quantity": new_qty,
            "old_price": cur_price,
            "new_price": new_price,
            "old_trigger_price": cur_trigger,
            "new_trigger_price": new_trigger,
            "order_type": new_type,
            "product_type": existing.get("product"),
            "message": "Call again with confirmed=True to execute this order modification.",
        }

    headers = await get_session_headers(ctx)
    client = await BaseClient.instance("investor")

    payload: dict = {
        "omsOrderId": str(existing.get("omsOrderId")),
        "omsOrderSerialNumber": str(existing.get("omsOrderSerialNumber", "1")),
        "openQty": new_qty,
        "totalQty": new_qty,
        "orderType": new_type,
        "productType": existing.get("product"),
        "transactionType": existing.get("transactionType"),
        "validityType": existing.get("validityType", "DAY"),
        "exchange": (
            "NSE" if "NSE" in str(existing.get("exchange", "")) else existing.get("exchange")
        ),
        "segment": existing.get("segment") or "EQ",
        "scriptId": str(existing.get("scriptId")),
    }
    if new_price is not None:
        payload["orderPrice"] = new_price
        payload["price"] = new_price
    if new_trigger is not None:
        payload["triggerPrice"] = new_trigger

    return await client.post("/trading/orders/modify-order", json=payload, headers=headers)


@tool()
@milotic_tool
async def trading_get_order(ctx: Context, order_id: str, segment: str = "EQ") -> dict:
    """
    Fetch the current status and details of a specific order.
    Use to check whether an order is still open, filled, or cancelled.
    order_id: omsOrderId or orderRefId.
    """
    headers = await get_session_headers(ctx)
    client = await BaseClient.instance("investor")

    for status_code in ("2", "1"):
        try:
            book = await client.post(
                "/trading/orders/get-order-book",
                json={"segment": segment.upper(), "orderStatus": status_code},
                headers=headers,
            )
            orders = (
                book.get("data", [])
                if isinstance(book, dict)
                else (book if isinstance(book, list) else [])
            )
            for order in orders:
                oms_id = str(order.get("omsOrderId"))
                ref_id = str(order.get("orderRefId"))
                if oms_id == str(order_id) or ref_id == str(order_id):
                    return order
        except Exception:
            pass

    return await client.get(f"/orders/{order_id}", headers=headers)


@tool()
@milotic_tool
async def trading_get_all_orders(ctx: Context, segment: str = "EQ", status: str = "2") -> dict:
    """
    Get all orders for the authenticated user from the order book.
    segment: 'EQ', 'FO', 'CURR', 'COMM' (defaults to 'EQ').
    status: Order book filter status code ('2' for executed/active, '1' for cancelled).
    """
    headers = await get_session_headers(ctx)
    client = await BaseClient.instance("investor")
    payload = {"segment": segment.upper(), "orderStatus": str(status)}
    return await client.post("/trading/orders/get-order-book", json=payload, headers=headers)


@tool()
@milotic_tool
async def trading_get_trades(ctx: Context, segment: str = "EQ") -> dict:
    """
    Fetch the executed trade book showing all individual trade fills, execution timestamps,
    exchange trade IDs, and average fill prices.
    segment: 'EQ', 'FO', 'CURR', 'COMM' (defaults to 'EQ').
    """
    headers = await get_session_headers(ctx)
    client = await BaseClient.instance("investor")
    payload = {"segment": segment.upper()}
    try:
        return await client.post("/trading/orders/get-trade-book", json=payload, headers=headers)
    except Exception:
        return await client.get("/trading/orders/trades", params=payload, headers=headers)


@tool()
@milotic_tool
async def trading_get_order_history(ctx: Context, order_id: str, segment: str = "EQ") -> dict:
    """
    Fetch the state-by-state lifecycle and audit trail of an order from placement
    to execution or cancellation.
    order_id: omsOrderId or orderRefId.
    segment: 'EQ', 'FO', 'CURR', 'COMM' (defaults to 'EQ').
    """
    headers = await get_session_headers(ctx)
    client = await BaseClient.instance("investor")
    payload = {"orderId": str(order_id), "segment": segment.upper()}
    try:
        return await client.post("/trading/orders/order-history", json=payload, headers=headers)
    except Exception:
        order = await trading_get_order(ctx, order_id=order_id, segment=segment)
        if order and "error" not in order:
            return {"orderId": order_id, "history": [order]}
        return {"error": f"Order {order_id} history not found"}
