"""Rate-limited HTTP client for SEC EDGAR.

A single process-wide token bucket enforces the SEC's 10 requests/second
cap. The bucket targets 9 req/sec to leave headroom for timing jitter.
Every outgoing request carries the project User-Agent.

Cache writes use the write-temp-then-rename pattern: the payload is
written to ``<path>.tmp.<pid>`` and then atomically renamed onto the
final path, so a crash mid-write cannot leave a half-written file.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx

# SEC-accepted format: "<Organization or Name> <contact email>".
# The contact email is project-fixed; see ca-PLAN.md.
USER_AGENT = "tra-research-pipeline Alex Sullivan sulli98@uw.edu"

# Conservative target; the SEC cap is 10/sec and a small safety margin
# absorbs network and timing jitter.
DEFAULT_RATE_PER_SEC = 9.0


class _TokenBucket:
    """Process-wide token bucket. One instance is shared across calls."""

    def __init__(self, rate_per_sec: float, capacity: float | None = None) -> None:
        if rate_per_sec <= 0:
            raise ValueError(f"rate_per_sec must be positive, got {rate_per_sec}")
        self._rate = float(rate_per_sec)
        self._capacity = float(capacity if capacity is not None else rate_per_sec)
        self._tokens = self._capacity
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self, tokens: float = 1.0) -> None:
        if tokens <= 0:
            raise ValueError(f"tokens must be positive, got {tokens}")
        while True:
            with self._lock:
                now = time.monotonic()
                elapsed = now - self._last_refill
                self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
                self._last_refill = now
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return
                deficit = tokens - self._tokens
                wait_s = deficit / self._rate
            time.sleep(wait_s)


# Single bucket per process. All EdgarClient instances share it because
# the SEC rate cap is per source IP, not per client object.
_BUCKET = _TokenBucket(DEFAULT_RATE_PER_SEC)


@dataclass(frozen=True)
class ResponseMeta:
    status: int
    latency_s: float
    cache_hit: bool
    url: str


class EdgarClient:
    """Thin wrapper over ``httpx.Client`` enforcing rate + User-Agent + cache.

    Cache layout: callers pass a ``cache_path`` (the on-disk artifact for
    this request). If it exists and is younger than ``cache_max_age_s``,
    the cached bytes are returned without a network call. Otherwise the
    network fetch happens, the result is written atomically, and the
    bytes are returned.

    Errors fail loud: HTTP non-2xx raises ``httpx.HTTPStatusError`` and
    network errors propagate as their httpx subclasses.
    """

    def __init__(
        self,
        user_agent: str = USER_AGENT,
        timeout_s: float = 30.0,
        bucket: _TokenBucket = _BUCKET,
    ) -> None:
        self._client = httpx.Client(
            headers={
                "User-Agent": user_agent,
                "Accept-Encoding": "gzip, deflate",
            },
            timeout=timeout_s,
            follow_redirects=True,
        )
        self._bucket = bucket

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "EdgarClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _maybe_cache_hit(
        self, cache_path: Optional[Path], cache_max_age_s: Optional[float]
    ) -> Optional[bytes]:
        if cache_path is None:
            return None
        if not cache_path.exists():
            return None
        if cache_max_age_s is not None:
            age = time.time() - cache_path.stat().st_mtime
            if age > cache_max_age_s:
                return None
        return cache_path.read_bytes()

    def _atomic_write(self, cache_path: Path, payload: bytes) -> None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache_path.with_name(f"{cache_path.name}.tmp.{os.getpid()}")
        tmp.write_bytes(payload)
        os.replace(tmp, cache_path)

    def get(
        self,
        url: str,
        cache_path: Optional[Path] = None,
        cache_max_age_s: Optional[float] = None,
        params: Optional[dict] = None,
    ) -> tuple[bytes, ResponseMeta]:
        """Issue a GET; return (body_bytes, ResponseMeta).

        If ``cache_path`` is supplied and fresh, no network call is made
        and the function returns the cached bytes with ``cache_hit=True``.
        """
        cached = self._maybe_cache_hit(cache_path, cache_max_age_s)
        if cached is not None:
            return cached, ResponseMeta(
                status=200, latency_s=0.0, cache_hit=True, url=url
            )

        # Narrow 429 (too many requests) retry loop. Honor Retry-After
        # when the server supplies it, otherwise sleep 1s. Cap at 3
        # retries; surface any other non-2xx (403, 404, 5xx, etc.)
        # immediately via raise_for_status.
        max_429_retries = 3
        attempt = 0
        while True:
            self._bucket.acquire()
            t0 = time.monotonic()
            resp = self._client.get(url, params=params)
            latency = time.monotonic() - t0
            if resp.status_code == 429 and attempt < max_429_retries:
                retry_after = resp.headers.get("Retry-After")
                if retry_after is not None:
                    sleep_s = float(retry_after)
                else:
                    sleep_s = 1.0
                time.sleep(sleep_s)
                attempt += 1
                continue
            # Fail loud on any other non-2xx (and on 429 once retries
            # are exhausted).
            resp.raise_for_status()
            break
        body = resp.content
        if cache_path is not None:
            self._atomic_write(cache_path, body)
        return body, ResponseMeta(
            status=resp.status_code, latency_s=latency, cache_hit=False, url=url
        )


def _self_test() -> None:
    """Trial run: issue >10 requests in a tight loop, prove the throttle.

    Hitting ``data.sec.gov/submissions/CIK0000320193.json`` 12 times in a
    row should take at least 1 second once the bucket is exhausted (the
    bucket starts full at 9 tokens, so the 10th call onward waits).
    """
    n = 12
    url = "https://data.sec.gov/submissions/CIK0000320193.json"
    with EdgarClient() as cli:
        t0 = time.monotonic()
        statuses = []
        for _ in range(n):
            _, meta = cli.get(url)
            statuses.append(meta.status)
        elapsed = time.monotonic() - t0
    print(f"client self-test: {n} fetches in {elapsed:.2f}s; statuses={set(statuses)}")
    if elapsed < 1.0:
        raise RuntimeError(
            f"throttle did not engage: {n} fetches in {elapsed:.2f}s < 1.0s"
        )


if __name__ == "__main__":
    _self_test()
