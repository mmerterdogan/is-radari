"""Turkish early-career / public job boards.

    youthall      youthall.com/tr/is-ilanlari/?page=N lists cards (link, title, company logo alt, city, deadline);
                  each detail page carries a schema.org JobPosting JSON-LD block with the full text.
    kariyerkapisi kariyerkapisi.gov.tr (public sector): the site's own JSON API. One announcement holds several
                  positions ("alt ilan"); only positions that mention mechanical engineering are kept.
"""
from __future__ import annotations

import html as htmllib
import json
import logging
import re

from bs4 import BeautifulSoup

from ..http import Fetcher
from ..models import Job, _norm

log = logging.getLogger("radar")


def _t(el) -> str:
    return " ".join(el.get_text(" ", strip=True).split()) if el else ""


def _html_text(s: str) -> str:
    return " ".join(BeautifulSoup(s or "", "html.parser").get_text(" ", strip=True).split())


def tr_title(s: str) -> str:
    """Turkish-aware title case: "TÜRKİYE BELEDİYELER BİRLİĞİ" -> "Türkiye Belediyeler Birliği"."""
    low = " ".join((s or "").split()).replace("I", "ı").replace("İ", "i").lower()
    keep = {"ve", "ile", "veya"}
    out = " ".join(w if w in keep else (("İ" if w[0] == "i" else w[0].upper()) + w[1:]) for w in low.split(" ") if w)
    acronyms = iter(re.findall(r"\(([^)]{1,8})\)", s or ""))            # "(MARKA)", "(BDDK)" stay upper-case
    return re.sub(r"\(([^)]{1,8})\)", lambda m: f"({next(acronyms, m.group(1))})", out)


def _iso(d: str) -> str:
    m = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", d or "")
    return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}" if m else (d or "")[:10]


def _tr(loc: str) -> str:
    loc = (loc or "").strip(" +") or "Türkiye"
    return loc if "türkiye" in loc.lower() else loc + ", Türkiye"


