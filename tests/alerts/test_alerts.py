"""Tests for Price Alerts tools."""

from unittest.mock import AsyncMock

import httpx
import pytest
import respx

from components.market.alerts import (
    alerts_create_alert,
    alerts_delete_alert,
    alerts_get_alerts,
)


def make_ctx(auth_token: str = "tok123", sub_account_id: str = "sub456") -> AsyncMock:
    """Build mock FastMCP context with session state."""
    ctx = AsyncMock()

    async def get_state(key: str):
        return {"auth_token": auth_token, "sub_account_id": sub_account_id}.get(key)

    ctx.get_state.side_effect = get_state
    return ctx


# ---------------------------------------------------------------------------
# alerts_create_alert tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_alerts_create_alert_with_script_id(mock_env):
    """Verify creating alert with direct script_id."""
    ctx = make_ctx()
    expected_response = {
        "statusCode": 200,
        "status": "OK",
        "data": {"alertId": "alt-12345", "status": "Active"},
    }

    with respx.mock(base_url="http://investor.test") as router:
        route = router.post("/alerts").mock(
            return_value=httpx.Response(200, json=expected_response)
        )

        result = await alerts_create_alert(
            ctx,
            script_id="2214366",
            value=13.0,
            condition="GT",
            status="Active",
            description="IDEA target hit",
        )

        assert result == expected_response
        assert route.called
        sent_request = route.calls.last.request
        assert sent_request.headers["x-authtoken"] == "tok123"
        assert sent_request.headers["x-subaccountid"] == "sub456"

        body = sent_request.read().decode("utf-8")
        import json

        parsed = json.loads(body)
        assert parsed["scriptId"] == "2214366"
        assert parsed["value"] == 13.0
        assert parsed["condition"] == "GT"
        assert parsed["status"] == "Active"
        assert parsed["description"] == "IDEA target hit"


@pytest.mark.asyncio
async def test_alerts_create_alert_with_symbol_resolution(mock_env):
    """Verify creating alert with symbol that resolves to script_id."""
    ctx = make_ctx()
    expected_response = {
        "statusCode": 200,
        "status": "OK",
        "data": {"alertId": "alt-67890", "status": "Active"},
    }

    with respx.mock(base_url="http://investor.test") as router:
        route = router.post("/alerts").mock(
            return_value=httpx.Response(200, json=expected_response)
        )

        # IDEA is statically mapped to 2214366 on NSE
        result = await alerts_create_alert(
            ctx,
            symbol="IDEA",
            value=14.5,
            condition=">",
            exchange="NSE",
        )

        assert result == expected_response
        sent_request = route.calls.last.request
        import json

        parsed = json.loads(sent_request.read().decode("utf-8"))
        assert parsed["scriptId"] == "2214366"
        assert parsed["value"] == 14.5
        assert parsed["condition"] == "GT"


@pytest.mark.asyncio
async def test_alerts_create_alert_condition_normalization(mock_env):
    """Verify various conditions are normalized properly."""
    ctx = make_ctx()

    with respx.mock(base_url="http://investor.test") as router:
        router.post("/alerts").mock(return_value=httpx.Response(200, json={"status": "OK"}))

        # Test '<' -> 'LT'
        res1 = await alerts_create_alert(ctx, script_id="2214366", value=10.0, condition="<")
        assert res1 == {"status": "OK"}

        import json

        last_body = json.loads(router.calls.last.request.read().decode("utf-8"))
        assert last_body["condition"] == "LT"

        # Test '<=' -> 'LTE'
        await alerts_create_alert(ctx, script_id="2214366", value=10.0, condition="<=")
        last_body = json.loads(router.calls.last.request.read().decode("utf-8"))
        assert last_body["condition"] == "LTE"

        # Test '>=' -> 'GTE'
        await alerts_create_alert(ctx, script_id="2214366", value=15.0, condition=">=")
        last_body = json.loads(router.calls.last.request.read().decode("utf-8"))
        assert last_body["condition"] == "GTE"


@pytest.mark.asyncio
async def test_alerts_create_alert_custom_sub_account_id(mock_env):
    """Verify custom sub_account_id parameter overrides session header."""
    ctx = make_ctx(sub_account_id="default123")

    with respx.mock(base_url="http://investor.test") as router:
        route = router.post("/alerts").mock(return_value=httpx.Response(200, json={"status": "OK"}))

        await alerts_create_alert(
            ctx,
            script_id="2214366",
            value=13.0,
            sub_account_id="AXS555",
        )

        sent_request = route.calls.last.request
        assert sent_request.headers["x-subaccountid"] == "AXS555"


