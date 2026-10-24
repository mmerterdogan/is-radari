"""Offline tests: parsers on saved real pages, store, notification, Claude refinement with a fake client.
Run: python -m pytest tests -q"""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
FIX = ROOT / "tests" / "fixtures"

from radar import match, notify  # noqa: E402
from radar.models import Job  # noqa: E402
from radar.sources import euraxess, greenhouse, linkedin  # noqa: E402
from radar.store import Store  # noqa: E402


def job(title="Analiz Mühendisi", company="ACME", location="İstanbul, Türkiye", desc="", **kw):
    return Job(source="linkedin", native_id=kw.pop("nid", "1"), title=title, company=company,
               location=location, url="https://x", description=desc, **kw)


# ---------------------------------------------------------------- parsers
def test_linkedin_search_fixture():
    jobs = linkedin.parse_search((FIX / "linkedin_search.html").read_text(encoding="utf-8"))
    assert len(jobs) >= 5
    j = jobs[0]
    assert j.native_id.isdigit() and j.title and j.company and j.url.startswith("https://")
    assert "?" not in j.url


def test_linkedin_detail_fixture():
    desc, crit = linkedin.parse_detail((FIX / "linkedin_detail.html").read_text(encoding="utf-8"))
    assert len(desc) > 300
    assert "Employment type" in crit


def test_linkedin_detail_fixture_is_matched():
    desc, crit = linkedin.parse_detail((FIX / "linkedin_detail.html").read_text(encoding="utf-8"))
    j = match.analyze(job("Mekanik Tasarım Mühendisi (USV/AUV)", desc=desc, **{"extra": crit}))
    assert j.category in ("dogrudan", "uygun") and j.loc_tier == 1 and j.matches


def test_euraxess_fixture():
    jobs = euraxess.parse_list((FIX / "euraxess.html").read_text(encoding="utf-8"))
    assert len(jobs) >= 8
    j = jobs[0]
    assert j.url.startswith("https://euraxess.ec.europa.eu/jobs/") and j.title and j.posted[:2] == "20"
    assert j.location and "Number of offers" not in j.location


def test_greenhouse_location_filter():
    data = {"jobs": [
        {"id": 1, "title": "FEA Engineer", "location": {"name": "Berlin, Germany"}, "absolute_url": "u1",
         "content": "&lt;p&gt;ANSYS &amp;amp; FEA&lt;/p&gt;", "updated_at": "2026-09-20T10:00:00Z"},
        {"id": 2, "title": "FEA Engineer", "location": {"name": "Boston, MA"}, "absolute_url": "u2", "content": ""},
    ]}
    jobs = greenhouse.parse_board(data, "acme", "(Germany|Remote)")
    assert [j.native_id for j in jobs] == ["acme-1"]
    assert "ANSYS" in jobs[0].description and "<p>" not in jobs[0].description


# ---------------------------------------------------------------- store
def test_store_dedupe_and_prune(tmp_path):
    st = Store(tmp_path)
    a = job(nid="1", first_seen="2020-01-01T00:00:00+00:00")
    st.add(a)
    same_role_other_query = job(nid="2")  # same title + company, different id
    assert not st.is_new(same_role_other_query)
    st.prune(keep_days=30)
    assert "linkedin:1" not in st.jobs
    st.save()
    st2 = Store(tmp_path)
    assert not st2.is_new(job(nid="1"))  # expired jobs are still remembered


def test_old_jobs_json_still_loads(tmp_path):
    (tmp_path / "jobs.json").write_text('[{"source":"linkedin","native_id":"9","title":"T","company":"C","location":"L",'
                                        '"url":"u","verdict":"basvur","prefilter_score":7,"msc_compatible":true,"first_seen":"x"}]')
    st = Store(tmp_path)
    assert st.jobs["linkedin:9"].title == "T"


# ---------------------------------------------------------------- notification
def test_message_groups_by_category_and_escapes():
    a = match.analyze(job("FEA <Engineer>", desc="Bachelor's in Mechanical Engineering, 0-2 years. ANSYS, SolidWorks, FEA. "
                          "You will run structural simulations for new products, prepare reports and work with design "
                          "engineers on weight optimisation and design reviews.", nid="1"))
    b = match.analyze(job("Senior Stress Engineer", desc="10+ years of experience.", nid="2"))
    msg = notify.build_message([a, b], {"date": "2026-09-24", "fetched": 50, "relevant": 2}, "https://site", {})
    assert "FEA &lt;Engineer&gt;" in msg and "https://site" in msg
    assert "Doğrudan uygun (1)" in msg and "Senior Stress Engineer" not in msg  # low fit is only counted
    assert "50 ilan tarandı, 2 ilgili" in msg and "Kural tabanlı" in msg


