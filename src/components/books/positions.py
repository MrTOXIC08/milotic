"""Positions management tools."""

import asyncio

from fastmcp import Context
from fastmcp.tools import tool

from api.base import BaseClient
from utils.constants import (
    HEADER_SECURITY_INFO_PROJECTION,
    SECURITY_INFO_PROJECTION_POSITIONS,
)
from utils.decorators import milotic_tool
from utils.session import get_session_headers


@tool()
@milotic_tool
async def books_get_positions(
    ctx: Context,
    segment: str = "EQ",
    position_type: str = "all",
    interop: bool | None = None,
) -> dict:
    """
    Fetch active intraday and open F&O / commodity / equity positions with live
    Mark-to-Market (MTM) P&L, buy/sell quantities, prices, lot sizes, and security details.
    segment: 'EQ', 'FO', 'COMM', 'CURR' (defaults to 'EQ').
    position_type: 'all', 'daily', or 'expiry' (defaults to 'all').
        - 'all': fetches both intraday ('daily') and carryforward ('expiry') open positions.
        - 'daily': only positions/trades initiated today during the current trading session.
        - 'expiry': carryforward open delivery / EMARGIN / F&O positions across expiry cycles.
    interop: Exchange interoperability enabled (defaults to True for EQ/FO, False for COMM).
    """
    seg = segment.strip().upper() if segment else "EQ"

    if interop is None:
        interop = seg != "COMM"

    p_type = position_type.strip().lower() if position_type else "all"

    headers = await get_session_headers(ctx)
    headers[HEADER_SECURITY_INFO_PROJECTION] = SECURITY_INFO_PROJECTION_POSITIONS

    client = await BaseClient.instance("investor")

    if p_type == "all":
        res_daily, res_expiry = await asyncio.gather(
            client.post(
                "/trading/portfolio/get-positions",
                json={"interop": interop, "segment": seg, "type": "daily"},
                headers=headers,
            ),
            client.post(
                "/trading/portfolio/get-positions",
                json={"interop": interop, "segment": seg, "type": "expiry"},
                headers=headers,
            ),
            return_exceptions=True,
        )

        daily_data = (
            res_daily.get("data", [])
            if isinstance(res_daily, dict) and isinstance(res_daily.get("data"), list)
            else []
        )
        expiry_data = (
            res_expiry.get("data", [])
            if isinstance(res_expiry, dict) and isinstance(res_expiry.get("data"), list)
            else []
        )

        return {
            "status": "OK",
            "statusCode": 200,
            "data": {
                "daily": daily_data,
                "expiry": expiry_data,
            },
            "summary": {
                "dailyCount": len(daily_data),
                "expiryCount": len(expiry_data),
                "totalCount": len(daily_data) + len(expiry_data),
            },
        }

    payload = {
        "interop": interop,
        "segment": seg,
        "type": p_type,
    }
    return await client.post("/trading/portfolio/get-positions", json=payload, headers=headers)


@tool()
@milotic_tool
async def trading_convert_position(
    ctx: Context,
    symbol: str,
    quantity: int,
    from_product: str,
    to_product: str,
    side: str = "buy",
    exchange: str = "NSE",
    segment: str = "EQ",
    confirmed: bool = False,
) -> dict:
    """
    Convert an open position product type (e.g. Intraday/MIS to Delivery/CNC/MTF or vice-versa).
    ALWAYS call with confirmed=False first to preview, then confirmed=True after user approval.
    """
    if quantity <= 0:
        return {"error": "quantity must be positive"}

    sym = symbol.strip().upper()
    from_p = from_product.upper()
    to_p = to_product.upper()
    side_norm = side.upper()

    if not confirmed:
        return {
            "preview": True,
            "symbol": sym,
            "quantity": quantity,
            "side": side_norm,
            "from_product": from_p,
            "to_product": to_p,
            "exchange": exchange.upper(),
            "segment": segment.upper(),
            "message": "Call again with confirmed=True to execute position conversion.",
        }

    headers = await get_session_headers(ctx)
    client = await BaseClient.instance("investor")
    payload = {
        "symbol": sym,
        "quantity": quantity,
        "transactionType": side_norm,
        "fromProductType": from_p,
        "toProductType": to_p,
        "exchange": exchange.upper(),
        "segment": segment.upper(),
    }
    return await client.post("/trading/orders/convert-position", json=payload, headers=headers)
