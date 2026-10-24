"""Job-specific CV: pick the CV language/variant for an ad and build a one-page Word + PDF CV.

Content comes from the private, git-ignored cv/ozel/cv.yaml (contact details, references) and
cv/ozel/sablon.docx (styles, bullet numbering and the photo). Nothing is invented for an ad: items are
only reordered so that the ones matching the ad's keywords come first.

    python -m radar cv linkedin:4458983259     # one ad (id, LinkedIn URL or a word from title/company)
    python -m radar cv --yeni [--gun 3]        # every new "doğrudan/uygun" ad of the last days
    python -m radar cv --temel                 # the four base CVs (tr/en x tasarim/uretim)
"""
from __future__ import annotations

import os
import re
import subprocess
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.sax.saxutils import escape

import yaml

from . import match
from .models import Job, _norm

PRIVATE = Path(__file__).resolve().parents[1] / "cv" / "ozel"
LANG_LABEL = {"tr": "Türkçe", "en": "İngilizce"}
VARIANT_LABEL = {"tasarim": "Tasarım", "uretim": "Üretim"}
# role families whose ads get the production-oriented CV
PRODUCTION_FAMILIES = {"uretim", "kalite", "bakim", "proje", "destek", "teknisyen"}
# tags pulled forward by each variant when the ad itself does not decide
# (cv.yaml is written in the design order, so the design variant keeps it as is)
VARIANT_BOOST = {"tasarim": set(),
                 "uretim": {"uretim", "rca", "lean", "dfm", "cnc", "kalite"}}
MAX_DROP = 3   # highest "opsiyonel" level that may be dropped to keep one page


# ------------------------------------------------------------------ choosing
def pick(job: Job) -> dict:
    """{"lang": "tr"|"en", "variant": "tasarim"|"uretim"} for an ad (no private data needed)."""
    lang = match.ad_language(job)
    if lang == "unknown":
        lang = "tr" if re.search(r"[çğışöüÇĞİŞÖÜ]", job.title or "") else "en"
    fam = job.role_family or match.primary_family(match.role_families(job))
    return {"lang": "tr" if lang == "tr" else "en", "variant": "uretim" if fam in PRODUCTION_FAMILIES else "tasarim"}


def label(choice: dict) -> str:
    return f"{LANG_LABEL[choice['lang']]} · {VARIANT_LABEL[choice['variant']]}"


def job_tags(job: Job | None) -> set[str]:
    if job is None:
        return set()
    tags = set(match.extract_skills(job)) | set(match.role_families(job))
    return tags | ({job.role_family} if job.role_family else set())


def rank(items: list[dict], tags: set[str], boost: set[str]) -> list[dict]:
    """Stable order: items sharing tags with the ad first, then items the variant favours."""
    def score(it):
        own = set(it.get("etiket") or [])
        return 2 * len(own & tags) + len(own & boost)
    return sorted(items, key=lambda it: -score(it))


# ------------------------------------------------------------------ docx xml
def _run(text: str, b=False, i=False, color=None, sz=None, lang=None) -> str:
    rpr = ("<w:b/><w:bCs/>" if b else "") + ("<w:i/><w:iCs/>" if i else "")
    rpr += f'<w:color w:val="{color}"/>' if color else ""
    rpr += f'<w:sz w:val="{sz}"/><w:szCs w:val="{sz}"/>' if sz else ""
    rpr += f'<w:lang w:val="{lang}"/>' if lang else ""
    rpr = f"<w:rPr>{rpr}</w:rPr>" if rpr else ""
    return f'<w:r>{rpr}<w:t xml:space="preserve">{escape(text)}</w:t></w:r>'


