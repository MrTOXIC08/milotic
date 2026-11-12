"""Price Alerts management tools under Market domain."""

from typing import Any

from fastmcp import Context
from fastmcp.tools import tool

import config as _config
from api.base import BaseClient
from components.books.orders import resolve_script_id_async
from utils.constants import (
    HEADER_SOURCE,
    HEADER_SOURCE_CHANNEL,
)
from utils.decorators import milotic_tool
from utils.errors import BackendConnectionError
from utils.session import get_session_headers

# Canonical condition mapping to ensure robustness with various user inputs
CONDITION_MAP: dict[str, str] = {
    ">": "GT",
    "GT": "GT",
    "GREATER": "GT",
    "GREATER_THAN": "GT",
    "<": "LT",
    "LT": "LT",
    "LESS": "LT",
    "LESS_THAN": "LT",
    ">=": "GTE",
    "GTE": "GTE",
    "<=": "LTE",
    "LTE": "LTE",
    "==": "EQ",
    "=": "EQ",
    "EQ": "EQ",
}


@tool()
@milotic_tool
async def market_create_alert(
    ctx: Context,
    value: float,
    symbol: str | None = None,
    script_id: str | int | None = None,
    condition: str = "GT",
    exchange: str = "NSE",
    status: str = "Active",
    description: str = "",
    sub_account_id: str | None = None,
) -> dict[str, Any]:
    """
    Create a new price alert for a security.

    value: Target price threshold for triggering the alert (e.g. 13.0). Must be > 0.
    symbol: Trading symbol (e.g. 'IDEA', 'RELIANCE', 'TCS').
        Resolved to scriptId if script_id is not given.
    script_id: Exchange instrument scriptId (e.g. '2214366'). Takes precedence if provided.
    condition: Trigger condition ('GT' for greater than, 'LT' for less than, 'GTE', 'LTE', 'EQ').
        Defaults to 'GT'.
    exchange: Exchange for symbol lookup ('NSE' or 'BSE'). Defaults to 'NSE'.
    status: Alert status ('Active', etc.). Defaults to 'Active'.
    description: Optional description / note for this alert. Defaults to ''.
    sub_account_id: Optional sub-account ID override.
    """
    try:
        val = float(value)
        if val <= 0:
            return {"error": "value must be a positive number greater than 0."}
    except (ValueError, TypeError):
        return {"error": "value must be a valid numeric price."}

    cond_key = condition.strip().upper() if condition else "GT"
    normalized_condition = CONDITION_MAP.get(cond_key)
    if not normalized_condition:
        return {
            "error": (
                f"Invalid condition '{condition}'. "
                f"Supported conditions: {', '.join(sorted(set(CONDITION_MAP.values())))}."
            )
        }

    target_script_id: str | None = None
    if script_id is not None:
        target_script_id = str(script_id).strip()
    elif symbol:
        target_script_id = await resolve_script_id_async(
            ctx, symbol.strip().upper(), exchange=exchange.strip().upper()
        )

    if not target_script_id:
        return {"error": "Either 'script_id' or 'symbol' must be provided."}

    headers = await get_session_headers(ctx)
    if sub_account_id:
        headers[_config.settings.CONST_SUB_ACCOUNT_HEADER_KEY] = sub_account_id.strip()

    headers.setdefault(HEADER_SOURCE, "galaxy")
    headers.setdefault(HEADER_SOURCE_CHANNEL, "galaxy")

    payload: dict[str, Any] = {
        "scriptId": str(target_script_id),
        "value": val,
        "condition": normalized_condition,
        "status": status.strip() if status else "Active",
        "description": description or "",
    }

    client = await BaseClient.instance("investor")
    return await client.post("/alerts", json=payload, headers=headers)


@tool()
@milotic_tool
async def market_get_alerts(
    ctx: Context,
    sub_account_id: str | None = None,
) -> dict[str, Any] | list[Any]:
    """
    Fetch all active price alerts configured for the user account.

    sub_account_id: Optional sub-account ID override.
    """
    headers = await get_session_headers(ctx)
    if sub_account_id:
        headers[_config.settings.CONST_SUB_ACCOUNT_HEADER_KEY] = sub_account_id.strip()

    client = await BaseClient.instance("investor")
    return await client.get("/alerts", headers=headers)


@tool()
@milotic_tool
async def market_delete_alert(
    ctx: Context,
    alert_id: str,
    sub_account_id: str | None = None,
) -> dict[str, Any]:
    """
    Delete an existing price alert by its alert ID or UUID.

    alert_id: Unique alert identifier (e.g. '41fd16b5-23d2-4b75-ab6a-cc7b2b12f74f').
    sub_account_id: Optional sub-account ID override.
    """
    clean_id = alert_id.strip()
    if not clean_id:
        return {"error": "alert_id must not be empty."}

    headers = await get_session_headers(ctx)
    if sub_account_id:
        headers[_config.settings.CONST_SUB_ACCOUNT_HEADER_KEY] = sub_account_id.strip()

    client = await BaseClient.instance("investor")
    try:
        return await client.get(f"/alerts/delete/{clean_id}", headers=headers)
    except BackendConnectionError as e:
        if "405" in str(e):
            return await client.delete(f"/alerts/delete/{clean_id}", headers=headers)
        raise


# Python aliases for direct functional usage
alerts_create_alert = market_create_alert
alerts_get_alerts = market_get_alerts
alerts_delete_alert = market_delete_alert
