"""Research & recommendations tools.

Axis exposes research as a two-call flow on the investor backend:
  1. GET  markettracking/research-and-recommendations/config  -> data.configTs
  2. POST markettracking/research-and-recommendations/fetch    (body {"configTS": <configTs>})
The config call is required to obtain the configTs that fetch needs, so it runs
internally on every request; it is not its own MCP tool.

Raw fetch entries carry a huge per-entry securityInfo[] block, so every entry is
projected down to essentials before it leaves the tool (see _slim).
"""

from typing import Any

from fastmcp import Context
from fastmcp.tools import tool

from api.base import BaseClient
from utils.constants import (
    HEADER_SECURITY_INFO_PROJECTION,
    SECURITY_INFO_PROJECTION_SCRIPT_ID_SEGMENT,
)
from utils.decorators import milotic_tool
from utils.session import get_session_headers

_CONFIG_PATH = "markettracking/research-and-recommendations/config"
_FETCH_PATH = "markettracking/research-and-recommendations/fetch"

# Fields kept from each raw research entry. Everything else (notably the heavy
# securityInfo[] block) is dropped to keep tool output within the token budget.
_KEEP_FIELDS = (
    "symbol",
    "displayName",
    "callType",
    "callStatus",
    "category",
    "subCategory",
    "segment",
    "entryPrice",
    "targetPrice",
    "stopLoss",
    "targetPercentage",
    "timeDurationOfInvestment",
    "timeOfCall",
    "validity",
    "rationaleOfStock",
    "reportHeader",
)


async def _fetch_recommendations(
    client: BaseClient,
    headers: dict[str, str],
    *,
    limit: int,
    offset: int,
    sort: str,
) -> tuple[list[dict[str, Any]], str]:
    """Run config -> fetch and return (raw entries, config_ts)."""
    config = await client.get(_CONFIG_PATH, headers=headers)
    config_ts = config["data"]["configTs"]

    fetch_headers = {
        **headers,
        HEADER_SECURITY_INFO_PROJECTION: SECURITY_INFO_PROJECTION_SCRIPT_ID_SEGMENT,
    }
    resp = await client.post(
        _FETCH_PATH,
        headers=fetch_headers,
        params={"sort": sort, "limit": limit, "offset": offset},
        json={"configTS": config_ts},
    )
    entries = (resp.get("data", {}).get("entries") or {}).get("entry") or []
    return entries, config_ts


def _script_id(entry: dict[str, Any]) -> str | None:
    """Pull scriptId from exchangeDetails, falling back to securityInfo."""
    for key in ("exchangeDetails", "securityInfo"):
        items = entry.get(key) or []
        if items and items[0].get("scriptId"):
            return str(items[0]["scriptId"])
    return None


def _slim(entry: dict[str, Any]) -> dict[str, Any]:
    """Project one raw entry to essentials; drop the heavy securityInfo bulk."""
    out: dict[str, Any] = {k: entry.get(k) for k in _KEEP_FIELDS}
    ex = (entry.get("exchangeDetails") or [{}])[0]
    out["ltp"] = ex.get("ltp")
    out["exchange"] = ex.get("exchange")
    out["scriptId"] = _script_id(entry)
    return out


def _held_script_ids(portfolio: dict[str, Any]) -> set[str]:
    """Collect every scriptId across all holdings' securityInfo entries."""
    held: set[str] = set()
    for block in portfolio.get("data") or []:
        for holding in block.get("holdings") or []:
            for sec in holding.get("securityInfo") or []:
                sid = sec.get("scriptId")
                if sid:
                    held.add(str(sid))
    return held


@tool()
@milotic_tool
async def research_get_recommendations(
    ctx: Context,
    limit: int = 10,
    offset: int = 0,
    sort: str = "desc",
    segment: str | None = None,
    sub_category: str | None = None,
) -> dict:
    """
    Browse Axis analyst research calls / recommendations independently.
    Returns slimmed entries (symbol, call type, entry/target/stop-loss, LTP, rationale, etc.).
    Optional filters (applied server-side): segment (e.g. 'EQ', 'FO', 'COMM') and
    sub_category (e.g. 'Long Term', 'Intraday', 'Positional', 'Commodity').
    """
    headers = await get_session_headers(ctx)
    client = await BaseClient.instance("investor")
    raw, config_ts = await _fetch_recommendations(
        client, headers, limit=limit, offset=offset, sort=sort
    )

    seg = segment.strip().lower() if segment else None
    sub = sub_category.strip().lower() if sub_category else None
    filtered = [
        e
        for e in raw
        if (seg is None or str(e.get("segment", "")).lower() == seg)
        and (sub is None or str(e.get("subCategory", "")).lower() == sub)
    ]

    recs = [_slim(e) for e in filtered]
    return {"recommendations": recs, "count": len(recs), "config_ts": config_ts}


@tool()
@milotic_tool
async def research_for_portfolio(ctx: Context, limit: int = 50, sort: str = "desc") -> dict:
    """
    Surface only the research calls that touch stocks the user actually holds,
    matched by scriptId. Each returned entry is flagged held=True.
    """
    headers = await get_session_headers(ctx)
    client = await BaseClient.instance("investor")

    portfolio_headers = {
        **headers,
        HEADER_SECURITY_INFO_PROJECTION: SECURITY_INFO_PROJECTION_SCRIPT_ID_SEGMENT,
    }
    portfolio = await client.get("trading/v2/portfolio/multi", headers=portfolio_headers)
    held = _held_script_ids(portfolio)

    raw, config_ts = await _fetch_recommendations(client, headers, limit=limit, offset=0, sort=sort)

    matched = []
    for e in raw:
        if _script_id(e) in held:
            slim = _slim(e)
            slim["held"] = True
            matched.append(slim)

    return {
        "matched": matched,
        "held_count": len(held),
        "matched_count": len(matched),
        "config_ts": config_ts,
    }
