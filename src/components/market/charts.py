"""Market candlestick and historical chart tools for Equity, Derivatives, and Commodity segments."""

from typing import Any

from fastmcp import Context
from fastmcp.tools import tool

from api.base import BaseClient
from config import settings
from utils.decorators import milotic_tool
from utils.session import get_session_headers

KNOWN_CO_CODES: dict[str, str] = {
    "CDSL": "20139",
    "IDEA": "23040",
    "VODAFONE IDEA": "23040",
    "RELIANCE": "2013",
    "TCS": "11536",
    "INFY": "1594",
    "HDFCBANK": "1333",
    "ICICIBANK": "4963",
    "SBIN": "3045",
    "ACC": "2222",
    "TATAMOTORS": "3456",
}

VALID_EQUITY_PERIODS = {"1", "5", "15", "30", "60", "D", "W", "M"}


@tool()
@milotic_tool
async def market_get_equity_chart(
    ctx: Context,
    co_code: str | int | None = None,
    exchange: str = "NSE",
    period: str = "W",
    count: str | int = "1",
    symbol: str | None = None,
    sub_account_id: str | None = None,
) -> dict[str, Any]:
    """Fetch historical candlestick chart data for Equity (shares/stocks).

    Queries Axis Direct POST /charts/equity endpoint.

    Parameters:
        co_code: Axis Direct company code (coCode, e.g. '20139' for CDSL, '23040' for IDEA).
        exchange: Exchange ('NSE' or 'BSE', defaults to 'NSE').
        period: Aggregation period ('1', '5', '15', '30', '60', 'D', 'W', 'M', defaults to 'W').
        count: Number of periods/bars to return (defaults to '1').
        symbol: Optional stock symbol (e.g. 'CDSL', 'IDEA') used if co_code is omitted.
        sub_account_id: Optional sub-account ID override.
    """
    resolved_code: str | None = None
    if co_code is not None:
        resolved_code = str(co_code).strip()
    elif symbol is not None:
        sym = symbol.strip().upper()
        if sym.isdigit():
            resolved_code = sym
        elif sym in KNOWN_CO_CODES:
            resolved_code = KNOWN_CO_CODES[sym]

    if not resolved_code:
        return {
            "status": "error",
            "message": (
                "Company code 'co_code' is required (e.g. co_code='20139' for CDSL). "
                "Provide a valid co_code or a recognized symbol."
            ),
        }

    payload = {
        "exchange": exchange.strip().upper() if exchange else "NSE",
        "coCode": resolved_code,
        "period": str(period).strip(),
        "count": str(count).strip(),
    }

    headers = await get_session_headers(ctx)
    if sub_account_id:
        headers[settings.CONST_SUB_ACCOUNT_HEADER_KEY] = str(sub_account_id).strip()

    client = await BaseClient.instance("investor")
    return await client.post("/charts/equity", json=payload, headers=headers)


@tool()
@milotic_tool
async def market_get_derivatives_chart(
    ctx: Context,
    symbol: str,
    expiry_date: str,
    instrument_type: str = "OPTIDX",
    opt_type: str | None = None,
    strike_price: str | int | float | None = None,
    period: str = "D1",
    count: str | int | None = None,
    sub_account_id: str | None = None,
) -> dict[str, Any]:
    """Fetch historical candlestick chart data for Futures & Options (Derivatives).

    Queries Axis Direct POST /charts/derivatives endpoint.

    Parameters:
        symbol: Underlying index or stock symbol (e.g. 'BANKNIFTY', 'NIFTY', 'RELIANCE').
        expiry_date: Contract expiry date (e.g. '10-jan-2024', '28-Nov-2024').
        instrument_type: Instrument type ('OPTIDX', 'FUTIDX', 'OPTSTK', 'FUTSTK',
            defaults to 'OPTIDX').
        opt_type: Option type ('CE' or 'PE') for option contracts.
        strike_price: Strike price (e.g. '47300', 47300) for option contracts.
        period: Chart candle interval ('D1', 'D', '1', '5', '15', '60', defaults to 'D1').
        count: Optional count of periods to fetch.
        sub_account_id: Optional sub-account ID override (e.g. 'ASX555').
    """
    if not symbol or not str(symbol).strip():
        return {"status": "error", "message": "'symbol' is required for derivatives chart."}
    if not expiry_date or not str(expiry_date).strip():
        return {"status": "error", "message": "'expiry_date' is required for derivatives chart."}

    itype = str(instrument_type).strip().upper() if instrument_type else "OPTIDX"
    payload: dict[str, Any] = {
        "instrumentType": itype,
        "symbol": str(symbol).strip().upper(),
        "expiryDate": str(expiry_date).strip(),
        "period": str(period).strip(),
    }
    if opt_type:
        payload["optType"] = str(opt_type).strip().upper()
    if strike_price is not None:
        payload["strikePrice"] = str(strike_price).strip()
    if count is not None:
        payload["count"] = str(count).strip()

    headers = await get_session_headers(ctx)
    if sub_account_id:
        headers[settings.CONST_SUB_ACCOUNT_HEADER_KEY] = str(sub_account_id).strip()

    client = await BaseClient.instance("investor")
    return await client.post("/charts/derivatives", json=payload, headers=headers)


