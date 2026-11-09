"""Utility functions and directory for resolving equity script IDs."""

import json
from pathlib import Path
from typing import Any

from fastmcp import Context

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
    "NTPC": {"NSE": "2211630", "BSE": "11532555", "isin": "INE733E01010"},
}


def resolve_script_id(symbol: str, exchange: str = "NSE") -> str:
    """Resolve an exchange-specific scriptId from symbol, portfolio, or known scrips."""
    sym = symbol.strip().upper()
    if sym.isdigit():
        return sym

    exchange_upper = exchange.strip().upper()
    if sym in KNOWN_SCRIPS and exchange_upper in KNOWN_SCRIPS[sym]:
        return KNOWN_SCRIPS[sym][exchange_upper]

    try:
        p = Path(".portfolio.json")
        if p.exists():
            data: dict[str, Any] = json.loads(p.read_text())
            for h in data.get("data", [{}])[0].get("holdings", []):
                h_name = h.get("name", "").upper()
                if sym == h_name or sym in h_name:
                    sec_info = h.get("securityInfo", [])
                    prefix = "22" if exchange_upper == "NSE" else "11"
                    for s in sec_info:
                        sid = str(s.get("scriptId", ""))
                        if sid.startswith(prefix):
                            return sid
                    if sec_info:
                        return str(sec_info[0].get("scriptId", ""))
    except Exception:
        pass
    return sym


async def resolve_script_id_async(ctx: Context, symbol: str, exchange: str = "NSE") -> str:
    """
    Resolve an exchange-specific scriptId asynchronously.
    First checks local static scrips & portfolio, then falls back to Axis Direct
    live search API (/search/get-all). Returns symbol unchanged if unresolvable.
    """
    sym = symbol.strip().upper()
    if sym.isdigit():
        return sym

    exchange_upper = exchange.strip().upper()
    local_resolved = resolve_script_id(sym, exchange=exchange_upper)
    if local_resolved != sym:
        return local_resolved

    try:
        from components.market.search import search_security_id

        api_resolved = await search_security_id(ctx, sym, exchange=exchange_upper)
        if api_resolved:
            return api_resolved
    except Exception:
        pass

    return sym

