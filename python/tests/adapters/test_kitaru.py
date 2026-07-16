"""Unit tests for Kitaru adapter."""

from unittest.mock import MagicMock, patch

import pytest

from adapters.kitaru import Client, KitaruAdapter, KitaruConfig, create_adapter


class TestKitaruClient:
    """Tests for Kitaru Client."""

    def test_client_init_default(self):
        """Test client initialization with defaults."""
        client = Client()
        assert client._kitaru is not None

    def test_client_init_custom(self):
        """Test client initialization with custom values."""
        client = Client(
            server_url="http://custom:9000",
            auth_token="test-token",
            project="test-project",
        )
        assert client._kitaru is not None

    @patch("adapters.kitaru.client.KitaruClientType")
    def test_get_deployments(self, mock_kitaru):
        """Test get_deployments method."""
        mock_deployment = MagicMock()
        mock_deployment.flow = "test-flow"
        mock_kitaru.return_value.deployments.list.return_value = [mock_deployment]

        client = Client()
        client._kitaru = mock_kitaru.return_value

        deployments = client.get_deployments()
        assert deployments == ["test-flow"]

    @patch("adapters.kitaru.client.KitaruClientType")
    def test_invoke(self, mock_kitaru):
        """Test invoke method."""
        mock_result = MagicMock()
        mock_result.execution_id = "exec-123"
        mock_kitaru.return_value.deployments.invoke.return_value = mock_result

        client = Client()
        client._kitaru = mock_kitaru.return_value

        exec_id = client.invoke("test-flow", {"input": "value"})
        assert exec_id == "exec-123"

    @patch("adapters.kitaru.client.KitaruClientType")
    def test_invoke_without_kitaru(self, mock_kitaru):
        """Test invoke raises when kitaru not installed."""
        client = Client()
        client._kitaru = None

        with pytest.raises(ImportError, match="kitaru is not installed"):
            client.invoke("test-flow", {})


class TestKitaruAdapter:
    """Tests for KitaruAdapter."""

    def test_adapter_init(self):
        """Test adapter initialization."""
        config = KitaruConfig(
            flow_mapping={"research": "research-flow"},
        )
        adapter = KitaruAdapter(config)
        assert adapter.config == config

    def test_create_adapter(self):
        """Test create_adapter factory."""
        adapter = create_adapter(
            flow_mapping={"test": "test-flow"},
            server_url="http://localhost:8080",
        )
        assert isinstance(adapter, KitaruAdapter)
        assert adapter.config.flow_mapping == {"test": "test-flow"}


class TestKitaruExecution:
    """Tests for Execution dataclass."""

    def test_execution_creation(self):
        """Test Execution creation."""
        from datetime import datetime

        from adapters.kitaru import Execution

        exec = Execution(
            id="exec-123",
            status="completed",
            started_at=datetime.now(),
            updated_at=datetime.now(),
            output={"result": "success"},
        )
        assert exec.id == "exec-123"
        assert exec.status == "completed"
        assert exec.output == {"result": "success"}
