"""FastMCP entrypoint."""

import os

from app import mcp
from utils.constants import NAME, VERSION
from utils.logging import logger, setup_logging

# Initialize logging
setup_logging(os.getenv("LOG_LEVEL", "INFO"))


def main() -> None:
    logger.info("server_starting", name=NAME, version=VERSION)
    mcp.run()


if __name__ == "__main__":
    main()