class _Doc:
    """Paragraph builders matching the template's look (Calibri 9.5, grey right-aligned dates)."""

    def __init__(self, lang: str):
        self.lang = "en-US" if lang == "en" else None
        self.links: list[str] = []
        self.parts: list[str] = []

    def r(self, text, **kw):
        return _run(text, lang=self.lang, **kw)

    def link(self, text: str, url: str) -> str:
        self.links.append(url)
        return f'<w:hyperlink r:id="rIdCv{len(self.links)}" w:history="1">{self.r(text)}</w:hyperlink>'

    def p(self, runs, after=20, before=None):
        sp = f'<w:spacing{f" w:before=\"{before}\"" if before else ""} w:after="{after}"/>'
        self.parts.append(f"<w:p><w:pPr>{sp}</w:pPr>{''.join(runs)}</w:p>")

    def section(self, title):
        bdr = '<w:pBdr><w:bottom w:val="single" w:sz="6" w:space="2" w:color="999999"/></w:pBdr>'
        self.parts.append(f'<w:p><w:pPr>{bdr}<w:spacing w:before="86" w:after="46"/></w:pPr>'
                          f'{self.r(title, b=True, color="000000", sz=20)}</w:p>')

    def entry(self, title, date=""):
        rs = self.r(title, b=True, sz=20) + (f"<w:r><w:tab/></w:r>{self.r(date, i=True, color='444444')}" if date else "")
        self.parts.append('<w:p><w:pPr><w:tabs><w:tab w:val="right" w:pos="10490"/></w:tabs>'
                          f'<w:spacing w:before="70" w:after="20"/></w:pPr>{rs}</w:p>')

    def bullet(self, text):
        self.parts.append('<w:p><w:pPr><w:pStyle w:val="ListeParagraf"/><w:numPr><w:ilvl w:val="0"/>'
                          f'<w:numId w:val="2"/></w:numPr><w:spacing w:after="20"/></w:pPr>{self.r(text)}</w:p>')


def _upper_first(s: str, lang: str) -> str:
    if not s:
        return s
    first = "İ" if (s[0] == "i" and lang == "tr") else s[0].upper()
    return first + s[1:]


def _keep(item: dict, drop: int) -> bool:
    return not (item.get("opsiyonel") and int(item["opsiyonel"]) <= drop)


def compose(content: dict, lang: str, variant: str, tags: set[str], drop: int = 0) -> _Doc:
    """The CV body (everything below the name/photo line) for one language and variant."""
    c, d = content[lang], _Doc(lang)
    boost = VARIANT_BOOST[variant]
    sep = "  |  "
    d.p([d.r(c["unvan"][variant], color="444444", sz=20)])
    contact = []
    for k, it in enumerate(c["iletisim"]):
        contact.append(d.r(sep) if k else "")
        contact.append(d.link(it["metin"], it["link"]) if isinstance(it, dict) else d.r(it))
    d.p(contact)
    d.p([d.r(c["durum"])], after=40)

    d.section(c["bolum"]["hakkimda"])
    d.p([d.r(" ".join(c["hakkimda"][variant].split()))])

    d.section(c["bolum"]["egitim"])
    for e in c["egitim"]:
        d.entry(e["baslik"], e.get("tarih", ""))
        d.p([d.r(e["alt"], i=True)])

    d.section(c["bolum"]["deneyim"])          # always reverse-chronological, as written in cv.yaml
    for e in c["deneyim"]:
        d.entry(e["baslik"], e.get("tarih", ""))
        d.bullet(e.get("uzun") if variant == "uretim" and e.get("uzun") else e["madde"])

    d.section(c["bolum"]["projeler"])
    for e in rank([e for e in c["projeler"] if _keep(e, drop)], tags, boost):
        d.entry(e["baslik"], e.get("tarih", ""))
        d.bullet(e["madde"])

    d.section(c["bolum"]["yetkinlikler"])
    d.p([d.r(c["yazilim"]["etiket"], b=True), d.r(c["yazilim"]["metin"])])
    skills = [it["metin"] for it in rank(c["uzmanlik"]["maddeler"], tags, boost)]
    d.p([d.r(c["uzmanlik"]["etiket"], b=True), d.r(_upper_first(", ".join(skills), lang))])
    d.p([d.r(c["dil"]["etiket"], b=True), d.r(c["dil"]["metin"])])

    d.section(c["bolum"]["sertifikalar"])
    for s in c["sertifikalar"]:
        d.bullet(s)

    d.section(c["bolum"]["uyelikler"])
    for e in c["uyelikler"]:
        if _keep(e, drop):
            d.entry(e["baslik"], e.get("tarih", ""))
            if e.get("madde"):
                d.bullet(e["madde"])
    if c.get("ilgi") and _keep(c["ilgi"], drop):
        d.p([d.r(c["ilgi"]["etiket"], b=True), d.r(c["ilgi"]["metin"])], before=60)

    if c.get("referanslar"):
        d.section(c["bolum"]["referanslar"])
        for ref in c["referanslar"]:
            d.p([d.r(ref["ad"], b=True), d.r(sep + ref["detay"])])
    return d


