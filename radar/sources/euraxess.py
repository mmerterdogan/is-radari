"""EURAXESS (European Commission research job portal): newest research, PhD and postdoc offers."""
from __future__ import annotations

import logging
import re
from datetime import datetime

from bs4 import BeautifulSoup

from ..http import Fetcher
from ..models import Job

log = logging.getLogger("radar")

BASE = "https://euraxess.ec.europa.eu"


def _text(el) -> str:
    return " ".join(el.get_text(" ", strip=True).split()) if el else ""


def _date(s: str) -> str:
    m = re.search(r"(\d{1,2} \w+ \d{4})", s)
    if not m:
        return ""
    try:
        return datetime.strptime(m.group(1), "%d %B %Y").date().isoformat()
    except ValueError:
        return ""


def parse_list(html: str) -> list[Job]:
    soup = BeautifulSoup(html, "html.parser")
    jobs = []
    for art in soup.select("article.ecl-content-item"):
        a = art.select_one("h3 a[href^='/jobs/']")
        if not a:
            continue
        jid = a["href"].rstrip("/").rsplit("/", 1)[-1]
        meta = [_text(li) for li in art.select(".ecl-content-block__primary-meta-item")]
        org = meta[0] if meta else ""
        posted = next((_date(m) for m in meta if "Posted" in m), "")
        loc_block = art.select_one(".id-Work-Locations .ecl-text-standard")
        loc = _text(loc_block)
        # "Number of offers: 1, Spain, INSTITUTE, CITY, ..." -> keep country + city-ish part
        loc = re.sub(r"^Number of offers:\s*\d+,\s*", "", loc)
        parts = [p.strip() for p in loc.split(",")]
        location = ", ".join(p for p in (parts[2] if len(parts) > 2 else "", parts[0] if parts else "") if p)
        field_block = art.select_one(".id-Research-Field .ecl-text-standard")
        jobs.append(Job(
            source="euraxess",
            native_id=jid,
            title=_text(a),
            company=org,
            location=location,
            url=BASE + a["href"],
            posted=posted,
            description=_text(art.select_one(".ecl-content-block__description"))[:1500],
            extra={"research_field": _text(field_block)[:200]} if field_block else {},
        ))
    return jobs


def fetch(cfg: dict, fetcher: Fetcher) -> list[Job]:
    out: dict[str, Job] = {}
    for page in range(int(cfg.get("pages", 5))):
        r = fetcher.get(f"{BASE}/jobs/search?page={page}")
        if r is None:
            break
        found = parse_list(r.text)
        if not found:
            break
        for j in found:
            out.setdefault(j.id, j)
    log.info("euraxess: %d jobs", len(out))
    return list(out.values())
