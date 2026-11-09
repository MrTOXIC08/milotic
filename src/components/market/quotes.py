"""Market quote and LTP tools."""

from fastmcp import Context
from fastmcp.tools import tool

from api.base import BaseClient
from utils.decorators import milotic_tool
from utils.session import get_session_headers


@tool()
@milotic_tool
async def market_get_quotes(
    ctx: Context,
    symbols: list[str],
    exchange: str = "NSE",
    segment: str = "EQ",
) -> dict:
    """
    Fetch real-time quotes for one or more securities, including LTP, day high/low, open,
    close, volume, and percentage change.
    """
    headers = await get_session_headers(ctx)
    client = await BaseClient.instance("investor")
    payload = {
        "symbols": [s.strip().upper() for s in symbols],
        "exchange": exchange.upper(),
        "segment": segment.upper(),
    }
    try:
        return await client.post("/market/quotes", json=payload, headers=headers)
    except Exception:
        return await client.get(
            "/quotes", params={"symbols": ",".join(payload["symbols"])}, headers=headers
        )


@tool()
@milotic_tool
async def market_get_ltp(
    ctx: Context,
    symbol: str,
    exchange: str = "NSE",
    segment: str = "EQ",
) -> dict:
    """
    Fetch the Last Traded Price (LTP) and day change for a single security.
    """
    headers = await get_session_headers(ctx)
    client = await BaseClient.instance("investor")
    sym = symbol.strip().upper()
    try:
        return await client.get(
            f"/market/ltp/{sym}",
            params={"exchange": exchange.upper(), "segment": segment.upper()},
            headers=headers,
        )
    except Exception:
        return await client.get(f"/ticker/{sym}", headers=headers)