def write_docx(d: _Doc, template: Path, out: Path, title: str) -> None:
    """Template's first paragraph (name + photo) and page setup, followed by the composed body."""
    with zipfile.ZipFile(template) as zin:
        files = {n: zin.read(n) for n in zin.namelist()}
        infos = zin.infolist()
    doc = files["word/document.xml"].decode("utf-8")
    head = re.search(r"<w:p[ >].*?</w:p>", doc, flags=re.S).group(0)
    sect = re.search(r"<w:sectPr\b[^>]*/>|<w:sectPr\b.*?</w:sectPr>", doc, flags=re.S).group(0)
    start, end = doc.index("<w:body>") + len("<w:body>"), doc.index("</w:body>")
    files["word/document.xml"] = (doc[:start] + head + "".join(d.parts) + sect + doc[end:]).encode("utf-8")
    rels = files["word/_rels/document.xml.rels"].decode("utf-8")
    rels = rels.replace("</Relationships>", "".join(
        f'<Relationship Id="rIdCv{k}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
        f'hyperlink" Target="{escape(u)}" TargetMode="External"/>' for k, u in enumerate(d.links, 1)) + "</Relationships>")
    files["word/_rels/document.xml.rels"] = rels.encode("utf-8")
    core = files["docProps/core.xml"].decode("utf-8")
    core = re.sub(r"<dc:title>.*?</dc:title>|<dc:creator>.*?</dc:creator>", "", core)
    core = core.replace("</cp:coreProperties>", f"<dc:title>{escape(title)} - CV</dc:title>"
                                                 f"<dc:creator>{escape(title)}</dc:creator></cp:coreProperties>")
    files["docProps/core.xml"] = core.encode("utf-8")
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for info in infos:
            z.writestr(info, files[info.filename])


# ------------------------------------------------------------------ pdf (Microsoft Word)
def to_pdf(pairs: list[tuple[Path, Path]], timeout_per_doc: int = 30) -> list[int | None] | None:
    """Export each docx to PDF with Word; page count per document (None where that one failed),
    or None if Word could not be used at all. A Word window the user already has open is reused and
    left open (never quit, never hidden); a hidden leftover instance with no documents is quit. The PowerShell script goes through a temp file: a long list
    of paths does not fit on a command line."""
    if not pairs:
        return []
    q = lambda p: "'" + str(p).replace("'", "''") + "'"   # noqa: E731  PowerShell single-quoted literal
    jobs = "\n".join(f"$todo += ,@({q(a)}, {q(b)})" for a, b in pairs)
    script = f"""$todo = @()
{jobs}
$running = [bool](Get-Process WINWORD -ErrorAction SilentlyContinue)
try {{
  if ($running) {{ $w = [Runtime.InteropServices.Marshal]::GetActiveObject('Word.Application') }}
  else {{ $w = New-Object -ComObject Word.Application; $w.Visible = $false }}
}} catch {{ Write-Output "NOWORD $($_.Exception.Message)"; exit 1 }}
$m = [Type]::Missing
try {{
  foreach ($t in $todo) {{
    try {{
      $d = $w.Documents.Open($t[0], $false, $true, $false, $m, $m, $m, $m, $m, $m, $m, $false)
      $n = $d.ComputeStatistics(2)
      $d.ExportAsFixedFormat($t[1], 17)
      $d.Close($false)
      Write-Output "PAGES $n"
    }} catch {{ Write-Output "FAIL $($_.Exception.Message)" }}
  }}
}} finally {{
  # quit Word we started, or a leftover hidden instance with nothing open; never the user's window
  if (-not $running -or (-not $w.Visible -and $w.Documents.Count -eq 0)) {{ $w.Quit() }}
}}
"""
    import tempfile
    fd, ps1 = tempfile.mkstemp(suffix=".ps1")
    os.close(fd)
    Path(ps1).write_text(script, encoding="utf-8-sig")       # BOM: Windows PowerShell 5.1 reads it as UTF-8
    try:
        res = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", ps1],
                             capture_output=True, text=True, encoding="utf-8", errors="replace",
                             timeout=60 + timeout_per_doc * len(pairs))
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"Word PDF hatası: {e}")
        return None
    finally:
        Path(ps1).unlink(missing_ok=True)
    lines = [ln.strip() for ln in (res.stdout or "").splitlines() if ln.strip().startswith(("PAGES", "FAIL", "NOWORD"))]
    if any(ln.startswith("NOWORD") for ln in lines) or len(lines) != len(pairs):
        err = re.sub(r"#< CLIXML.*?</Objs>", "", res.stderr or "", flags=re.S).strip()
        print(f"Word PDF hatası: {' '.join(lines)[-300:] or err[-300:]}")
        return None
    for (a, _), ln in zip(pairs, lines):
        if ln.startswith("FAIL"):
            print(f"PDF üretilemedi: {a.parent.name}: {ln[5:][:150]}")
    return [int(ln.split()[1]) if ln.startswith("PAGES") else None for ln in lines]


