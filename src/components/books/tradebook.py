"""Trade book management tools."""

from typing import Any

from fastmcp import Context
from fastmcp.tools import tool

from api.base import BaseClient
from utils.decorators import milotic_tool
from utils.session import get_session_headers

VALID_TRADE_BOOK_SEGMENTS = {"EQ", "FO", "CURR", "COMM"}


@tool()
@milotic_tool
async def books_get_trade_book(
    ctx: Context,
    segment: str = "EQ",
    oms_order_id: str | None = None,
    order_details: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Fetch the executed trade book showing all individual trade fills, execution timestamps,
    exchange trade IDs, quantities, and execution prices.

    Queries Axis Direct /trading/books/get-trade-book endpoint.

    Parameters:
        segment: Market segment ('EQ', 'FO', 'CURR', 'COMM', defaults to 'EQ').
        oms_order_id: Optional OMS order ID to filter trade fills for a specific order.
        order_details: Optional explicit list of order detail objects.
    """
    seg = segment.strip().upper() if segment else "EQ"
    if seg not in VALID_TRADE_BOOK_SEGMENTS:
        valid_segs = ", ".join(sorted(VALID_TRADE_BOOK_SEGMENTS))
        return {
            "status": "error",
            "message": f"Invalid segment '{segment}'. Must be one of: {valid_segs}.",
        }

    if order_details is not None:
        details = order_details
    elif oms_order_id:
        details = [{"omsOrderId": str(oms_order_id).strip()}]
    else:
        details = [{"omsOrderId": ""}]

    headers = await get_session_headers(ctx)
    client = await BaseClient.instance("investor")
    payload = {
        "segment": seg,
        "orderDetails": details,
    }
    return await client.post("/trading/books/get-trade-book", json=payload, headers=headers)


@tool()
@milotic_tool
async def books_get_trades(
    ctx: Context,
    segment: str = "EQ",
    oms_order_id: str | None = None,
) -> dict[str, Any]:
    """
    Alias for books_get_trade_book to fetch executed trades.
    """
    return await books_get_trade_book(ctx, segment=segment, oms_order_id=oms_order_id)
