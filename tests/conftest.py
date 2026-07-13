"""Shared pytest fixtures for all Milotic tests."""

import importlib

import pytest

from api.base import BaseClient


@pytest.fixture(autouse=True)
def reset_client_registry():
    """Clear the BaseClient registry before and after every test."""
    BaseClient.reset()
    yield
    BaseClient.reset()


@pytest.fixture
def mock_env(monkeypatch):
    """Inject all required env vars and reload Settings so BaseClient picks them up."""
    monkeypatch.setenv("CRYPTO_ENABLED", "false")
    monkeypatch.setenv("API_CLIENT_ID", "test-client")
    monkeypatch.setenv("API_SESSION_SECRET", "a" * 32)
    monkeypatch.setenv("ACCOUNT_BACKEND_URL", "http://account.test")
    monkeypatch.setenv("TRADING_BACKEND_URL", "http://trading.test")

    import config as cfg

    importlib.reload(cfg)
