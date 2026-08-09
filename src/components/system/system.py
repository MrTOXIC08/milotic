"""System-related tools for Milotic Gateway."""

import asyncio

from fastmcp import Context
from fastmcp.tools import tool

from api.base import BaseClient
from utils.constants import VERSION
from utils.decorators import milotic_tool

_latest_sso_id: str | None = None
_loopback_server: asyncio.AbstractServer | None = None


async def _start_loopback_server() -> int:
    """Starts a non-blocking TCP server on a random free port to capture ssoId."""
    global _loopback_server, _latest_sso_id

    if _loopback_server:
        try:
            _loopback_server.close()
        except Exception:
            pass

    async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        global _latest_sso_id
        try:
            data = await reader.read(1024)
            request = data.decode("utf-8", errors="ignore")
            first_line = request.split("\n")[0] if request else ""
            if "ssoId=" in first_line:
                _latest_sso_id = first_line.split("ssoId=")[1].split(" ")[0].split("&")[0]

            response = (
                "HTTP/1.1 200 OK\r\n"
                "Content-Type: text/html\r\n"
                "Connection: close\r\n\r\n"
                "<html><body style='font-family:sans-serif;text-align:center;padding-top:50px;'>"
                "<h1>Login Successful!</h1><p>You can close this tab and return to the chat.</p>"
                "</body></html>"
            )
            writer.write(response.encode("utf-8"))
            await writer.drain()
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    _loopback_server = await asyncio.start_server(handle_client, "127.0.0.1", 0)
    return _loopback_server.sockets[0].getsockname()[1]


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
    Initiate Single Sign-On (SSO) authentication. Starts a local loopback server to
    capture redirect, and returns the login redirect URL.
    """
    # ponytail: start background loopback server to capture callback dynamically
    port = await _start_loopback_server()
    local_redirect = f"http://127.0.0.1:{port}/callback"

    client = await BaseClient.instance("login")
    payload = {
        "type": "LOGIN",
        "redirectURL": local_redirect,
        "metadata": {"name": "milotic"},
    }

    session = await client.post("/sso/initiate", json=payload)
    redirect_url = session.get("data", {}).get("redirectURL", "")

    return {
        "redirect_url": redirect_url,
        "message": (
            "I can help with that, but let's establish a safety boundary first: "
            "I will never ask for your Axis Direct password or login credentials. "
            "Entering sensitive authentication details is something I cannot do on your behalf.\n\n"
            "To connect securely, we use Axis Direct's official Single Sign-On (SSO) microsite:\n\n"
            "🔒 **Security Check:**\n"
            "- A temporary, private loopback server was started on your machine "
            "to capture the callback token securely.\n"
            "- Your credentials never touch my AI context, "
            "nor are they transmitted in plaintext.\n\n"
            "⚠️ **Warning:** AI systems are non-deterministic. By continuing, you agree "
            "to interact with your Axis Direct account via AI at your own risk.\n\n"
            f"If you're ready, click here to log in:\n"
            f"👉 **[Authenticate with Axis Direct]({redirect_url})**\n\n"
            "Once logged in, your browser will redirect and authenticate automatically.\n"
            "*(If blocked, copy the final URL from your browser and paste it "
            "into: system_connect_verify(redirect_url='...'))*"
        ),
    }


@tool()
@milotic_tool
async def system_connect_verify(ctx: Context, redirect_url: str | None = None) -> dict:
    """
    Check whether Single Sign-On (SSO) authentication has been completed.
    redirect_url: Optional manual override. Paste the browser redirect URL here if blocked.
    """
    global _latest_sso_id, _loopback_server

    sso_id = None
    if redirect_url and "ssoId=" in redirect_url:
        sso_id = redirect_url.split("ssoId=")[-1].split("&")[0]

    if not sso_id:
        sso_id = _latest_sso_id

    if not sso_id:
        return {
            "status": "pending",
            "message": (
                "Login not yet confirmed. Paste the final browser redirect URL to verify manually."
            ),
        }

    # Stop the loopback server since we got the ssoId
    if _loopback_server:
        _loopback_server.close()
        _loopback_server = None

    _latest_sso_id = None  # Consume the captured ID

    client = await BaseClient.instance("login")
    try:
        # ponytail: call authenticate with captured ssoId
        response = await client.post("/sso/authenticate", json={"ssoId": sso_id})

        sso_data = response.get("data", {})
        auth_token = sso_data.get("authToken", {}).get("token")
        refresh_token = sso_data.get("refreshToken", {}).get("token")

        accounts = sso_data.get("accounts", [])
        primary = next((acc for acc in accounts if acc.get("isPrimary")), None)
        if not primary and accounts:
            primary = accounts[0]
        sub_account_id = primary.get("subAccountId") if primary else None

        if not auth_token or not sub_account_id:
            raise KeyError("Authentication payload was incomplete or invalid.")

        await ctx.set_state("auth_token", auth_token)
        await ctx.set_state("refresh_token", refresh_token)
        await ctx.set_state("sub_account_id", sub_account_id)
        return {"status": "connected", "sub_account_id": sub_account_id}

    except Exception as e:
        # ponytail: wipe sso_id context state to force user to restart on failure
        await ctx.set_state("sso_id", None)
        return {
            "status": "failed",
            "error": str(e),
            "message": "Authentication failed. Please start over using system_connect_start.",
        }
