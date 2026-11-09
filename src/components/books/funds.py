"""Funds and margin management tools."""

from fastmcp import Context
from fastmcp.tools import tool

from api.base import BaseClient
from utils.decorators import milotic_tool
from utils.session import get_session_headers

VALID_FUNDS_SEGMENTS = {"EQ", "COMM"}


@tool()
@milotic_tool
async def books_get_funds(ctx: Context, segment: str = "EQ") -> dict:
    """
    Fetch available margin, ledger balance, utilized margin, collateral margin,
    and cash/MTF buying power for trading.
    segment: 'EQ' (Equity & Derivatives/F&O limits) or 'COMM' (Commodities). Defaults to 'EQ'.
    """
    seg = segment.strip().upper() if segment else "EQ"
    if seg not in VALID_FUNDS_SEGMENTS:
        return {
            "error": (
                f"segment must be 'EQ' or 'COMM', got '{segment}'. "
                "Note: F&O / derivative margins are reported under 'EQ'."
            )
        }

    headers = await get_session_headers(ctx)
    client = await BaseClient.instance("investor")
    return await client.post(
        "/funds/inquiry/get-limits",
        json={"segment": seg},
        headers=headers,
    )


@tool()
@milotic_tool
async def trading_calculate_margin(
    ctx: Context,
    symbol: str,
    quantity: float,
    side: str = "buy",
    product_type: str = "MTF",
    order_type: str = "market",
    price: float | None = None,
    exchange: str = "NSE",
    segment: str = "EQ",
) -> dict:
    """
    Calculate the required margin, estimated leverage, and brokerage for a hypothetical trade
    before placing an order.
    """
    headers = await get_session_headers(ctx)
    client = await BaseClient.instance("investor")
    payload: dict = {
        "symbol": symbol.strip().upper(),
        "quantity": quantity,
        "transactionType": side.upper(),
        "productType": product_type.upper(),
        "orderType": order_type.upper(),
        "exchange": exchange.upper(),
        "segment": segment.upper(),
    }
    if price is not None:
        payload["price"] = price

    try:
        return await client.post("/trading/orders/margin-calculator", json=payload, headers=headers)
    except Exception:
        return await client.get("/trading/margin/calculate", params=payload, headers=headers)
