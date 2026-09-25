"""Greenhouse public job boards (official, documented, no auth): company career pages."""
from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup

from ..http import Fetcher
from ..models import Job

log = logging.getLogger("radar")

API = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"


def parse_board(data: dict, board: str, location_regex: str | None) -> list[Job]:
    rx = re.compile(location_regex, re.I) if location_regex else None
    jobs = []
    for j in data.get("jobs", []):
        loc = (j.get("location") or {}).get("name", "")
        if rx and not rx.search(loc):
            continue
        content = BeautifulSoup(j.get("content") or "", "html.parser")
        # Greenhouse double-escapes HTML in "content"
        text = BeautifulSoup(content.get_text(), "html.parser").get_text(" ", strip=True)
        jobs.append(Job(
            source="greenhouse",
            native_id=f"{board}-{j['id']}",
            title=j.get("title", ""),
            company=(j.get("company_name") or board).strip(),
            location=loc,
            url=j.get("absolute_url", ""),
            posted=(j.get("updated_at") or "")[:10],
            description=" ".join(text.split())[:6000],
        ))
    return jobs


def fetch(cfg: dict, fetcher: Fetcher) -> list[Job]:
    out = []
    for board in cfg.get("boards", []):
        r = fetcher.get(API.format(board=board))
        if r is None:
            continue
        found = parse_board(r.json(), board, cfg.get("location_regex"))
        log.info("greenhouse/%s: %d jobs in target locations", board, len(found))
        out.extend(found)
    return out
