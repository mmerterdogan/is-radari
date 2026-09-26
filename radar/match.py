"""Rule-based profile matching - works without any API.

Answers: "with a BSc in Mechanical Engineering, an ongoing MSc, and these skills and projects,
can the candidate realistically apply to this job?" Education is never a hard filter: jobs are
sorted into four categories instead of being thrown away.

    dogrudan  Doğrudan uygun        clear overlap with the profile
    uygun     Uygun                 reasonable application, some gaps
    stretch   Potansiyel / Stretch  some requirements above the profile, still worth a look
    dusuk     Düşük uygunluk        clear mismatch on a core requirement

Location never changes the category; it is extracted for display, filtering and sorting.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .models import Job, _norm

CATEGORY_LABEL = {"dogrudan": "Doğrudan uygun", "uygun": "Uygun", "stretch": "Potansiyel / Stretch",
                  "belirsiz": "Değerlendirilemedi", "dusuk": "Düşük uygunluk"}
CATEGORY_ORDER = {"dogrudan": 0, "uygun": 1, "stretch": 2, "belirsiz": 3, "dusuk": 4}


def _lite(s: str) -> str:
    """Lower-case, Turkish letters folded, digits and + - ' kept (for year / degree patterns)."""
    s = (s or "").replace("İ", "i").replace("I", "i").lower().replace("̇", "")
    s = s.replace("’", "'").replace("–", "-").replace("—", "-")
    s = s.translate(str.maketrans("çğıöşüâîûéèêàáíóúñäß", "cgiosuaiueeeaaiounas"))
    return re.sub(r"\s+", " ", s)


def _any(rx: str, text: str) -> bool:
    return re.search(rx, text) is not None


# ============================================================================ profile
CORE_SKILLS = {"solidworks", "ansys", "fea", "statik", "modal", "topoloji", "cad", "eklemeli", "dfm", "teknik_resim"}

# key -> (label, regex on _lite text)
SKILLS: dict[str, tuple[str, str]] = {
    # ---- typically in the profile
    "solidworks": ("SolidWorks", r"solid ?works"),
    "ansys": ("ANSYS", r"\bansys\b"),
    "fea": ("FEA/FEM", r"\bfea\b|\bfem\b|finite[- ]element|sonlu eleman|elementos finitos|elements finis|finite-elemente|fe-(berechnung|simulation|analyse)"),
    "statik": ("Statik/yapısal analiz", r"static (structural|analysis|analyses)|statik analiz|structural (analysis|analyses|calculation|simulation)|yapisal analiz|mukavemet (analiz|hesap)|strength (analysis|calculation)|stress analysis"),
    "modal": ("Modal/titreşim analizi", r"\bmodal (analysis|analiz)|vibration|titresim|natural frequenc|dogal frekans"),
    "topoloji": ("Topoloji optimizasyonu", r"topolog\w* optimi|topology optimi|optistruct|tosca"),
    "cad": ("CAD / 3D modelleme", r"\bcad\b|3d model|3b model|kati model|3d design|3d tasarim"),
    "teknik_resim": ("Teknik resim", r"technical drawing|teknik resim|engineering drawing|2d drawing|drafting|imalat resmi|production drawing"),
    "tolerans": ("Tolerans / GD&T", r"gd ?& ?t|\bgdt\b|toleranc|tolerans|dimensioning|olculendirme"),
    "autocad": ("AutoCAD", r"autocad"),
    "fusion": ("Fusion 360", r"fusion ?360"),
    "nx": ("Siemens NX", r"siemens nx|\bnx\b|unigraphics"),
    "matlab": ("MATLAB/Simulink", r"matlab|simulink"),
    "excel": ("Excel / Office", r"\bexcel\b|ms office|microsoft office|office (programlari|uygulamalari)"),
    "eklemeli": ("Eklemeli imalat / 3D baskı", r"additive manufactur|eklemeli imalat|3d print|3b baski|\bfdm\b|\bslm\b|\blpbf\b|powder bed|rapid prototyp|hizli prototip"),
    "dfm": ("DFM", r"\bdfm\b|\bdfma\b|design for (manufactur|assembly)|uretilebilirlik|imal edilebilir"),
    "rca": ("Kök neden analizi", r"root cause|kok neden|\brca\b|\b8d\b"),
    "cnc": ("Talaşlı imalat / CNC", r"\bcnc\b|machining|talasli|\btorna|\bfreze|milling|turning"),
    "uretim": ("Üretim süreçleri", r"manufacturing process|production process|uretim (surec|yontem|teknik)|imalat (yontem|surec)|manufacturing method"),
    "prototip": ("Prototip ve test", r"prototyp|prototip"),
    "ingilizce": ("İngilizce", r"\benglish\b|ingilizce"),
    # ---- usually not in the profile (shown as "profilinde görünmüyor")
    "catia": ("CATIA", r"\bcatia\b"),
    "creo": ("Creo / Pro-E", r"\bcreo\b|pro ?/? ?engineer"),
    "inventor": ("Inventor", r"\binventor\b"),
    "abaqus": ("Abaqus", r"abaqus"),
    "nastran": ("Nastran/Patran", r"nastran|patran|femap"),
    "hypermesh": ("HyperMesh/HyperWorks", r"hypermesh|hyperworks"),
    "lsdyna": ("LS-DYNA / crash", r"ls ?-? ?dyna|radioss|pam ?-?crash"),
    "cfd": ("CFD", r"\bcfd\b|\bfluent\b|star ?-?ccm|openfoam|computational fluid"),
    "python": ("Python", r"\bpython\b"),
    "cpp": ("C/C++", r"c\+\+|\bc programming"),
    "plc": ("PLC / otomasyon", r"\bplc\b|siemens s7|tia portal"),
    "plm": ("PLM/PDM (Teamcenter, Windchill)", r"\bplm\b|teamcenter|windchill|enovia|\bpdm\b"),
    "sap": ("SAP / ERP", r"\bsap\b|\berp\b"),
    "fmea": ("FMEA", r"\bfmea\b|dfmea|pfmea"),
    "apqp": ("APQP/PPAP", r"apqp|ppap"),
    "sixsigma": ("Six Sigma", r"six sigma|6 sigma|green belt|black belt"),
    "lean": ("Yalın üretim / Kaizen", r"\blean (manufactur|production)|yalin uretim|kaizen|\b5s\b"),
    "hidrolik": ("Hidrolik / Pnömatik", r"hydraulic|pneumatic|hidrolik|pnomatik"),
    "kaynak": ("Kaynak teknolojisi", r"welding|kaynak (teknolojisi|yontemleri|muhendis|bilgisi)|kaynakli imalat"),
    "sac": ("Sac metal", r"sheet metal|sac metal|sac sekillendirme"),
    "enjeksiyon": ("Plastik enjeksiyon / kalıp", r"injection mold|plastik enjeksiyon|enjeksiyon kalip|mold design|kalip tasarim"),
}

