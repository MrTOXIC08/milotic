import functools
import inspect
import time
from collections.abc import Callable
from typing import Any

from utils.errors import MiloticError
from utils.logging import logger


def milotic_tool(func: Callable) -> Callable:
    """
    Decorator for Milotic tools to provide standardized logging,
    timing, and error handling.
    """

    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs) -> Any:
        tool_name = func.__name__
        logger.info("tool_call_start", tool=tool_name, params=kwargs)
        start_time = time.perf_counter()
        try:
            result = await func(*args, **kwargs)
            duration = time.perf_counter() - start_time
            logger.info("tool_call_success", tool=tool_name, duration_ms=round(duration * 1000, 2))
            return result
        except MiloticError as e:
            logger.error(
                "tool_call_error_known",
                tool=tool_name,
                error=str(e),
                error_type=e.__class__.__name__,
            )  # noqa: E501
            return {"error": str(e), "category": e.__class__.__name__}
        except Exception as e:
            logger.exception("tool_call_error_unexpected", tool=tool_name, error=str(e))
            return {
                "error": "An internal error occurred while processing the request.",
                "category": "InternalError",
            }  # noqa: E501

    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs) -> Any:
        tool_name = func.__name__
        logger.info("tool_call_start", tool=tool_name, params=kwargs)
        start_time = time.perf_counter()
        try:
            result = func(*args, **kwargs)
            duration = time.perf_counter() - start_time
            logger.info("tool_call_success", tool=tool_name, duration_ms=round(duration * 1000, 2))
            return result
        except MiloticError as e:
            logger.error(
                "tool_call_error_known",
                tool=tool_name,
                error=str(e),
                error_type=e.__class__.__name__,
            )  # noqa: E501
            return {"error": str(e), "category": e.__class__.__name__}
        except Exception as e:
            logger.exception("tool_call_error_unexpected", tool=tool_name, error=str(e))
            return {
                "error": "An internal error occurred while processing the request.",
                "category": "InternalError",
            }  # noqa: E501

    if inspect.iscoroutinefunction(func):
        return async_wrapper
    return sync_wrapper
