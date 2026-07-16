"""Unit tests for Hermes adapter."""

import subprocess
from unittest.mock import MagicMock, patch

from adapters.hermes import Client, HermesAdapter, HermesConfig, create_adapter


class TestHermesClient:
    """Tests for Hermes Client."""

    def test_client_init_default(self):
        """Test client initialization with defaults."""
        client = Client()
        assert client.hermes_path == "hermes"

    def test_client_init_custom(self):
        """Test client initialization with custom values."""
        from pathlib import Path

        client = Client(
            config_path=Path("/custom/path"),
            hermes_path="/usr/local/bin/hermes",
        )
        assert client.hermes_path == "/usr/local/bin/hermes"

    @patch("subprocess.run")
    def test_list_tools_empty(self, mock_run):
        """Test listing tools when none available."""
        mock_run.return_value = MagicMock(returncode=0, stdout="[]")

        client = Client()
        tools = client.list_tools()

        assert tools == []
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_list_tools_parsed(self, mock_run):
        """Test parsing tools from JSON output."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"tools": [{"name": "web_search", "description": "Search the web"}]}',
        )

        client = Client()
        tools = client.list_tools()

        assert len(tools) == 1
        assert tools[0].name == "web_search"
        assert tools[0].description == "Search the web"

    @patch("subprocess.run")
    def test_execute_success(self, mock_run):
        """Test successful tool execution."""
        mock_run.return_value = MagicMock(returncode=0, stdout="result data", stderr="")

        client = Client()
        output, error = client.execute("mytool", {"arg": "value"})

        assert output == "result data"
        assert error is None

    @patch("subprocess.run")
    def test_execute_failure(self, mock_run):
        """Test failed tool execution."""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="tool not found")

        client = Client()
        output, error = client.execute("badtool", {})

        assert output == ""
        assert error == "tool not found"

    @patch("subprocess.run")
    def test_execute_timeout(self, mock_run):
        """Test tool execution timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired("cmd", 1)

        client = Client()
        output, error = client.execute("slowtool", {})

        assert output == ""
        assert error == "timeout"

    @patch("subprocess.run")
    def test_get_skills(self, mock_run):
        """Test getting skills list."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="skill1\nskill2\n# comment\n",
        )

        client = Client()
        skills = client.get_skills()

        assert "skill1" in skills
        assert "skill2" in skills


class TestHermesAdapter:
    """Tests for Hermes Adapter."""

    def test_adapter_init(self):
        """Test adapter initialization."""
        mock_client = MagicMock()
        adapter = HermesAdapter(client=mock_client)
        assert adapter._client == mock_client
        assert adapter._tool_cache is None

    @patch("adapters.hermes.client.Client.list_tools")
    def test_adapter_list_tools(self, mock_list):
        """Test listing tools."""
        mock_list.return_value = [
            MagicMock(name="tool1", description="desc1"),
            MagicMock(name="tool2", description="desc2"),
        ]

        mock_client = MagicMock()
        adapter = HermesAdapter(client=mock_client)
        tools = adapter.list_tools()

        assert len(tools) == 2
        assert tools[0].name == "tool1"

    @patch("adapters.hermes.client.Client.list_tools")
    def test_adapter_list_tools_cached(self, mock_list):
        """Test tool caching."""
        mock_list.return_value = [MagicMock(name="tool1", description="desc")]

        mock_client = MagicMock()
        adapter = HermesAdapter(client=mock_client)

        adapter.list_tools()
        adapter.list_tools()

        assert mock_list.call_count == 1

    def test_adapter_execute_success(self):
        """Test successful execution."""
        mock_client = MagicMock()
        mock_client.execute.return_value = ("result", None)

        adapter = HermesAdapter(client=mock_client)
        result = adapter.execute("mytool", {"arg": "value"})

        assert result.success is True
        assert result.output == "result"

    def test_adapter_execute_failure(self):
        """Test failed execution."""
        mock_client = MagicMock()
        mock_client.execute.return_value = ("", "error message")

        adapter = HermesAdapter(client=mock_client)
        result = adapter.execute("badtool", {})

        assert result.success is False
        assert result.error == "error message"

    def test_adapter_refresh_tools(self):
        """Test refreshing tools cache."""
        mock_client = MagicMock()
        adapter = HermesAdapter(client=mock_client)
        adapter._tool_cache = [MagicMock()]

        adapter.refresh_tools()
        assert adapter._tool_cache is None


class TestCreateAdapter:
    """Tests for create_adapter factory."""

    def test_create_adapter(self):
        """Test create_adapter factory."""
        mock_client = MagicMock()
        with patch("adapters.hermes.adapter.Client", return_value=mock_client):
            client, adapter = create_adapter(
                hermes_path="/bin/hermes",
                timeout=30.0,
            )
            assert adapter._config.timeout == 30.0


class TestHermesConfig:
    """Tests for HermesConfig."""

    def test_config_defaults(self):
        """Test default configuration."""
        config = HermesConfig()
        assert config.timeout == 60.0
        assert config.hermes_path == "hermes"

    def test_config_custom(self):
        """Test custom configuration."""
        from pathlib import Path

        config = HermesConfig(
            config_path=Path("/custom"),
            hermes_path="/bin/hermes",
            timeout=30.0,
        )
        assert config.timeout == 30.0
        assert config.hermes_path == "/bin/hermes"
