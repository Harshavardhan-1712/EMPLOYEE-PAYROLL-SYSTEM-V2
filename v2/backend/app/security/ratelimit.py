"""Tiny in-memory sliding-window limiter for login attempts.
Limitation (documented): per-process memory; use a shared store behind multiple workers."""
from __future__ import annotations

import time
from collections import defaultdict, deque


class LoginLimiter:
    def __init__(self, max_failures: int, window_seconds: int) -> None:
        self.max_failures, self.window = max_failures, window_seconds
        self._fails: dict[str, deque[float]] = defaultdict(deque)

    def _prune(self, key: str, now: float) -> deque[float]:
        q = self._fails[key]
        while q and now - q[0] > self.window:
            q.popleft()
        return q

    def retry_after(self, key: str) -> int:
        now = time.monotonic()
        q = self._prune(key, now)
        if len(q) >= self.max_failures:
            return max(1, int(self.window - (now - q[0])))
        return 0

    def record_failure(self, key: str) -> None:
        self._prune(key, time.monotonic()).append(time.monotonic())

    def reset(self, key: str) -> None:
        self._fails.pop(key, None)
