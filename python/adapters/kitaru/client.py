"""Kitaru Python library client wrapper.

Kitaru is a Python library (pip install kitaru), not a REST API.
This client wraps the Kitaru Python library for use with pedro-agentware.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class Execution:
    """Represents a Kitaru flow execution."""

    id: str
    status: str
    started_at: datetime
    updated_at: datetime
    output: dict[str, Any] | None = None


class Client:
    """Client for Kitaru Python library.

    Wraps the kitaru library to execute flows and manage deployments.
    """

    def __init__(
        self,
        server_url: str | None = None,
        auth_token: str | None = None,
        project: str | None = None,
    ):
        """Initialize Kitaru client.

        Args:
            server_url: Kitaru server URL (optional, defaults to local)
            auth_token: Auth token for remote server (optional)
            project: Project name (optional)
        """
        try:
            from kitaru import KitaruClient as KitaruClientType
            self._kitaru = KitaruClientType(
                server_url=server_url,
                auth_token=auth_token,
                project=project,
            )
        except ImportError:
            self._kitaru = None

    def _require_kitaru(self):
        """Raise error if kitaru not installed."""
        if self._kitaru is None:
            raise ImportError("kitaru is not installed. Install with: pip install kitaru")

    def get_deployments(self) -> list[str]:
        """List deployed flow names."""
        self._require_kitaru()
        return [d.flow for d in self._kitaru.deployments.list()]

    def invoke(self, flow: str, inputs: dict[str, Any]) -> str:
        """Invoke a deployed flow.

        Returns:
            Execution ID
        """
        result = self._kitaru.deployments.invoke(flow=flow, inputs=inputs)
        return str(result.execution_id)

    def wait_for_completion(
        self,
        execution_id: str,
        poll_interval: float = 2.0,
        timeout: float = 60.0,
    ) -> Execution:
        """Wait for execution to complete."""
        import time

        start = time.time()
        while time.time() - start < timeout:
            result = self._kitaru.executions.get(execution_id)
            if result.status in ("completed", "failed", "error", "canceled"):
                return Execution(
                    id=execution_id,
                    status=result.status,
                    started_at=result.created_at,
                    updated_at=result.updated_at,
                    output=self._get_execution_output(result),
                )
            time.sleep(poll_interval)
        raise TimeoutError(f"Execution {execution_id} timed out")

    def _get_execution_output(self, result: Any) -> dict[str, Any] | None:
        """Get output from execution result."""
        try:
            output = result.output
            if hasattr(output, 'model_dump'):
                return output.model_dump()
            if hasattr(output, 'dict'):
                return output.dict()
            if isinstance(output, dict):
                return output
            return {"value": str(output)}
        except Exception:
            return None

    def get_execution(self, execution_id: str) -> Execution:
        """Get execution status."""
        result = self._kitaru.executions.get(execution_id)
        return Execution(
            id=execution_id,
            status=result.status,
            started_at=result.created_at,
            updated_at=result.updated_at,
            output=self._get_execution_output(result),
        )

    def list_executions(self) -> list[Execution]:
        """List recent executions."""
        return [
            Execution(
                id=str(e.execution_id),
                status=e.status,
                started_at=e.created_at,
                updated_at=e.updated_at,
                output=None,
            )
            for e in self._kitaru.executions.list()
        ]


def get_default_server_url() -> str:
    """Get default Kitaru server from environment."""
    import os

    return os.environ.get("KITARU_URL", "")  # Empty = local