LANG_REQ = {
    "almanca": ("Almanca", r"deutschkenntnisse|fliessend(e)? deutsch|sehr gute deutsch|german (c1|b2|fluent|native)|fluent (in )?german|business fluent german|german language (skills|proficiency)|almanca (bilen|bilgisi)|verhandlungssicher"),
    "fransizca": ("Fransızca", r"french (c1|b2|fluent|native)|fluent (in )?french|francais courant|fransizca (bilen|bilgisi)"),
}
PROFILE_LANGS = {"tr", "en"}


@dataclass
class Profile:
    skills: set[str] = field(default_factory=lambda: {
        "solidworks", "ansys", "fea", "statik", "modal", "topoloji", "cad", "teknik_resim", "tolerans", "autocad",
        "fusion", "nx", "matlab", "excel", "eklemeli", "dfm", "rca", "cnc", "uretim", "prototip", "ingilizce"})
    languages: set[str] = field(default_factory=lambda: set(PROFILE_LANGS))

    @classmethod
    def from_config(cls, cfg: dict | None) -> "Profile":
        p = cls()
        if cfg and cfg.get("skills"):
            p.skills = {s for s in cfg["skills"] if s in SKILLS}
        if cfg and cfg.get("languages"):
            p.languages = set(cfg["languages"])
        return p


# ============================================================================ role families
# (key, label, weight, regex on _norm(title))
FAMILIES = [
    ("cae", "CAE / Analiz", 30, r"\bfea\b|\bfem\b|finite element|sonlu eleman|\bcae\b|simulat|simulasyon|structural (analysis|analyst|engineer|integrity|design)|yapisal|\bstress\b|mukavemet|analysis engineer|analiz muhendis|calcul|berechnung|berakning|durability|dayanim|fatigue|yorulma|crash|\bnvh\b|mechanical analysis|computational|numerical|\bstructures?\b"),
    ("eklemeli", "Eklemeli imalat", 30, r"additive|eklemeli|3d print|3b baski|\blpbf\b|\bslm\b|\bam (engineer|specialist|process)"),
    ("tasarim", "Tasarım", 28, r"design|tasarim|\bcad\b|konstrukt|conception|disenador|diseno|progettist|ontwerp|drafting|teknik ressam"),
    ("arge", "Ar-Ge", 26, r"\br d\b|\bar ge\b|\barge\b|research|arastirma|forschung|recherche|investigac|ricerca|\binnovation"),
    ("urun", "Ürün geliştirme", 26, r"product (development|engineer|design)|urun gelistirme|urun muhendis|new product|\bnpi\b|development engineer|gelistirme muhendis|produktentwickl|entwicklung|urun ve metot|metot muhendis|method engineer"),
    ("doktora", "Doktora / araştırma", 24, r"\bphd\b|doctoral|doktora|predoc|doktorand|research assistant|arastirma gorevlisi|bursiyer|scholarship|doctorat|dottorato|promotionsstelle|masterarbeit|master thesis|tez ogrencisi"),
    ("test", "Test / doğrulama", 22, r"\btest\b|testing|validation|dogrulama|verification|homolog|versuch|essais"),
    ("otomotiv", "Otomotiv / araç", 22, r"automotive|otomotiv|vehicle|\barac\b|chassis|\bsasi\b|powertrain|body in white|\bbiw\b|drivetrain|fahrzeug|automobile"),
    ("sistem", "Mekanik sistem / bileşen", 20, r"mechanical systems?|systems engineer|sistem muhendis|component|bilesen|komponent|mechanism|mekanizma"),
    ("uretim", "Üretim / proses", 20, r"manufactur|production|uretim|imalat|process engineer|proses|machining|tooling|kalip|fabrication|assembly|montaj|industrializ|fertigung|produktion|fabricat|operations engineer|planlama muhendis|endustri muhendis|industrial engineer|\bcam\b|\bcnc\b|tezgah|metot|kalibrasyon|calibration|metrolog|yan sanayi|tedarikci|supplier"),
    ("makine", "Makine mühendisliği", 20, r"mechanical|makine|makina|mecanique|mecanico|meccanic|maschinenbau|mechanik|werktuigbouw|mekanik"),
    ("proje", "Proje / uygulama", 14, r"project engineer|proje muhendis|application|uygulama muhendis|field engineer|saha muhendis|commissioning|devreye alma|installation|montaj sefi"),
    ("kalite", "Kalite", 12, r"quality|kalite|qualitat|supplier"),
    ("genel", "Genel mühendislik", 12, r"engineer|muhendis|ingenieur|ingeniero|ingegnere|ingenjor|engineering specialist|graduate|trainee|junior|working student|werkstudent|intern\b|internship|stajyer|\bstaj\b|praktikant|praktikum"),
    ("destek", "Teknik destek / servis", 12, r"technical support|product support|customer support|support (engineer|specialist)|field service|service engineer|servis muhendis|teknik destek|destek muhendis"),
    ("bakim", "Bakım / tesis", 10, r"maintenance|\bbakim|facility|tesis|reliability|instandhaltung"),
    ("teknisyen", "Teknisyen", 6, r"technician|tekniker|teknisyen|techniker"),
    ("satis", "Teknik satış", 5, r"sales|satis|business development|key account"),
]
FAMILY_WEIGHT = {k: w for k, _, w, _ in FAMILIES}
FAMILY_LABEL = {k: lbl for k, lbl, _, _ in FAMILIES}
FAMILY_LABEL["diger"] = "Diğer"

# Titles that are simply not engineering jobs for this profile
EXCLUDE_TITLE = (r"\bbank|banka|\bfinans|finance|accountant|accounting|muhasebe|auditor|denetci|marketing|pazarlama|"
                 r"\bhr\b|human resources|insan kaynak|recruit|talent acquisition|nurse|hemsire|\bdoktor\b|physician|pharmac|eczaci|"
                 r"biolog|oncolog|clinical|\bmodel\b|fashion|\bmoda\b|driver|sofor|cashier|kasiyer|waiter|garson|\bcook\b|asci|"
                 r"teacher|ogretmen|lawyer|avukat|\blegal\b|translator|tercuman|customer service|musteri hizmet|call center|"
                 r"cagri merkezi|\bturing\b|annotat|ai trainer|freelance expert|\bchef\b|receptionist|resepsiyon|security guard|guvenlik gorevlisi|"
                 r"sales (manager|representative|executive|specialist|associate)|satis (temsilci|uzmani|muduru|danisman)|store|magaza")
