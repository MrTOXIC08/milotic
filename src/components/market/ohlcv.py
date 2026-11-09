"""Market historical OHLCV candlestick data tools."""

from fastmcp import Context
from fastmcp.tools import tool

from api.base import BaseClient
from utils.decorators import milotic_tool
from utils.session import get_session_headers


@tool()
@milotic_tool
async def market_get_ohlcv(
    ctx: Context,
    symbol: str,
    interval: str = "1d",
    limit: int = 100,
    exchange: str = "NSE",
) -> dict:
    """
    Fetch historical candlestick (OHLCV) data for charting, trend analysis, or technical indicators.
    interval: '1m', '5m', '15m', '1h', '1d', '1w' (defaults to '1d').
    limit: Number of candles to return (1-500, defaults to 100).
    """
    headers = await get_session_headers(ctx)
    client = await BaseClient.instance("investor")
    sym = symbol.strip().upper()
    params = {
        "interval": interval,
        "limit": min(max(1, limit), 500),
        "exchange": exchange.upper(),
    }
    try:
        return await client.get(f"/market/ohlcv/{sym}", params=params, headers=headers)
    except Exception:
        return await client.get(f"/ohlcv/{sym}", params=params, headers=headers)
