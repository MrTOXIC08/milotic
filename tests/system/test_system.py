"""Tests for system tools."""

import pytest

from app import mcp


@pytest.mark.asyncio
async def test_tool_registration():
    tools = await mcp.list_tools()
    tool_names = [t.name for t in tools]
    assert "system_get_health" in tool_names


@pytest.mark.asyncio
async def test_tool_naming_convention():
    tools = await mcp.list_tools()
    allowed_categories = {"system", "trading", "books"}
    for tool in tools:
        parts = tool.name.split("_")
        assert len(parts) >= 3, f"Tool '{tool.name}' does not follow category_action_entity."
        assert parts[0] in allowed_categories, f"Unknown category '{parts[0]}' in '{tool.name}'."


@pytest.mark.asyncio
async def test_all_categories_represented():
    """Verify at least one tool is registered from each category."""
    tools = await mcp.list_tools()
    registered_categories = {t.name.split("_")[0] for t in tools}
    expected = {"system", "trading", "books"}
    assert expected == registered_categories, (
        f"Missing categories: {expected - registered_categories}"
    )
