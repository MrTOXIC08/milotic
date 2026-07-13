"""System-related tools for Milotic Gateway."""

from fastmcp import Context
from fastmcp.tools import tool

from api.base import BaseClient
from utils.decorators import milotic_tool
from utils.constants import VERSION


@tool()
@milotic_tool
def system_get_health() -> dict[str, str]:
    """
    Return server health status.
    Verifies the gateway is online and correctly configured.
    """
    return {"status": "ok", "version": VERSION, "foundation": "refined", "backend": "not_connected"}


@tool()
@milotic_tool
async def system_connect_start(ctx: Context) -> dict:
    """
    Initiate QR-code authentication. Returns a QR code image to display to the user.
    The user must scan it with their mobile trading app, then call system_connect_verify.
    """
    client = await BaseClient.instance("account")
    # TBD endpoint — confirm against Axis Direct RAPID API docs before production use
    session = await client.post("/auth/qr-session")
    await ctx.set_state("qr_session_id", session["session_id"])
    return {
        "session_id": session["session_id"],
        "qr_image_base64": session.get("qr_image_base64"),
        "message": (
            "Scan this QR code with your mobile trading app, then call system_connect_verify."
        ),
    }


@tool()
@milotic_tool
async def system_connect_verify(ctx: Context) -> dict:
    """
    Check whether QR authentication has been confirmed on the mobile app.
    Call this after the user has scanned the QR code from system_connect_start.
    """
    session_id = await ctx.get_state("qr_session_id")
    if not session_id:
        return {"error": "No pending connection. Call system_connect_start first."}

    client = await BaseClient.instance("account")
    # TBD endpoint — confirm against Axis Direct RAPID API docs before production use
    status = await client.get(f"/auth/qr-status/{session_id}")

    if status.get("status") != "confirmed":
        return {"status": "pending", "message": "Not yet scanned. Try again shortly."}

    await ctx.set_state("auth_token", status["auth_token"])
    await ctx.set_state("sub_account_id", status["sub_account_id"])
    return {"status": "connected", "sub_account_id": status["sub_account_id"]}
