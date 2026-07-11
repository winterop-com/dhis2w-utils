"""Retry policy + httpx transport wrapper for transient HTTP failures.

Default-off. Opt in by passing `retry_policy=RetryPolicy(...)` to
`Dhis2Client` — the client wraps its httpx transport with `_RetryTransport`
which retries on the configured status codes and on connection-level
errors (ConnectError, ReadTimeout, etc.) with exponential backoff + jitter.

Design:

- Only idempotent HTTP methods (GET, HEAD, PUT, DELETE, OPTIONS) retry by
  default. POST / PATCH are skipped unless `retry_non_idempotent=True` —
  double-writes can cause DHIS2-side duplicates (duplicate create, double
  delete, etc). Caller opts in explicitly when they know the endpoint is
  safe (analytics refresh kick-offs, for instance).
- A server-provided `Retry-After` header (sent on 429 / 503) overrides the
  computed backoff for that attempt, capped at the policy's `max_delay`.
- Exponential: `delay = min(max_delay, base_delay * backoff_factor ** (attempt - 1))`
  with a +/- jitter applied before sleeping.
"""

from __future__ import annotations

import asyncio
import random

import httpx
from pydantic import BaseModel, ConfigDict, Field

_IDEMPOTENT_METHODS: frozenset[str] = frozenset({"GET", "HEAD", "PUT", "DELETE", "OPTIONS"})


class RetryPolicy(BaseModel):
    """Retry config for transient HTTP failures."""

    model_config = ConfigDict(frozen=True)

    max_attempts: int = Field(default=3, ge=1, le=10, description="Total attempt count including the first call.")
    base_delay: float = Field(default=0.5, ge=0.0, description="Initial backoff in seconds before the second attempt.")
    max_delay: float = Field(default=30.0, gt=0.0, description="Hard cap on the per-sleep delay.")
    backoff_factor: float = Field(default=2.0, ge=1.0, description="Multiplier applied per attempt (exponential).")
    jitter: float = Field(
        default=0.1,
        ge=0.0,
        le=1.0,
        description="Fractional random jitter applied to each delay (0.1 = +/- 10%).",
    )
    retry_statuses: frozenset[int] = Field(
        default=frozenset({429, 502, 503, 504}),
        description="HTTP status codes that trigger a retry. Defaults match transient-failure conventions.",
    )
    retry_non_idempotent: bool = Field(
        default=False,
        description="When True, retry POST/PATCH too. Leave False unless you know the endpoint is idempotent.",
    )

    def compute_delay(self, attempt: int, *, rng: random.Random | None = None) -> float:
        """Compute the sleep before attempt `attempt` (1-based; `compute_delay(1)` is before the 2nd try)."""
        raw = self.base_delay * (self.backoff_factor ** max(0, attempt - 1))
        capped = min(self.max_delay, raw)
        if self.jitter <= 0.0:
            return capped
        rnd = rng or random
        # Sample from [1 - jitter, 1 + jitter] so it's symmetric around the nominal delay.
        return capped * (1.0 + rnd.uniform(-self.jitter, self.jitter))


def _parse_retry_after(value: str | None) -> float | None:
    """Parse a `Retry-After` header. Seconds-integer form only (HTTP-date form ignored)."""
    if not value:
        return None
    try:
        seconds = float(value.strip())
    except ValueError:
        return None
    return max(0.0, seconds)


class _RetryTransport(httpx.AsyncBaseTransport):
    """Wrap another transport and retry per the given `RetryPolicy`.

    Retries on:

    - Connection-level exceptions (`httpx.ConnectError`, `ConnectTimeout`,
      `ReadTimeout`, `WriteTimeout`, `PoolTimeout`, `RemoteProtocolError`).
    - Responses whose status is in `policy.retry_statuses`.

    Non-idempotent methods (POST, PATCH) are exempt unless the policy
    opts in via `retry_non_idempotent=True`.
    """

    def __init__(self, inner: httpx.AsyncBaseTransport, policy: RetryPolicy) -> None:
        """Compose a retry transport over `inner` using `policy`."""
        self._inner = inner
        self._policy = policy

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """Dispatch with retries. Always returns a final Response or raises the last transport error."""
        method = request.method.upper()
        allowed = self._policy.retry_non_idempotent or method in _IDEMPOTENT_METHODS
        last_error: Exception | None = None
        for attempt in range(1, self._policy.max_attempts + 1):
            try:
                response = await self._inner.handle_async_request(request)
            except _RETRYABLE_ERRORS as exc:
                last_error = exc
                if not allowed or attempt == self._policy.max_attempts:
                    raise
                await asyncio.sleep(self._policy.compute_delay(attempt))
                continue
            if response.status_code in self._policy.retry_statuses and allowed and attempt < self._policy.max_attempts:
                # Consume body so the underlying stream is free to close, then sleep.
                await response.aclose()
                server_hint = _parse_retry_after(response.headers.get("Retry-After"))
                if server_hint is not None:
                    # Honor the server's hint but never sleep past the
                    # policy's cap — a pathological Retry-After: 86400
                    # must not wedge the caller for a day.
                    delay = min(self._policy.max_delay, server_hint)
                else:
                    delay = self._policy.compute_delay(attempt)
                await asyncio.sleep(delay)
                continue
            return response
        # Exhausted attempts with nothing but exceptions — re-raise the last.
        if last_error is None:
            raise RuntimeError("retry loop exhausted without a recorded error — should be unreachable")
        raise last_error

    async def aclose(self) -> None:
        """Close the wrapped inner transport."""
        await self._inner.aclose()


_RETRYABLE_ERRORS: tuple[type[Exception], ...] = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.PoolTimeout,
    httpx.RemoteProtocolError,
)


def build_retry_transport(policy: RetryPolicy, *, inner: httpx.AsyncBaseTransport | None = None) -> _RetryTransport:
    """Compose a retry-wrapped transport; defaults to wrapping a fresh `AsyncHTTPTransport`."""
    base: httpx.AsyncBaseTransport = inner if inner is not None else _default_transport()
    return _RetryTransport(base, policy)


def _default_transport() -> httpx.AsyncBaseTransport:
    """Build httpx's default async transport — matches what `httpx.AsyncClient()` would pick."""
    return httpx.AsyncHTTPTransport()


__all__ = ["RetryPolicy", "build_retry_transport"]
