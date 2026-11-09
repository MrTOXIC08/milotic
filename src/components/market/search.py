"""Market instrument search and discovery tools."""

import contextlib
import json
from pathlib import Path
from typing import Any

from fastmcp import Context
from fastmcp.tools import tool

from api.base import BaseClient
from utils.decorators import milotic_tool
from utils.session import get_session_headers

KNOWN_SCRIPS: dict[str, dict[str, str]] = {
    "IDEA": {"NSE": "2214366", "BSE": "11532822", "isin": "INE669E01016"},
    "VODAFONE IDEA": {"NSE": "2214366", "BSE": "11532822", "isin": "INE669E01016"},
    "ACC": {"NSE": "2222", "BSE": "11500410", "isin": "INE012A01025"},
    "RELIANCE": {"NSE": "222885", "BSE": "11500325", "isin": "INE002A01018"},
    "TCS": {"NSE": "2211536", "BSE": "11532540", "isin": "INE467B01029"},
    "INFY": {"NSE": "221594", "BSE": "11500209", "isin": "INE009A01021"},
    "HDFCBANK": {"NSE": "221333", "BSE": "11500180", "isin": "INE040A01034"},
    "ICICIBANK": {"NSE": "224963", "BSE": "11532174", "isin": "INE090A01021"},
    "SBIN": {"NSE": "223045", "BSE": "11500112", "isin": "INE062A01020"},
}


def _extract_item_data(item: dict[str, Any], exchange: str) -> dict[str, Any] | None:
    """Normalize raw search item from Axis Direct /search/get-all or portfolio."""
    exchange_upper = exchange.upper()
    symbol = (
        item.get("symbol")
        or item.get("tradingSymbol")
        or item.get("scripName")
        or item.get("securityName")
        or ""
    )
    name = item.get("name") or item.get("companyName") or item.get("scripName") or symbol
    isin = item.get("isin") or item.get("isinNumber") or ""
    segment = item.get("segment") or "EQ"

    ltp_raw = item.get("ltp") or item.get("lastPrice") or item.get("close")
    try:
        ltp = float(ltp_raw) if ltp_raw is not None else None
    except (ValueError, TypeError):
        ltp = None

    # Resolve exchange-specific scriptId
    script_id = None
    sec_info = item.get("securityInfo")
    if isinstance(sec_info, list):
        prefix = "22" if exchange_upper == "NSE" else "11"
        for s in sec_info:
            if isinstance(s, dict):
                s_exch = str(s.get("exchange", "")).upper()
                sid = str(s.get("scriptId") or s.get("scripId") or "")
                if s_exch == exchange_upper or sid.startswith(prefix):
                    script_id = sid
                    break
        if not script_id and sec_info and isinstance(sec_info[0], dict):
            script_id = str(sec_info[0].get("scriptId") or sec_info[0].get("scripId") or "")

    if not script_id and isinstance(item.get("exchangeDetails"), list):
        for ed in item["exchangeDetails"]:
            if isinstance(ed, dict) and str(ed.get("exchange", "")).upper() == exchange_upper:
                script_id = str(ed.get("scriptId") or ed.get("scripId") or "")
                if ed.get("ltp") is not None and ltp is None:
                    with contextlib.suppress(ValueError, TypeError):
                        ltp = float(ed["ltp"])
                break

    if not script_id:
        sid_raw = (
            item.get("scriptId")
            or item.get("scripId")
            or item.get("token")
            or item.get("instrumentToken")
        )
        if sid_raw is not None:
            script_id = str(sid_raw)

    if not script_id or not symbol:
        return None

    return {
        "symbol": str(symbol).strip().upper(),
        "name": str(name).strip(),
        "scriptId": str(script_id),
        "exchange": exchange_upper,
        "segment": str(segment).strip().upper(),
        "isin": str(isin).strip().upper(),
        "ltp": ltp,
    }


