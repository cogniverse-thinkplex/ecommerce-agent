from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
import hashlib
from threading import RLock
from time import monotonic


@dataclass
class _AttemptState:
    failures: deque[float] = field(default_factory=deque)
    blocked_until: float | None = None


class LoginRateLimiter:
    def __init__(
        self,
        *,
        max_failures: int = 5,
        window_seconds: int = 300,
        block_seconds: int = 900,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if min(max_failures, window_seconds, block_seconds) < 1:
            raise ValueError("Login rate-limit values must be positive")
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self.block_seconds = block_seconds
        self._clock = clock
        self._states: dict[str, _AttemptState] = {}
        self._lock = RLock()

    def key(self, client_ip: str, email: str) -> str:
        normalized = f"{client_ip.strip()}\0{email.strip().lower()}"
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def retry_after(self, key: str) -> int | None:
        now = self._clock()
        with self._lock:
            state = self._states.get(key)
            if state is None:
                return None
            self._prune(state, now)
            if state.blocked_until is not None and state.blocked_until > now:
                return max(1, int(state.blocked_until - now + 0.999))
            if not state.failures:
                self._states.pop(key, None)
            return None

    def record_failure(self, key: str) -> None:
        now = self._clock()
        with self._lock:
            state = self._states.setdefault(key, _AttemptState())
            self._prune(state, now)
            state.failures.append(now)
            if len(state.failures) >= self.max_failures:
                state.blocked_until = now + self.block_seconds

    def record_success(self, key: str) -> None:
        with self._lock:
            self._states.pop(key, None)

    def snapshot(self) -> dict[str, dict[str, int | float | None]]:
        now = self._clock()
        with self._lock:
            for state in self._states.values():
                self._prune(state, now)
            return {
                key: {
                    "failure_count": len(state.failures),
                    "blocked_until": state.blocked_until,
                }
                for key, state in self._states.items()
                if state.failures or (state.blocked_until and state.blocked_until > now)
            }

    def _prune(self, state: _AttemptState, now: float) -> None:
        while state.failures and state.failures[0] <= now - self.window_seconds:
            state.failures.popleft()
        if state.blocked_until is not None and state.blocked_until <= now:
            state.blocked_until = None
            state.failures.clear()