# Other engineering disciplines: kept only if the ad accepts mechanical engineers
OTHER_DISCIPLINE = (r"electrical|elektrik|electronic|elektronik|embedded|gomulu|antenna|\banten|\brf\b|civil|insaat|construction|"
                    r"hardware|donanim|test automation|software test|\bsdet\b|presales|pre sales|"
                    r"santiye|site engineer|chemical engineer|kimya|software|yazilim|developer|frontend|backend|full stack|devops|"
                    r"data (scientist|engineer|analyst)|machine learning|\bai\b|\bml\b|network|cyber|firmware|power electronics|"
                    r"environmental|cevre|\bfood|\bgida|textile|tekstil|mining|maden|geolog|petroleum|architect|mimar|interior|harita|survey|"
                    r"chemistry|chemist\b|biochem|biotech|pharma|python|visuali[sz]|cloud|algoritma|algorithm|signal processing|"
                    r"sinyal isleme|image processing|goruntu isleme|\bfpga\b|siber|orbit|yorunge")
MECH_TITLE = r"mechanical|makine|makina|mekanik|mechanik|maschinenbau|mecanique|\bfea\b|simulat|structural|additive|eklemeli|mechatron|mekatronik"

# Research / PhD / generic titles must show a mechanical-engineering domain somewhere in the ad
DOMAIN = (r"mechanic|makine|makina|mekanik|structural|yapisal|solid mechanic|material|malzeme|manufactur|imalat|uretim|"
          r"additive|eklemeli|3d print|\bfea\b|finite element|sonlu eleman|simulat|composite|kompozit|aerospace|havacilik|"
          r"automotive|otomotiv|robot|mechatron|mekatronik|\bcad\b|fatigue|fracture|vibration|thermal|termal|machine design|"
          r"tribolog|welding|metal|polymer|design engineer|tasarim muhendis|product development|urun gelistirme|machining|"
          r"maschinenbau|konstruktion|fertigung|werkstoff|genie mecanique|mecanica|meccanica|engineering design|biomechanic|"
          r"turbine|engine|motor|gearbox|redukt|hydraulic|pneumatic|hidrolik")


# Clearly mechanical terms: research / PhD / generic titles need the title or >= 2 of these in the text
MECH_STRONG = [r"mechanic|makine|makina|mekanik|maschinenbau|mecanique|mecanica|meccanica",
               r"structural|yapisal|solid mechanic|strength of material|mukavemet",
               r"manufactur|imalat|fertigung|machining|talasli",
               r"additive|eklemeli|3d print",
               r"\bfea\b|\bfem\b|finite element|sonlu eleman|\bcae\b",
               r"composite|kompozit|fatigue|yorulma|fracture|kirilma|tribolog",
               r"aerospace|havacilik|automotive|otomotiv|vehicle",
               r"robot|mechatron|mekatronik",
               r"\bcad\b|solidworks|catia|\bcreo\b|siemens nx|machine design|makine tasarim|konstruktion",
               r"vibration|titresim|dynamics|heat transfer|isi transferi|thermodynamic|turbine|turbin|engine|gearbox|redukt"]


DOMAIN_TITLE_EXTRA = r"\bcam\b|\bcnc\b|metot|kalibrasyon|calibration|metrolog|homolog|tezgah|yan sanayi|tedarikci|otomobil|automobile"
# Engineering-heavy employers: the company name alone is a domain signal for generic titles
COMPANY_DOMAIN = (r"aerospace|havacilik|aviation|otomotiv|automotive|otomobil|makina|makine|machinery|savunma|defen[cs]e|"
                  r"tofas|ford otosan|mercedes|toyota|renault|hyundai|honda|bosch|otokar|bmc|karsan|temsa|isuzu|arcelik|beko|vestel|"
                  r"tusas|turk havacilik|tei\b|roketsan|aselsan|stm\b|fnss|mkek|baykar|asfat|havelsan|pratt|coskunoz|kale (pratt|kalip|oto|aero)|siemens|"
                  r"schindler|otis|airbus|safran|rolls royce|continental|\bzf\b|valeo|avl|eaton|atlas copco|sandvik")


def _mech_domain(job: Job, strict: bool = False) -> bool:
    """Is there a mechanical-engineering signal? strict=True (research/PhD) needs 3 body signals instead of 2."""
    head = _norm(job.title)
    if _any(DOMAIN, head) or _any(DOMAIN_TITLE_EXTRA, head):
        return True
    if not strict and _any(COMPANY_DOMAIN, _norm(job.company)):
        return True
    body = _norm(job.description[:5000])
    return sum(1 for rx in MECH_STRONG if _any(rx, body)) >= (3 if strict else 2)


def role_families(job: Job) -> list[str]:
    t = _norm(job.title)
    fams = [k for k, _, _, rx in FAMILIES if _any(rx, t)]
    return fams or ["diger"]


def primary_family(fams: list[str]) -> str:
    return max(fams, key=lambda f: FAMILY_WEIGHT.get(f, 0))


# ============================================================================ experience
YEARS = r"(?:years?|yrs?|yil|sene|jahre?n?|ans?\b|anos|anni|jaar)"
EXP_WORD = r"(?:experience|deneyim|tecrube|professional|industry|industrial|relevant|work|working|erfahrung|experiencia|esperienza|ervaring|in (?:a|the) (?:similar|related)|in (?:mechanical|design|fea|simulation))"

SENIOR_TITLE = (r"\bsenior\b|\bsr\b|kidemli|\blead\b|principal|\bstaff (engineer|mechanical)|head of|\bmanager\b|\bmudur|\bsef\b|"
                r"team lead|takim lideri|\bleader\b|\blider\b|supervisor|superintendent|director|direktor|\bchief\b|"
                r"\bexpert\b|experte|leiter|responsable|responsabile|jefe|capo")
ENTRY_TITLE_EXTRA = r"\bgraduates?\b(?! degree)"   # bare "Graduate" only counts in the title
ENTRY = (r"new grad|newly graduated|recent(ly)? grad|fresh grad|graduate (engineer|program|programme|trainee|scheme|position)|"
         r"entry[- ]level|\bjunior\b|\bjr\b|"
         r"trainee|yeni mezun|deneyimsiz|tecrubesiz|deneyim (sarti )?(aranmamaktadir|aranmaz|gerekmemektedir|sart degil)|"
         r"genc muhendis|management trainee|\bmt program|berufseinsteiger|absolvent|einsteiger|debutant|jeune diplome|"
         r"recien titulado|neolaureat|early career|0 ?- ?[12] (years?|yil)|no prior experience|no experience (is )?required|"
         r"without (prior )?experience|erste (berufs)?erfahrung|premiere experience|recently graduated")
