"""Funds and margin management tools."""

from fastmcp import Context
from fastmcp.tools import tool

from api.base import BaseClient
from utils.decorators import milotic_tool
from utils.session import get_session_headers


@tool()
@milotic_tool
async def books_get_funds(ctx: Context, segment: str = "EQ") -> dict:
    """
    Fetch available cash balance, utilized margin, collateral margin, MTF buying power,
    and withdrawable balance for trading.
    segment: 'EQ', 'FO', 'CURR', 'COMM' (defaults to 'EQ').
    """
    headers = await get_session_headers(ctx)
    client = await BaseClient.instance("investor")
    try:
        return await client.get(
            "/trading/v2/funds", params={"segment": segment.upper()}, headers=headers
        )
    except Exception:
        return await client.get(
            "/trading/margin", params={"segment": segment.upper()}, headers=headers
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
