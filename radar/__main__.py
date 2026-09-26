"""İş Radarı daily pipeline.

    python -m radar run                 # full run (fetch, match, Claude refine, letters, site, Telegram)
    python -m radar run --no-notify     # no Telegram message
    python -m radar run --no-llm        # rule-based matching only (no API cost)
    python -m radar run --only linkedin # a single source (debugging)
    python -m radar rebuild             # re-classify stored jobs with the current rules, re-export the site
    python -m radar profile             # regenerate site/profile.json from cv/cv.md + config.yaml
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from . import match, notify
from .http import Fetcher
from .models import Job, now_iso
from .sources import SOURCES, linkedin
from .store import Store

ROOT = Path(__file__).resolve().parents[1]
log = logging.getLogger("radar")

# description length kept in data.json (the site uses it for search and cover-letter prompts)
DESC_LEN = {"dogrudan": 1500, "uygun": 1500, "stretch": 1200, "dusuk": 300}
LOW_KEEP_DAYS = 7


def load_env(path: Path) -> None:
    """Minimal .env loader for local runs (GitHub Actions passes secrets as env vars)."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def load_config() -> dict:
    return yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))


def export_site(store: Store, out: Path, keep_days: int, stats: dict) -> None:
    low_cutoff = (datetime.now(timezone.utc) - timedelta(days=LOW_KEEP_DAYS)).isoformat()
    jobs = []
    for j in store.jobs.values():
        if j.category == "dusuk" and j.first_seen < low_cutoff:
            continue
        d = j.to_dict()
        d.pop("extra", None)
        d["employment"] = j.extra.get("Employment type", "")
        d["description"] = (j.description or "")[: DESC_LEN.get(j.category, 300)]
        jobs.append(d)
    jobs.sort(key=lambda d: (d["first_seen"][:10], -match.CATEGORY_ORDER.get(d["category"], 9), d["score"] or 0), reverse=True)
    payload = {"generated_at": now_iso(), "last_run": stats, "runs": store.runs[-14:], "jobs": jobs}
    out.mkdir(parents=True, exist_ok=True)
    (out / "data.json").write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def export_profile(cfg: dict) -> None:
    """Write site/profile.json: CV + letter instructions for the site's "Ön yazı" prompt."""
    from .llm import LETTER_INSTRUCTIONS, profile_block
    cv_text = (ROOT / cfg["profile"]["cv_file"]).read_text(encoding="utf-8")
    data = {"instructions": LETTER_INSTRUCTIONS, "profile": profile_block(cv_text, cfg["profile"].get("preferences", ""))}
    (ROOT / "site" / "profile.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def _by_category(jobs) -> dict:
    c = Counter(j.category for j in jobs)
    return {k: c.get(k, 0) for k in match.CATEGORY_ORDER}


def refine_with_claude(jobs: list[Job], cfg: dict, stats: dict, args) -> None:
    """Optional: Claude re-evaluates the most promising jobs and writes cover letters."""
    sc = cfg["scoring"]
    if args.no_llm or not os.environ.get("ANTHROPIC_API_KEY") or not jobs:
        log.info("ANTHROPIC_API_KEY not set (or --no-llm): rule-based matching only")
        return
    from .llm import Scorer
    cv_text = (ROOT / cfg["profile"]["cv_file"]).read_text(encoding="utf-8")
    scorer = Scorer(sc, cv_text, cfg["profile"].get("preferences", ""))
    ranked = sorted(jobs, key=lambda j: (match.CATEGORY_ORDER[j.category], -(j.score or 0)))
    scorer.score(ranked[: int(sc.get("max_llm_jobs", 40))])
    stats["scored"] = sum(1 for j in jobs if j.scored_by == "claude")
    best = [j for j in ranked if j.scored_by == "claude" and j.category == "dogrudan"][: int(sc["letters_per_day"])]
    for j in best:
        scorer.write_letter(j)
    stats["letters"] = sum(1 for j in best if j.letter)
    stats["cost_usd"] = round(scorer.cost_usd(), 4)
    stats["tokens"] = scorer.usage


def run(args) -> int:
    cfg = load_config()
    profile = match.Profile.from_config(cfg.get("profile"))
    store = Store(ROOT / "data")
    started = time.time()
    stats = {"date": datetime.now(timezone.utc).date().isoformat(), "fetched": 0, "new": 0, "relevant": 0,
             "dropped": 0, "enriched": 0, "scored": 0, "letters": 0, "by_category": {}, "sources": {},
             "failed_sources": [], "cost_usd": 0.0}

    # 1. fetch --------------------------------------------------------------------------
    fresh: list[Job] = []
    if args.hours:  # e.g. first run: look back further than the daily 24 hours
        cfg["search"]["linkedin"]["hours"] = args.hours
    for name, module in SOURCES.items():
        scfg = cfg["search"].get(name, {})
        if not scfg.get("enabled", False) or (args.only and name != args.only):
            continue
        fetcher = Fetcher(delay=float(scfg.get("delay_seconds", 2)))
        try:
            found = module.fetch(scfg, fetcher)
        except Exception as exc:  # one broken source must not stop the others
            log.exception("source %s failed: %s", name, exc)
            found = []
        stats["sources"][name] = len(found)
        if not found:
            stats["failed_sources"].append(name)
        fresh.extend(found)
    stats["fetched"] = len(fresh)

    # 2. dedupe -------------------------------------------------------------------------
    new_jobs: list[Job] = []
    batch_keys = set()
    for j in fresh:
        if store.is_new(j) and j.dedupe_key not in batch_keys:
            batch_keys.add(j.dedupe_key)
            j.first_seen = now_iso()
            new_jobs.append(j)
    stats["new"] = len(new_jobs)

    # 3. relevance gate: drop only jobs that are clearly not for a mechanical engineer ---------
    # Generic titles without a domain signal and without text yet are "pending": decided after step 4.
    relevant, dropped_log, pending = [], [], set()
    for j in new_jobs:
        keep, why = match.relevance(j, profile, allow_pending=True)
        if keep:
            relevant.append(j)
            if why == "pending":
                pending.add(j.id)
        else:
            store.dedupe.update((j.dedupe_key, j.id))
            dropped_log.append({"title": j.title, "company": j.company, "location": j.location, "url": j.url, "reason": why})
    stats["dropped"] = len(new_jobs) - len(relevant)
    log.info("%d fetched, %d new, %d relevant (%d pending full text)", len(fresh), len(new_jobs), len(relevant), len(pending))

    # 4. fetch full text for LinkedIn ads: pending decisions first, then the most promising titles ---
    mcfg = cfg.get("match", {})
    li_fetcher = Fetcher(delay=float(cfg["search"]["linkedin"].get("delay_seconds", 6)))
    to_enrich = sorted((j for j in relevant if j.source == "linkedin" and len(j.description) < match.SHORT_TEXT),
                       key=lambda j: match.quick_rank(j) + (25 if j.id in pending else 0),
                       reverse=True)[: int(mcfg.get("enrich_limit", 100))]
    for j in to_enrich:
        linkedin.enrich(j, li_fetcher)
    stats["enriched"] = sum(1 for j in to_enrich if len(j.description) >= match.SHORT_TEXT)

    # 5. re-check the gate with the full text, then rule-based matching for every relevant job ------
    #    (pending jobs whose text could not be fetched are kept and marked "title only")
    kept = []
    for j in relevant:
        keep, why = match.relevance(j, profile, allow_pending=True)
        if keep and why == "pending" and not match.keep_without_text(j):
            keep, why = False, "Genel başlık, ilan metni alınamadı"
        if not keep:
            store.dedupe.update((j.dedupe_key, j.id))
            stats["dropped"] += 1
            dropped_log.append({"title": j.title, "company": j.company, "location": j.location, "url": j.url,
                                "reason": why + " (tam metinden)"})
            continue
        kept.append(match.analyze(j, profile))
    stats["relevant"] = len(kept)

    # 6. optional Claude refinement + cover letters ---------------------------------------
    refine_with_claude(kept, cfg, stats, args)
    stats["by_category"] = _by_category(kept)

    # 7. persist -------------------------------------------------------------------------
    for j in kept:
        store.add(j)
    store.prune(int(cfg["site"]["keep_days"]))
    stats["seconds"] = round(time.time() - started)
    store.runs.append(stats)
    if not args.dry:
        store.save()
        export_site(store, ROOT / "site", int(cfg["site"]["keep_days"]), stats)
        export_profile(cfg)
        # transparency: what the relevance gate removed in this run (to tune the rules)
        (ROOT / "data" / "dropped_last.json").write_text(
            json.dumps(sorted(dropped_log, key=lambda d: d["reason"])[:400], ensure_ascii=False, indent=1), encoding="utf-8")

    # 8. notify -------------------------------------------------------------------------
    if cfg["notify"].get("telegram") and not args.no_notify and not args.dry:
        notify.send(notify.build_message(kept, stats, os.environ.get("SITE_URL", ""), cfg["notify"]))

    log.info("done: %s", json.dumps({k: v for k, v in stats.items() if k != "tokens"}, ensure_ascii=False))
    return 0


def rebuild(args) -> int:
    """Re-run the rule-based matcher on stored jobs (after changing rules or the profile)."""
    cfg = load_config()
    profile = match.Profile.from_config(cfg.get("profile"))
    store = Store(ROOT / "data")
    dropped = 0
    for key, j in list(store.jobs.items()):
        keep, why = match.relevance(j, profile, allow_pending=True)
        if not keep or (why == "pending" and not match.keep_without_text(j)):
            store.dedupe.update((j.dedupe_key, key))
            del store.jobs[key]
            dropped += 1
            continue
        letter = j.letter
        claude = j.scored_by == "claude"
        if not claude or args.force:
            match.analyze(j, profile)
        j.letter = letter
    stats = dict(store.runs[-1]) if store.runs else {"date": datetime.now(timezone.utc).date().isoformat()}
    stats["by_category"] = _by_category(store.jobs.values())
    store.save()
    export_site(store, ROOT / "site", int(cfg["site"]["keep_days"]), stats)
    export_profile(cfg)
    log.info("rebuilt %d jobs (%d dropped): %s", len(store.jobs), dropped, stats["by_category"])
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="radar", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--no-llm", action="store_true", help="rule-based matching only")
    r.add_argument("--no-notify", action="store_true", help="do not send Telegram")
    r.add_argument("--dry", action="store_true", help="do not write data/ or site/")
    r.add_argument("--only", choices=list(SOURCES), help="run a single source")
    r.add_argument("--hours", type=int, help="LinkedIn look-back window (default from config, e.g. 168 for a first run)")
    b = sub.add_parser("rebuild", help="re-classify stored jobs with the current rules")
    b.add_argument("--force", action="store_true", help="also overwrite Claude assessments with the rules")
    sub.add_parser("profile", help="regenerate site/profile.json from cv/cv.md + config.yaml")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    load_env(ROOT / ".env")
    if args.cmd == "profile":
        export_profile(load_config())
        return 0
    if args.cmd == "rebuild":
        return rebuild(args)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
