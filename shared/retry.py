from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

from shared.logging import get_logger

T = TypeVar("T")


class RetryExhaustedError(RuntimeError):
    """Raised when an operation keeps failing after all retries."""


@dataclass(frozen=True)
class RetryResult:
    attempts: int


def run_with_retry(
    operation: Callable[[], T],
    *,
    operation_name: str,
    max_attempts: int = 3,
    initial_delay_seconds: float = 0.2,
    backoff_factor: float = 2.0,
    retry_exceptions: tuple[type[Exception], ...] = (Exception,),
    sleep_func: Callable[[float], None] = time.sleep,
) -> tuple[T, RetryResult]:
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")

    logger = get_logger(__name__)
    delay = initial_delay_seconds
    attempts = 0

    while True:
        attempts += 1
        try:
            value = operation()
            return value, RetryResult(attempts=attempts)
        except retry_exceptions as exc:
            if attempts >= max_attempts:
                logger.error(
                    "operation_failed_exhausted op=%s attempts=%s error=%s",
                    operation_name,
                    attempts,
                    exc,
                )
                raise RetryExhaustedError(f"{operation_name} failed after {attempts} attempts") from exc

            logger.warning(
                "operation_retry op=%s attempt=%s/%s delay=%.2fs error=%s",
                operation_name,
                attempts,
                max_attempts,
                delay,
                exc,
            )
            sleep_func(delay)
            delay *= backoff_factor