# Body phrases that point to an experienced hire when no year count is given
MID_TEXT = r"significant experience|extensive experience|substantial experience|solid years of experience|proven track record"
INTERN = (r"\bintern\b|internship|stajyer|\bstaj\b|praktikum|praktikant|\bstage\b|stagiaire|becario|tirocin|"
          r"working student|werkstudent|student assistant|ogrenci (asistan|calisan)|part[- ]time student|master thesis|masterarbeit|tez ogrencisi")
MID_TITLE = r"deneyimli|experienced|experimente|\bmid\b|intermediate|erfahren"


def _year_mentions(text: str) -> list[tuple[int, int | None]]:
    """(min, max) year requirements found near experience words."""
    found = []
    pats = [
        rf"(?P<a>\d{{1,2}})\s*(?:-|to|ile|~|/)\s*(?P<b>\d{{1,2}})\s*\+?\s*{YEARS}",
        rf"(?P<a>\d{{1,2}})\s*\+\s*{YEARS}",
        rf"(?:at least|minimum|min\.?|en az|asgari|mindestens|au moins|al menos|almeno|minimaal)\s*(?P<a>\d{{1,2}})\s*\+?\s*{YEARS}",
        rf"(?P<a>\d{{1,2}})\s*{YEARS}\s*(?:ve uzeri|ve daha fazla|and above|or more|plus)",
        rf"(?P<a>\d{{1,2}})\s*{YEARS}\s*(?:of\s+)?(?:\w+\s+){{0,3}}?{EXP_WORD}",
    ]
    # Self-evident requirement phrasings: no experience word needed nearby
    explicit = [
        rf"(?P<a>\d{{1,2}})\s*\+?\s*{YEARS}\s*(?:minimum|min\b|en az)",                 # "1 an minimum", "2 yıl en az"
        rf"(?P<a>\d{{1,2}})\s*\+\s*{YEARS}\s+(?:of|in)\b",                              # "1+ years of customer service"
    ]
    for p in pats + explicit:
        for m in re.finditer(p, text):
            window = text[max(0, m.start() - 80): m.end() + 80]
            if p not in explicit and not re.search(EXP_WORD, window):
                continue
            a = int(m.group("a"))
            b = int(m.group("b")) if "b" in m.groupdict() and m.group("b") else None
            if a > 15 or (b is not None and (b > 20 or b < a)):
                continue
            found.append((a, b))
    return found


def parse_experience(job: Job) -> dict:
    title = _lite(job.title)
    text = _lite(f"{job.title}\n{job.description}")
    seniority = _norm(str(job.extra.get("Seniority level", "")))
    employment = _norm(str(job.extra.get("Employment type", "")))

    if _any(INTERN, title) or employment == "internship" or seniority == "internship":
        level = "staj"
    elif _any(SENIOR_TITLE, _norm(job.title)):
        level = "kidemli"
    elif _any(ENTRY, title) or _any(ENTRY_TITLE_EXTRA, title) or seniority == "entry level":
        level = "yeni_mezun"
    elif _any(MID_TITLE, _norm(job.title)):
        level = "orta"
    elif seniority == "associate":
        level = "associate"
    elif seniority in ("mid senior level",):
        level = "orta_kidemli"
    elif seniority in ("director", "executive"):
        level = "kidemli"
    elif _any(ENTRY, text):
        level = "yeni_mezun"
    elif _any(MID_TEXT, text):
        level = "orta"
    else:
        level = "belirtilmemis"

    years = _year_mentions(text)
    ymin = min((a for a, _ in years), default=None)
    ymax = None
    if years:
        ranges = [b for a, b in years if a == ymin and b is not None]
        ymax = max(ranges) if ranges else None

    if level == "kidemli":
        fit = "uzak"
    elif ymin is not None:
        fit = "iyi" if ymin == 0 else "yakin" if ymin <= 2 else "zor" if ymin <= 4 else "uzak"
    elif level in ("staj", "yeni_mezun"):
        fit = "iyi"
    elif level == "associate":
        fit = "yakin"
    elif level == "orta":
        fit = "zor"
    elif level == "orta_kidemli":
        fit = "yakin"   # LinkedIn labels many 2-3 year roles "Mid-Senior"; judge by the text instead
    else:
        fit = "belirtilmemis"

    if ymin is not None:
        label = f"{ymin}-{ymax} yıl" if ymax is not None and ymax > ymin else f"{ymin}+ yıl"
        if ymin == 0 and ymax is None:
            label = "Deneyimsiz olabilir"
    else:
        label = {"staj": "Staj / öğrenci", "yeni_mezun": "Yeni mezun / junior", "kidemli": "Kıdemli seviye",
                 "orta": "Deneyimli", "associate": "Başlangıç-orta (LinkedIn: Associate)",
                 "orta_kidemli": "Orta seviye (LinkedIn)"}.get(level, "Belirtilmemiş")
    return {"min": ymin, "max": ymax, "level": level, "label": label, "fit": fit}


# ============================================================================ education
BSC = (r"bachelor|\bb\.? ?sc\b|\bbs\b(?! office)|\bb\.s\.|\bb\.? ?eng\b|undergraduate|university degree|college degree|"
       r"degree in (mechanical|engineering)|engineering degree|\blisans (mezun|derece|diploma|ogrenim|egitim)|lisans ve|"
       r"universitelerin|fakultesi|fakultelerin|bolumlerinden|bolumu mezun|muhendisligi mezun|4 yillik|dort yillik|"
       r"\bon lisans|bachelier|\blicence\b|grado en|laurea triennale|hochschulstudium|studium der|abgeschlossenes studium|"
       r"degree qualified|degree level|degree,? hnd|\bhnd\b|a degree in|degree in (a |an )?(technical|relevant|related)|"
       r"bolumunden mezun|bolumlerinden mezun|fakultelerinden|graduates? of (relevant )?engineering|studium (im bereich|maschinenbau|der)|"
       r"ecole d'ingenieur|diplome d'ingenieur|ingenieursopleiding|\bhbo\b")
MASTER_NOISE = r"master (data|plan|schedule|file|record|production schedule|card)|scrum master|web ?master|mastercard|master of ceremonies|toolmaster|masterclass"
MSC = (r"master'?s|\bmaster (degree|of|in)|\bm\.? ?sc\b|\bms\b(?! office| word| excel| project| teams| dynamics| sql)|\bm\.s\.|"
       r"\bm\.? ?eng\b|graduate degree|yuksek lisans|diplom-ingenieur|dipl\.-ing|laurea magistrale|maitrise|\bmaster\b|"
       r"bac ?\+ ?5|masterdiploma")