# ------------------------------------------------------------------ building
def load_private() -> dict:
    src = PRIVATE / "cv.yaml"
    if not src.exists() or not (PRIVATE / "sablon.docx").exists():
        raise FileNotFoundError(f"{src} ve {PRIVATE / 'sablon.docx'} gerekli (gizli CV kaynağı, KURULUM.md'ye bak)")
    return yaml.safe_load(src.read_text(encoding="utf-8"))


def _safe(s: str, n: int = 70) -> str:
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', " ", s)
    return re.sub(r"\s+", " ", s).strip(" .")[:n].strip(" .")


def ad_folder(job: Job) -> str:
    """<first-seen date>\\<company - title>, relative to the output folder (also shown on the site)."""
    return f"{(job.first_seen or '')[:10] or 'tarihsiz'}\\{_safe(f'{job.company} - {job.title}', 80)}"


AUTO_CATEGORIES = ("dogrudan", "uygun")   # ads that get a CV automatically (python -m radar cv --yeni)
DATE_DIR = re.compile(r"\d{4}-\d{2}-\d{2}")


def clean_old(out_root: Path, keep_days: int, file_stem: str) -> int:
    """Remove date folders older than keep_days that hold nothing but CVs this tool wrote."""
    import shutil
    cutoff = (datetime.now(timezone.utc) - timedelta(days=keep_days)).date().isoformat()
    ours = {f"{file_stem}.docx", f"{file_stem}.pdf"}
    removed = 0
    for d in out_root.iterdir() if out_root.exists() else []:
        if d.is_dir() and DATE_DIR.fullmatch(d.name) and d.name < cutoff:
            files = [p for p in d.rglob("*") if p.is_file()]
            if all(p.name in ours for p in files):
                shutil.rmtree(d)
                removed += 1
    return removed


def build(targets: list[tuple[str, Job | None, dict]], content: dict, pdf: bool = True) -> list[dict]:
    """targets: (output folder, job or None, {"lang", "variant"}). Writes <folder>/<dosya_adi>.docx/.pdf and,
    when Word is available, drops "opsiyonel" items one level at a time until every CV fits one page."""
    name = content.get("ad") or content.get("dosya_adi", "CV").replace("_CV", "").replace("_", " ")
    template = PRIVATE / "sablon.docx"
    todo = [{"dir": Path(f), "job": j, "choice": ch, "drop": 0, "pages": None} for f, j, ch in targets]
    while True:
        pending = [t for t in todo if t["pages"] is None or (t["pages"] > 1 and t["drop"] < MAX_DROP)]
        if not pending:
            break
        for t in pending:
            if t["pages"] is not None:
                t["drop"] += 1
            base = t["dir"] / content.get("dosya_adi", "CV")
            t["docx"], t["pdf"] = base.with_suffix(".docx"), base.with_suffix(".pdf")
            d = compose(content, t["choice"]["lang"], t["choice"]["variant"], job_tags(t["job"]), t["drop"])
            write_docx(d, template, t["docx"], name)
        pages = to_pdf([(t["docx"], t["pdf"]) for t in pending]) if pdf else None
        if pages is None:
            for t in pending:
                t["pages"], t["pdf"] = 0, None   # unknown: Word missing or failed
            break
        for t, n in zip(pending, pages):
            t["pages"] = n or 0
            if n is None:
                t["pdf"] = None
    return todo


