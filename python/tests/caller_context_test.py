"""Tests for CallerContext delegation fields (Go parity)."""

import sys

sys.path.insert(0, "src")

import pytest

from pedro_agentware.middleware import AuditedToolClient, CallerContext


def test_defaults_are_fail_closed():
    """An unpopulated context must not be trusted."""
    assert CallerContext().trusted is False


def test_has_go_parity_delegation_fields():
    ctx = CallerContext(invoking_subject="U_HUMAN", parent_span="span-0", delegation_depth=2)

    assert ctx.invoking_subject == "U_HUMAN"
    assert ctx.parent_span == "span-0"
    assert ctx.delegation_depth == 2


def test_delegate_preserves_invoking_subject_and_increments_depth():
    parent = CallerContext(user_id="pedro-agent", invoking_subject="U_HUMAN", session_id="C123")

    child = parent.delegate("span-parent")
    grandchild = child.delegate("span-child")

    assert child.invoking_subject == "U_HUMAN"
    assert grandchild.invoking_subject == "U_HUMAN"
    assert (parent.delegation_depth, child.delegation_depth, grandchild.delegation_depth) == (0, 1, 2)
    assert child.parent_span == "span-parent"
    assert grandchild.parent_span == "span-child"
    assert parent.delegation_depth == 0, "delegating must not mutate the parent"


def test_delegate_refuses_to_overwrite_invoking_subject():
    """The whole point: a subagent cannot claim to be the human."""
    parent = CallerContext(invoking_subject="U_HUMAN")

    child = parent.delegate("span-a", invoking_subject="pedro-agent", role="subagent")

    assert child.invoking_subject == "U_HUMAN"
    assert child.role == "subagent"


def test_delegate_copies_metadata():
    parent = CallerContext(invoking_subject="U_HUMAN", metadata={"channel_id": "C1"})

    child = parent.delegate("span-a")
    child.metadata["channel_id"] = "C2"

    assert parent.metadata["channel_id"] == "C1"


def test_delegate_accepts_a_metadata_override():
    parent = CallerContext(invoking_subject="U_HUMAN", metadata={"channel_id": "C1"})

    child = parent.delegate("span-a", metadata={**parent.metadata, "subtask_id": "t1"})

    assert child.metadata == {"channel_id": "C1", "subtask_id": "t1"}
    assert parent.metadata == {"channel_id": "C1"}
    assert child.invoking_subject == "U_HUMAN"


async def test_audited_tool_client_records_and_executes():
    client = AuditedToolClient()

    async def tool(value: str) -> str:
        return f"got {value}"

    result = await client.Execute(
        tool_name="echo",
        tool_args={"value": "hi"},
        user_id="U_HUMAN",
        channel_id="C123",
        guild_id=None,
        func=tool,
    )

    assert result == "got hi"
    records = client.records()
    assert len(records) == 1
    assert records[0].tool_name == "echo"
    assert records[0].session_id == "C123"


async def test_audited_tool_client_denies_and_still_audits():
    class DenyAll:
        def evaluate(self, tool_name, args, caller):
            from pedro_agentware.middleware import Action, Decision

            return Decision(action=Action.DENY, rule="deny-all", reason="nope")

    client = AuditedToolClient().with_policy(DenyAll())

    async def tool(**kwargs):  # pragma: no cover - must never run
        raise AssertionError("denied tool must not execute")

    with pytest.raises(PermissionError):
        await client.Execute("echo", {}, "U_HUMAN", "C123", None, tool)

    assert len(client.records()) == 1