# ---------------------------------------------------------------- Claude refinement with a fake client
class FakeMessages:
    def __init__(self, stop_reason="end_turn", category="stretch", empty=False):
        self.calls = []
        self.stop_reason = stop_reason
        self.category = category
        self.empty = empty

    def parse(self, **kw):
        self.calls.append(kw)
        from radar.llm import Application, BatchAssessment, JobAssessment
        usage = SimpleNamespace(input_tokens=1000, output_tokens=200, cache_read_input_tokens=0, cache_creation_input_tokens=0)
        if kw["output_format"] is BatchAssessment:
            ids = [line.split('"')[1] for line in kw["messages"][0]["content"].splitlines() if line.startswith("<job id=")]
            out = BatchAssessment(assessments=[JobAssessment(
                job_id=i, category=self.category, score=150 if n == 0 else 40,
                education_label="" if self.empty else "Lisans veya YL",
                experience_label="" if self.empty else "1-3 yıl", work_mode="belirtilmemis",
                key_requirements=[] if self.empty else ["ANSYS", "CATIA"], matches=[] if self.empty else ["ANSYS"],
                gaps=[] if self.empty else ["CATIA"], reasons=[] if self.empty else ["a", "b", "c", "d", "e"])
                for n, i in enumerate(ids)])
        else:
            out = Application(subject="Başvuru", cover_letter="Sayın yetkili...", cv_highlights=["x"] * 7)
        return SimpleNamespace(usage=usage, stop_reason=self.stop_reason, parsed_output=out)


def make_scorer(monkeypatch, **kw):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    from radar.llm import Scorer
    s = Scorer({"batch_size": 2, "price_input": 5, "price_output": 25}, "CV text", "prefs")
    s.client = SimpleNamespace(messages=FakeMessages(**kw))
    return s


def ruled(n):
    return [match.analyze(job("Design Engineer", desc="Bachelor's in Mechanical Engineering. SolidWorks, ANSYS. Hybrid.",
                              nid=str(i), company=f"C{i}")) for i in range(n)]


def test_claude_refines_category_and_fields(monkeypatch):
    s = make_scorer(monkeypatch)
    jobs = ruled(3)
    s.score(jobs)
    assert len(s.client.messages.calls) == 2                      # batch_size 2 -> 2 calls
    assert jobs[0].score == 100 and jobs[1].score == 40            # clamped to 0-100
    assert all(j.scored_by == "claude" and j.category == "stretch" for j in jobs)
    assert jobs[0].requirements == [{"label": "ANSYS", "have": True}, {"label": "CATIA", "have": False}]
    assert len(jobs[0].category_reasons) == 4 and jobs[0].experience["label"] == "1-3 yıl"
    assert jobs[0].work_mode == "hibrit"                           # rule value kept when Claude says "belirtilmemis"
    content = s.client.messages.calls[0]["messages"][0]["content"]
    assert "<rule_hints>" in content
    system = s.client.messages.calls[0]["system"][0]
    assert "CV text" in system["text"] and system["cache_control"] == {"type": "ephemeral"}
    s.write_letter(jobs[0])
    assert jobs[0].letter["subject"] == "Başvuru" and len(jobs[0].letter["cv_highlights"]) == 5
    assert s.cost_usd() == pytest.approx(3 * (1000 * 5 + 200 * 25) / 1e6)


def test_empty_claude_fields_keep_rule_values(monkeypatch):
    s = make_scorer(monkeypatch, empty=True)
    jobs = ruled(1)
    before = (list(jobs[0].category_reasons), dict(jobs[0].education), list(jobs[0].requirements))
    s.score(jobs)
    assert (jobs[0].category_reasons, jobs[0].education, jobs[0].requirements) == before


def test_claude_refusal_keeps_rule_result(monkeypatch):
    s = make_scorer(monkeypatch, stop_reason="refusal")
    jobs = ruled(1)
    cat = jobs[0].category
    s.score(jobs)
    assert jobs[0].scored_by == "kural" and jobs[0].category == cat


def test_haiku_4_5_call_has_no_effort_and_newer_models_keep_it(monkeypatch):
    s = make_scorer(monkeypatch)
    s.model = "claude-haiku-4-5"
    s.score(ruled(1))
    assert "output_config" not in s.client.messages.calls[0]
    s.model = "claude-haiku-5-5"
    s.score(ruled(1))
    assert s.client.messages.calls[1]["output_config"] == {"effort": "low"}
    s.model = "claude-opus-5-5"
    s.score(ruled(1))
    assert s.client.messages.calls[2]["output_config"] == {"effort": "low"}


