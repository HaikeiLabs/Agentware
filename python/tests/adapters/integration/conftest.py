"""Integration test configuration for adapters."""

import os

import pytest


@pytest.fixture
def kitaru_url() -> str:
    """Kitaru server URL from environment or default."""
    return os.environ.get("KITARU_URL", "http://localhost:8081")


@pytest.fixture
def llm_endpoint() -> str:
    """LLM endpoint for integration tests (Qwen3.6)."""
    return os.environ.get("LLM_ENDPOINT", "http://localhost:8080/v1")


@pytest.fixture
def llm_api_key() -> str:
    """LLM API key."""
    return os.environ.get("LLM_API_KEY", "test-key")


@pytest.fixture
def hermes_path() -> str:
    """Path to hermes CLI."""
    return os.environ.get("HERMES_PATH", "hermes")
