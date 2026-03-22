from __future__ import annotations

import pytest

from shared.retry import RetryExhaustedError, run_with_retry


def test_run_with_retry_succeeds_after_retries() -> None:
    attempts = {"count": 0}

    def flaky() -> str:
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise RuntimeError("temporary")
        return "ok"

    value, meta = run_with_retry(
        flaky,
        operation_name="flaky_op",
        max_attempts=3,
        initial_delay_seconds=0.0,
    )

    assert value == "ok"
    assert meta.attempts == 3


def test_run_with_retry_raises_after_exhausted() -> None:
    def always_fail() -> None:
        raise RuntimeError("boom")

    with pytest.raises(RetryExhaustedError):
        run_with_retry(
            always_fail,
            operation_name="always_fail",
            max_attempts=2,
            initial_delay_seconds=0.0,
        )
