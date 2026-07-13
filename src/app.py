"""FastMCP app instance configuration."""

from pathlib import Path

from fastmcp import FastMCP
from fastmcp.server.providers import FileSystemProvider

_components = Path(__file__).parent / "components"

mcp = FastMCP(
    "Milotic",
    providers=[
        FileSystemProvider(root=_components / "system", reload=True),
        FileSystemProvider(root=_components / "trading", reload=True),
    ],
)
