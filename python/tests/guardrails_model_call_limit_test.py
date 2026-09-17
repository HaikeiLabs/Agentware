"""Tests for the model-call limit guardrail."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

from pedro_agentware.middleware.guardrails.model_call_limit import (
    ModelCallLimiter,
    ModelCallLimitError,
)


def test_counts_are_scoped_per_session() -> None:
    limiter = ModelCallLimiter(hard_limit=3)
    limiter.record("a")
    limiter.record("a")
    limiter.record("b")

    assert limiter.calls("a") == 2
    assert limiter.calls("b") == 1
    assert limiter.calls("never-seen") == 0


def test_allow_goes_false_exactly_at_the_hard_limit() -> None:
    limiter = ModelCallLimiter(hard_limit=2)

    assert limiter.allow("s") is True
    limiter.record("s")
    assert limiter.allow("s") is True
    limiter.record("s")
    # Two calls recorded against a limit of two: no third call is permitted.
    assert limiter.allow("s") is False
    assert limiter.status("s").exhausted is True
    assert limiter.status("s").remaining == 0


def test_budget_defaults_to_eighty_percent_and_warns_before_the_wall() -> None:
    limiter = ModelCallLimiter(hard_limit=10)
    assert limiter.budget == 8

    for _ in range(7):
        limiter.record("s")
    assert limiter.status("s").over_budget is False

    limiter.record("s")
    status = limiter.status("s")
    assert status.over_budget is True
    assert status.exhausted is False
    assert status.remaining == 2


def test_explicit_budget_is_clamped_to_the_hard_limit() -> None:
    limiter = ModelCallLimiter(hard_limit=4, budget=9)
    assert limiter.budget == 4


def test_hard_limit_below_one_is_clamped_so_progress_stays_possible() -> None:
    limiter = ModelCallLimiter(hard_limit=0)
    assert limiter.hard_limit == 1
    assert limiter.allow("s") is True


def test_enforce_raises_only_once_exhausted() -> None:
    limiter = ModelCallLimiter(hard_limit=1)

    limiter.enforce("s")
    limiter.record("s")

    with pytest.raises(ModelCallLimitError) as excinfo:
        limiter.enforce("s")

    assert excinfo.value.session_id == "s"
    assert excinfo.value.calls == 1
    assert excinfo.value.hard_limit == 1


def test_reset_session_clears_only_that_session() -> None:
    limiter = ModelCallLimiter(hard_limit=2)
    limiter.record("a")
    limiter.record("b")

    limiter.reset_session("a")

    assert limiter.calls("a") == 0
    assert limiter.calls("b") == 1


def test_check_does_not_record() -> None:
    limiter = ModelCallLimiter(hard_limit=2)

    limiter.check("s")
    limiter.check("s")

    assert limiter.calls("s") == 0
