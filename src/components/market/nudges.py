"""Market Nudge tools.

Axis exposes corporate actions, earnings, dividends, and market events via:
  GET markettracking/market-nudge/portfolio?limit=10&offset=0&isDashboard=false

Each item includes multi-exchange securityInfo listings (NSE/BSE) and an array of
nudgesData (with label, sentiment, and schedule/announcements).
"""

from typing import Any

from fastmcp import Context
from fastmcp.tools import tool

from api.base import BaseClient
from utils.constants import (
    HEADER_SECURITY_INFO_PROJECTION,
    SECURITY_INFO_PROJECTION_SCRIPT_ID,
)
from utils.decorators import milotic_tool
from utils.session import get_session_headers

_NUDGE_PATH = "markettracking/market-nudge/portfolio"


async def _fetch_raw_nudges(
    client: BaseClient,
    headers: dict[str, str],
    *,
    limit: int,
    offset: int,
    is_dashboard: bool,
) -> list[dict[str, Any]]:
    """Fetch raw market nudges from the investor backend."""
    fetch_headers = {
        **headers,
        HEADER_SECURITY_INFO_PROJECTION: SECURITY_INFO_PROJECTION_SCRIPT_ID,
    }
    resp = await client.get(
        _NUDGE_PATH,
        headers=fetch_headers,
        params={
            "limit": limit,
            "offset": offset,
            "isDashboard": str(is_dashboard).lower(),
        },
    )
    return resp.get("data") or []


def _slim_nudge(entry: dict[str, Any]) -> dict[str, Any]:
    """Slim a raw nudge entry down to key fields to save token budget."""
    security_info = entry.get("securityInfo") or []
    first_sec = security_info[0] if security_info else {}

    symbol = first_sec.get("symbol")
    display_name = first_sec.get("displayName")
    company_name = first_sec.get("securityDescription")

    script_ids = [str(sec["scriptId"]) for sec in security_info if sec.get("scriptId")]
    exchanges = [str(sec["exchange"]) for sec in security_info if sec.get("exchange")]

    nudges_data = entry.get("nudgesData") or []
    slim_nudges = [
        {
            "label": n.get("label"),
            "shortText": n.get("shortText"),
            "longText": n.get("longText"),
            "sentiment": n.get("sentiment"),
            "createdAt": n.get("createdAt"),
        }
        for n in nudges_data
    ]

    return {
        "isin": entry.get("isin"),
        "symbol": symbol,
        "displayName": display_name,
        "companyName": company_name,
        "scriptIds": script_ids,
        "exchanges": exchanges,
        "expireAt": entry.get("expireAt"),
        "nudges": slim_nudges,
    }


def _extract_portfolio_identifiers(
    portfolio: dict[str, Any],
) -> tuple[set[str], set[str]]:
    """Extract all held ISINs and scriptIds across portfolio holdings."""
    held_isins: set[str] = set()
    held_script_ids: set[str] = set()

    for block in portfolio.get("data") or []:
        for holding in block.get("holdings") or []:
            isin = holding.get("isin") or holding.get("isinCode")
            if isin:
                held_isins.add(str(isin).strip())

            for sec in holding.get("securityInfo") or []:
                sid = sec.get("scriptId")
                if sid:
                    held_script_ids.add(str(sid).strip())
                sec_isin = sec.get("isin") or sec.get("isinCode")
                if sec_isin:
                    held_isins.add(str(sec_isin).strip())

    return held_isins, held_script_ids


def _entry_matches_held(
    entry: dict[str, Any], held_isins: set[str], held_script_ids: set[str]
) -> bool:
    """Check if an entry matches held securities by ISIN or scriptId."""
    entry_isin = entry.get("isin")
    if entry_isin and str(entry_isin).strip() in held_isins:
        return True

    for sec in entry.get("securityInfo") or []:
        sid = sec.get("scriptId")
        if sid and str(sid).strip() in held_script_ids:
            return True
        sec_isin = sec.get("isin") or sec.get("isinCode")
        if sec_isin and str(sec_isin).strip() in held_isins:
            return True

    return False


