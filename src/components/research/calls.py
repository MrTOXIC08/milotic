"""Research and advisory recommendations tools for Milotic Gateway."""

from typing import Any

from fastmcp import Context
from fastmcp.tools import tool

from api.base import BaseClient
from components.books import portfolio as books_portfolio
from utils.constants import CATEGORY_RESEARCH
from utils.decorators import milotic_tool
from utils.session import get_session_headers


def _extract_prices(prices: list[float | int] | None) -> list[float]:
    """Filter out trailing zeroes and return clean non-zero price targets."""
    if not prices:
        return []
    return [float(p) for p in prices if p and p > 0]


def _format_call_summary(entry: dict[str, Any]) -> dict[str, Any]:
    """Format a raw research call entry into a structured, readable summary."""
    exchange_details = entry.get("exchangeDetails") or [{}]
    first_exchange = exchange_details[0] if exchange_details else {}

    return {
        "symbol": entry.get("displayName") or entry.get("symbol", ""),
        "segment": entry.get("segment", "EQ"),
        "call_type": str(entry.get("callType", "")).upper(),
        "call_status": str(entry.get("callStatus", "")).capitalize(),
        "category": entry.get("category"),
        "sub_category": entry.get("subCategory"),
        "entry_price": _extract_prices(entry.get("entryPrice")),
        "target_price": _extract_prices(entry.get("targetPrice")),
        "stop_loss": _extract_prices(entry.get("stopLoss")),
        "target_percentage": entry.get("targetPercentage"),
        "time_duration": entry.get("timeDurationOfInvestment"),
        "time_of_call": entry.get("timeOfCall"),
        "expiry_date": entry.get("expiryDate"),
        "market_cap": entry.get("marketCap"),
        "market_category": entry.get("marketCategory"),
        "ltp": first_exchange.get("ltp"),
        "script_id": first_exchange.get("scriptId"),
        "report_header": entry.get("reportHeader"),
        "report_attachment": entry.get("reportAttachment"),
    }


@tool()
@milotic_tool
async def research_get_config(ctx: Context) -> dict[str, Any]:
    """
    Fetch the research & recommendations configuration and metadata from Axis Direct.

    Returns the latest `configTs` timestamp (required for fetching calls),
    active segment counts (e.g. EQ, FO, COMM), and subcategory breakdowns
    (Long Term, Intraday, Positional, Commodity).
    """
    headers = await get_session_headers(ctx)
    client = await BaseClient.instance(CATEGORY_RESEARCH)

    response = await client.get(
        "markettracking/research-and-recommendations/config", headers=headers
    )
    data = response.get("data", {})

    unified_counts = data.get("unifiedCounts", {})
    return {
        "status": "OK",
        "configTs": data.get("configTs"),
        "lastUpdatedAt": data.get("lastUpdatedAt"),
        "segmentCounts": unified_counts.get("segmentCounts", []),
        "subCategories": unified_counts.get("subCategoryCounts", []),
        "raw_data": data,
    }


