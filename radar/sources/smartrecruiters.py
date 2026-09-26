"""SmartRecruiters public posting API (official, no auth): company career sites such as Bosch.

List:   GET https://api.smartrecruiters.com/v1/companies/{company}/postings?country=tr&limit=100&offset=N
Detail: GET https://api.smartrecruiters.com/v1/companies/{company}/postings/{id}
An unknown company id answers 200 with an empty list, so "0 jobs" is logged, not treated as an error.
"""
from __future__ import annotations

import logging

from bs4 import BeautifulSoup

from ..http import Fetcher
from ..models import Job

log = logging.getLogger("radar")

API = "https://api.smartrecruiters.com/v1/companies/{company}/postings"
PAGE = 100

# SmartRecruiters experience levels -> the LinkedIn "Seniority level" labels the matcher understands
SENIORITY = {"internship": "Internship", "entry_level": "Entry level", "associate": "Associate",
             "mid_senior_level": "Mid-Senior level", "director": "Director", "executive": "Executive",
             "not_applicable": "Not Applicable"}


def _html_text(html: str) -> str:
    return " ".join(BeautifulSoup(html or "", "html.parser").get_text(" ", strip=True).split())


def parse_posting(p: dict) -> Job:
    loc = p.get("location") or {}
    raw = loc.get("fullLocation") or ", ".join(x for x in (loc.get("city"), loc.get("country", "").upper()) if x)
    parts = []
    for part in (p.strip() for p in raw.split(",")):
        if part and part not in parts:   # "Bursa, , Turkey" / "Kocaeli, Kocaeli, Turkey"
            parts.append(part)
    where = ", ".join(parts)
    if loc.get("remote"):
        where += " (Remote)"
    elif loc.get("hybrid"):
        where += " (Hybrid)"
    company = (p.get("company") or {})
    extra = {}
    level = (p.get("experienceLevel") or {}).get("id")
    if level in SENIORITY:
        extra["Seniority level"] = SENIORITY[level]
    emp = (p.get("typeOfEmployment") or {}).get("label")
    if emp:
        extra["Employment type"] = emp
    return Job(
        source="smartrecruiters",
        native_id=f"{company.get('identifier', '')}-{p['id']}",
        title=p.get("name", "").strip(),
        company=company.get("name", "") or company.get("identifier", ""),
        location=where,
        url=p.get("postingUrl") or f"https://jobs.smartrecruiters.com/{company.get('identifier', '')}/{p['id']}",
        posted=(p.get("releasedDate") or "")[:10],
        extra=extra,
    )


def parse_detail(d: dict) -> str:
    """Job description + qualifications as plain text (the company boilerplate is skipped)."""
    sections = (d.get("jobAd") or {}).get("sections") or {}
    parts = [_html_text((sections.get(k) or {}).get("text", "")) for k in ("jobDescription", "qualifications", "additionalInformation")]
    return " ".join(p for p in parts if p)[:6000]


def fetch(cfg: dict, fetcher: Fetcher) -> list[Job]:
    out: list[Job] = []
    detail_budget = int(cfg.get("detail_limit", 80))
    for c in cfg.get("companies", []):
        company, country = c["id"], c.get("country", "")
        base = API.format(company=company)
        jobs, offset = [], 0
        while True:
            url = f"{base}?limit={PAGE}&offset={offset}" + (f"&country={country}" if country else "")
            r = fetcher.get(url)
            if r is None:
                break
            data = r.json()
            jobs += [parse_posting(p) for p in data.get("content", [])]
            offset += PAGE
            if offset >= int(data.get("totalFound", 0)):
                break
        for j in jobs:
            if detail_budget <= 0:
                break
            r = fetcher.get(f"{base}/{j.native_id.rsplit('-', 1)[1]}")
            if r is not None:
                j.description = parse_detail(r.json())
                detail_budget -= 1
        log.info("smartrecruiters/%s: %d jobs", company, len(jobs))
        out += jobs
    return out
