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


class Fetcher:
    def __init__(self, delay: float = 2.0, retries: int = 3, timeout: float = 25.0):
        self.delay = delay
        self.retries = retries
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self._last = 0.0

    def get(self, url: str, **kw) -> requests.Response | None:
        """GET with pacing. Returns None when the request keeps failing (never raises)."""
        for attempt in range(self.retries + 1):
            wait = self.delay - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait + random.uniform(0, 0.5 * self.delay))
            self._last = time.monotonic()
            try:
                r = self.session.get(url, timeout=self.timeout, **kw)
            except requests.RequestException as exc:
                log.warning("request error %s: %s", url, exc)
                r = None
            if r is not None and r.status_code == 200:
                return r
            status = r.status_code if r is not None else "ERR"
            if r is not None and r.status_code in (400, 401, 403, 404):
                log.warning("HTTP %s for %s - not retrying", status, url)
                return None
            backoff = (2 ** attempt) * max(self.delay, 2) * 2
            log.info("HTTP %s for %s - retry in %.0fs", status, url, backoff)
            time.sleep(backoff)
        return None