PHD = r"\bphd\b|ph\.d|doctorate|doctoral degree|doktora (derece|mezun|diploma)|\bdoctorat|dottorato|promotion\b"
MSC_REQUIRED = (r"(master'?s?|\bmsc\b|m\.sc|yuksek lisans)[^.;\n]{0,70}(required|mandatory|\bmust\b|is a must|zorunlu|sarttir|gereklidir|"
                r"mezunu olmak|derecesine sahip)|(must|required to) (have|hold) a (master|msc)|requires? a (master|msc)|"
                r"master'?s degree (is )?required")
MSC_PREFERRED = (r"(master'?s?|\bmsc\b|m\.sc|yuksek lisans)[^.;\n]{0,70}(preferred|a plus|advantage|desirable|beneficial|nice to have|"
                 r"tercih sebebi|tercihen|tercih edilir|avantaj|arti)|(preferably|ideally) (with )?(a |an )?(master|msc)")
MSC_STUDENT = (r"yuksek lisans (ogrencisi|programina kayitli|egitimine devam)|lisansustu (ogrencisi|egitimine devam)|"
               r"(currently )?(enrolled|studying) in a master|master'?s student|msc student|studierende[rn]? (im )?master|"
               r"master thesis|masterarbeit|master'?s thesis|immatrikuliert")
BOTH = (r"(bachelor'?s?|\bb\.? ?sc\b|\bbs\b|\bb\.? ?eng\b|\blisans)[^.;\n]{0,30}(\bor\b|/|veya|ya da|and/or)[^.;\n]{0,20}"
        r"(master'?s?|\bm\.? ?sc\b|\bms\b|\bm\.? ?eng\b|yuksek lisans)|(master'?s?|\bm\.? ?sc\b)[^.;\n]{0,30}(\bor\b|/|veya)[^.;\n]{0,20}"
        r"(bachelor|\bb\.? ?sc\b|\blisans)")
PHD_REQUIRED = r"(phd|ph\.d|doctorate|doktora)[^.;\n]{0,60}(required|\bmust\b|zorunlu|mezunu)|(hold|have|completed|obtained) (a |an )?(phd|doctorate|doctoral degree)"
POSTDOC = r"postdoc|post-doc|post doc|postdoktor|postdoctoral|post-doctoral"

FIELD_MECH = r"mechanical|makine|makina|maschinenbau|mecanique|mecanica|meccanica|werktuigbouw|mechanik|mekanik"
FIELD_RELATED = (r"mechatron|mekatronik|manufactur|imalat|uretim|industrial|endustri|aerospace|aeronautic|havacilik|ucak|automotive|"
                 r"otomotiv|materials?|malzeme|metallurg|metalurji|physics engineering|engineering (degree|discipline|field|background)|"
                 r"degree in engineering|technical degree|muhendislik (bolum|fakulte|alan)|ilgili (muhendislik|bolum)|related (engineering|field|discipline|technical)|"
                 r"equivalent|similar field|stem|polymer|naval|gemi|energy|enerji|ingenieurwissenschaft|ingenieurstudium")
FIELD_OTHER = (r"electrical|elektrik|electronic|elektronik|computer|bilgisayar|software|yazilim|chemical|chemistry|kimya|civil|insaat|"
               r"biolog|medicine|economics|business|finance|mathematic|informatics|informatik|biomedical|environmental|textile|"
               r"food|mining|geolog|architecture|psycholog|physics")
LEVEL_LABEL = {"lisans": "Lisans", "lisans_veya_yl": "Lisans veya YL", "yl_tercih": "Lisans (YL tercih sebebi)",
               "yl_ogrencisi": "YL öğrencisi", "yl_zorunlu": "YL şartı", "doktora_zorunlu": "Doktora şartı",
               "belirtilmemis": "Belirtilmemiş"}
FIELD_LABEL = {"makine": "Makine Müh.", "ilgili": "İlgili müh. bölümleri", "ilgisiz": "Farklı bölüm", "belirtilmemis": ""}


DIRECT_FIELD = (r"(?:degree|bachelor'?s?|master'?s?|b\.? ?sc|m\.? ?sc|phd|diploma|studies|studium)\s+(?:degree\s+)?(?:in|of)\s+"
                r"([a-z &/,-]{3,70})")
TR_FIELD = r"([a-z ]{3,40}?)\s+(?:muhendisligi|mühendisliği|bolum)"


def _classify_field(s: str) -> str | None:
    if _any(FIELD_MECH, s):
        return "makine"
    if _any(FIELD_RELATED, s):
        return "ilgili"
    if _any(FIELD_OTHER, s):
        return "ilgisiz"
    return None


def _degree_field(text: str) -> str:
    # 1) the field named right after the degree ("degree in X", "X mühendisliği bölümü") decides first
    direct = [_classify_field(m.group(1)) for m in re.finditer(DIRECT_FIELD, text)]
    direct += [_classify_field(m.group(1)) for m in re.finditer(TR_FIELD, text) if "mezun" in text[m.end(): m.end() + 120]]
    direct = [d for d in direct if d]
    if direct:
        return "makine" if "makine" in direct else "ilgili" if "ilgili" in direct else "ilgisiz"
    # 2) otherwise look around any degree mention
    windows = []
    for m in re.finditer(rf"{BSC}|{MSC}|{PHD}|\bdegree\b|mezun|bolum|diploma|studium|studies in|diplome", text):
        windows.append(text[max(0, m.start() - 150): m.end() + 150])
    if not windows:
        return "belirtilmemis"
    joined = " ".join(windows)
    return _classify_field(joined) or "belirtilmemis"


def parse_education(job: Job, families: list[str] | None = None) -> dict:
    title = _norm(job.title)
    text = re.sub(MASTER_NOISE, " ", _lite(f"{job.title}\n{job.description}"))
    no_yl = text.replace("yuksek lisans", " ")
    has_bsc = _any(BSC, no_yl)
    has_msc = _any(MSC, text)
    phd_position = families is not None and "doktora" in families and _any(r"phd|doctoral|doktora|predoc|doktorand|doctorat|dottorato|promotion", title)

    if _any(POSTDOC, title) or _any(PHD_REQUIRED, text):
        level = "doktora_zorunlu"
    elif _any(MSC_STUDENT, text):
        level = "yl_ogrencisi"
    elif phd_position:
        level = "yl_zorunlu"
    elif _any(BOTH, text):
        level = "lisans_veya_yl"
    elif has_msc and _any(MSC_PREFERRED, text):
        level = "yl_tercih"
    elif has_msc and _any(MSC_REQUIRED, text):
        level = "yl_zorunlu"
    elif has_msc and has_bsc:
        level = "lisans_veya_yl"
    elif has_bsc:
        level = "lisans"
    elif has_msc:
        level = "yl_zorunlu"   # only a master's degree is mentioned as the requirement
    else:
        level = "belirtilmemis"

    fld = _degree_field(text) if level != "belirtilmemis" or _any(r"\bdegree\b|mezun|bolum", text) else "belirtilmemis"
    label = LEVEL_LABEL[level] + (f" · {FIELD_LABEL[fld]}" if FIELD_LABEL.get(fld) else "")
    return {"level": level, "field": fld, "label": label, "phd_position": phd_position}


