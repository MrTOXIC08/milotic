#!/usr/bin/env zsh
# =============================================================================
# Milotic MCP — Automated Installer
# Wires: Cursor · Claude Desktop · Gemini CLI
# Usage: ./install.sh
# =============================================================================

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"

# ── Colours ──────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; RESET='\033[0m'
info()    { echo "${GREEN}[✔]${RESET} $*"; }
warn()    { echo "${YELLOW}[!]${RESET} $*"; }
error()   { echo "${RED}[✘]${RESET} $*"; exit 1; }

# Absolute path required — GUI apps (Cursor/Claude) do not inherit shell PATH.
resolve_uv() {
  if command -v uv &>/dev/null; then
    command -v uv
  elif [ -x "$HOME/.local/bin/uv" ]; then
    echo "$HOME/.local/bin/uv"
  else
    echo "uv"
  fi
}

# Merge milotic into any MCP-style JSON config that uses "mcpServers".
# Args: <config_path> <label>
merge_mcp_config() {
  local config_path="$1"
  local label="$2"
  local uv_bin
  local config_dir
  uv_bin="$(resolve_uv)"
  config_dir="$(dirname "$config_path")"
  mkdir -p "$config_dir"

  python3 - "$config_path" "$REPO_DIR" "$label" "$uv_bin" <<'PY'
import json
import os
import sys

config_path, repo_dir, label, uv_bin = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
entry = {
    "command": uv_bin,
    "args": ["run", "--no-sync", "--directory", repo_dir, "python", "src/server.py"],
    "env": {"PYTHONPATH": "src"},
}

if os.path.exists(config_path):
    with open(config_path) as f:
        try:
            config = json.load(f)
        except json.JSONDecodeError:
            config = {}
    action = f"Updated {label}"
else:
    config = {}
    action = f"Created {label}"

config.setdefault("mcpServers", {})["milotic"] = entry

with open(config_path, "w") as f:
    json.dump(config, f, indent=2)
    f.write("\n")

print(f"  {action}: {config_path}")
PY
  info "$label config ready: $config_path"
}

echo ""
echo "══════════════════════════════════════"
echo "   Milotic MCP — Installer"
echo "══════════════════════════════════════"
echo ""

# ── Step 1: Install uv if missing ─────────────────────────────────────────────
if ! command -v uv &>/dev/null; then
  warn "uv not found — installing via official installer..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
  if ! command -v uv &>/dev/null; then
    error "uv installation failed. Please install manually: https://docs.astral.sh/uv/getting-started/installation/"
  fi
  info "uv installed: $(uv --version)"
else
  info "uv already installed: $(uv --version)"
fi

# ── Step 2: Ensure Python 3.12+ is available ──────────────────────────────────
if ! uv python list 2>/dev/null | grep -qE "3\.(12|13|14)"; then
  warn "Python 3.12 not found — installing via uv..."
  uv python install 3.12
fi
info "Python OK: $(uv run python --version 2>/dev/null || echo 'available via uv')"

# ── Step 3: Sync dependencies ─────────────────────────────────────────────────
info "Syncing dependencies (uv sync --all-extras --dev)..."
cd "$REPO_DIR"
uv sync --all-extras --dev
info "Dependencies synced."

# ── Step 4: Set up .env ───────────────────────────────────────────────────────
if [ ! -f "$REPO_DIR/.env" ]; then
  cp "$REPO_DIR/.env.example" "$REPO_DIR/.env"
  warn ".env created from .env.example — please fill in your credentials:"
  warn "  $REPO_DIR/.env"
else
  info ".env already exists — skipping."
fi

# ── Step 5: Wire MCP clients ──────────────────────────────────────────────────
echo ""
info "Configuring MCP clients..."

# Cursor — ~/.cursor/mcp.json
merge_mcp_config "$HOME/.cursor/mcp.json" "Cursor"

# Claude Desktop — macOS / Linux paths
case "$(uname -s)" in
  Darwin)
    CLAUDE_CFG="$HOME/Library/Application Support/Claude/claude_desktop_config.json"
    ;;
  *)
    CLAUDE_CFG="$HOME/.config/Claude/claude_desktop_config.json"
    ;;
esac
merge_mcp_config "$CLAUDE_CFG" "Claude Desktop"

# Gemini CLI — ~/.gemini/settings.json
merge_mcp_config "$HOME/.gemini/settings.json" "Gemini CLI"

# ── Step 6: Fix project .mcp.json cwd to this machine ─────────────────────────
LOCAL_MCP_JSON="$REPO_DIR/.mcp.json"
if [ -f "$LOCAL_MCP_JSON" ]; then
  python3 - <<PYEOF
import json

local_mcp = "$LOCAL_MCP_JSON"
repo_dir  = "$REPO_DIR"

with open(local_mcp) as f:
    cfg = json.load(f)

updated = False
for name, server in cfg.get("mcpServers", {}).items():
    if server.get("cwd") != repo_dir:
        server["cwd"] = repo_dir
        updated = True

if updated:
    with open(local_mcp, "w") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")
    print("  Patched .mcp.json cwd →", repo_dir)
else:
    print("  .mcp.json cwd already correct.")
PYEOF
  info ".mcp.json patched."
fi

# ── Step 7: Smoke test — inspect MCP tools ────────────────────────────────────
echo ""
info "Verifying MCP tool registration..."
uv run fastmcp inspect src/app.py:mcp 2>/dev/null || warn "fastmcp inspect failed — check src/app.py"

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════"
echo "   Installation Complete!"
echo "══════════════════════════════════════"
echo ""
echo "  Next steps:"
echo "  1. Edit .env with your credentials:"
echo "       $REPO_DIR/.env"
echo ""
echo "  2. Reload / restart your client(s):"
echo "       • Cursor        → Cmd+Shift+P → 'Reload Window'"
echo "       • Claude Desktop → Quit & reopen the app"
echo "       • Gemini CLI     → restart the CLI session"
echo ""
echo "  Config files written:"
echo "       Cursor         $HOME/.cursor/mcp.json"
echo "       Claude Desktop $CLAUDE_CFG"
echo "       Gemini CLI     $HOME/.gemini/settings.json"
echo ""
echo "  Manual run:"
echo "       uv run python src/server.py"
echo ""