def jsonld_jobposting(html: str) -> dict:
    """The first schema.org JobPosting object embedded in a page (empty dict if none)."""
    for m in re.finditer(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', html or "", re.S):
        try:
            data = json.loads(m.group(1))
        except ValueError:
            continue
        for d in data if isinstance(data, list) else [data]:
            if isinstance(d, dict) and d.get("@type") == "JobPosting":
                return d
    return {}


# ---------------------------------------------------------------- Youthall
YOUTHALL = "https://www.youthall.com"
EMPLOYMENT = {"FULL_TIME": "Full-time", "PART_TIME": "Part-time", "INTERN": "Internship", "TEMPORARY": "Temporary",
              "CONTRACTOR": "Contract"}


def parse_youthall_list(html: str) -> list[Job]:
    soup = BeautifulSoup(html, "html.parser")
    jobs, seen = [], set()
    for card in soup.select(".jobs"):
        a = card.select_one("a[href]")
        m = re.search(r"youthall\.com/(?:tr|en)/([^/]+)/[^/]+_(\d+)/?$", a["href"]) if a else None
        if not m:
            continue
        nid = f"{m.group(1).lower()}_{m.group(2)}"
        if nid in seen:
            continue
        seen.add(nid)
        logo = card.select_one(".jobs-content-logo")
        company = re.sub(r"\s+logo$", "", logo.get("alt", "")).strip() if logo else m.group(1)
        loc = deadline = ""
        for tag in card.select(".jobs-tag"):
            icon = " ".join(tag.select_one("i").get("class", [])) if tag.select_one("i") else ""
            if "map-marker" in icon:
                loc = _t(tag)
            elif "clock" in icon:
                deadline = _t(tag)
        jobs.append(Job(source="youthall", native_id=nid, title=_t(card.select_one("h5")), company=company,
                        location=_tr(loc), url=a["href"], description=_t(card.select_one(".jobs-content-desc")),
                        extra={"deadline": _iso(deadline)} if deadline else {}))
    return jobs


def parse_youthall_detail(html: str, job: Job) -> None:
    d = jsonld_jobposting(html)
    if not d:
        return
    job.description = _html_text(htmllib.unescape(d.get("description", "")))[:6000] or job.description
    job.posted = (d.get("datePosted") or "")[:10] or job.posted
    emp = d.get("employmentType")
    emp = emp[0] if isinstance(emp, list) and emp else emp
    if emp:
        job.extra["Employment type"] = EMPLOYMENT.get(emp, emp)
    if d.get("validThrough"):
        job.extra["deadline"] = d["validThrough"][:10]
    places = d.get("jobLocation") or []
    cities = [p.get("address", {}).get("addressLocality", "") for p in (places if isinstance(places, list) else [places])]
    if any(cities):
        job.location = _tr(", ".join(dict.fromkeys(c for c in cities if c)))


def fetch_youthall(cfg: dict, fetcher: Fetcher) -> list[Job]:
    jobs: list[Job] = []
    for page in range(1, int(cfg.get("pages", 8)) + 1):
        r = fetcher.get(f"{YOUTHALL}/tr/is-ilanlari/" + (f"?page={page}" if page > 1 else ""))
        if r is None:
            break
        have = {j.id for j in jobs}
        new = [j for j in parse_youthall_list(r.text) if j.id not in have]
        if not new:
            break
        jobs += new
    for j in jobs[: int(cfg.get("detail_limit", 100))]:
        r = fetcher.get(j.url)
        if r is not None:
            parse_youthall_detail(r.text, j)
    log.info("youthall: %d jobs", len(jobs))
    return jobs


# ---------------------------------------------------------------- Kariyer Kapısı
KK_API = "https://api.kariyerkapisi.gov.tr/api"
KK_SITE = "https://kariyerkapisi.gov.tr"
KK_HEADERS = {"Referer": KK_SITE + "/", "Content-Type": "application/json"}
KK_KEEP = re.compile(r"makine\s*muh|mechanical eng")   # engineer posts only (not "makine teknisyeni")


def bbcode_text(s: str) -> str:
    s = re.sub(r"\[url=([^\]]+)\](.*?)\[/url\]", r"\2 (\1)", s or "", flags=re.S)
    s = re.sub(r"\[/?[a-z]+(?:=[^\]]*)?\]", " ", s)
    return re.sub(r"[ \t\xa0]+", " ", _html_text(s) if "<" in s else s).strip()


def parse_kariyerkapisi(item: dict, alts: list[dict], main_text: str = "") -> list[Job]:
    """One Job per position of an announcement that mentions mechanical engineering."""
    jobs = []
    for i, a in enumerate(alts or []):
        title = " ".join((a.get("ilanBaslik") or a.get("unvan") or "").split())
        req = bbcode_text(a.get("ilanMetni", ""))
        if not KK_KEEP.search(_norm(f"{title} {req}")):
            continue
        cities = [k.get("il", "") for k in a.get("kontenjanList") or [] if k.get("il")
                  and not re.search(r"ajans|bakanl|mudurl|teskilat|genel|merkez", _norm(k["il"]))]  # "BATI AKDENİZ KALKINMA AJANSI"
        if title.isupper():
            title = tr_title(title)
        stages = ", ".join(s.get("asamaAdi", "") for s in a.get("degerlemeAsamaList") or [] if s.get("asamaAdi"))
        full = title
        if len(title) > 90:                # "Uzman (KPSS Puanı) Çevre Müh., Bilgisayar Müh., ... Makine Müh., ..."
            head = re.split(r"\s*\(?\s*\b\w+\s+m[üu]h", title, maxsplit=1, flags=re.I)[0].strip(" (-,")
            title = f"{tr_title(head) if head.isupper() else head or 'Uzman'} - Makine Mühendisliği dahil birkaç bölüm"
        desc = "\n".join(x for x in [
            f"Kamu ilanı: {item.get('ilanTuru', '')} - {item.get('ilanBaslik', '')}",
            f"Pozisyon: {full}" if full != title else "",
            f"Aranan nitelikler: {req}" if req else "",
            f"Değerlendirme: {stages}" if stages else "",
            main_text[:4000]] if x)
        jobs.append(Job(source="kariyerkapisi", native_id=f"{item['guid']}-{i}", title=title,
                        company=tr_title(item.get("kurumAdi", "")),
                        location=_tr(", ".join(dict.fromkeys(tr_title(c.split("/")[0]) for c in cities))),
                        url=f"{KK_SITE}/IlanDetay?i={item['guid']}", posted=(item.get("basTarih") or "")[:10],
                        description=desc,
                        extra={"deadline": (item.get("bitTarih") or "")[:10], "Employment type": "Kamu"}))
    return jobs


def fetch_kariyerkapisi(cfg: dict, fetcher: Fetcher) -> list[Job]:
    r = fetcher.post(f"{KK_API}/ilan/GetIseAlimPage", headers=KK_HEADERS,
                     json={"krM_ID": 0, "searchText": "", "il": "0", "ilanTuru": "0"})
    if r is None:
        return []
    items = r.json().get("searchIlan") or []
    out = []
    for it in items[: int(cfg.get("limit", 80))]:
        a = fetcher.post(f"{KK_API}/altilan/GetAltIlanInfoByIlanIdPublic", headers=KK_HEADERS, json={"ilanGuid": it["guid"]})
        alts = a.json() if a is not None else []
        if not parse_kariyerkapisi(it, alts):          # nothing mechanical -> skip the long announcement text
            continue
        d = fetcher.post(f"{KK_API}/ilan/GetIlanPreviewPublic", headers=KK_HEADERS, json={"ilanGuid": it["guid"]})
        main = bbcode_text(d.json().get("ilanMetni", "")) if d is not None else ""
        out += parse_kariyerkapisi(it, alts, main)
    log.info("kariyerkapisi: %d announcements, %d mechanical positions", len(items), len(out))
    return out
