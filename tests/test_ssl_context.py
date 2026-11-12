import ssl
from unittest.mock import patch

from utils.ssl_context import get_ssl_context


def test_get_ssl_context_default():
    get_ssl_context.cache_clear()
    ctx = get_ssl_context()
    assert isinstance(ctx, ssl.SSLContext)


def test_get_ssl_context_disabled(monkeypatch):
    monkeypatch.setenv("SSL_VERIFY", "false")
    get_ssl_context.cache_clear()
    res = get_ssl_context()
    assert res is False
    get_ssl_context.cache_clear()


def test_get_ssl_context_failure_fallback():
    get_ssl_context.cache_clear()
    with patch("ssl.create_default_context", side_effect=Exception("boom")):
        res = get_ssl_context()
        assert res is True
    get_ssl_context.cache_clear()
