"""Market depth and best-five broadcast tools."""

from typing import Any

from fastmcp import Context
from fastmcp.tools import tool

from api.base import BaseClient
from components.books.orders import resolve_script_id_async
from utils.decorators import milotic_tool
from utils.session import get_session_headers


@tool()
@milotic_tool
async def market_get_best_five(
    ctx: Context,
    script_id: str | None = None,
    symbol: str | None = None,
    exchange: str = "NSE",
) -> dict[str, Any]:
    """
    Fetch real-time Best-Five (Level-2) market depth broadcast for an equity scrip.

    Queries Axis Direct /feedbroadcast/best-five API.
    Accepts either an explicit script_id or a ticker symbol (resolved automatically).
    """
    if not script_id and not symbol:
        return {"status": "error", "message": "Either 'script_id' or 'symbol' must be provided."}

    sid = str(script_id).strip() if script_id else ""
    if not sid and symbol:
        sid = await resolve_script_id_async(ctx, symbol.strip().upper(), exchange=exchange.upper())

    headers = await get_session_headers(ctx)
    client = await BaseClient.instance("market")
    return await client.post("feedbroadcast/best-five", json={"scriptId": sid}, headers=headers)


@tool()
@milotic_tool
async def market_get_depth(
    ctx: Context,
    symbol: str,
    depth: int = 5,
    exchange: str = "NSE",
) -> dict[str, Any]:
    """
    Fetch Level-2 market depth (top bid and ask price levels, quantities, and order counts).
    depth: number of price levels (e.g. 5 or 20).
    """
    headers = await get_session_headers(ctx)
    client = await BaseClient.instance("market")
    sym = symbol.strip().upper()
    script_id = await resolve_script_id_async(ctx, sym, exchange=exchange.upper())

    resp = await client.post(
        "feedbroadcast/best-five", json={"scriptId": script_id}, headers=headers
    )
    data = resp.get("data", {}) if isinstance(resp, dict) else {}
    bids = data.get("buy", [])[:depth]
    asks = data.get("sell", [])[:depth]

    return {
        "status": resp.get("status", "OK"),
        "symbol": sym,
        "scriptId": script_id,
        "ltp": data.get("ltp"),
        "bids": bids,
        "asks": asks,
        "data": data,
    }