@tool()
@milotic_tool
async def market_get_commodity_chart(
    ctx: Context,
    symbol: str,
    expiry_date: str,
    type: str = "FUT",
    exchange: str = "MCX",
    period: str = "d",
    count: str | int = "1",
    sub_account_id: str | None = None,
) -> dict[str, Any]:
    """Fetch historical candlestick chart data for Commodities (MCX Futures / Options).

    Queries Axis Direct POST /charts/commodity endpoint.

    Parameters:
        symbol: Commodity symbol (e.g. 'gold', 'SILVER', 'CRUDEOIL').
        expiry_date: Contract expiry date (e.g. '05-feb-2024').
        type: Contract type ('FUT' or 'OPT', defaults to 'FUT').
        exchange: Commodity exchange (defaults to 'MCX').
        period: Chart candle interval ('d', '1', '5', '15', defaults to 'd').
        count: Number of historical periods to fetch (defaults to '1').
        sub_account_id: Optional sub-account ID override.
    """
    if not symbol or not str(symbol).strip():
        return {"status": "error", "message": "'symbol' is required for commodity chart."}
    if not expiry_date or not str(expiry_date).strip():
        return {"status": "error", "message": "'expiry_date' is required for commodity chart."}

    payload = {
        "type": str(type).strip().upper() if type else "FUT",
        "exchange": str(exchange).strip().upper() if exchange else "MCX",
        "symbol": str(symbol).strip(),
        "expiryDate": str(expiry_date).strip(),
        "period": str(period).strip(),
        "count": str(count).strip(),
    }

    headers = await get_session_headers(ctx)
    if sub_account_id:
        headers[settings.CONST_SUB_ACCOUNT_HEADER_KEY] = str(sub_account_id).strip()

    client = await BaseClient.instance("investor")
    return await client.post("/charts/commodity", json=payload, headers=headers)


@tool()
@milotic_tool
async def market_get_chart(
    ctx: Context,
    asset_class: str = "EQ",
    symbol: str | None = None,
    co_code: str | int | None = None,
    exchange: str = "NSE",
    period: str | None = None,
    count: str | int = "1",
    instrument_type: str = "OPTIDX",
    expiry_date: str | None = None,
    opt_type: str | None = None,
    strike_price: str | int | float | None = None,
    type: str = "FUT",
    sub_account_id: str | None = None,
) -> dict[str, Any]:
    """Unified entry point to fetch candlestick chart data across segments.

    Supports Equity, Derivatives, and Commodity segments.

    Dispatches to:
      - /charts/equity for Equity ('EQ', 'EQUITY', 'STOCK')
      - /charts/derivatives for F&O ('FO', 'DERIVATIVES', 'FNO', 'OPT', 'FUT')
      - /charts/commodity for Commodities ('COMM', 'COMMODITY', 'MCX')

    Parameters:
        asset_class: Asset class ('EQ', 'DERIVATIVES', 'COMMODITY', defaults to 'EQ').
        symbol: Scrip, index, stock or commodity symbol.
        co_code: Axis Direct company code for Equity charts.
        exchange: Exchange ('NSE', 'BSE', 'MCX').
        period: Aggregation period ('W', 'D', 'D1', 'd', '1', '5', '15', '60', 'M').
        count: Number of periods to fetch (defaults to '1').
        instrument_type: Derivative instrument type ('OPTIDX', 'FUTIDX', 'OPTSTK', 'FUTSTK').
        expiry_date: Expiry date for derivatives or commodity contracts.
        opt_type: Option type ('CE' or 'PE').
        strike_price: Option strike price.
        type: Commodity contract type ('FUT' or 'OPT').
        sub_account_id: Optional sub-account ID override.
    """
    normalized_asset = asset_class.strip().upper() if asset_class else "EQ"

    if normalized_asset in {"EQ", "EQUITY", "STOCK", "STK"}:
        p = period if period is not None else "W"
        return await market_get_equity_chart(
            ctx=ctx,
            co_code=co_code,
            exchange=exchange,
            period=p,
            count=count,
            symbol=symbol,
            sub_account_id=sub_account_id,
        )

    if normalized_asset in {"DERIVATIVES", "FO", "FNO", "F&O", "OPT", "FUT"}:
        if not symbol:
            return {
                "status": "error",
                "message": "'symbol' is required for derivatives chart (e.g. 'BANKNIFTY').",
            }
        if not expiry_date:
            return {
                "status": "error",
                "message": "'expiry_date' is required for derivatives chart (e.g. '10-jan-2024').",
            }
        p = period if period is not None else "D1"
        return await market_get_derivatives_chart(
            ctx=ctx,
            symbol=symbol,
            expiry_date=expiry_date,
            instrument_type=instrument_type,
            opt_type=opt_type,
            strike_price=strike_price,
            period=p,
            count=count,
            sub_account_id=sub_account_id,
        )

    if normalized_asset in {"COMMODITY", "COMM", "MCX"}:
        if not symbol:
            return {
                "status": "error",
                "message": "'symbol' is required for commodity chart (e.g. 'gold').",
            }
        if not expiry_date:
            return {
                "status": "error",
                "message": "'expiry_date' is required for commodity chart (e.g. '05-feb-2024').",
            }
        p = period if period is not None else "d"
        exch = exchange if exchange and exchange.upper() != "NSE" else "MCX"
        return await market_get_commodity_chart(
            ctx=ctx,
            symbol=symbol,
            expiry_date=expiry_date,
            type=type,
            exchange=exch,
            period=p,
            count=count,
            sub_account_id=sub_account_id,
        )

    return {
        "status": "error",
        "message": (
            f"Unsupported asset_class '{asset_class}'. "
            "Must be one of: 'EQ' / 'EQUITY', 'DERIVATIVES' / 'FO', 'COMMODITY' / 'COMM'."
        ),
    }
