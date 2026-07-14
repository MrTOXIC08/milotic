"""Tests for SSO-based authentication session tools."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

import components.system.system as system_mod
from components.system.system import system_connect_start, system_connect_verify


@pytest.mark.asyncio
@patch("api.base.BaseClient.post", new_callable=AsyncMock)
async def test_system_connect_start_success(mock_post: AsyncMock, mock_env):
    mock_post.return_value = {
        "data": {"redirectURL": "https://auth.uat.asldt.com/sso/validate?ssoId=abc123"}
    }

    ctx = AsyncMock()

    result = await system_connect_start(ctx)

    assert result["redirect_url"] == "https://auth.uat.asldt.com/sso/validate?ssoId=abc123"
    ctx.set_state.assert_not_awaited()


@pytest.mark.asyncio
@patch("api.base.BaseClient.post", new_callable=AsyncMock)
async def test_system_connect_verify_confirmed(mock_post: AsyncMock, mock_env):
    mock_post.return_value = {
        "statusCode": 200,
        "status": "OK",
        "data": {
            "authToken": {"token": "tok123"},
            "refreshToken": {"token": "ref456"},
            "accounts": [{"subAccountId": "sub456", "isPrimary": True}],
        },
    }

    ctx = AsyncMock()

    result = await system_connect_verify(ctx, redirect_url="https://google.com?ssoId=abc123")

    assert result == {"status": "connected", "sub_account_id": "sub456"}
    assert ctx.set_state.await_count == 3
    ctx.set_state.assert_any_await("auth_token", "tok123")
    ctx.set_state.assert_any_await("refresh_token", "ref456")
    ctx.set_state.assert_any_await("sub_account_id", "sub456")


@pytest.mark.asyncio
@patch("api.base.BaseClient.post", new_callable=AsyncMock)
async def test_system_connect_verify_failure(mock_post: AsyncMock, mock_env):
    mock_post.side_effect = Exception("Invalid SSO token")

    ctx = AsyncMock()

    result = await system_connect_verify(ctx, redirect_url="https://google.com?ssoId=abc123")

    assert result["status"] == "failed"
    assert "Invalid SSO token" in result["error"]
    ctx.set_state.assert_awaited_once_with("sso_id", None)


@pytest.mark.asyncio
async def test_system_connect_verify_no_session(mock_env):
    ctx = AsyncMock()

    with patch("api.base.BaseClient.instance", new_callable=AsyncMock) as mock_instance:
        result = await system_connect_verify(ctx, redirect_url=None)

    assert result["status"] == "pending"
    mock_instance.assert_not_awaited()
    ctx.set_state.assert_not_awaited()


@pytest.mark.asyncio
async def test_system_loopback_server_capture():
    port = await system_mod._start_loopback_server()
    assert port > 0

    async with httpx.AsyncClient() as client:
        response = await client.get(f"http://127.0.0.1:{port}/callback?ssoId=capture123")
        assert response.status_code == 200
        assert "Login Successful" in response.text

    assert system_mod._latest_sso_id == "capture123"

    if system_mod._loopback_server:
        system_mod._loopback_server.close()
        system_mod._loopback_server = None
    system_mod._latest_sso_id = None
