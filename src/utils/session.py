"""Helpers for resolving authenticated session state into request headers."""

from fastmcp import Context

import config as _config
from utils.errors import BackendConnectionError


async def get_session_headers(ctx: Context) -> dict[str, str]:
    """Resolve auth_token + sub_account_id from session state into request headers."""
    auth_token = await ctx.get_state("auth_token")
    sub_account_id = await ctx.get_state("sub_account_id")
    if not auth_token:
        raise BackendConnectionError("Not connected. Call system_connect_start first.")
    headers = {
        _config.settings.TRADING_AUTH_HEADER: auth_token,
    }
    if sub_account_id:
        headers[_config.settings.TRADING_SUB_ACCOUNT_HEADER] = sub_account_id
    return headers
