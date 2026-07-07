"""FastMCP entrypoint."""

import os

from app import mcp
from dotenv import load_dotenv

from utils.logging import logger, setup_logging
from utils.constants import NAME, VERSION

# Load environment variables
load_dotenv()

# Initialize logging
setup_logging(os.getenv("LOG_LEVEL", "INFO"))

def main() -> None:
    logger.info("server_starting", name=NAME, version=VERSION)
    mcp.run()

if __name__ == "__main__":
    main()
