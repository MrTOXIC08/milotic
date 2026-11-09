"""Market depth and best-five order book tools."""

from typing import Any

from fastmcp import Context
from fastmcp.tools import tool

from api.base import BaseClient
from utils.decorators import milotic_tool
from utils.scrips import resolve_script_id_async
from utils.session import get_session_headers


def _format_depth_levels(raw_levels: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Format and normalize price levels into standardized entries."""
    formatted = []
    for item in raw_levels:
        if not isinstance(item, dict):
            continue
        price_raw = item.get("price", 0.0)
        qty_raw = item.get("quantity") or item.get("qty", 0)
        orders_raw = item.get("noOfOrders") or item.get("orders", 0)

        try:
            price = float(price_raw)
        except (ValueError, TypeError):
            price = 0.0

        try:
            qty = int(qty_raw)
        except (ValueError, TypeError):
            qty = qty_raw

        try:
            orders = int(orders_raw)
        except (ValueError, TypeError):
            orders = orders_raw

        formatted.append(
            {
                "price": price,
                "quantity": qty,
                "orders": orders,
            }
        )
    return formatted


@tool()
@milotic_tool
async def market_get_best_five(
    ctx: Context,
    symbol: str | None = None,
    script_id: str | None = None,
    exchange: str = "NSE",
) -> dict[str, Any]:
    """
    Fetch real-time Best-Five (Level-2) market depth broadcast for an equity scrip.

    Retrieves top 5 buy bids and top 5 sell asks with prices, order quantities,
    number of orders, LTP, day OHLC, ATP, total buy/sell quantities, volume,
    and 52-week/life-time ranges.

    Parameters:
        symbol: Ticker symbol (e.g. 'IDEA', 'ACC', 'NTPC', 'RELIANCE').
        script_id: Direct Axis Direct script ID (e.g. '2214366').
        exchange: Exchange ('NSE' or 'BSE', defaults to 'NSE').
    """
    return await market_get_depth(
        ctx,
        symbol=symbol,
        script_id=script_id,
        depth=5,
        exchange=exchange,
    )


@tool()
@milotic_tool
async def market_get_depth(
    ctx: Context,
    symbol: str | None = None,
    script_id: str | None = None,
    depth: int = 5,
    exchange: str = "NSE",
) -> dict[str, Any]:
    """
    Fetch Level-2 market depth (top bid and ask price levels, quantities, and order counts).

    Uses the Axis Direct /feedbroadcast/best-five broadcast API.
    Accepts either an explicit script_id or a ticker symbol (which is resolved automatically).

    Parameters:
        symbol: Ticker symbol (e.g. 'IDEA', 'ACC', 'SBIN').
        script_id: Direct Axis Direct script ID (e.g. '2214366').
        depth: Number of price levels to return (defaults to 5).
        exchange: Exchange code ('NSE' or 'BSE', defaults to 'NSE').
    """
    if not symbol and not script_id:
        return {
            "status": "error",
            "message": "Either 'symbol' or 'script_id' must be provided.",
        }

    exchange_upper = exchange.strip().upper()
    resolved_script_id: str | None = None

    if script_id and str(script_id).strip():
        resolved_script_id = str(script_id).strip()
    elif symbol:
        sym_clean = symbol.strip().upper()
        resolved_script_id = await resolve_script_id_async(ctx, sym_clean, exchange=exchange_upper)
        if not resolved_script_id.isdigit():
            return {
                "status": "error",
                "message": (
                    f"Could not resolve numeric scriptId for symbol '{symbol}' "
                    f"on exchange '{exchange}'. Please specify an explicit script_id."
                ),
                "symbol": sym_clean,
                "exchange": exchange_upper,
            }

    headers = await get_session_headers(ctx)
    client = await BaseClient.instance("market")

    try:
        resp = await client.post(
            "feedbroadcast/best-five",
            json={"scriptId": resolved_script_id},
            headers=headers,
        )
    except Exception as exc:
        return {
            "status": "error",
            "message": f"Failed to fetch market depth for script {resolved_script_id}: {exc}",
            "symbol": symbol.strip().upper() if symbol else None,
            "scriptId": resolved_script_id,
            "exchange": exchange_upper,
        }

    data: dict[str, Any] = resp.get("data", {}) if isinstance(resp, dict) else {}
    if not data and isinstance(resp, dict):
        data = resp

    raw_buys = data.get("buy") or data.get("bids") or resp.get("bids") or []
    raw_sells = data.get("sell") or data.get("asks") or resp.get("asks") or []

    bids = _format_depth_levels(raw_buys)[:depth]
    asks = _format_depth_levels(raw_sells)[:depth]

    return {
        "status": "OK",
        "symbol": symbol.strip().upper() if symbol else None,
        "scriptId": resolved_script_id,
        "exchange": exchange_upper,
        "ltp": data.get("ltp"),
        "bids": bids,
        "asks": asks,
        "totalBuyQty": data.get("totalBuyQty"),
        "totalSellQty": data.get("totalSellQty"),
        "averageTradedPrice": data.get("averageTradedPrice"),
        "open": data.get("openPrice") or data.get("open"),
        "high": data.get("highPrice") or data.get("high"),
        "low": data.get("lowPrice") or data.get("low"),
        "close": data.get("closePrice") or data.get("close"),
        "volume": data.get("volume"),
        "netChange": data.get("netChangeFromPrevClose") or data.get("netChange"),
        "lastTradeTime": data.get("lastTradeTime"),
        "lastTradeQty": data.get("lastTradeQuantity"),
        "lifeTimeHigh": data.get("lifeTimeHigh"),
        "lifeTimeLow": data.get("lifeTimeLow"),
        "data": data,
    }
