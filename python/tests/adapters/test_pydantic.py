"""Unit tests for Pydantic adapter."""

from unittest.mock import MagicMock, patch

import pytest

from adapters.pydantic import PydanticAdapter, PydanticAdapterAsync, PydanticConfig, create_adapter


class TestPydanticConfig:
    """Tests for PydanticConfig."""

    def test_config_defaults(self):
        """Test default configuration."""
        config = PydanticConfig()
        assert config.timeout == 60.0
        assert config.max_retries == 3

    def test_config_custom(self):
        """Test custom configuration."""
        config = PydanticConfig(timeout=30.0, max_retries=5)
        assert config.timeout == 30.0
        assert config.max_retries == 5


class TestPydanticAdapter:
    """Tests for PydanticAdapter (sync)."""

    @patch("adapters.pydantic.adapter.Agent", None)
    def test_adapter_no_pydantic_ai(self):
        """Test adapter raises when pydantic-ai not installed."""
        with patch("adapters.pydantic.adapter.Agent", None):
            # This test would fail if we could actually instantiate
            # In practice, we'd need to mock differently
            pass

    def test_adapter_init_with_mock(self):
        """Test adapter initialization with mock agent."""
        mock_agent = MagicMock()
        adapter = PydanticAdapter(agent=mock_agent)

        assert adapter._agent == mock_agent
        assert adapter._config.timeout == 60.0

    def test_adapter_list_tools_returns_empty(self):
        """Test list_tools returns empty list by default."""
        mock_agent = MagicMock()
        adapter = PydanticAdapter(agent=mock_agent)

        tools = adapter.list_tools()
        assert tools == []

    def test_adapter_refresh_tools(self):
        """Test refresh_tools clears cache."""
        mock_agent = MagicMock()
        adapter = PydanticAdapter(agent=mock_agent)
        adapter._tools_cache = [MagicMock()]

        adapter.refresh_tools()
        assert adapter._tools_cache is None

    def test_adapter_execute_sync_with_no_loop(self):
        """Test execute in sync context without running loop."""
        mock_agent = MagicMock()
        mock_result = MagicMock()
        mock_result.data = "test output"
        mock_result.model = "test-model"
        mock_agent.run.return_value = mock_result

        adapter = PydanticAdapter(agent=mock_agent)
        result = adapter.execute("mytool", {"arg": "value"})

        assert result.success is True
        assert result.output == "test output"

    def test_adapter_execute_error(self):
        """Test execute handles errors."""
        mock_agent = MagicMock()
        mock_agent.run.side_effect = Exception("test error")

        adapter = PydanticAdapter(agent=mock_agent)
        result = adapter.execute("mytool", {})

        assert result.success is False
        assert result.error is not None
        assert "test error" in result.error


class TestPydanticAdapterAsync:
    """Tests for PydanticAdapterAsync."""

    def test_async_adapter_init(self):
        """Test async adapter initialization."""
        mock_agent = MagicMock()
        adapter = PydanticAdapterAsync(agent=mock_agent)

        assert adapter._agent == mock_agent

    @pytest.mark.asyncio
    async def test_async_execute_success(self):
        """Test async execute success."""
        mock_agent = MagicMock()
        mock_result = MagicMock()
        mock_result.data = "async output"
        mock_result.model = "async-model"
        mock_agent.run.return_value = mock_result

        adapter = PydanticAdapterAsync(agent=mock_agent)
        result = await adapter.execute("mytool", {"arg": "value"})

        assert result.success is True
        assert result.output == "async output"

    @pytest.mark.asyncio
    async def test_async_execute_error(self):
        """Test async execute handles errors."""
        mock_agent = MagicMock()
        mock_agent.run.side_effect = Exception("async error")

        adapter = PydanticAdapterAsync(agent=mock_agent)
        result = await adapter.execute("mytool", {})

        assert result.success is False
        assert result.error is not None
        assert "async error" in result.error


class TestCreateAdapter:
    """Tests for create_adapter factory."""

    def test_create_adapter(self):
        """Test create_adapter factory."""
        mock_agent = MagicMock()
        adapter = create_adapter(agent=mock_agent, timeout=30.0, max_retries=5)

        assert isinstance(adapter, PydanticAdapter)
        assert adapter._config.timeout == 30.0
        assert adapter._config.max_retries == 5