@tool()
@milotic_tool
async def research_get_calls(
    ctx: Context,
    sub_category: str | list[str] | None = None,
    call_type: str | list[str] | None = None,
    call_status: str | list[str] | None = "open",
    asset_class: str | list[str] | None = "EQ",
    time_since_call: str | list[str] | None = None,
    expected_return: str | list[str] | None = None,
    near_target: str | list[str] | None = None,
    profit_loss_filter: str | None = None,
    is_emargin_allowed: bool | None = None,
    max_ltp: float | None = None,
    symbol: str | None = None,
    offset: int = 0,
    limit: int = 10,
    sort_by: str = "timeOfCall",
    sort_order: str = "desc",
    config_ts: str | None = None,
) -> dict[str, Any]:
    """
    Fetch active research recommendations and trading/investment ideas from Axis Direct.

    Args:
        sub_category: Filter by investment horizon e.g. "Long Term", "Intraday",
            "Positional", "Commodity".
        call_type: "buy" or "sell".
        call_status: "open", "closed", or None for all. Defaults to "open".
        asset_class: "EQ", "FO", "COMM". Defaults to "EQ".
        time_since_call: Filter e.g. "today".
        expected_return: Return threshold filter e.g. ">20%".
        near_target: Target proximity filter e.g. "Near5%".
        profit_loss_filter: Filter e.g. "PROFIT".
        is_emargin_allowed: Whether E-margin (MTF) is allowed.
        max_ltp: Maximum stock price threshold.
        symbol: Filter results by stock symbol or company name (e.g. "HINDALCO", "IDEA", "ACC").
        offset: Pagination offset. Defaults to 0.
        limit: Number of records to return. Defaults to 10.
        sort_by: Sort field e.g. "timeOfCall", "displayName", "targetPercentage".
        sort_order: "desc" or "asc". Defaults to "desc".
        config_ts: Optional explicit config timestamp. Automatically resolved if omitted.
    """
    headers = await get_session_headers(ctx)
    client = await BaseClient.instance(CATEGORY_RESEARCH)

    resolved_config_ts = config_ts
    if not resolved_config_ts:
        config_res = await client.get(
            "markettracking/research-and-recommendations/config", headers=headers
        )
        resolved_config_ts = config_res.get("data", {}).get("configTs")

    payload: dict[str, Any] = {
        "configTS": resolved_config_ts,
    }

    if call_status:
        payload["callStatus"] = [call_status] if isinstance(call_status, str) else call_status
    if call_type:
        payload["callType"] = [call_type] if isinstance(call_type, str) else call_type
    if asset_class:
        payload["assetClass"] = [asset_class] if isinstance(asset_class, str) else asset_class
    if sub_category:
        payload["subCategory"] = [sub_category] if isinstance(sub_category, str) else sub_category
    if time_since_call:
        payload["timeSinceTheCall"] = (
            [time_since_call] if isinstance(time_since_call, str) else time_since_call
        )
    if expected_return:
        payload["expectedReturn"] = (
            [expected_return] if isinstance(expected_return, str) else expected_return
        )
    if near_target:
        payload["nearTarget"] = [near_target] if isinstance(near_target, str) else near_target
    if profit_loss_filter:
        payload["profitLossFilter"] = profit_loss_filter
    if is_emargin_allowed is not None:
        payload["isEmarginAllowed"] = is_emargin_allowed
    if max_ltp is not None:
        payload["maxLtp"] = max_ltp

    path = (
        f"markettracking/research-and-recommendations/fetch"
        f"?offset={offset}&limit={limit}&sort={sort_order}&sortBy={sort_by}"
    )

    response = await client.post(path, headers=headers, json=payload)
    raw_entries = response.get("data", {}).get("entries", {}).get("entry", [])

    if symbol:
        sym_upper = symbol.strip().upper()
        raw_entries = [
            e
            for e in raw_entries
            if sym_upper in str(e.get("displayName", "")).upper()
            or sym_upper in str(e.get("symbol", "")).upper()
        ]

    formatted_calls = [_format_call_summary(e) for e in raw_entries]

    return {
        "status": "OK",
        "configTs": resolved_config_ts,
        "total_calls": len(formatted_calls),
        "calls": formatted_calls,
        "raw_entries": raw_entries,
    }


@tool()
@milotic_tool
async def research_get_portfolio_calls(ctx: Context) -> dict[str, Any]:
    """
    Cross-reference the user's active portfolio holdings against open research recommendations.

    Checks which stocks in the user's portfolio currently have active BUY/SELL or target updates.
    """
    portfolio_res = await books_portfolio.books_get_portfolio(ctx)
    holdings = portfolio_res.get("data", [{}])[0].get("holdings", [])

    holding_map: dict[str, dict[str, Any]] = {}
    for h in holdings:
        name = str(h.get("name", "")).strip().upper()
        if name:
            holding_map[name] = h

    calls_res = await research_get_calls(
        ctx,
        call_status="open",
        limit=200,
        sort_by="timeOfCall",
        sort_order="desc",
    )
    all_calls = calls_res.get("calls", [])

    matched_calls: list[dict[str, Any]] = []
    for call in all_calls:
        call_sym = str(call.get("symbol", "")).strip().upper()
        if call_sym in holding_map:
            h_info = holding_map[call_sym]
            matched_calls.append(
                {
                    "holding_symbol": call_sym,
                    "holding_quantity": h_info.get("quantity") or h_info.get("totalQty"),
                    "avg_buy_price": h_info.get("averagePrice") or h_info.get("avgPrice"),
                    "current_price": h_info.get("currentPrice"),
                    "current_pnl": h_info.get("unrealizedGain") or h_info.get("unrealizedPl"),
                    "current_pnl_pct": h_info.get("unrealizedGainPercentage"),
                    "invested_amount": h_info.get("investedAmount"),
                    "current_amount": h_info.get("currentAmount"),
                    "call": call,
                }
            )

    return {
        "status": "OK",
        "total_holdings_analyzed": len(holding_map),
        "matching_research_calls_count": len(matched_calls),
        "matched_calls": matched_calls,
    }
