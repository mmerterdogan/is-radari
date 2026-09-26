"""Turkish company career portals that render their job lists as plain HTML.

    hrpeak   HRPeak-hosted portals (ROKETSAN, TEI, ...): {base}/jobs?p=N lists rows <tr> with a link to
             "{base}/<id>.job", the location and the publication date (d.mm.yyyy).
    baykar   kariyer.baykartech.com: the home page lists every open position (/tr/acik-pozisyonlar/detay/<slug>).
"""
from __future__ import annotations

import logging
import re
from datetime import datetime

from bs4 import BeautifulSoup

from ..http import Fetcher
from ..models import Job

log = logging.getLogger("radar")


def _t(el) -> str:
    return " ".join(el.get_text(" ", strip=True).split()) if el else ""


def _tr_date(s: str) -> str:
    m = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", s or "")
    if not m:
        return ""
    try:
        return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1))).date().isoformat()
    except ValueError:
        return ""


# ---------------------------------------------------------------- HRPeak
def parse_hrpeak_list(html: str, base: str, company: str) -> list[Job]:
    soup = BeautifulSoup(html, "html.parser")
    jobs, seen = [], set()
    for a in soup.select('a[href$=".job"]'):
        title = _t(a)
        href = a["href"]
        if not title or href in seen:
            continue
        seen.add(href)
        row = a.find_parent("tr")
        cells = [_t(td) for td in row.select("td")] if row else []
        date = next((_tr_date(c) for c in cells if _tr_date(c)), "")
        loc = _t(row.select_one(".location")) if row else ""
        url = href if href.startswith("http") else base.rstrip("/") + "/" + href.lstrip("/")
        loc = loc or "Türkiye"
        if "türkiye" not in loc.lower():
            loc += ", Türkiye"
        jobs.append(Job(source="hrpeak", native_id=href.rsplit("/", 1)[-1].replace(".job", ""), title=title,
                        company=company, location=loc, url=url, posted=date))
    return jobs


def parse_hrpeak_detail(html: str, title: str) -> str:
    """Body text after the header block ("... Yayın Tarihi: x Çalışma Yeri: y ...")."""
    text = _t(BeautifulSoup(html, "html.parser").body)
    m = re.search(r"Çalışma Yeri:\s*\S+", text)
    if m:
        # keep the work-mode word ("Yerinde", "Hibrit", "Uzaktan") for the matcher
        return (m.group(0) + " " + text[m.end():]).strip()[:6000]
    i = text.find(title)
    return text[i + len(title):].strip()[:6000] if i >= 0 else text[:6000]


def fetch_hrpeak(cfg: dict, fetcher: Fetcher) -> list[Job]:
    out = []
    for p in cfg.get("portals", []):
        base, company = p["base"].rstrip("/"), p["company"]
        jobs = []
        for page in range(int(p.get("pages", 5))):
            r = fetcher.get(f"{base}/jobs" + (f"?p={page}" if page else ""))
            if r is None:
                break
            found = parse_hrpeak_list(r.text, base, company)
            new = [j for j in found if j.id not in {x.id for x in jobs}]
            if not new:
                break
            jobs += new
        for j in jobs[: int(cfg.get("detail_limit", 60))]:
            r = fetcher.get(j.url)
            if r is not None:
                j.description = parse_hrpeak_detail(r.text, j.title)
        log.info("hrpeak/%s: %d jobs", company, len(jobs))
        out += jobs
    return out


# ---------------------------------------------------------------- Baykar
BAYKAR = "https://kariyer.baykartech.com"


def parse_baykar_list(html: str) -> list[Job]:
    soup = BeautifulSoup(html, "html.parser")
    jobs, seen = [], set()
    for a in soup.select('a[href*="/acik-pozisyonlar/detay/"]'):
        href = a["href"]
        slug = href.rstrip("/").rsplit("/", 1)[-1]
        if slug in seen:
            continue
        seen.add(slug)
        title = _t(a) or slug.replace("-", " ").title()
        jobs.append(Job(source="baykar", native_id=slug, title=title, company="Baykar",
                        location="İstanbul, Türkiye", url=BAYKAR + href if href.startswith("/") else href))
    return jobs


def parse_baykar_detail(html: str) -> tuple[str, str]:
    """(title, description)"""
    soup = BeautifulSoup(html, "html.parser")
    title = _t(soup.select_one("h1")) or (_t(soup.title).split("|", 1)[-1].strip() if soup.title else "")
    text = _t(soup.body)
    i = text.find(title) if title else -1
    body = text[i + len(title):] if i >= 0 else text
    body = re.split(r"Başvur|BAŞVUR|Apply", body)[0] if len(body) > 400 else body
    return title, body.strip()[:6000]


def fetch_baykar(cfg: dict, fetcher: Fetcher) -> list[Job]:
    r = fetcher.get(f"{BAYKAR}/tr/")
    if r is None:
        return []
    jobs = parse_baykar_list(r.text)
    for j in jobs[: int(cfg.get("detail_limit", 60))]:
        d = fetcher.get(j.url)
        if d is not None:
            title, j.description = parse_baykar_detail(d.text)
            if title and len(title) > 3:
                j.title = title
    log.info("baykar: %d jobs", len(jobs))
    return jobs
