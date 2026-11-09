"""Market depth and order book tools."""

from fastmcp import Context
from fastmcp.tools import tool

from api.base import BaseClient
from utils.decorators import milotic_tool
from utils.session import get_session_headers


@tool()
@milotic_tool
async def market_get_depth(
    ctx: Context,
    symbol: str,
    depth: int = 5,
    exchange: str = "NSE",
) -> dict:
    """
    Fetch Level-2 market depth (top bid and ask price levels, quantities, and order counts).
    depth: number of price levels (e.g. 5 or 20).
    """
    headers = await get_session_headers(ctx)
    client = await BaseClient.instance("investor")
    sym = symbol.strip().upper()
    params = {"depth": depth, "exchange": exchange.upper()}
    try:
        return await client.get(f"/market/orderbook/{sym}", params=params, headers=headers)
    except Exception:
        return await client.get(f"/orderbook/{sym}", params=params, headers=headers)
