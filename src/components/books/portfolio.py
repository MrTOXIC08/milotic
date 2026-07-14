"""Portfolio holdings tools."""

from fastmcp import Context
from fastmcp.tools import tool

from api.base import BaseClient
from utils.constants import (
    HEADER_SECURITY_INFO_PROJECTION,
    SECURITY_INFO_PROJECTION_SCRIPT_ID,
)
from utils.decorators import milotic_tool
from utils.session import get_session_headers


@tool()
@milotic_tool
async def books_get_portfolio(ctx: Context) -> dict:
    """
    Fetch the authenticated user's portfolio holdings, including asset allocation,
    unrealized gain/loss, average buy price, current market value, and daily P&L.
    """
    headers = await get_session_headers(ctx)
    # ponytail: append projection header using global constants
    headers[HEADER_SECURITY_INFO_PROJECTION] = SECURITY_INFO_PROJECTION_SCRIPT_ID

    client = await BaseClient.instance("investor")
    # ponytail: call portfolio multi endpoint
    return await client.get("trading/v2/portfolio/multi", headers=headers)
