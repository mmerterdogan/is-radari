"""LinkedIn public (guest) job search - no login, no account involved.

Note: LinkedIn's terms discourage automated access. This module only reads the
public guest endpoints at a slow pace and never logs in, so no account can be
banned; worst case the endpoint returns 429 and the source is skipped that day.
Disable it in config.yaml (search.linkedin.enabled: false) if you prefer.
"""
from __future__ import annotations

import logging
import re
from urllib.parse import quote

from bs4 import BeautifulSoup

from ..http import Fetcher
from ..models import Job

log = logging.getLogger("radar")

SEARCH = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
DETAIL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{id}"


def _text(el) -> str:
    return " ".join(el.get_text(" ", strip=True).split()) if el else ""


def parse_search(html: str) -> list[Job]:
    soup = BeautifulSoup(html, "html.parser")
    jobs = []
    for card in soup.select("[data-entity-urn]"):
        urn = card.get("data-entity-urn", "")
        if "jobPosting" not in urn:
            continue
        jid = urn.rsplit(":", 1)[-1]
        link = card.select_one("a.base-card__full-link") or card.select_one("a[href*='/jobs/view/']")
        url = link["href"].split("?")[0] if link and link.get("href") else f"https://www.linkedin.com/jobs/view/{jid}"
        t = card.select_one("time")
        jobs.append(Job(
            source="linkedin",
            native_id=jid,
            title=_text(card.select_one(".base-search-card__title")),
            company=_text(card.select_one(".base-search-card__subtitle")),
            location=_text(card.select_one(".job-search-card__location")),
            url=url,
            posted=(t.get("datetime") if t else "") or "",
        ))
    return jobs


# LinkedIn answers in the request language; criteria are stored with the canonical English labels.
CRITERIA_KEYS = {"Kıdem düzeyi": "Seniority level", "İstihdam türü": "Employment type",
                 "Görev tanımı": "Job function", "Sektörler": "Industries"}
CRITERIA_VALUES = {
    "Stajyer": "Internship", "Başlangıç Seviye": "Entry level", "Uzman": "Associate",
    "Orta-Üst Düzey Yönetici": "Mid-Senior level", "Direktör": "Director", "Üst Düzey Yönetici": "Executive",
    "Geçerli Değil": "Not Applicable", "Tam Zamanlı": "Full-time", "Yarı Zamanlı": "Part-time",
    "Sözleşmeli": "Contract", "Geçici": "Temporary", "Gönüllü": "Volunteer", "Diğer": "Other",
}


def normalize_criteria(extra: dict) -> dict:
    """Translate Turkish criteria labels/values to the English ones the matcher expects (in place)."""
    for tr, en in CRITERIA_KEYS.items():
        if tr in extra:
            v = extra.pop(tr)
            extra[en] = CRITERIA_VALUES.get(v, v) if en in ("Seniority level", "Employment type") else v
    return extra


def _applicants(text: str) -> str:
    """'172 başvuru' / '137 applicants' -> '172'; 'Be among the first 25' / 'İlk 25 başvurandan' -> '<25'."""
    m = re.search(r"(\d[\d.,]*)", text)
    if not m:
        return ""
    n = m.group(1).replace(".", "").replace(",", "")
    if re.search(r"first|ilk", text, re.I):
        return f"<{n}"
    return f"{n}+" if re.search(r"over|more than|fazla|üzeri", text, re.I) else n


def parse_detail(html: str) -> tuple[str, dict]:
    soup = BeautifulSoup(html, "html.parser")
    desc = _text(soup.select_one(".show-more-less-html__markup") or soup.select_one(".description__text"))
    crit = {}
    for h, v in zip(soup.select(".description__job-criteria-subheader"), soup.select(".description__job-criteria-text")):
        crit[_text(h)] = _text(v)
    normalize_criteria(crit)
    if soup.select_one(".closed-job"):
        crit["closed"] = True
    applicants = _applicants(_text(soup.select_one(".num-applicants__caption")))
    if applicants:
        crit["applicants"] = applicants
    return desc, crit


def fetch(cfg: dict, fetcher: Fetcher) -> list[Job]:
    hours = int(cfg.get("hours", 24))
    pages = int(cfg.get("max_pages", 1))
    out: dict[str, Job] = {}
    for q in cfg.get("queries", []):
        for page in range(int(q.get("pages", pages))):
            url = (f"{SEARCH}?keywords={quote(q['keywords'])}&location={quote(q['location'])}"
                   f"&f_TPR=r{hours * 3600}&start={page * 10}")
            if q.get("experience"):
                url += f"&f_E={quote(str(q['experience']))}"
            r = fetcher.get(url)
            if r is None:
                break
            found = parse_search(r.text)
            for j in found:
                j.extra["query"] = q["keywords"]
                j.extra["query_location"] = q["location"]
                out.setdefault(j.id, j)
            if len(found) < 10:
                break
    log.info("linkedin: %d unique jobs", len(out))
    return list(out.values())


def enrich(job: Job, fetcher: Fetcher) -> None:
    """Fetch the full description, seniority / employment type, applicant count and closed flag."""
    r = fetcher.get(DETAIL.format(id=job.native_id))
    if r is None:
        return
    desc, crit = parse_detail(r.text)
    if desc:
        job.description = desc[:6000]
    job.closed = bool(crit.pop("closed", False))
    job.extra.update(crit)