def find_jobs(store_jobs: dict[str, Job], query: str) -> list[Job]:
    if query in store_jobs:
        return [store_jobs[query]]
    m = re.search(r"(\d{6,})", query)
    if m and ("linkedin" in query or query.isdigit()):
        hit = [j for j in store_jobs.values() if j.native_id == m.group(1)]
        if hit:
            return hit
    q = _norm(query)
    return [j for j in store_jobs.values() if q and q in _norm(f"{j.title} {j.company}")]


def run_cli(args, store_jobs: dict[str, Job]) -> int:
    try:
        content = load_private()
    except FileNotFoundError as e:
        print(e)
        return 1
    out_root = Path(content.get("cikti_klasoru") or PRIVATE / "cikti")
    force = {k: v for k, v in (("lang", args.dil), ("variant", args.tur)) if v}
    targets: list[tuple[str, Job | None, dict]] = []
    if args.temel:
        for lang in ("tr", "en"):
            for variant in ("tasarim", "uretim"):
                targets.append((str(out_root / "_temel" / f"{lang}_{variant}"), None, {"lang": lang, "variant": variant}))
    elif args.yeni:
        removed = clean_old(out_root, args.sakla, content.get("dosya_adi", "CV"))
        if removed:
            print(f"{args.sakla} günden eski {removed} günlük CV klasörü silindi.")
        cutoff = (datetime.now(timezone.utc) - timedelta(days=args.gun)).isoformat()
        jobs = [j for j in store_jobs.values()
                if j.category in AUTO_CATEGORIES and not j.closed and (j.first_seen or "") >= cutoff]
        jobs = [j for j in jobs if not (out_root / ad_folder(j)).exists()]
        if not jobs:
            print(f"Son {args.gun} günde CV'si hazırlanmamış doğrudan/uygun ilan yok.")
            return 0
        targets = [(str(out_root / ad_folder(j)), j, {**pick(j), **force}) for j in jobs]
    elif args.ilan:
        query = re.sub(r"^\s*python -m radar cv\s+", "", (args.ilan.strip().splitlines() or [""])[0]).strip()
        hits = find_jobs(store_jobs, query)
        if len(hits) != 1:
            print("İlan bulunamadı." if not hits else f"{len(hits)} ilan eşleşti, kimliğiyle (id) tekrar dene:")
            for j in hits[:15]:
                print(f"  {j.id}  {j.title[:60]} - {j.company[:30]}")
            return 1
        j = hits[0]
        targets = [(str(out_root / ad_folder(j)), j, {**pick(j), **force})]
    else:
        print("Bir ilan ver (python -m radar cv linkedin:123) ya da --yeni / --temel kullan.")
        return 1

    done = build(targets, content, pdf=not args.no_pdf)
    word_missing = False
    for t in done:
        what = t["job"].company + " - " + t["job"].title if t["job"] else "temel"
        page = (f"{t['pages']} sayfa" if t["pages"] else "PDF yok")
        warn = "  (!) tek sayfaya sığmadı" if t["pages"] and t["pages"] > 1 else ""
        dropped = f", {t['drop']} isteğe bağlı satır çıkarıldı" if t["drop"] else ""
        print(f"✓ {what[:70]}  [{label(t['choice'])}, {page}{dropped}]{warn}\n    {t['pdf'] or t['docx']}")
        word_missing |= t["pdf"] is None and not args.no_pdf
    if word_missing:
        print("PDF üretilemedi (Word bulunamadı ya da hata verdi): Word dosyasını açıp Farklı Kaydet > PDF yap.")
    if getattr(args, "ac", False) and hasattr(os, "startfile"):
        os.startfile(done[0]["dir"] if len(done) == 1 else out_root)
    return 0
