"""Polite HTTP: browser-like headers, pacing, retry with backoff on 429/5xx."""
from __future__ import annotations

import logging
import random
import time

import requests

log = logging.getLogger("radar")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/128.0 Safari/537.36",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
}
MAX_BACKOFF = 60.0


class Fetcher:
    def __init__(self, delay: float = 2.0, retries: int = 3, timeout: float = 25.0):
        self.delay = delay
        self.retries = retries
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self._last = 0.0
        self.rate_limited_streak = 0  # consecutive requests that ended in 429 (circuit breaker input)

    def _backoff(self, attempt: int, r: requests.Response | None) -> float:
        if r is not None and r.status_code == 429:
            ra = r.headers.get("Retry-After", "")
            if ra.strip().isdigit():
                return min(float(ra), MAX_BACKOFF)
        return min((2 ** attempt) * max(self.delay, 2) * 2, MAX_BACKOFF)

    def request(self, method: str, url: str, **kw) -> requests.Response | None:
        """Paced request. Returns None when it keeps failing (never raises)."""
        got_429 = False
        for attempt in range(self.retries + 1):
            wait = self.delay - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait + random.uniform(0, 0.5 * self.delay))
            self._last = time.monotonic()
            try:
                r = self.session.request(method, url, timeout=self.timeout, **kw)
            except requests.RequestException as exc:
                log.warning("request error %s: %s", url, exc)
                r = None
            if r is not None and r.status_code == 200:
                self.rate_limited_streak = 0
                return r
            status = r.status_code if r is not None else "ERR"
            got_429 = got_429 or status == 429
            if r is not None and r.status_code in (400, 401, 403, 404, 410):
                log.warning("HTTP %s for %s - not retrying", status, url)
                self.rate_limited_streak = 0
                return None
            if attempt < self.retries:
                backoff = self._backoff(attempt, r)
                log.info("HTTP %s for %s - retry in %.0fs", status, url, backoff)
                time.sleep(backoff)
        self.rate_limited_streak = self.rate_limited_streak + 1 if got_429 else 0
        return None

    def get(self, url: str, **kw) -> requests.Response | None:
        return self.request("GET", url, **kw)

    def post(self, url: str, **kw) -> requests.Response | None:
        return self.request("POST", url, **kw)