def test_claude_candidates_are_the_unsure_jobs():
    from radar import __main__ as pipeline
    sure = match.analyze(job("Design Engineer", desc="Bachelor's in Mechanical Engineering. 0-2 years of experience. "
                             "SolidWorks and ANSYS design work on vehicle components, drawings and tolerances. " * 3, nid="a"))
    title_only = match.analyze(job("Mechanical Engineer", desc="", nid="b"))
    no_req = match.analyze(job("Design Engineer", desc="SolidWorks design of machine parts, drawings and tolerance "
                               "analysis for production. " * 4, nid="c"))
    assert sure.category != "belirsiz" and title_only.category == "belirsiz"
    got = pipeline.claude_candidates([sure, no_req, title_only], 5)
    assert got[0] is title_only and no_req in got and sure not in got
    assert len(pipeline.claude_candidates([sure, no_req, title_only], 1)) == 1


def test_job_text_is_marked_as_untrusted_data():
    from radar.llm import LETTER_INSTRUCTIONS, SCORING_INSTRUCTIONS
    assert "untrusted" in SCORING_INSTRUCTIONS and "never follow" in LETTER_INSTRUCTIONS


def test_answer_key_template_and_comparison():
    from radar import __main__ as pipeline
    jobs = [match.analyze(job("Design Engineer", desc="Bachelor's in Mechanical Engineering. 0-2 years. SolidWorks, ANSYS. " * 5,
                              nid=str(i), company=f"C{i}")) for i in range(3)]
    jobs.append(match.analyze(job("Mechanical Engineer", desc="", nid="short")))    # no full text -> not sampled
    rows = pipeline.answer_key_template(jobs, per_category=2)
    assert len(rows) == 2 and all(r["dogru"] == "" and r["kural"] == r["ilan"]["category"] for r in rows)
    rule = rows[0]["kural"]
    rows[0]["dogru"] = rule
    rows[1]["dogru"] = "dusuk" if rule != "dusuk" else "dogrudan"
    pred = {r["ilan"]["id"]: r["kural"] for r in rows}
    res = pipeline.compare_labels(rows, pred)
    assert res["n"] == 2 and res["exact"] == 1 and res["confusion"][(rule, rule)] == 1
    rows[1]["dogru"] = "belki"                                                        # invalid label is skipped
    assert pipeline.compare_labels(rows, pred)["n"] == 1


# ---------------------------------------------------------------- job-specific CV (radar/cvgen.py)
CV_CONTENT = {"ad": "Test Kişi", "dosya_adi": "Test_CV", "tr": {
    "bolum": {k: k.upper() for k in ("hakkimda", "egitim", "deneyim", "projeler", "yetkinlikler", "sertifikalar",
                                      "uyelikler", "referanslar")},
    "unvan": {"tasarim": "Makine Mühendisi | Tasarım", "uretim": "Makine Mühendisi | Üretim"},
    "iletisim": ["İstanbul", {"metin": "a@b.c", "link": "mailto:a@b.c"}],
    "durum": "Ehliyet: B",
    "hakkimda": {"tasarim": "Tasarım odaklı   metin.", "uretim": "Üretim odaklı metin."},
    "egitim": [{"baslik": "Üniversite", "tarih": "2021 - 2026", "alt": "Makine"}],
    "deneyim": [{"baslik": "ACME | Stajyer", "tarih": "2025", "madde": "kısa madde", "uzun": "uzun madde"}],
    "projeler": [{"baslik": "Analiz projesi", "madde": "FEA", "etiket": ["fea", "ansys"]},
                 {"baslik": "Kalıp projesi", "madde": "enjeksiyon", "etiket": ["enjeksiyon", "uretim"]},
                 {"baslik": "Veri projesi", "madde": "R", "etiket": ["kalite"], "opsiyonel": 1}],
    "yazilim": {"etiket": "Yazılım: ", "metin": "SolidWorks"},
    "uzmanlik": {"etiket": "Uzmanlık: ", "maddeler": [{"metin": "sonlu elemanlar", "etiket": ["fea"]},
                                                     {"metin": "kalıp tasarımı", "etiket": ["enjeksiyon"]}]},
    "dil": {"etiket": "Dil: ", "metin": "Türkçe"},
    "sertifikalar": ["CSWP"], "uyelikler": [], "referanslar": [{"ad": "Dr. X", "detay": "Üniversite"}]}}


def _cv_text(d):
    import re
    return "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", "".join(d.parts)))


