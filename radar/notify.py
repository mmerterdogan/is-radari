"""Telegram daily summary, grouped by fit category."""
from __future__ import annotations

import html
import logging
import os

import requests

from .match import CATEGORY_LABEL, CATEGORY_ORDER
from .models import Job

log = logging.getLogger("radar")

ICON = {"dogrudan": "🟢", "uygun": "🔵", "stretch": "🟡", "belirsiz": "❔", "dusuk": "⚪"}


def _line(j: Job) -> list[str]:
    facts = " · ".join(x for x in [
        j.loc_label + (f" ({html.escape(j.location)})" if j.location else ""),
        {"uzaktan": "uzaktan", "hibrit": "hibrit"}.get(j.work_mode, ""),
        j.experience.get("label", ""),
        j.education.get("label", "") if j.education.get("level") != "belirtilmemis" else "",
        "staj" if j.is_internship else "",
    ] if x)
    out = [f"• <a href=\"{html.escape(j.url)}\">{html.escape(j.title)}</a> - {html.escape(j.company)}",
           f"   <i>{html.escape(facts)}</i>"]
    if j.category_reasons:
        out.append(f"   {html.escape(j.category_reasons[0])}")
    return out


def build_message(jobs: list[Job], stats: dict, site_url: str, ncfg: dict | None = None) -> str:
    ncfg = ncfg or {}
    per_cat = {"dogrudan": int(ncfg.get("top_direct", 6)), "uygun": int(ncfg.get("top_fit", 4)),
               "stretch": int(ncfg.get("top_stretch", 2))}
    by_cat: dict[str, list[Job]] = {k: [] for k in CATEGORY_ORDER}
    for j in jobs:
        by_cat.setdefault(j.category, []).append(j)
    for lst in by_cat.values():
        lst.sort(key=lambda j: (j.loc_tier, -(j.score or 0)))

    counts = " · ".join(f"{ICON[k]} {len(by_cat[k])}" for k in CATEGORY_ORDER)
    lines = [f"<b>🎯 İş Radarı</b> · {stats.get('date', '')}",
             f"{stats.get('fetched', 0)} ilan tarandı, {stats.get('relevant', len(jobs))} ilgili: {counts}"]
    if not stats.get("scored"):
        lines.append("<i>Kural tabanlı eşleştirme (Claude API yok)</i>")
    if stats.get("failed_sources"):
        lines.append("⚠️ Sonuç vermeyen kaynak: " + ", ".join(stats["failed_sources"]))
    shown = False
    for cat, n in per_cat.items():
        if not by_cat[cat] or n <= 0:
            continue
        shown = True
        lines += ["", f"<b>{ICON[cat]} {CATEGORY_LABEL[cat]} ({len(by_cat[cat])})</b>"]
        for j in by_cat[cat][:n]:
            lines += _line(j)
        if len(by_cat[cat]) > n:
            lines.append(f"   … ve {len(by_cat[cat]) - n} ilan daha")
    if not shown:
        lines += ["", "Bugün doğrudan uygun, uygun veya stretch yeni ilan yok."]
    if site_url:
        lines += ["", f"<a href=\"{html.escape(site_url)}\">Tüm liste, filtreler ve başvuru takibi →</a>"]
    return "\n".join(lines)


def send(text: str) -> bool:
    token, chat = os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        log.warning("TELEGRAM_TOKEN / TELEGRAM_CHAT_ID not set - skipping notification")
        return False
    # Telegram limit is 4096 chars; split on line boundaries
    chunks, cur = [], ""
    for line in text.split("\n"):
        if len(cur) + len(line) + 1 > 3800:
            chunks.append(cur)
            cur = ""
        cur += line + "\n"
    chunks.append(cur)
    ok = True
    for chunk in chunks:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          data={"chat_id": chat, "text": chunk, "parse_mode": "HTML",
                                "disable_web_page_preview": "true"}, timeout=20)
        if not r.ok:
            log.error("Telegram error %s: %s", r.status_code, r.text[:200])
            ok = False
    return ok
