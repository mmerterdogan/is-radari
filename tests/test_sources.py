"""Sprint 1: HTTP retry/circuit breaker, LinkedIn detail (closed, applicants, Turkish criteria),
SmartRecruiters parser, enrich/backfill queue and per-query stats. Run: python -m pytest tests -q"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
FIX = ROOT / "tests" / "fixtures"

from radar import __main__ as pipeline  # noqa: E402
from radar import http as rhttp  # noqa: E402
from radar import match  # noqa: E402
from radar.models import Job  # noqa: E402
from radar.sources import linkedin, smartrecruiters  # noqa: E402


# ---------------------------------------------------------------- Fetcher
class FakeSession:
    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = 0
        self.headers = {}

    def request(self, method, url, **kw):
        self.calls += 1
        status, headers = self.answers.pop(0)
        return SimpleNamespace(status_code=status, headers=headers, text="ok")


def fetcher_with(answers, monkeypatch, retries=2):
    slept = []
    monkeypatch.setattr(rhttp.time, "sleep", lambda s: slept.append(s))
    f = rhttp.Fetcher(delay=0, retries=retries)
    f.session = FakeSession(answers)
    return f, slept


def test_retry_after_is_respected_and_capped(monkeypatch):
    f, slept = fetcher_with([(429, {"Retry-After": "7"}), (429, {"Retry-After": "999"}), (200, {})], monkeypatch)
    assert f.get("u").status_code == 200
    assert slept == [7.0, rhttp.MAX_BACKOFF] and f.rate_limited_streak == 0


def test_rate_limited_streak_counts_failed_requests(monkeypatch):
    f, _ = fetcher_with([(429, {})] * 6, monkeypatch, retries=1)
    assert f.get("a") is None and f.get("b") is None and f.get("c") is None
    assert f.rate_limited_streak == 3


def test_404_is_not_retried(monkeypatch):
    f, _ = fetcher_with([(404, {})], monkeypatch)
    assert f.get("u") is None and f.session.calls == 1


# ---------------------------------------------------------------- LinkedIn detail
def test_closed_ad_and_turkish_criteria():
    desc, crit = linkedin.parse_detail((FIX / "linkedin_closed.html").read_text(encoding="utf-8"))
    assert crit["closed"] is True
    assert "Kıdem düzeyi" not in crit and ("Seniority level" in crit or not crit.get("Seniority level"))


def test_open_ad_is_not_closed():
    _, crit = linkedin.parse_detail((FIX / "linkedin_detail.html").read_text(encoding="utf-8"))
    assert "closed" not in crit


def test_normalize_criteria_maps_turkish_labels():
    extra = {"Kıdem düzeyi": "Başlangıç Seviye", "İstihdam türü": "Yarı Zamanlı", "Sektörler": "Savunma"}
    linkedin.normalize_criteria(extra)
    assert extra == {"Seniority level": "Entry level", "Employment type": "Part-time", "Industries": "Savunma"}
    j = Job(source="linkedin", native_id="1", title="Mechanical Engineer", company="X", location="İstanbul", url="u",
            extra={"Seniority level": "Entry level"})
    assert match.parse_experience(j)["fit"] == "iyi"


def test_applicant_count_parsing():
    assert linkedin._applicants("172 başvuru") == "172"
    assert linkedin._applicants("1,204 applicants") == "1204"
    assert linkedin._applicants("İlk 25 başvurandan biri olun") == "<25"
    assert linkedin._applicants("Be among the first 25 applicants") == "<25"
    assert linkedin._applicants("Over 200 applicants") == "200+"
    assert linkedin._applicants("200'den fazla başvuru") == "200+"
    assert linkedin._applicants("") == ""


# ---------------------------------------------------------------- SmartRecruiters
def test_smartrecruiters_list_and_detail():
    data = json.loads((FIX / "smartrecruiters_list.json").read_text(encoding="utf-8"))
    jobs = [smartrecruiters.parse_posting(p) for p in data["content"]]
    j = jobs[0]
    assert j.source == "smartrecruiters" and j.native_id.startswith("BoschGroup-")
    assert j.company == "Bosch Group" and "Turkey" in j.location and j.url.startswith("https://jobs.smartrecruiters.com/")
    assert j.posted[:2] == "20" and j.extra.get("Seniority level")
    desc = smartrecruiters.parse_detail(json.loads((FIX / "smartrecruiters_detail.json").read_text(encoding="utf-8")))
    assert len(desc) > 200 and "<" not in desc
    assert match.location_tier(j, "belirtilmemis") in (1, 2, 3)


# ---------------------------------------------------------------- enrich queue / query stats
def test_enrich_queue_stops_when_rate_limited(monkeypatch):
    calls = []

    def fake_enrich(job, fetcher):
        calls.append(job.native_id)
        fetcher.rate_limited_streak += 1   # every request ends in 429

    monkeypatch.setattr(linkedin, "enrich", fake_enrich)
    jobs = [Job(source="linkedin", native_id=str(i), title="T", company="C", location="", url="u") for i in range(10)]
    stats = {}
    got = pipeline.enrich_queue(jobs, SimpleNamespace(rate_limited_streak=0), stats)
    assert got == 0 and len(calls) == pipeline.RATE_LIMIT_STOP and stats["enrich_blocked"]


def test_query_stats_accumulate(tmp_path):
    def job(i, q):
        return Job(source="linkedin", native_id=str(i), title="T", company=f"C{i}", location="", url="u",
                   extra={"query": q, "query_location": "Turkey"})
    a, b, c = job(1, "makine mühendisi"), job(2, "makine mühendisi"), job(3, "FEA")
    a.category, b.category = "uygun", "dusuk"
    path = tmp_path / "q.json"
    pipeline.update_query_stats(path, [a, b, c], [a, b])
    pipeline.update_query_stats(path, [a], [a])
    d = json.loads(path.read_text(encoding="utf-8"))
    assert d["makine mühendisi @ Turkey"] == {"total": 3, "good": 2, "yield": 0.67}
    assert d["FEA @ Turkey"]["good"] == 0


def test_skill_gaps_roadmap():
    from radar.models import now_iso

    def job(i, cat, gaps):
        j = Job(source="linkedin", native_id=str(i), title="T", company="C", location="", url="u")
        j.category, j.gaps, j.first_seen = cat, gaps, now_iso()
        return j
    jobs = [job(1, "uygun", ["CATIA", "FMEA"]), job(2, "stretch", ["CATIA"]), job(3, "dusuk", ["CATIA", "SAP / ERP"])]
    rows = pipeline.skill_gaps(jobs, learning={"catia": [{"label": "x", "url": "https://x"}]})
    assert rows[0] == {"label": "CATIA", "key": "catia", "count": 2, "share": 1.0, "resources": [{"label": "x", "url": "https://x"}]}
    assert [r["label"] for r in rows] == ["CATIA", "FMEA"]   # low-fit ads do not count


# ---------------------------------------------------------------- Sprint 3 sources
from radar.sources import ats, portals  # noqa: E402


def test_hrpeak_list_and_detail():
    jobs = portals.parse_hrpeak_list((FIX / "hrpeak_list.html").read_text(encoding="utf-8"), "https://kariyer.roketsan.com.tr", "ROKETSAN")
    assert len(jobs) >= 15 and all(j.url.endswith(".job") for j in jobs)
    p = next(j for j in jobs if j.title == "Proses Mühendisi (Mekanik)")
    assert p.location == "Ankara, Türkiye" and p.posted == "2026-09-25" and p.company == "ROKETSAN"
    desc = portals.parse_hrpeak_detail((FIX / "hrpeak_detail.html").read_text(encoding="utf-8"), p.title)
    assert desc.startswith("Çalışma Yeri") and "Makine Mühendisliği" in desc
    p.description = desc
    j = match.analyze(p)
    assert j.education["field"] == "makine" and j.work_mode == "ofiste" and j.loc_tier == 2


def test_baykar_list_and_detail():
    jobs = portals.parse_baykar_list((FIX / "baykar_list.html").read_text(encoding="utf-8"))
    assert len(jobs) >= 20 and len({j.id for j in jobs}) == len(jobs)
    title, body = portals.parse_baykar_detail((FIX / "baykar_detail.html").read_text(encoding="utf-8"))
    assert title and len(body) > 200


def test_workday_list_and_detail():
    t = {"tenant": "hitachi", "wd": "wd1", "site": "hitachi", "company": "Hitachi Energy"}
    jobs = ats.parse_workday_list(json.loads((FIX / "workday_list.json").read_text(encoding="utf-8")), t)
    assert jobs and jobs[0].url.startswith("https://hitachi.wd1.myworkdayjobs.com/hitachi/job/")
    assert jobs[0].native_id.startswith("hitachi-")
    desc, posted, loc = ats.parse_workday_detail(json.loads((FIX / "workday_detail.json").read_text(encoding="utf-8")))
    assert len(desc) > 100 and posted[:2] == "20" and loc


def test_lever_and_ashby_location_filter():
    lever = json.loads((FIX / "lever.json").read_text(encoding="utf-8"))
    assert ats.parse_lever(lever, "velo3d", "Velo3D", r"Turkey") == []
    everywhere = ats.parse_lever(lever, "velo3d", "Velo3D", r".")
    assert everywhere and everywhere[0].url and everywhere[0].posted[:2] == "20"
    ashby = json.loads((FIX / "ashby.json").read_text(encoding="utf-8"))
    got = ats.parse_ashby(ashby, "1x", "1X", r".")
    assert got and got[0].description
