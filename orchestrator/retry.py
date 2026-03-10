from __future__ import annotations


class RetryPolicy:
    def __init__(self, retry_limit: int = 0, backoff_seconds: float = 0.0):
        self.retry_limit = max(0, retry_limit)
        self.backoff_seconds = max(0.0, backoff_seconds)

    def should_retry(self, attempt_number: int, retry_limit: int | None = None) -> bool:
        max_retries = self.retry_limit if retry_limit is None else max(0, retry_limit)
        return attempt_number <= max_retries

    def backoff_duration(self, attempt_number: int) -> float:
        if attempt_number <= 0:
            return 0.0
        return self.backoff_seconds * (2 ** (attempt_number - 1))
