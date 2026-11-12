"""SSL context helper for corporate proxy and keychain certificate resolution."""

import os
import ssl
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

import certifi

from utils.logging import logger


@lru_cache(maxsize=1)
def get_ssl_context() -> ssl.SSLContext | bool | str:
    """
    Return an SSLContext (or bool/str for httpx verify) that trusts standard
    public CA certificates and system keychain certificates (e.g., corporate
    Zscaler/proxy root CAs on macOS).
    """
    # Check for explicit environment override
    ssl_verify_env = os.environ.get("SSL_VERIFY")
    if ssl_verify_env is not None:
        val = ssl_verify_env.strip().lower()
        if val in ("false", "0", "no"):
            return False
        if Path(ssl_verify_env).exists():
            return ssl_verify_env

    try:
        ctx = ssl.create_default_context(cafile=certifi.where())

        # If custom SSL_CERT_FILE is set in environment, load it as well
        custom_cert_file = os.environ.get("SSL_CERT_FILE")
        if custom_cert_file and Path(custom_cert_file).exists():
            ctx.load_verify_locations(cafile=custom_cert_file)

        # On macOS, extract certificates from the system keychain so
        # corporate proxies (e.g. Zscaler) are trusted
        if sys.platform == "darwin":
            try:
                res = subprocess.run(
                    ["security", "find-certificate", "-a", "-p"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                )
                if res.returncode == 0 and res.stdout:
                    ctx.load_verify_locations(None, None, res.stdout)
            except Exception as e:
                logger.debug("keychain_cert_load_failed", error=str(e))

        return ctx
    except Exception as e:
        logger.warning("ssl_context_init_failed", error=str(e))
        return True