# ============================================================================ work mode / location / language / sectors
REMOTE_NOISE = r"remote (sensing|monitoring|control|access|diagnos|operat|site)"


def parse_work_mode(job: Job) -> str:
    text = re.sub(REMOTE_NOISE, " ", _lite(f"{job.title} {job.location} {job.description[:4000]}"))
    remote = _any(r"\bremote\b|fully remote|uzaktan (calisma|calis)|home ?office|work from home|evden calis|telework|teletrabajo|telelavoro|100% remote|remote-first", text)
    hybrid = _any(r"hybrid|hibrit|hybride|ibrido|hibrido", text)
    onsite = _any(r"on[- ]?site|ofisten|ofiste|yerinde|is yerinde|office[- ]based|in the office|vor ort|presencial|in presenza|sur site", text)
    if hybrid:
        return "hibrit"
    if remote:
        return "uzaktan"
    if onsite:
        return "ofiste"
    return "belirtilmemis"


ISTANBUL = (r"istanbul|kagithane|umraniye|basaksehir|kadikoy|maslak|sariyer|besiktas|sisli|atasehir|kartal|pendik|tuzla|"
            r"esenyurt|beylikduzu|avcilar|bagcilar|bahcelievler|bakirkoy|beykoz|uskudar|maltepe|sancaktepe|sultanbeyli|cekmekoy|"
            r"arnavutkoy|silivri|catalca|buyukcekmece|zeytinburnu|gungoren|esenler|eyup|gaziosmanpasa|sultangazi|kucukcekmece|"
            r"beyoglu|halkali|ikitelli|hadimkoy|dudullu|levent|mecidiyekoy|kavacik|kozyatagi|atakoy|yenibosna|sefakoy")
INDUSTRIAL = (r"kocaeli|gebze|izmit|dilovasi|korfez|golcuk|kartepe|derince|cayirova|darica|bursa|nilufer|gemlik|inegol|orhangazi|"
              r"ankara|sincan|temelli|etimesgut|cankaya|yenimahalle|kahramankazan|akyurt|izmir|torbali|aliaga|kemalpasa|cigli|"
              r"bornova|menemen|sakarya|adapazari|eskisehir|konya|kayseri|manisa|tekirdag|corlu|cerkezkoy|duzce|bilecik|"
              r"gaziantep|adana|mersin|denizli|yalova|balikesir|kirklareli|luleburgaz|bolu|osmaniye|hatay|samsun|kutahya")
TURKEY = (r"turkey|turkiye|turkei|turquie|aydin|mugla|antalya|diyarbakir|erzurum|malatya|elazig|sivas|tokat|ordu|rize|"
          r"zonguldak|karabuk|kastamonu|kirikkale|nevsehir|nigde|usak|isparta|burdur|edirne|canakkale|amasya|corum|trabzon|"
          r"giresun|erzincan|van|batman|mardin|sanliurfa|kahramanmaras|karaman|aksaray|afyon|bartin|\bof\b")
LOC_LABEL = {1: "İstanbul", 2: "Sanayi şehri", 3: "Türkiye", 4: "Uzaktan", 5: "Yurt dışı"}


REMOTE_ANYWHERE = r"^$|remote|uzaktan|worldwide|anywhere|global|emea|europe|europa|avrupa|european union"


def location_tier(job: Job, work_mode: str) -> int:
    loc = _norm(job.location)
    if _any(ISTANBUL, loc):
        return 1
    if _any(INDUSTRIAL, loc):
        return 2
    if _any(TURKEY, loc):
        return 3
    if not loc:  # no location on the card: fall back to where we searched
        qloc = _norm(str(job.extra.get("query_location", "")))
        if _any(ISTANBUL, qloc):
            return 1
        if _any(TURKEY, qloc):
            return 3
    # remote only counts as "Uzaktan" when it is not tied to one foreign country ("UK Remote" stays abroad)
    if work_mode == "uzaktan" and _any(REMOTE_ANYWHERE, loc) and not _any(r"\buk\b|united kingdom|usa|united states|\bus\b", _norm(job.title)):
        return 4
    return 5


STOPWORDS = {
    "de": {"und", "der", "die", "das", "wir", "sie", "mit", "fur", "ihre", "bei", "ist", "eine", "von", "unsere", "sowie", "zur"},
    "fr": {"les", "des", "et", "pour", "vous", "une", "dans", "avec", "est", "nous", "sur", "votre", "sont"},
    "es": {"los", "las", "para", "con", "una", "por", "del", "nuestro", "somos", "tus", "experiencia"},
    "it": {"il", "della", "per", "con", "una", "sono", "nostro", "gli", "delle", "nella", "siamo"},
    "nl": {"het", "een", "van", "voor", "met", "wij", "zijn", "ons", "jouw", "bij", "je"},
    "sv": {"och", "att", "for", "med", "som", "vi", "ar", "har", "dig", "inom"},
    "tr": {"ve", "bir", "icin", "ile", "olarak", "veya", "olan", "olmak", "sahip", "bilgisi"},
    "en": {"the", "and", "for", "with", "you", "our", "are", "will", "your", "this"},
}
LANG_NAME = {"de": "Almanca", "fr": "Fransızca", "es": "İspanyolca", "it": "İtalyanca", "nl": "Felemenkçe", "sv": "İsveççe", "pt": "Portekizce"}


TITLE_FUNCTION_WORDS = {
    "es": {"de", "del", "la", "las", "los", "para", "y", "en", "el", "con"},
    "fr": {"de", "des", "du", "le", "la", "les", "et", "pour", "en", "au"},
    "it": {"di", "della", "del", "per", "e", "il", "la", "nel", "delle"},
    "pt": {"de", "da", "do", "das", "dos", "para", "e", "em"},
}


def ad_language(job: Job) -> str:
    words = _norm(f"{job.title} {job.description[:2500]}").split()
    if len(words) < 25:
        # too little text: judge the title alone (e.g. "Habilitando simulaciones de máquinas para ...")
        tw = _norm(job.title).split()
        if len(tw) >= 4:
            counts = {lang: sum(1 for w in tw if w in sw) for lang, sw in TITLE_FUNCTION_WORDS.items()}
            lang = max(counts, key=counts.get)
            if counts[lang] >= 2 and not ({"the", "and", "for", "of", "with"} & set(tw)):
                return lang
        return "unknown"
    counts = {lang: sum(1 for w in words if w in sw) for lang, sw in STOPWORDS.items()}
    lang = max(counts, key=counts.get)
    return lang if counts[lang] >= 6 else "unknown"


