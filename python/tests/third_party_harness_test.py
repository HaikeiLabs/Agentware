"""Third-party harness viability test.

This test proves that a third party can build a complete harness using ONLY
pedro_agentware, without importing pedro_service, pedro_tag, or any repo-specific
layout. It demonstrates the "bring your own agent" product thesis.

Constraints:
- No imports from pedro_service or pedro_tag
- No shutil.which
- No assumed repo layout
- No os.environ reads inside library code on the test path
"""

import pytest


class TestThirdPartyHarness:
    """Test that a third-party harness can be built with only pedro_agentware."""

    def test_minimal_harness_contract(self):
        """Build a minimal harness using only pedro_agentware."""
        from pedro_agentware.kei import (
            EnvSecretProvider,
            HarnessContract,
            OpaqueTokenProvider,
            ToolNotFoundError,
            validate_contract,
        )

        class MinimalToolExecutor:
            def execute(self, tool_name: str, args: dict) -> dict:
                if tool_name == "echo":
                    return {"echo": args.get("message", "")}
                raise ToolNotFoundError(f"Tool not found: {tool_name}")

        contract = HarnessContract(
            auth_provider=OpaqueTokenProvider(token="test-token"),
            tool_executor=MinimalToolExecutor(),
            secret_provider=EnvSecretProvider(),
        )

        errors = validate_contract(contract)
        assert errors == [], f"Contract validation failed: {errors}"

    def test_harness_with_policy(self):
        """Build a harness with policy evaluation."""
        from pedro_agentware.kei import (
            EnvSecretProvider,
            HarnessContract,
            OpaqueTokenProvider,
            ToolNotFoundError,
            validate_contract,
        )
        from pedro_agentware.middleware.policy import Policy, SimplePolicyEvaluator

        class MinimalToolExecutor:
            def execute(self, tool_name: str, args: dict) -> dict:
                if tool_name == "hello":
                    return {"greeting": f"Hello, {args.get('name', 'world')}!"}
                raise ToolNotFoundError(f"Tool not found: {tool_name}")

        policy = Policy(
            rules=[],
            default_deny=True,  # Fail-closed: deny by default
        )

        contract = HarnessContract(
            auth_provider=OpaqueTokenProvider(token="test-token"),
            tool_executor=MinimalToolExecutor(),
            secret_provider=EnvSecretProvider(),
            policy_evaluator=SimplePolicyEvaluator(policy),
        )

        errors = validate_contract(contract)
        assert errors == [], f"Contract validation failed: {errors}"

    def test_harness_with_auditor(self):
        """Build a harness with audit logging."""
        from pedro_agentware.kei import (
            EnvSecretProvider,
            HarnessContract,
            OpaqueTokenProvider,
            ToolNotFoundError,
            validate_contract,
        )
        from pedro_agentware.middleware.audit import InMemoryAuditor

        class MinimalToolExecutor:
            def execute(self, tool_name: str, args: dict) -> dict:
                if tool_name == "add":
                    return {"result": args.get("a", 0) + args.get("b", 0)}
                raise ToolNotFoundError(f"Tool not found: {tool_name}")

        auditor = InMemoryAuditor()

        contract = HarnessContract(
            auth_provider=OpaqueTokenProvider(token="test-token"),
            tool_executor=MinimalToolExecutor(),
            secret_provider=EnvSecretProvider(),
            auditor=auditor,
        )

        errors = validate_contract(contract)
        assert errors == [], f"Contract validation failed: {errors}"

    @pytest.mark.asyncio
    async def test_harness_audited_tool_client(self):
        """Verify AuditedToolClient works with harness-provided components."""
        from pedro_agentware.kei import (
            EnvSecretProvider,
            HarnessContract,
            OpaqueTokenProvider,
            ToolNotFoundError,
            validate_contract,
        )
        from pedro_agentware.middleware import AuditedToolClient, CallerContext
        from pedro_agentware.middleware.policy import Policy, SimplePolicyEvaluator

        tools = {}

        def register_tool(name: str, func):
            tools[name] = func

        def call_tool(name: str, args: dict) -> dict:
            if name not in tools:
                raise ToolNotFoundError(f"Tool not found: {name}")
            return tools[name](**args)

        register_tool("multiply", lambda a, b: {"product": a * b})

        class HarnessToolExecutor:
            def __init__(self, handler):
                self._handler = handler

            def execute(self, tool_name: str, args: dict) -> dict:
                return self._handler(tool_name, args)

        policy = Policy(
            rules=[],
            default_deny=False,  # Allow by default for this test
        )

        client = AuditedToolClient(
            source="third-party-harness",
            evaluator=SimplePolicyEvaluator(policy),
        )

        executor = HarnessToolExecutor(call_tool)
        contract = HarnessContract(
            auth_provider=OpaqueTokenProvider(token="test-token"),
            tool_executor=executor,
            secret_provider=EnvSecretProvider(),
            policy_evaluator=SimplePolicyEvaluator(policy),
        )

        errors = validate_contract(contract)
        assert errors == [], f"Contract validation failed: {errors}"

        caller = CallerContext(
            user_id="test-user",
            invoking_subject="test-user",
            source="third-party-harness",
        )

        result = await client.Execute(
            tool_name="multiply",
            tool_args={"a": 3, "b": 4},
            user_id="test-user",
            channel_id="test-channel",
            guild_id=None,
            func=lambda a, b: {"product": a * b},
            caller=caller,
        )

        assert result == {"product": 12}

    def test_caller_context_delegation(self):
        """Verify CallerContext delegation preserves invoking_subject."""
        from pedro_agentware.middleware import CallerContext

        caller = CallerContext(
            user_id="agent-1",
            invoking_subject="human-user-123",
            source="third-party-harness",
            delegation_depth=0,
        )

        child = caller.delegate(span="subagent-1")

        assert child.invoking_subject == "human-user-123"
        assert child.delegation_depth == 1
        assert child.parent_span == "subagent-1"

        grandchild = child.delegate(span="subagent-2")
        assert grandchild.invoking_subject == "human-user-123"
        assert grandchild.delegation_depth == 2

    def test_fail_closed_unknown_policy(self):
        """Verify fail-closed: unknown policy decision = DENY."""
        from pedro_agentware.middleware.policy import Action, Policy, SimplePolicyEvaluator

        policy = Policy(
            rules=[],
            default_deny=True,
        )
        evaluator = SimplePolicyEvaluator(policy)

        from pedro_agentware.middleware import CallerContext

        caller = CallerContext(
            user_id="test",
            invoking_subject="test",
        )

        decision = evaluator.evaluate("unknown_tool", {"arg": "value"}, caller)

        assert decision.action == Action.DENY

    def test_no_pedro_service_import(self):
        """Verify pedro_agentware does not import pedro_service or pedro_tag."""
        import pedro_agentware.kei
        import pedro_agentware.middleware

        kei_module = pedro_agentware.kei
        middleware_module = pedro_agentware.middleware

        kei_source = open(kei_module.__file__).read() if hasattr(kei_module, "__file__") else ""
        middleware_source = (
            open(middleware_module.__file__).read()
            if hasattr(middleware_module, "__file__")
            else ""
        )

        assert "pedro_service" not in kei_source, "kei must not import pedro_service"
        assert "pedro_tag" not in kei_source, "kei must not import pedro_tag"
        assert "pedro_service" not in middleware_source, "middleware must not import pedro_service"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