@pytest.mark.asyncio
async def test_alerts_create_alert_validations(mock_env):
    """Verify input validation errors for invalid value, condition, and missing identifiers."""
    ctx = make_ctx()

    # Zero or negative value
    res = await alerts_create_alert(ctx, script_id="2214366", value=0)
    assert "error" in res
    assert "positive number" in res["error"]

    res_neg = await alerts_create_alert(ctx, script_id="2214366", value=-5.0)
    assert "error" in res_neg
    assert "positive number" in res_neg["error"]

    # Invalid condition
    res_cond = await alerts_create_alert(ctx, script_id="2214366", value=13.0, condition="INVALID")
    assert "error" in res_cond
    assert "Invalid condition" in res_cond["error"]

    # Missing both symbol and script_id
    res_missing = await alerts_create_alert(ctx, value=13.0)
    assert "error" in res_missing
    assert "Either 'script_id' or 'symbol' must be provided" in res_missing["error"]


@pytest.mark.asyncio
async def test_alerts_create_alert_unauthenticated():
    """Verify BackendConnectionError is returned when user is not connected."""
    ctx = make_ctx(auth_token="")
    res = await alerts_create_alert(ctx, script_id="2214366", value=13.0)
    assert "error" in res
    assert "Not connected" in res["error"]


# ---------------------------------------------------------------------------
# alerts_get_alerts tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_alerts_get_alerts_success(mock_env):
    """Verify fetching list of alerts."""
    ctx = make_ctx(sub_account_id="4433009")
    expected_response = {
        "statusCode": 200,
        "status": "OK",
        "data": [
            {
                "id": "41fd16b5-23d2-4b75-ab6a-cc7b2b12f74f",
                "scriptId": "2214366",
                "value": 13.0,
                "condition": "GT",
                "status": "Active",
            }
        ],
    }

    with respx.mock(base_url="http://investor.test") as router:
        route = router.get("/alerts").mock(return_value=httpx.Response(200, json=expected_response))

        result = await alerts_get_alerts(ctx)
        assert result == expected_response
        sent_request = route.calls.last.request
        assert sent_request.headers["x-authtoken"] == "tok123"
        assert sent_request.headers["x-subaccountid"] == "4433009"


@pytest.mark.asyncio
async def test_alerts_get_alerts_custom_sub_account(mock_env):
    """Verify fetching alerts with sub_account_id parameter."""
    ctx = make_ctx()

    with respx.mock(base_url="http://investor.test") as router:
        route = router.get("/alerts").mock(return_value=httpx.Response(200, json={"data": []}))

        await alerts_get_alerts(ctx, sub_account_id="CUSTOM_SUB")
        sent_request = route.calls.last.request
        assert sent_request.headers["x-subaccountid"] == "CUSTOM_SUB"


# ---------------------------------------------------------------------------
# alerts_delete_alert tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_alerts_delete_alert_success(mock_env):
    """Verify deleting alert via GET /alerts/delete/{alert_id}."""
    ctx = make_ctx(sub_account_id="AXS555")
    alert_id = "41fd16b5-23d2-4b75-ab6a-cc7b2b12f74f"
    expected_response = {"statusCode": 200, "status": "OK", "message": "Alert deleted"}

    with respx.mock(base_url="http://investor.test") as router:
        route = router.get(f"/alerts/delete/{alert_id}").mock(
            return_value=httpx.Response(200, json=expected_response)
        )

        result = await alerts_delete_alert(ctx, alert_id=alert_id)
        assert result == expected_response
        sent_request = route.calls.last.request
        assert sent_request.headers["x-authtoken"] == "tok123"
        assert sent_request.headers["x-subaccountid"] == "AXS555"


@pytest.mark.asyncio
async def test_alerts_delete_alert_fallback_to_http_delete_on_405(mock_env):
    """Verify fallback to HTTP DELETE method if GET endpoint returns 405 Method Not Allowed."""
    ctx = make_ctx()
    alert_id = "alt-delete-405"

    with respx.mock(base_url="http://investor.test") as router:
        router.get(f"/alerts/delete/{alert_id}").mock(return_value=httpx.Response(405))
        del_route = router.delete(f"/alerts/delete/{alert_id}").mock(
            return_value=httpx.Response(200, json={"status": "deleted via DELETE"})
        )

        result = await alerts_delete_alert(ctx, alert_id=alert_id)
        assert result == {"status": "deleted via DELETE"}
        assert del_route.called


@pytest.mark.asyncio
async def test_alerts_delete_alert_empty_id(mock_env):
    """Verify error returned when alert_id is empty."""
    ctx = make_ctx()
    res = await alerts_delete_alert(ctx, alert_id="   ")
    assert "error" in res
    assert "alert_id must not be empty" in res["error"]