SECTORS = [
    ("Otomotiv", r"automotive|otomotiv|vehicle|\boem\b|tier 1|ford|tofas|toyota|renault|mercedes|bmw|volkswagen|hyundai|honda|bosch|continental|\bzf\b|valeo|\bavl\b|togg|otokar|karsan|temsa|\bbmc\b|isuzu|stellantis"),
    ("Havacılık", r"aerospace|aviation|havacilik|aircraft|\bucak|airbus|boeing|tusas|\btai\b|\btei\b|safran|rolls royce|turkish technic|pratt|space\b|uzay"),
    ("Savunma", r"defense|defence|savunma|aselsan|roketsan|havelsan|\bstm\b|fnss|mkek|baykar|asfat|military|askeri"),
    ("Üretim", r"manufactur|uretim|imalat|production|factory|fabrika"),
    ("Makine / ekipman", r"machinery|makina sanayi|makine sanayi|industrial equipment|machine builder|makine imalat|ekipman"),
    ("Robotik / otomasyon", r"robot|otomasyon|automation|mechatron|mekatronik"),
    ("Enerji", r"\benergy|enerji|\bwind\b|ruzgar|\bsolar\b|gunes enerji|turbine|turbin|power plant|santral|nuclear|nukleer|oil and gas|petrol"),
    ("Mühendislik hizmetleri", r"consult|danismanlik|engineering services|muhendislik hizmet|design office|tasarim ofisi"),
    ("Ar-Ge / akademi", r"research institute|arastirma enstitu|universit|fraunhofer|tubitak|max planck|\bcnrs\b|\btno\b|\bcea\b"),
    ("Eklemeli imalat", r"additive|3d print|eklemeli"),
    ("Beyaz eşya", r"white goods|beyaz esya|arcelik|\bbeko\b|vestel|\bbsh\b|home appliance"),
    ("Medikal", r"medical device|tibbi cihaz|medtech|stryker|medtronic|siemens healthineers"),
]


def sectors(job: Job) -> list[str]:
    text = _norm(f"{job.company} {job.title} {job.description[:2500]}")
    return [name for name, rx in SECTORS if _any(rx, text)][:3]


def extract_skills(job: Job) -> list[str]:
    text = _lite(f"{job.title}\n{job.description}")
    return [k for k, (_, rx) in SKILLS.items() if _any(rx, text)]


# ============================================================================ relevance gate
GIG = r"\bturing\b|crossing hurdles|ai training|ai trainer|data annotation|annotat|\$\d+ ?/ ?(hr|hour)|per hour|mercor|outlier ai"


WEAK_FAMILIES = ("doktora", "arge", "genel", "sistem", "test", "proje", "kalite", "bakim", "teknisyen", "satis", "destek", "uretim")
SHORT_TEXT = 200  # below this the full ad text has not been fetched yet


def relevance(job: Job, profile: Profile | None = None, allow_pending: bool = False) -> tuple[bool, str]:
    """(keep, reason). Drops only jobs that are clearly not for a mechanical engineer.

    allow_pending=True (before the full ad text is fetched): a generic title without a domain signal is
    kept for now instead of dropped, so the decision can be made on the full text.
    """
    profile = profile or Profile()
    title = _norm(job.title)
    if _any(GIG, _lite(f"{job.company} {job.title} {job.description[:1500]}")):
        return False, "Yapay zekâ eğitim / freelance platformu"
    if _any(EXCLUDE_TITLE, title) and not _any(MECH_TITLE, title):
        return False, "Mühendislik dışı pozisyon"
    if _any(OTHER_DISCIPLINE, title) and not _any(MECH_TITLE, title):
        # e.g. "Electrical Design Engineer": keep only if mechanical engineers are explicitly accepted
        if _degree_field(_lite(job.description)) == "makine":
            return True, ""
        return False, "Başka mühendislik disiplini (makine kabul edilmiyor)"
    fams = role_families(job)
    prim = primary_family(fams)
    research = "doktora" in fams or prim == "arge"
    accepts_me = _degree_field(_lite(job.description)) == "makine"   # "Makine Mühendisliği mezunu" etc.
    if (prim in WEAK_FAMILIES or research) and not accepts_me and not _mech_domain(job, strict=research):
        if allow_pending and len(job.description) < SHORT_TEXT:
            return True, "pending"
        return False, "Makine mühendisliği alanıyla bağlantı bulunamadı"
    if prim != "diger":
        return True, ""
    have = [s for s in extract_skills(job) if s in profile.skills and s != "ingilizce"]
    return (True, "") if len(have) >= 2 else (False, "Pozisyon alanı tanınmadı, profil becerisi geçmiyor")


def is_relevant(job: Job, profile: Profile | None = None) -> bool:
    return relevance(job, profile)[0]


# If a pending ad's full text could not be fetched, keep it only for clearly engineering families
PENDING_KEEP = ("uretim", "test", "sistem", "proje")


def keep_without_text(job: Job) -> bool:
    return primary_family(role_families(job)) in PENDING_KEEP


def quick_rank(job: Job) -> int:
    """Cheap title-based priority for deciding which ads get their full text fetched."""
    t = _norm(job.title)
    r = FAMILY_WEIGHT.get(primary_family(role_families(job)), 0)
    if _any(ENTRY, _lite(job.title)) or _any(INTERN, _lite(job.title)):
        r += 15
    if _any(SENIOR_TITLE, t):
        r -= 20
    # the user's location priority: read nearby ads in full first
    loc = _norm(job.location or str(job.extra.get("query_location", "")))
    r += 12 if _any(ISTANBUL, loc) else 8 if _any(INDUSTRIAL, loc) else 4 if _any(TURKEY, loc) else 0
    return r


