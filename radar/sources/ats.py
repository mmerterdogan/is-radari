"""Company career sites on public applicant-tracking-system APIs (no auth, official endpoints).

    workday   POST https://{tenant}.{wd}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs
    lever     GET  https://api.lever.co/v0/postings/{slug}?mode=json
    ashby     GET  https://api.ashbyhq.com/posting-api/job-board/{slug}

Each fetch_* returns Job objects; a location regex keeps only the regions we care about.
"""
from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup

from ..http import Fetcher
from ..models import Job

log = logging.getLogger("radar")

DEFAULT_LOCATION_RX = (r"Turkey|Türkiye|Turkiye|Istanbul|İstanbul|Ankara|Izmir|İzmir|Kocaeli|Gebze|Bursa|Manisa|Remote|"
                       r"Netherlands|Ireland|Denmark|Sweden|United Kingdom|\bUK\b|Germany|Norway|Europe|EMEA")


def _text(html: str) -> str:
    return " ".join(BeautifulSoup(html or "", "html.parser").get_text(" ", strip=True).split())


def _loc_ok(loc: str, rx: str | None) -> bool:
    return bool(re.search(rx or DEFAULT_LOCATION_RX, loc or "", re.I))


# ---------------------------------------------------------------- Workday
def parse_workday_list(data: dict, t: dict) -> list[Job]:
    base = f"https://{t['tenant']}.{t['wd']}.myworkdayjobs.com/{t['site']}"
    jobs = []
    for p in data.get("jobPostings", []):
        path = p.get("externalPath", "")
        if not path:
            continue
        jobs.append(Job(source="workday", native_id=f"{t['tenant']}-{path.rsplit('_', 1)[-1]}",
                        title=p.get("title", "").strip(), company=t.get("company", t["tenant"]),
                        location=p.get("locationsText", ""), url=base + path, extra={"wd_path": path}))
    return jobs


def parse_workday_detail(d: dict) -> tuple[str, str, str]:
    """(description, posted date, full location)"""
    info = d.get("jobPostingInfo") or {}
    return _text(info.get("jobDescription", ""))[:6000], (info.get("startDate") or "")[:10], info.get("location", "")


def fetch_workday(cfg: dict, fetcher: Fetcher) -> list[Job]:
    out: dict[str, Job] = {}
    rx = cfg.get("location_regex")
    for t in cfg.get("tenants", []):
        api = f"https://{t['tenant']}.{t['wd']}.myworkdayjobs.com/wday/cxs/{t['tenant']}/{t['site']}"
        found: dict[str, Job] = {}
        for q in t.get("search", ["Turkey", "Türkiye"]):
            offset = 0
            while offset < 200:
                r = fetcher.post(f"{api}/jobs", json={"limit": 20, "offset": offset, "searchText": q, "appliedFacets": {}},
                                 headers={"Accept": "application/json", "Content-Type": "application/json"})
                if r is None:
                    break
                data = r.json()
                for j in parse_workday_list(data, t):
                    found.setdefault(j.id, j)
                offset += 20
                if offset >= int(data.get("total") or 0):
                    break
        kept = [j for j in found.values() if _loc_ok(j.location, rx) or "Location" in j.location]
        for j in kept[: int(cfg.get("detail_limit", 60))]:
            r = fetcher.get(api + j.extra["wd_path"], headers={"Accept": "application/json"})
            if r is not None:
                j.description, j.posted, full = parse_workday_detail(r.json())
                if full and ("Locations" in j.location or not j.location):
                    j.location = full
        kept = [j for j in kept if _loc_ok(j.location, rx)]
        log.info("workday/%s: %d jobs in target locations", t["tenant"], len(kept))
        out.update({j.id: j for j in kept})
    return list(out.values())


# ---------------------------------------------------------------- Lever
def parse_lever(items: list, slug: str, company: str, rx: str | None) -> list[Job]:
    jobs = []
    for p in items:
        cat = p.get("categories") or {}
        loc = ", ".join(cat.get("allLocations") or [cat.get("location", "")])
        if p.get("workplaceType") == "remote":
            loc += " (Remote)"
        if not _loc_ok(loc, rx):
            continue
        desc = " ".join(x for x in (p.get("descriptionPlain", ""), " ".join(
            _text(l.get("content", "")) for l in p.get("lists", [])), p.get("additionalPlain", "")) if x)
        extra = {"Employment type": cat.get("commitment", "")} if cat.get("commitment") else {}
        created = p.get("createdAt")
        jobs.append(Job(source="lever", native_id=f"{slug}-{p['id']}", title=p.get("text", ""), company=company,
                        location=loc, url=p.get("hostedUrl", ""), description=" ".join(desc.split())[:6000],
                        posted=_ms_date(created), extra=extra))
    return jobs


def _ms_date(ms) -> str:
    from datetime import datetime, timezone
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).date().isoformat()
    except (TypeError, ValueError):
        return ""


def fetch_lever(cfg: dict, fetcher: Fetcher) -> list[Job]:
    out = []
    for c in cfg.get("companies", []):
        r = fetcher.get(f"https://api.lever.co/v0/postings/{c['slug']}?mode=json")
        if r is None:
            continue
        jobs = parse_lever(r.json(), c["slug"], c.get("company", c["slug"]), cfg.get("location_regex"))
        log.info("lever/%s: %d jobs in target locations", c["slug"], len(jobs))
        out += jobs
    return out


# ---------------------------------------------------------------- Ashby
def parse_ashby(data: dict, slug: str, company: str, rx: str | None) -> list[Job]:
    jobs = []
    for p in data.get("jobs", []):
        if not p.get("isListed", True):
            continue
        locs = [p.get("location", "")] + [x.get("location", "") for x in p.get("secondaryLocations") or []]
        loc = ", ".join(x for x in locs if x) + (" (Remote)" if p.get("isRemote") else "")
        if not _loc_ok(loc, rx):
            continue
        extra = {"Employment type": p.get("employmentType", "")} if p.get("employmentType") else {}
        jobs.append(Job(source="ashby", native_id=f"{slug}-{p['id']}", title=p.get("title", ""), company=company,
                        location=loc, url=p.get("jobUrl", ""), posted=(p.get("publishedAt") or "")[:10],
                        description=" ".join((p.get("descriptionPlain") or _text(p.get("descriptionHtml", ""))).split())[:6000],
                        extra=extra))
    return jobs


def fetch_ashby(cfg: dict, fetcher: Fetcher) -> list[Job]:
    out = []
    for c in cfg.get("companies", []):
        r = fetcher.get(f"https://api.ashbyhq.com/posting-api/job-board/{c['slug']}")
        if r is None:
            continue
        jobs = parse_ashby(r.json(), c["slug"], c.get("company", c["slug"]), cfg.get("location_regex"))
        log.info("ashby/%s: %d jobs in target locations", c["slug"], len(jobs))
        out += jobs
    return out