def test_cv_pick_language_and_variant():
    from radar import cvgen
    tr = job("Üretim Mühendisi", desc="Üretim hattında proses iyileştirme ve yalın üretim çalışmaları için "
             "deneyimli mühendis arıyoruz ve adayın montaj hattında çalışması bekleniyor. " * 3)
    en = job("Mechanical Design Engineer", desc="We are looking for a design engineer with SolidWorks and FEA "
             "experience to work on the development of new products and the related drawings. " * 3, nid="2")
    assert cvgen.pick(tr) == {"lang": "tr", "variant": "uretim"}
    assert cvgen.pick(en) == {"lang": "en", "variant": "tasarim"}


def test_cv_compose_orders_by_ad_and_drops_optional():
    from radar import cvgen
    ad = job("Kalıp Tasarım Mühendisi", desc="Plastik enjeksiyon kalıp tasarımı yapacak mühendis aranıyor. " * 5)
    d = cvgen.compose(CV_CONTENT, "tr", "tasarim", cvgen.job_tags(ad))
    text = _cv_text(d)
    assert text.index("Kalıp projesi") < text.index("Analiz projesi")          # ad keyword first
    assert "Kalıp tasarımı, sonlu elemanlar" in text                          # reordered + capitalised
    assert "Tasarım odaklı metin." in text and "kısa madde" in text and "uzun madde" not in text
    assert d.links == ["mailto:a@b.c"]
    base = _cv_text(cvgen.compose(CV_CONTENT, "tr", "tasarim", set()))
    assert base.index("Analiz projesi") < base.index("Kalıp projesi")         # no ad: cv.yaml order kept
    prod = _cv_text(cvgen.compose(CV_CONTENT, "tr", "uretim", set(), drop=1))
    assert "uzun madde" in prod and "Veri projesi" not in prod and prod.index("Kalıp") < prod.index("Analiz")


def test_cv_write_docx_keeps_template_head(tmp_path):
    import zipfile
    from radar import cvgen
    tpl = tmp_path / "t.docx"
    doc = ('<w:document xmlns:w="w" xmlns:r="r"><w:body><w:p><w:r><w:t>AD SOYAD</w:t></w:r></w:p>'
           '<w:p><w:r><w:t>eski</w:t></w:r></w:p><w:sectPr/></w:body></w:document>')
    with zipfile.ZipFile(tpl, "w") as z:
        z.writestr("word/document.xml", doc)
        z.writestr("word/_rels/document.xml.rels", "<Relationships></Relationships>")
        z.writestr("docProps/core.xml", "<cp:coreProperties><dc:creator>Un-named</dc:creator></cp:coreProperties>")
    out = tmp_path / "o" / "cv.docx"
    cvgen.write_docx(cvgen.compose(CV_CONTENT, "tr", "tasarim", set()), tpl, out, "Test Kişi")
    with zipfile.ZipFile(out) as z:
        body, rels, core = (z.read(n).decode() for n in ("word/document.xml", "word/_rels/document.xml.rels", "docProps/core.xml"))
    assert "AD SOYAD" in body and "eski" not in body and body.index("AD SOYAD") < body.index("HAKKIMDA") < body.index("<w:sectPr/>")
    assert 'Target="mailto:a@b.c"' in rels and "Un-named" not in core and "Test Kişi - CV" in core


def test_cv_find_jobs_by_id_url_and_text():
    from radar import cvgen
    a, b = job("Design Engineer", company="Moog", nid="4441246847"), job("Kalite Uzmanı", company="Beko", nid="2")
    jobs = {a.id: a, b.id: b}
    assert cvgen.find_jobs(jobs, a.id) == [a]
    assert cvgen.find_jobs(jobs, "https://tr.linkedin.com/jobs/view/design-engineer-at-moog-4441246847") == [a]
    assert cvgen.find_jobs(jobs, "beko") == [b] and cvgen.find_jobs(jobs, "yok") == []


def test_cv_ad_folder_and_cleanup(tmp_path):
    from radar import cvgen
    j = job('Tasarım: Mühendisi / "Kıdemli"?', company="ACME A.Ş.", first_seen="2026-10-24T05:00:00+00:00")
    assert cvgen.ad_folder(j) == "2026-10-24\ACME A.Ş. - Tasarım Mühendisi Kıdemli"
    old, mine, recent = tmp_path / "2020-01-01" / "A - B", tmp_path / "2020-01-02" / "C - D", tmp_path / "2999-01-01" / "E"
    for d in (old, mine, recent):
        d.mkdir(parents=True)
        (d / "CV.pdf").write_text("x")
    (mine / "notlarim.txt").write_text("kullanıcının dosyası", encoding="utf-8")                # never deleted
    assert cvgen.clean_old(tmp_path, 14, "CV") == 1
    assert not old.parent.exists() and mine.exists() and recent.exists()