# ============================================================================ analysis
def analyze(job: Job, profile: Profile | None = None) -> Job:
    """Fill all match fields on the job (in place) and return it."""
    profile = profile or Profile()
    fams = role_families(job)
    prim = primary_family(fams)
    fam_w = FAMILY_WEIGHT.get(prim, 0)
    role_label = FAMILY_LABEL[prim]
    edu = parse_education(job, fams)
    if ("doktora" in fams or prim == "arge") and edu["field"] != "makine" and not _mech_domain(job, strict=True):
        fam_w = 8  # research outside the mechanical domain (unless the ad asks for mechanical engineers)
    if "teknisyen" in fams:        # technician roles are below an engineering degree
        fam_w, role_label = min(fam_w, 8), FAMILY_LABEL["teknisyen"]
    elif "satis" in fams or "destek" in fams:   # technical sales / support: possible, not a core engineering role
        key = "satis" if "satis" in fams else "destek"
        fam_w, role_label = min(fam_w, 14), FAMILY_LABEL[key]
    title_only = len(job.description) < SHORT_TEXT

    exp = parse_experience(job)
    mode = parse_work_mode(job)
    tier = location_tier(job, mode)

    found = extract_skills(job)
    have = [s for s in found if s in profile.skills]
    missing = [s for s in found if s not in profile.skills]
    core = [s for s in have if s in CORE_SKILLS]
    other = [s for s in have if s not in CORE_SKILLS and s != "ingilizce"]

    lang = ad_language(job)
    lang_gaps = [lbl for key, (lbl, rx) in LANG_REQ.items() if _any(rx, _lite(f"{job.title}\n{job.description}"))]
    if lang in LANG_NAME and lang not in profile.languages and LANG_NAME[lang] not in lang_gaps:
        lang_gaps.append(LANG_NAME[lang])

    # ---- score (for ordering; the category is decided by explicit rules below)
    score = fam_w
    score += min(30, 8 * len(core) + 3 * len(other))
    score -= min(12, 3 * len(missing))
    score += {"iyi": 25, "belirtilmemis": 15, "yakin": 12, "zor": 0, "uzak": -25}[exp["fit"]]
    score += {"lisans": 10, "lisans_veya_yl": 12, "yl_tercih": 12, "yl_ogrencisi": 14, "belirtilmemis": 10,
              "yl_zorunlu": 0, "doktora_zorunlu": -20}[edu["level"]]
    score += {"makine": 5, "ilgili": 2, "belirtilmemis": 0, "ilgisiz": -25}[edu["field"]]
    score -= 15 if lang_gaps else 0
    score = max(0, min(100, round(score * 100 / 95)))

    title_core = prim in ("cae", "eklemeli", "tasarim")
    exp_ok = exp["fit"] in ("iyi", "belirtilmemis")
    edu_ok = edu["level"] not in ("yl_zorunlu", "doktora_zorunlu")
    reasons: list[str] = []

    if exp["fit"] == "uzak" or edu["level"] == "doktora_zorunlu" or edu["field"] == "ilgisiz" or lang_gaps or fam_w < 10:
        cat = "dusuk"
    elif exp_ok and edu_ok and score >= 68 and ((fam_w >= 22 and (core or title_core)) or (fam_w >= 20 and len(core) >= 2)):
        cat = "dogrudan"
    elif exp_ok and edu_ok and fam_w >= 12:
        cat = "uygun"
    elif (exp["fit"] == "yakin" and (fam_w >= 20 or len(core) >= 2)) or \
         (exp["fit"] == "zor" and (len(core) >= 2 or (fam_w >= 22 and core))) or \
         (edu["level"] == "yl_zorunlu" and exp["fit"] != "uzak") or edu.get("phd_position"):
        cat = "stretch"
    else:
        cat = "dusuk"

    # ---- human-readable reasons, decisive ones first
    exp_reason = {
        "iyi": f"Deneyim: {exp['label']} - yeni mezun olarak uygun",
        "belirtilmemis": "Deneyim şartı belirtilmemiş",
        "yakin": f"{exp['label']} deneyim isteniyor - staj ve projelerinle stretch",
        "zor": f"{exp['label']} deneyim isteniyor",
        "uzak": f"{exp['label']} - kıdemli / uzun deneyim isteyen pozisyon",
    }[exp["fit"]]
    if edu.get("phd_position") and edu["level"] != "doktora_zorunlu":
        edu_reason = "Doktora pozisyonu - genelde YL derecesi ister, YL'n bitince başvurabilirsin"
    else:
        edu_reason = {
            "lisans": "Lisans mezunu kabul ediliyor",
            "lisans_veya_yl": "Lisans veya YL kabul ediliyor - YL'n artı",
            "yl_tercih": "Lisans yeterli, YL tercih sebebi - YL'n devam ediyor",
            "yl_ogrencisi": "YL öğrencisi aranıyor - şu an YL öğrencisisin",
            "yl_zorunlu": "YL derecesi isteniyor - YL'n devam ediyor",
            "doktora_zorunlu": "Doktora derecesi gerektiriyor",
            "belirtilmemis": "",
        }[edu["level"]]
    field_reason = {"makine": "Makine mühendisliği doğrudan isteniyor", "ilgili": "İlgili mühendislik bölümleri kabul ediliyor",
                    "ilgisiz": "Farklı bir bölüm isteniyor", "belirtilmemis": ""}[edu["field"]]
    skill_reason = ("Örtüşen: " + ", ".join(SKILLS[s][0] for s in (core + other)[:4])) if (core or other) else ""
    if cat == "dusuk":
        decisive = [lang_gaps and f"Dil şartı: {', '.join(lang_gaps)}",
                    exp["fit"] == "uzak" and exp_reason,
                    edu["level"] == "doktora_zorunlu" and edu_reason,
                    edu["field"] == "ilgisiz" and field_reason,
                    fam_w < 10 and "Pozisyon alanı profille zayıf örtüşüyor"]
        reasons = [r for r in decisive if r] + [skill_reason]
    elif cat == "stretch":
        reasons = [exp_reason if exp["fit"] in ("yakin", "zor") else "", edu_reason, skill_reason, field_reason]
    else:
        reasons = [skill_reason or f"Alan: {FAMILY_LABEL[prim]}", edu_reason, exp_reason, field_reason]
    if missing:
        reasons.append("Profilinde görünmüyor: " + ", ".join(SKILLS[s][0] for s in missing[:4]))
    if title_only and cat != "dusuk":
        # without the ad text the requirements are unknown: don't pretend it is a fit
        reasons = ["İlan metni alınamadı - şartlar bilinmiyor, ilana göz at",
                   f"Başlığa göre alan: {role_label}",
                   f"Başlığa göre tahmin: {CATEGORY_LABEL[cat]}"]
        cat = "belirsiz"
    job.category_reasons = [r for r in reasons if r][:5]

    job.category = cat
    job.score = score
    job.scored_by = "kural"
    job.experience = exp
    job.education = {k: edu[k] for k in ("level", "field", "label")}
    job.work_mode = mode
    job.loc_tier = tier
    job.loc_label = LOC_LABEL[tier]
    job.role_family = prim
    job.role_label = role_label
    job.sectors = sectors(job)
    job.is_internship = exp["level"] == "staj"
    job.requirements = [{"label": SKILLS[s][0], "have": s in profile.skills} for s in found if s != "ingilizce"][:10]
    if lang_gaps:
        job.requirements += [{"label": g, "have": False} for g in lang_gaps]
    job.matches = [SKILLS[s][0] for s in have if s != "ingilizce"]
    job.gaps = [SKILLS[s][0] for s in missing] + lang_gaps
    return job