@tool()
@milotic_tool
async def market_get_nudges(
    ctx: Context,
    limit: int = 10,
    offset: int = 0,
    is_dashboard: bool = False,
    label: str | None = None,
    sentiment: str | None = None,
    symbol: str | None = None,
) -> dict:
    """
    Browse Axis market nudges (corporate announcements, board meetings,
    quarterly results, dividend alerts, order wins, etc.) independently.

    Args:
        limit: Number of items to retrieve (default: 10).
        offset: Offset for pagination (default: 0).
        is_dashboard: Whether to query dashboard-specific nudge mode.
        label: Filter by nudge label/type (e.g., 'Dividend', 'Results', 'Order Win').
        sentiment: Filter by sentiment (e.g., 'neutral', 'positive', 'negative').
        symbol: Filter by company stock symbol (e.g., 'LT', 'TATAMOTORS').
    """
    headers = await get_session_headers(ctx)
    client = await BaseClient.instance("investor")
    raw = await _fetch_raw_nudges(
        client,
        headers,
        limit=limit,
        offset=offset,
        is_dashboard=is_dashboard,
    )

    filtered = raw
    if symbol:
        sym_lower = symbol.strip().lower()
        filtered = [
            e
            for e in filtered
            if any(
                str(s.get("symbol", "")).lower() == sym_lower for s in (e.get("securityInfo") or [])
            )
        ]

    if label:
        lbl_lower = label.strip().lower()
        filtered = [
            e
            for e in filtered
            if any(
                lbl_lower in str(n.get("label", "")).lower() for n in (e.get("nudgesData") or [])
            )
        ]

    if sentiment:
        sent_lower = sentiment.strip().lower()
        filtered = [
            e
            for e in filtered
            if any(
                str(n.get("sentiment", "")).lower() == sent_lower
                for n in (e.get("nudgesData") or [])
            )
        ]

    slimmed = [_slim_nudge(e) for e in filtered]
    return {
        "nudges": slimmed,
        "count": len(slimmed),
        "total_returned": len(raw),
    }


@tool()
@milotic_tool
async def market_nudges_for_portfolio(
    ctx: Context,
    limit: int = 50,
    offset: int = 0,
    is_dashboard: bool = False,
    label: str | None = None,
    sentiment: str | None = None,
) -> dict:
    """
    Surface only market nudges that touch stocks currently held in the user's
    portfolio, matched via ISIN and exchange scriptId.
    Each returned entry is marked held=True.

    Args:
        limit: Number of nudges to inspect (default: 50).
        offset: Offset for pagination (default: 0).
        is_dashboard: Whether to query dashboard-specific nudge mode.
        label: Optional filter by nudge label (e.g., 'Dividend', 'Results').
        sentiment: Optional filter by sentiment (e.g., 'positive', 'neutral').
    """
    headers = await get_session_headers(ctx)
    client = await BaseClient.instance("investor")

    # Fetch user's current holdings
    portfolio_headers = {
        **headers,
        HEADER_SECURITY_INFO_PROJECTION: SECURITY_INFO_PROJECTION_SCRIPT_ID,
    }
    portfolio = await client.get("trading/v2/portfolio/multi", headers=portfolio_headers)
    held_isins, held_script_ids = _extract_portfolio_identifiers(portfolio)

    raw = await _fetch_raw_nudges(
        client,
        headers,
        limit=limit,
        offset=offset,
        is_dashboard=is_dashboard,
    )

    matched = []
    for e in raw:
        if _entry_matches_held(e, held_isins, held_script_ids):
            nudges_data = e.get("nudgesData") or []

            if label:
                lbl_lower = label.strip().lower()
                nudges_data = [
                    n for n in nudges_data if lbl_lower in str(n.get("label", "")).lower()
                ]

            if sentiment:
                sent_lower = sentiment.strip().lower()
                nudges_data = [
                    n for n in nudges_data if str(n.get("sentiment", "")).lower() == sent_lower
                ]

            if nudges_data:
                entry_copy = dict(e)
                entry_copy["nudgesData"] = nudges_data
                slim = _slim_nudge(entry_copy)
                slim["held"] = True
                matched.append(slim)

    return {
        "matched": matched,
        "held_securities_count": len(held_isins),
        "matched_count": len(matched),
    }
