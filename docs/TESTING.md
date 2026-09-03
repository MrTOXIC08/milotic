# Milotic Gateway — Testing & Server Guide

Comprehensive guide on running, inspecting, and testing the Milotic Trading MCP Gateway.

---

## Prerequisites & Setup

Ensure dependencies are installed and the local environment is configured:

```bash
# 1. Sync virtual environment and dev dependencies
uv sync --all-extras --dev

# 2. Configure local environment
cp .env.example .env
```

> **Tip for Local Testing**: For offline testing without live backend endpoints, set `CRYPTO_ENABLED=false` in `.env`.

---

## 1. Interactive Testing via MCP Inspector

The recommended way to test Milotic tools interactively in your browser is using the **FastMCP Inspector**.

### Launching the Inspector

Run the following command from the project root:

```bash
uv run fastmcp dev inspector src/app.py:mcp
```

This starts:
1. The **FastMCP dev server** watching `src/` for auto-reloads.
2. The **MCP Inspector Web UI** at `http://localhost:6274` with an auto-generated authentication token.

#### Active Inspector Instance Details
When launched, the server outputs the tokenized Inspector URL:
```text
MCP Inspector Web is up and running at:
   http://localhost:6274?MCP_INSPECTOR_API_TOKEN=<token>

   Sandbox (MCP Apps): http://localhost:<port>/sandbox
   Auth token: <token>
```
* **Default UI Port**: `6274`
* **Access URL**: Open `http://localhost:6274` in your browser and provide the `MCP_INSPECTOR_API_TOKEN` if prompted.

### Testing Tools in Inspector

Once open in your browser (`http://localhost:6274`):

1. **Verify Health**:
   - Select `system_get_health` and click **Run Tool**.
   - Expected Output: `{"status": "ok", "version": "0.1.0", "foundation": "refined", "backend": "not_connected"}`

2. **Test SSO Authentication Flow**:
   - Select `system_connect_start` and click **Run Tool**.
   - It will start a local loopback server on a free port and return a redirect URL.
   - Select `system_connect_verify` with `redirect_url="http://127.0.0.1:<port>/callback?ssoId=TEST_ID"` to simulate callback verification.

3. **Test Safety Preview on Orders**:
   - Select `trading_place_order` with arguments:
     - `symbol`: `"RELIANCE"`
     - `side`: `"buy"`
     - `quantity`: `10`
     - `order_type`: `"limit"`
     - `price`: `2500`
     - `confirmed`: `false`
   - Click **Run Tool**.
   - **Expected Result**: Safety preview returned (`{"preview": true, "message": "Call again with confirmed=True..."}`).
   - Re-run with `confirmed`: `true` to execute the order against the backend.

---

## 2. CLI Inspection & Schema Verification

Verify tool registration, auto-discovery, and input JSON schemas directly from the command line:

```bash
# Verify that all 8 tools register without import errors
uv run fastmcp inspect src/app.py:mcp

# View full JSON schema for all tools
uv run fastmcp inspect src/app.py:mcp --format mcp
```

---

## 3. Running Server for MCP Clients (Stdio & SSE)

### Stdio Transport (Default for Cursor / Claude Desktop)

To run the server in stdio mode:

```bash
uv run python src/server.py
```

#### Cursor Integration Configuration (`.cursor/mcp.json`)

```json
{
  "mcpServers": {
    "milotic": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/absolute/path/to/milotic",
        "python",
        "src/server.py"
      ]
    }
  }
}
```

### SSE Transport (HTTP Server Mode)

To run as an SSE server listening on a TCP port:

```bash
MCP_TRANSPORT=sse MCP_PORT=8000 uv run python src/server.py
```

---

## 4. Automated Testing (Pytest & Ruff)

Run unit and integration contract tests with `pytest`:

```bash
# Run all tests
uv run pytest

# Run specific test suite
uv run pytest tests/test_integration_contracts.py

# Run linter
uv run ruff check .
```

---

## 5. Debugging & Verbose Logging

### Enable Debug Logs

Set `LOG_LEVEL=DEBUG` in `.env` or pass as an environment variable:

```bash
LOG_LEVEL=DEBUG uv run python src/server.py
```

### Remote Debugging with debugpy

To attach a debugger (VS Code, PyCharm, Cursor):

```bash
DEBUGPY_PORT=5678 DEBUGPY_WAIT=1 uv run python src/server.py
```

---

## Summary of Tool Names & Operations

| Category | Tool | Parameters | Purpose |
|---|---|---|---|
| **System** | `system_get_health` | None | Gateway health check |
| **System** | `system_connect_start` | None | Initiates SSO loopback |
| **System** | `system_connect_verify` | `redirect_url` (optional) | Verifies SSO callback |
| **Books** | `books_get_portfolio` | None | Retrieves user holdings |
| **Trading** | `trading_place_order` | `symbol`, `side`, `quantity`, `order_type`, `price`, `confirmed` | Two-step order placement |
| **Trading** | `trading_cancel_order` | `order_id` | Cancels an order |
| **Trading** | `trading_get_order` | `order_id` | Order status lookup |
| **Trading** | `trading_get_all_orders` | None | Full order history |
