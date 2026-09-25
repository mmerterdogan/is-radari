"""Rule-based matcher: education is never a hard filter, jobs are categorised instead.
Run: python -m pytest tests -q"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from radar import match  # noqa: E402
from radar.models import Job  # noqa: E402


def J(title="Mechanical Engineer", desc="", location="İstanbul, Türkiye", company="ACME", **extra):
    return Job(source="linkedin", native_id="1", title=title, company=company, location=location, url="https://x",
               description=desc, extra=extra)


FEA_BODY = " Responsibilities: FEA with ANSYS, SolidWorks design, static and modal analysis, prototype testing."


# ---------------------------------------------------------------- education (the user's examples)
@pytest.mark.parametrize("text, level", [
    ("Bachelor's degree in Mechanical Engineering.", "lisans"),
    ("Bachelor's or Master's degree in Mechanical Engineering.", "lisans_veya_yl"),
    ("BSc/MSc in Mechanical Engineering or related field.", "lisans_veya_yl"),
    ("Master's degree required in Mechanical Engineering.", "yl_zorunlu"),
    ("Bachelor's degree in Mechanical Engineering; a Master's degree is a plus.", "yl_tercih"),
    ("Üniversitelerin Makine Mühendisliği bölümlerinden lisans veya yüksek lisans mezunu.", "lisans_veya_yl"),
    ("Üniversitelerin Makine Mühendisliği bölümünden mezun, yüksek lisans tercih sebebidir.", "yl_tercih"),
    ("Makine Mühendisliği bölümlerinden lisans mezunu.", "lisans"),
    ("Yüksek lisans öğrencisi olmak, makine mühendisliği.", "yl_ogrencisi"),
    ("PhD in Mechanical Engineering required.", "doktora_zorunlu"),
    ("Great team, flexible hours.", "belirtilmemis"),
])
def test_education_levels(text, level):
    assert match.parse_education(J(desc=text))["level"] == level


def test_ms_office_is_not_a_masters_degree():
    assert match.parse_education(J(desc="Bachelor's degree in Mechanical Engineering. Good MS Office skills."))["level"] == "lisans"


def test_master_data_is_not_a_masters_degree():
    assert match.parse_education(J(desc="Maintain master data in SAP. Engineering degree."))["level"] == "lisans"


def test_bachelor_job_is_not_hidden_for_msc_student():
    j = match.analyze(J("Design Engineer", "Bachelor's degree in Mechanical Engineering. 0-2 years of experience." + FEA_BODY))
    assert j.category in ("dogrudan", "uygun")
    assert "Lisans mezunu kabul ediliyor" in j.category_reasons


def test_master_required_is_flagged_not_dropped():
    j = match.analyze(J("Simulation Engineer", "Master's degree required in Mechanical Engineering." + FEA_BODY))
    assert j.education["level"] == "yl_zorunlu" and j.category == "stretch"


def test_unrelated_master_field_lowers_fit():
    j = match.analyze(J("Research Engineer", "Master's degree in Chemistry required. Experience with polymer synthesis and materials."))
    assert j.education["field"] == "ilgisiz" and j.category == "dusuk"


def test_field_mechanical_or_related():
    assert match.parse_education(J(desc="Bachelor's in Mechanical or Electrical Engineering"))["field"] == "makine"
    assert match.parse_education(J(desc="Bachelor's degree in Mechatronics or a related engineering discipline"))["field"] == "ilgili"


# ---------------------------------------------------------------- experience
@pytest.mark.parametrize("title, text, fit", [
    ("Design Engineer", "0-2 years of experience in mechanical design.", "iyi"),
    ("Tasarım Mühendisi", "Yeni mezun veya deneyimsiz adaylar başvurabilir.", "iyi"),
    ("Junior Mechanical Engineer", "", "iyi"),
    ("Graduate Engineer - Mechanical", "", "iyi"),
    ("Design Engineer", "1-3 yıl deneyimli, SolidWorks.", "yakin"),
    ("Design Engineer", "Minimum 3 years of experience in product design.", "zor"),
    ("Design Engineer", "5+ years of relevant experience.", "uzak"),
    ("Senior Stress Engineer", "", "uzak"),
    ("Kıdemli Tasarım Mühendisi", "", "uzak"),
    ("Design Engineer", "Our company has over 50 years of history in the industry.", "belirtilmemis"),
])
def test_experience_fit(title, text, fit):
    assert match.parse_experience(J(title, text))["fit"] == fit


@pytest.mark.parametrize("title, fit", [
    ("Manufacturing Programs Leader - Hybrid", "uzak"), ("Experienced Mechanical Engineer", "zor"),
    ("Newly graduated Mechanical Engineers", "iyi"), ("Mechanical Engineering Graduate Programme", "iyi"),
])
def test_title_seniority_words(title, fit):
    assert match.parse_experience(J(title, ""))["fit"] == fit


def test_graduate_word_in_body_is_not_entry_level():
    e = match.parse_experience(J("Design Engineer", "You graduated from a mechanical engineering department."))
    assert e["fit"] == "belirtilmemis"


def test_language_requirement_in_title():
    j = match.analyze(J("Product Design Engineer – fluent German (m/f/d)", "Bachelor's degree in Mechanical Engineering." + FEA_BODY))
    assert j.category == "dusuk" and "Almanca" in j.gaps


def test_research_outside_mechanics_is_dropped():
    assert not match.is_relevant(J("Researcher in extractions of plant polysaccharides", "Food chemistry, polysaccharides, thermal treatment of plant materials."))
    assert match.is_relevant(J("PhD position in fatigue of additively manufactured metals", "Finite element modelling of fatigue."))


def test_technician_and_sales_are_capped():
    t = match.analyze(J("Mekanik Teknikeri", "Teknik resim, üretim süreçleri, yeni mezun."))
    s = match.analyze(J("Sales Engineer (3D Printing Solution)", "Sell additive manufacturing systems. Bachelor's in engineering."))
    assert t.category == "dusuk" and t.role_label == "Teknisyen"
    assert s.category != "dogrudan" and s.role_label == "Teknik satış"


def test_generic_mechanical_title_with_strong_overlap_is_direct():
    j = match.analyze(J("Mechanical Engineer (m/f/d)", "Junior level. Bachelor's or Master's in Mechanical Engineering. SolidWorks, modal analysis, technical drawings, CAD."))
    assert j.category == "dogrudan"


def test_linkedin_mid_senior_label_is_not_treated_as_senior():
    e = match.parse_experience(J("Mechanical Engineer", "", **{"Seniority level": "Mid-Senior level"}))
    assert e["fit"] == "yakin"


def test_one_to_three_years_with_strong_overlap_is_stretch():
    j = match.analyze(J("FEA Engineer", "1-3 years of experience. Bachelor's degree in Mechanical Engineering." + FEA_BODY))
    assert j.category == "stretch"


def test_senior_roles_are_low_not_hidden():
    j = match.analyze(J("Senior FEA Engineer", "Bachelor's in Mechanical Engineering. 8+ years of experience." + FEA_BODY))
    assert j.category == "dusuk"
    assert match.is_relevant(J("Senior FEA Engineer", FEA_BODY))


def test_internship_is_tagged():
    j = match.analyze(J("Mechanical Design Intern", "Students in mechanical engineering." + FEA_BODY))
    assert j.is_internship and j.category in ("dogrudan", "uygun")


# ---------------------------------------------------------------- role coverage (user's list)
ROLES = ["Mechanical Design Engineer", "Design Engineer", "CAE Engineer", "Simulation Engineer", "FEA Engineer",
         "Structural Analysis Engineer", "Stress Engineer", "R&D Engineer", "Research & Development Engineer",
         "Product Development Engineer", "Product Design Engineer", "Manufacturing Engineer", "Production Engineer",
         "Process Engineer", "Additive Manufacturing Engineer", "Mechanical Analysis Engineer", "Test Engineer",
         "Validation Engineer", "Durability Engineer", "Automotive Engineer", "Vehicle Engineer", "Component Engineer",
         "Mechanical Systems Engineer", "CAD Engineer", "Engineering Specialist", "Junior Engineer", "Graduate Engineer",
         "Entry-Level Engineer", "Makine Mühendisi", "Ar-Ge Mühendisi", "Üretim Mühendisi", "Analiz Mühendisi"]


@pytest.mark.parametrize("title", ROLES)
def test_all_target_roles_are_recognised_and_relevant(title):
    j = J(title, "Mechanical engineering background." + FEA_BODY)
    assert match.primary_family(match.role_families(j)) != "diger"
    assert match.is_relevant(j)


@pytest.mark.parametrize("title, desc", [
    ("Sermaye Yönetimi Uzman Yardımcısı", "Bankacılık, finans"),
    ("Model", "Fashion shoot"),
    ("Sales Representative", "B2B sales"),
    ("Software Developer", "React, Node.js"),
    ("Remote Engineering Expert", "Turing is hiring experts for AI training, $50/hr"),
    ("PhD Position: Cellular Oncology", "Cancer markers and cell biology"),
])
def test_irrelevant_jobs_are_dropped(title, desc):
    assert not match.is_relevant(J(title, desc))


def test_other_discipline_kept_only_if_mechanical_accepted():
    assert not match.is_relevant(J("Electrical Design Engineer", "Bachelor's in Electrical Engineering, circuit design"))
    assert match.is_relevant(J("Electrical Design Engineer", "Bachelor's in Electrical or Mechanical Engineering"))


# ---------------------------------------------------------------- location / mode / language
@pytest.mark.parametrize("loc, mode, tier", [
    ("İstanbul, Türkiye", "ofiste", 1), ("Kağıthane", "belirtilmemis", 1), ("Gebze, Kocaeli, Türkiye", "ofiste", 2),
    ("Ankara, Türkiye", "ofiste", 2), ("Torbalı", "belirtilmemis", 2), ("Aydın", "ofiste", 3), ("Türkiye", "uzaktan", 3),
    ("Remote", "uzaktan", 4), ("EMEA", "uzaktan", 4), ("Berlin, Germany", "uzaktan", 5),
    ("Munich, Bavaria, Germany", "ofiste", 5),
])
def test_location_tiers(loc, mode, tier):
    assert match.location_tier(J(location=loc), mode) == tier


def test_empty_location_falls_back_to_search_location():
    assert match.location_tier(J(location="", query_location="Turkey"), "belirtilmemis") == 3
    assert match.location_tier(J(location="", query_location="Istanbul"), "belirtilmemis") == 1


def test_country_bound_remote_is_abroad():
    assert match.location_tier(J("Field Service Engineer - UK Remote", location="Remote"), "uzaktan") == 5


@pytest.mark.parametrize("title, company", [
    ("CAM Metot Mühendisi", "Coşkunöz Aerospace"), ("Ürün ve Metot Mühendisi", "Coşkunöz Aerospace"),
    ("CAM & CNC Tezgah Mühendislik Uzmanı", "TOFAŞ Türk Otomobil Fabrikası"),
    ("Yan Sanayi Yönetimi Mühendisi", "Mercedes-Benz Türk A.Ş."), ("Undergraduate Development Program", "Toyota Otomotiv Sanayi"),
    ("Kalibrasyon Mühendisi", "Türk Havacılık ve Uzay Sanayii"), ("Lider Test Mühendisi", "STM"),
])
def test_engineering_employers_generic_titles_are_kept(title, company):
    assert match.is_relevant(J(title, "", company=company))


def test_generic_title_without_text_is_pending_until_full_text():
    j = J("Proje Mühendisi", "", company="Bilinmeyen Ltd")
    assert match.relevance(j, allow_pending=True) == (True, "pending")
    assert not match.is_relevant(j)
    j.description = "Makine Mühendisliği bölümü mezunu, AutoCAD bilen, proje takibi yapacak mühendis. " * 3
    assert match.is_relevant(j)


def test_pending_without_text_kept_only_for_engineering_families():
    assert match.keep_without_text(J("Production Engineer", ""))
    assert not match.keep_without_text(J("QA Engineer", ""))
    assert not match.keep_without_text(J("Sales Engineer", ""))


def test_title_language_when_text_is_short():
    j = match.analyze(J("CPI-26-485. Habilitando simulaciones de máquinas para la industria", "", location="Valencia, Spain"))
    assert j.category == "dusuk" and "İspanyolca" in j.gaps
    assert match.ad_language(J("Design Engineer for the automotive industry", "")) == "unknown"


def test_nearby_ads_get_full_text_first():
    ist = J("Makine Mühendisi", "", location="İstanbul, Türkiye")
    abroad = J("Makine Mühendisi", "", location="Munich, Germany")
    assert match.quick_rank(ist) > match.quick_rank(abroad)


def test_research_needs_strong_mechanical_signal():
    assert not match.is_relevant(J("Research Grant - project Polina", "Materials for energy; manufacturing of electrodes; thermal behaviour of cells."))
    assert not match.is_relevant(J("Research Engineer in Analytical Chemistry and Metabolomics", "Chemistry lab"))


def test_support_roles_are_capped():
    j = match.analyze(J("Product Support Specialist (3D Printing)", "Help customers with 3D printers. SolidWorks, CAD, additive manufacturing."))
    assert j.category != "dogrudan" and j.role_label == "Teknik destek / servis"


def test_title_only_jobs_are_marked():
    j = match.analyze(J("Makine Mühendisi", ""))
    assert any("sadece başlığa göre" in r for r in j.category_reasons)


def test_location_does_not_change_category():
    body = "Bachelor's degree in Mechanical Engineering. 0-2 years." + FEA_BODY
    a = match.analyze(J("Design Engineer", body, location="İstanbul, Türkiye"))
    b = match.analyze(J("Design Engineer", body, location="Eindhoven, Netherlands"))
    assert a.category == b.category and a.loc_tier == 1 and b.loc_tier == 5


@pytest.mark.parametrize("text, mode", [
    ("This is a hybrid role, 3 days in office.", "hibrit"),
    ("Fully remote position.", "uzaktan"),
    ("On-site in our Gebze plant.", "ofiste"),
    ("Remote sensing data analysis on site", "ofiste"),
    ("Nothing about it.", "belirtilmemis"),
])
def test_work_mode(text, mode):
    assert match.parse_work_mode(J(desc=text)) == mode


def test_german_ad_is_low_with_language_gap():
    de = ("Wir suchen einen Konstrukteur für unsere Entwicklung. Sie haben ein abgeschlossenes Studium im Maschinenbau "
          "und Erfahrung mit SolidWorks und FEM. Wir bieten Ihnen eine spannende Aufgabe mit der Möglichkeit zur "
          "Weiterentwicklung bei einer der führenden Firmen und die Arbeit in einem jungen Team von der Region.")
    j = match.analyze(J("Konstrukteur Maschinenbau (m/w/d)", de, location="Stuttgart, Deutschland"))
    assert j.category == "dusuk" and "Almanca" in j.gaps


# ---------------------------------------------------------------- card fields
def test_card_fields_are_filled():
    j = match.analyze(J("Mechanical Design Engineer", "Hybrid. Bachelor's degree in Mechanical Engineering. 0-2 years. "
                        "SolidWorks, ANSYS, CATIA, GD&T, automotive supplier." , location="Bursa, Türkiye"))
    assert j.work_mode == "hibrit" and j.loc_label == "Sanayi şehri"
    assert {"label": "CATIA", "have": False} in j.requirements
    assert "SolidWorks" in j.matches and "CATIA" in j.gaps
    assert "Otomotiv" in j.sectors and j.category_reasons
    assert j.category == "dogrudan"
