"""Trading order management tools."""

import uuid

from fastmcp import Context
from fastmcp.tools import tool

from api.base import BaseClient
from utils.decorators import milotic_tool
from utils.errors import BackendConnectionError
from utils.session import get_session_headers

VALID_SIDES = {"buy", "sell"}
VALID_ORDER_TYPES = {"market", "limit", "stop_limit"}


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
    confirmed: bool = False,
) -> dict:
    """
    Place a new order. ALWAYS call with confirmed=False first to preview, then
    confirmed=True only after the user explicitly approves the previewed order.
    side: 'buy' or 'sell'. order_type: 'market', 'limit', 'stop_limit'.
    """
    symbol = symbol.strip().upper()
    side_norm = side.lower()
    order_type_norm = order_type.lower()

    if side_norm not in VALID_SIDES:
        return {"error": f"side must be 'buy' or 'sell', got '{side}'"}
    if order_type_norm not in VALID_ORDER_TYPES:
        return {"error": "order_type must be 'market', 'limit', or 'stop_limit'"}
    if quantity <= 0:
        return {"error": "quantity must be positive"}
    if order_type_norm in ("limit", "stop_limit") and price is None:
        return {"error": f"price is required for {order_type_norm} orders"}

    if not confirmed:
        return {
            "preview": True,
            "symbol": symbol,
            "side": side_norm,
            "quantity": quantity,
            "order_type": order_type_norm,
            "price": price,
            "message": "Call again with confirmed=True to place this order.",
        }

    headers = await get_session_headers(ctx)
    reference_id = str(uuid.uuid4())
    payload: dict = {
        "symbol": symbol,
        "side": side_norm,
        "quantity": quantity,
        "order_type": order_type_norm,
        "reference_id": reference_id,  # field name TBD from API docs
    }
    if price is not None:
        payload["price"] = price

    client = await BaseClient.instance("investor")
    try:
        return await client.post("/orders", json=payload, headers=headers)
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
    return await client.delete(f"/orders/{order_id}", headers=headers)


@tool()
@milotic_tool
async def trading_get_order(ctx: Context, order_id: str) -> dict:
    """
    Fetch the current status and details of a specific order.
    Use to check whether an order is still open, filled, or cancelled.
    """
    headers = await get_session_headers(ctx)
    client = await BaseClient.instance("investor")
    return await client.get(f"/orders/{order_id}", headers=headers)


@tool()
@milotic_tool
async def trading_get_all_orders(ctx: Context) -> dict:
    """
    Get all orders for the authenticated user.
    """
    headers = await get_session_headers(ctx)
    client = await BaseClient.instance("investor")
    return await client.get("/orders", headers=headers)
