import logging
import re
import sys
from typing import Any

import structlog

# Keywords that trigger redaction in log values
SECRET_KEYWORDS = ["secret", "token", "password", "key", "payload", "encryption", "signature"]
REDACTION_PATTERN = re.compile("|".join(f"\\b{key}\\b" for key in SECRET_KEYWORDS), re.IGNORECASE)


def redact_secrets_processor(_, __, event_dict: dict[str, Any]) -> dict[str, Any]:
    """
    A structlog processor to recursively redact sensitive information from logs.
    """
    for key, value in event_dict.items():
        if isinstance(value, dict):
            # Recurse into nested dictionaries
            event_dict[key] = redact_secrets_processor(_, __, value)
        elif REDACTION_PATTERN.search(key):
            event_dict[key] = "[REDACTED]"
    return event_dict


def setup_logging(log_level: str = "INFO"):
    """Configure structlog for structured JSON logging with secret redaction."""
    level_num = getattr(logging, log_level.upper(), logging.INFO)

    # Standard library logging configuration
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stderr,
        level=level_num,
    )

    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        redact_secrets_processor,  # Add our custom processor
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    if sys.stderr.isatty():
        # Pretty console output for local dev
        processors.append(structlog.dev.ConsoleRenderer())
    else:
        # Structured JSON for production/CI
        processors.append(structlog.processors.JSONRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(level_num),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )


logger = structlog.get_logger()
