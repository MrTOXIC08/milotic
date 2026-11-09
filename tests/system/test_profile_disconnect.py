"""Tests for system profile and disconnect tools."""

from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
import respx

from components.system.system import system_disconnect_session, system_get_profile


def make_ctx() -> AsyncMock:
    ctx = AsyncMock()

    async def get_state(key: str):
        return {"auth_token": "tok123", "sub_account_id": "sub456"}.get(key)

    ctx.get_state.side_effect = get_state
    return ctx


@pytest.mark.asyncio
async def test_system_get_profile(mock_env):
    ctx = make_ctx()
    with respx.mock(base_url="http://investor.test") as router:
        router.get("/user/profile").mock(
            return_value=httpx.Response(
                200, json={"status": "OK", "data": {"clientName": "Test User"}}
            )
        )
        res = await system_get_profile(ctx)
        assert res["subAccountId"] == "sub456"
        assert res.get("details", {}).get("clientName") == "Test User"


@pytest.mark.asyncio
async def test_system_disconnect_session(mock_env, tmp_path, monkeypatch):
    ctx = make_ctx()
    session_file = tmp_path / ".session.json"
    session_file.write_text('{"auth_token": "abc"}')
    monkeypatch.chdir(tmp_path)

    res = await system_disconnect_session(ctx)
    assert res["status"] == "disconnected"
    assert not Path(".session.json").exists()
    ctx.set_state.assert_any_await("auth_token", None)