async def search_security_id(
    ctx: Context,
    query: str,
    exchange: str = "NSE",
) -> str | None:
    """Query Axis Direct /search/get-all endpoint and resolve best scriptId match."""
    q = query.strip().upper()
    headers: dict[str, str] = {}
    try:
        headers = await get_session_headers(ctx)
    except Exception:
        try:
            sub_id = await ctx.get_state("sub_account_id")
            if sub_id:
                headers = {"x-subAccountId": str(sub_id)}
        except Exception:
            pass

    try:
        client = await BaseClient.instance("investor")
        resp = await client.get(
            "/search/get-all",
            params={"limit": "null", "sort": "null", "query": q, "q": q},
            headers=headers,
        )
        raw_items: list[dict[str, Any]] = []
        if isinstance(resp, list):
            raw_items = resp
        elif isinstance(resp, dict):
            data = resp.get("data", [])
            if isinstance(data, list):
                raw_items = data
            elif isinstance(data, dict):
                raw_items = data.get("entries") or data.get("scrips") or data.get("results") or []

        exact_match: str | None = None
        prefix_match: str | None = None

        for item in raw_items:
            if not isinstance(item, dict):
                continue
            details = _extract_item_data(item, exchange=exchange)
            if not details:
                continue
            sym = details["symbol"]
            name = details["name"].upper()
            if sym == q:
                return details["scriptId"]
            if sym.startswith(q) and not prefix_match:
                prefix_match = details["scriptId"]
            elif q in name and not exact_match:
                exact_match = details["scriptId"]

        return prefix_match or exact_match
    except Exception:
        return None


@tool()
@milotic_tool
async def market_search_instruments(
    ctx: Context,
    query: str,
    exchange: str = "NSE",
    segment: str = "EQ",
) -> dict:
    """
    Search tradeable instruments/scrips by ticker symbol or company name.
    Queries Axis Direct live search API (/search/get-all) and returns matching scrips
    with their scriptId, exchange token, ISIN, and canonical name.
    Useful for resolving scriptId dynamically before placing or modifying orders.
    """
    q = query.strip().upper()
    results: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str]] = set()

    def add_result(entry: dict[str, Any], source: str) -> None:
        key = (entry.get("symbol", ""), entry.get("scriptId", ""))
        if key not in seen_keys:
            seen_keys.add(key)
            item = dict(entry)
            item["source"] = source
            results.append(item)

    # 1. Search in local portfolio holdings first
    try:
        p = Path(".portfolio.json")
        if p.exists():
            data = json.loads(p.read_text())
            for block in data.get("data", []):
                for h in block.get("holdings", []):
                    h_name = h.get("name", "").upper()
                    if q in h_name:
                        for s in h.get("securityInfo", []):
                            entry = {
                                "symbol": h.get("name", "").upper(),
                                "name": h.get("name", ""),
                                "isin": h.get("isin", ""),
                                "scriptId": str(s.get("scriptId", "")),
                                "exchange": exchange.upper(),
                                "segment": segment.upper(),
                                "ltp": None,
                            }
                            add_result(entry, "portfolio")
    except Exception:
        pass

    # 2. Known scrip directory
    for k, v in KNOWN_SCRIPS.items():
        if q == k or q in k:
            sid = v.get(exchange.upper()) or v.get("NSE")
            if sid:
                entry = {
                    "symbol": k,
                    "name": k,
                    "isin": v.get("isin", ""),
                    "scriptId": sid,
                    "exchange": exchange.upper(),
                    "segment": segment.upper(),
                    "ltp": None,
                }
                add_result(entry, "master")

    # 3. Query Axis Direct backend /search/get-all endpoint
    headers: dict[str, str] = {}
    try:
        headers = await get_session_headers(ctx)
    except Exception:
        try:
            sub_id = await ctx.get_state("sub_account_id")
            if sub_id:
                headers = {"x-subAccountId": str(sub_id)}
        except Exception:
            pass

    try:
        client = await BaseClient.instance("investor")
        resp = await client.get(
            "/search/get-all",
            params={"limit": "null", "sort": "null", "query": q, "q": q},
            headers=headers,
        )
        raw_items: list[dict[str, Any]] = []
        if isinstance(resp, list):
            raw_items = resp
        elif isinstance(resp, dict):
            data = resp.get("data", [])
            if isinstance(data, list):
                raw_items = data
            elif isinstance(data, dict):
                raw_items = data.get("entries") or data.get("scrips") or data.get("results") or []

        api_results: list[dict[str, Any]] = []
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            extracted = _extract_item_data(raw, exchange=exchange)
            if not extracted:
                continue
            sym = extracted["symbol"]
            name = extracted["name"].upper()
            isin = extracted["isin"]
            if q in sym or q in name or (isin and q in isin):
                api_results.append(extracted)

        # Sort API results: exact symbol matches first, then prefix, then others
        def sort_priority(item: dict[str, Any]) -> int:
            sym = item["symbol"]
            if sym == q:
                return 0
            if sym.startswith(q):
                return 1
            if q in sym:
                return 2
            if item["name"].upper().startswith(q):
                return 3
            return 4

        api_results.sort(key=sort_priority)
        for r in api_results:
            add_result(r, "search_api")
    except Exception:
        pass

    return {
        "query": query,
        "count": len(results),
        "results": results[:15],
    }
