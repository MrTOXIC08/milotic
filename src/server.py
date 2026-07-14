"""FastMCP entrypoint."""

import os

if _port := os.getenv("DEBUGPY_PORT"):
    import debugpy

    debugpy.listen(("127.0.0.1", int(_port)))
    if os.getenv("DEBUGPY_WAIT"):
        debugpy.wait_for_client()

from app import mcp
from utils.constants import NAME, VERSION
from utils.logging import logger, setup_logging

# Initialize logging
setup_logging(os.getenv("LOG_LEVEL", "INFO"))


def main() -> None:
    logger.info("server_starting", name=NAME, version=VERSION)
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    if transport == "stdio":
        mcp.run()
    else:
        port = int(os.getenv("MCP_PORT", "8000"))
        mcp.run(transport=transport, port=port)


if __name__ == "__main__":
    main()
