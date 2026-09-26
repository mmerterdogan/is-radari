// İş Radarı - job list with fit categories + application tracker.
// Scanned jobs come from data.json (written by the daily GitHub Action, classified by radar/match.py).
// Your tracker (stages, notes, manual jobs, letters) lives in `S`, saved in this browser only
// (move it between devices with the backup export / import in Settings).
import { EMPTY, mergeState } from "./merge.js";

const LS_STATE = "radar-state-v2";
const LS_FILTERS = "radar-filters-v2";   // v2: new "belirsiz" category and "closed" filter
const FOLLOWUP_BDAYS = 6;   // follow up ~6 business days after applying

const STAGES = [
  ["", "Durum seç…"],
  ["kaydedildi", "⭐ Kaydedildi"],
  ["basvuruldu", "📨 Başvuruldu"],
  ["mulakat", "🗣 Mülakat"],
  ["teklif", "🎉 Teklif"],
  ["red", "✕ Olumsuz"],
  ["gizli", "🙈 İlgilenmiyorum"],
];
const STAGE_LABEL = Object.fromEntries(STAGES);
const PIPELINE = ["mulakat", "basvuruldu", "kaydedildi", "teklif", "red"];
const CAT = { dogrudan: "Doğrudan uygun", uygun: "Uygun", stretch: "Stretch", belirsiz: "Değerlendirilemedi", dusuk: "Düşük uygunluk" };
const CAT_ORDER = { dogrudan: 0, uygun: 1, stretch: 2, belirsiz: 3, dusuk: 4 };
const SRC = { linkedin: "LinkedIn", euraxess: "EURAXESS", greenhouse: "Şirket sitesi", smartrecruiters: "Şirket sitesi", manual: "Elle eklendi" };
const MODE = { uzaktan: "Uzaktan", hibrit: "Hibrit", ofiste: "Ofiste", belirtilmemis: "Çalışma şekli belirtilmemiş" };
const LOC = { 1: "İstanbul", 2: "Sanayi şehri", 3: "Türkiye", 4: "Uzaktan", 5: "Yurt dışı" };
// filter groups -> role families produced by radar/match.py
const FAM_GROUP = {
  cae: ["cae"], tasarim: ["tasarim"], arge: ["arge", "urun"], eklemeli: ["eklemeli"],
  uretim: ["uretim", "kalite", "bakim"], test: ["test"], otomotiv: ["otomotiv", "sistem"],
  arastirma: ["doktora"], genel: ["makine", "genel", "proje", "teknisyen", "satis", "diger"],
};
const EDU_GROUP = {
  lisans: ["lisans", "lisans_veya_yl", "yl_tercih", "yl_ogrencisi"], yl: ["yl_zorunlu"],
  doktora: ["doktora_zorunlu"], belirtilmemis: ["belirtilmemis"],
};
const DEFAULT_FILTERS = () => ({ cats: ["dogrudan", "uygun", "stretch", "belirsiz"], loc: [], exp: [], edu: [], mode: [], fam: [],
  date: "all", intern: "show", closed: "hide" });

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const nowIso = () => new Date().toISOString();
const today = () => new Date().toISOString().slice(0, 10);
const addDays = (d, n) => new Date(new Date(d).getTime() + n * 864e5).toISOString().slice(0, 10);
function addBusinessDays(d, n) {
  const x = new Date(d + "T12:00:00");
  while (n > 0) { x.setDate(x.getDate() + 1); if (x.getDay() % 6 !== 0) n--; }
  return x.toISOString().slice(0, 10);
}
const nextFollowup = () => addBusinessDays(today(), FOLLOWUP_BDAYS);
const fmtDate = (d) => (d ? new Date(d).toLocaleDateString("tr-TR", { day: "numeric", month: "short" }) : "");
const daysAgo = (d) => (d ? Math.floor((Date.now() - new Date(d.length === 10 ? d + "T12:00:00" : d).getTime()) / 864e5) : null);

const ls = {
  get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} },
};

let DATA = { jobs: [], runs: [] };
let S = ls.get(LS_STATE, EMPTY());
let F = { ...DEFAULT_FILTERS(), ...ls.get(LS_FILTERS, {}) };
let view = "jobs";
let lastDay = "";
let openNotes = new Set();
let expanded = new Set();

function saveEntry(id, patch) {
  S.entries[id] = { ...(S.entries[id] || {}), ...patch, updated: nowIso() };
  ls.set(LS_STATE, S);
}

// ------------------------------------------------------------------ data helpers
const EXP_FROM_MANUAL = { iyi: "Yeni mezun / junior", yakin: "1-2 yıl", zor: "3-4 yıl", uzak: "5+ yıl", belirtilmemis: "Belirtilmemiş" };
const EDU_FROM_MANUAL = { lisans: "Lisans", lisans_veya_yl: "Lisans veya YL", yl_zorunlu: "YL şartı", belirtilmemis: "Belirtilmemiş" };

function allJobs() {
  const manual = Object.values(S.manual)
    .filter((m) => !m.deleted)
    .map((m) => ({
      ...m, source: "manual", category: "", score: null, first_seen: m.added, posted: (m.added || "").slice(0, 10),
      loc_tier: Number(m.loc_tier || 3), loc_label: LOC[m.loc_tier || 3], work_mode: m.work_mode || "belirtilmemis",
      experience: { fit: m.exp || "belirtilmemis", label: EXP_FROM_MANUAL[m.exp || "belirtilmemis"] },
      education: { level: m.edu || "belirtilmemis", label: EDU_FROM_MANUAL[m.edu || "belirtilmemis"] },
      role_family: "diger", requirements: [], category_reasons: [], sectors: [],
    }));
  return [...DATA.jobs, ...manual];
}
const entry = (id) => S.entries[id] || {};
const letterOf = (j) => entry(j.id).letter || j.letter || null;
const stageOf = (j) => entry(j.id).stage || "";
const followDue = (j) => stageOf(j) === "basvuruldu" && entry(j.id).followup_at && entry(j.id).followup_at <= today();
const jobDate = (j) => j.posted || (j.first_seen || "").slice(0, 10);

function passesFilters(j) {
  if (j.source !== "manual" && F.cats.length && !F.cats.includes(j.category)) return false;
  if (F.loc.length) {
    const remoteish = ["uzaktan", "hibrit"].includes(j.work_mode);
    if (!F.loc.some((t) => Number(t) === j.loc_tier || (t === "4" && remoteish))) return false;
  }
  if (F.exp.length && !F.exp.includes(j.experience?.fit || "belirtilmemis")) return false;
  if (F.edu.length && !F.edu.some((g) => EDU_GROUP[g].includes(j.education?.level || "belirtilmemis"))) return false;
  if (F.mode.length && !F.mode.includes(j.work_mode || "belirtilmemis")) return false;
  if (F.fam.length && j.source !== "manual" && !F.fam.some((g) => FAM_GROUP[g].includes(j.role_family))) return false;
  if (F.date !== "all") {
    const d = daysAgo(jobDate(j));
    if (d === null || d > Number(F.date)) return false;
  }
  if (F.intern === "hide" && j.is_internship) return false;
  if (F.intern === "only" && !j.is_internship) return false;
  if (F.closed === "hide" && j.closed && !stageOf(j)) return false;   // tracked ads stay visible
  const q = $("#q").value.trim().toLocaleLowerCase("tr");
  if (q) {
    const hay = [j.title, j.company, j.location, j.description, entry(j.id).notes, entry(j.id).contact, ...(j.matches || []), ...(j.gaps || []),
      ...(j.sectors || [])].join(" ").toLocaleLowerCase("tr");
    if (!hay.includes(q)) return false;
  }
  return true;
}

function inView(j) {
  const st = stageOf(j);
  if (view === "apps") return PIPELINE.includes(st);
  if (view === "followup") return followDue(j);
  return st !== "gizli" && !PIPELINE.slice(0, 2).includes(st) && j.source !== "manual";
}

// ------------------------------------------------------------------ rendering
const linkedinPeople = (q) => `https://www.linkedin.com/search/results/people/?keywords=${encodeURIComponent(q)}`;
function freshness(j) {
  const d = daysAgo(jobDate(j));
  if (d === null) return "";
  return d <= 0 ? "bugün" : d === 1 ? "dün" : `${d} gün önce`;
}

function card(j) {
  const e = entry(j.id);
  const st = e.stage || "";
  const isNew = j.source !== "manual" && (j.first_seen || "").slice(0, 10) === lastDay;
  const letter = letterOf(j);
  const badge = j.source === "manual"
    ? `<span class="badge manual">✎ Elle eklendi</span>`
    : `<span class="badge ${esc(j.category)}">${esc(CAT[j.category] || "")}<span class="sc">${j.score ?? ""}</span></span>`;
  const tags = [
    st ? `<span class="tag stage">${esc(STAGE_LABEL[st])}${e.applied_at && st !== "kaydedildi" ? " · " + fmtDate(e.applied_at) : ""}</span>` : "",
    followDue(j) ? `<span class="tag due">Takip zamanı</span>` : "",
    isNew ? `<span class="tag new">Yeni</span>` : "",
    j.is_internship ? `<span class="tag">Staj / öğrenci</span>` : "",
    j.closed ? `<span class="tag closed" title="İlan artık başvuru kabul etmiyor">Kapandı</span>` : "",
    j.scored_by === "claude" ? `<span class="tag" title="Claude ile değerlendirildi">Claude</span>` : "",
  ].join("");
  const loc = `${esc(j.loc_label || "")}${j.location ? ` <b>${esc(j.location)}</b>` : ""}`;
  const facts = [
    `<span class="loc" title="Lokasyon">📍 ${loc}</span>`,
    `<span title="Çalışma şekli">🏢 ${esc(MODE[j.work_mode] || MODE.belirtilmemis)}</span>`,
    `<span title="Deneyim şartı">⏱ ${esc(j.experience?.label || "Belirtilmemiş")}</span>`,
    `<span title="Eğitim şartı">🎓 ${esc(j.education?.label || "Belirtilmemiş")}</span>`,
    freshness(j) ? `<span title="İlan tarihi">🗓 ${esc(freshness(j))}</span>` : "",
    j.applicants ? `<span title="LinkedIn'deki başvuru sayısı">👥 ${esc(j.applicants)} başvuru</span>` : "",
    j.role_label ? `<span title="Pozisyon alanı">🧭 ${esc(j.role_label)}</span>` : "",
    `<span>${esc(SRC[j.source] || j.source)}</span>`,
  ].filter(Boolean).join("");
  const reasons = j.category_reasons || [];
  const showAll = expanded.has(j.id);
  const why = reasons.slice(0, showAll ? 9 : 3).map((r) => `<li>${esc(r)}</li>`).join("");
  const reqs = (j.requirements || []).map((r) => `<span class="req ${r.have ? "have" : "miss"}" title="${r.have ? "Profilinde var" : "Profilinde görünmüyor"}">${r.have ? "✓" : "✗"} ${esc(r.label)}</span>`).join("");
  const opts = STAGES.map(([v, l]) => `<option value="${v}" ${v === st ? "selected" : ""}>${l}</option>`).join("");
  const noteOpen = openNotes.has(j.id);
  return `<article class="card2 ${esc(j.category || "manual")} ${st === "gizli" ? "hidden-job" : ""} ${j.closed ? "is-closed" : ""}" data-id="${esc(j.id)}">
    <div class="card-top">${badge}<div class="tags" style="margin:0">${tags}</div></div>
    ${j.url ? `<a class="title" href="${esc(j.url)}" target="_blank" rel="noopener">${esc(j.title)}</a>` : `<span class="title">${esc(j.title)}</span>`}
    <div class="company">${esc(j.company)}</div>
    <div class="facts">${facts}</div>
    ${why ? `<ul class="why2">${why}</ul>` : ""}
    ${reasons.length > 3 ? `<button class="btn link" data-act="more">${showAll ? "Daha az" : `+${reasons.length - 3} gerekçe`}</button>` : ""}
    ${reqs ? `<div class="reqs" aria-label="Ana gereksinimler">${reqs}</div>` : ""}
    ${j.sectors?.length ? `<div class="sectors">Sektör: ${j.sectors.map(esc).join(", ")}</div>` : ""}
    ${(e.notes || e.contact) && !noteOpen ? `<div class="note-view">${e.contact ? `👤 ${esc(e.contact)}${e.notes ? "\n" : ""}` : ""}${esc(e.notes || "")}</div>` : ""}
    <div class="actions">
      <select data-act="stage" aria-label="Başvuru durumu">${opts}</select>
      ${j.url ? `<a class="btn primary" href="${esc(j.url)}" target="_blank" rel="noopener">İlana git</a>` : ""}
      <button class="btn" data-act="letter">${letter ? "Ön yazı" : "Ön yazı oluştur"}</button>
      <button class="btn" data-act="note">${noteOpen ? "Notu kapat" : e.notes ? "Notu düzenle" : "Not"}</button>
      ${st === "basvuruldu" ? `<button class="btn" data-act="followup-msg">${e.followup_msg ? "Takip mesajı" : "Takip mesajı yaz"}</button>` : ""}
      ${followDue(j) ? `<button class="btn" data-act="followed">Takip ettim</button>` : ""}
      ${["mulakat", "teklif"].includes(st) ? `<button class="btn" data-act="interview">${e.interview_prep ? "Mülakat notları" : "Mülakat hazırlığı"}</button>` : ""}
      ${j.source === "manual" ? `<button class="btn" data-act="delete">Sil</button>` : ""}
    </div>
    ${noteOpen ? `<div class="note">
      <input data-act="contact" placeholder="İletişim kişisi (ad, unvan, LinkedIn)" value="${esc(e.contact || "")}">
      <textarea data-act="notes" placeholder="Görüşme tarihi, maaş, izlenim…">${esc(e.notes || "")}</textarea></div>` : ""}
    ${j.company ? `<div class="netlinks">Bağlantı kur:
      <a href="${linkedinPeople(`${j.company} İstanbul Üniversitesi-Cerrahpaşa`)}" target="_blank" rel="noopener">İÜC mezunları</a> ·
      <a href="${linkedinPeople(`${j.company} mechanical engineer`)}" target="_blank" rel="noopener">şirketteki mühendisler</a> ·
      <a href="${linkedinPeople(`${j.company} recruiter`)}" target="_blank" rel="noopener">İK / işe alım</a></div>` : ""}
  </article>`;
}

function sortJobs(jobs) {
  const sort = $("#sort").value;
  const fit = (a, b) => (CAT_ORDER[a.category] ?? 4) - (CAT_ORDER[b.category] ?? 4) || (b.score ?? 0) - (a.score ?? 0);
  if (sort === "date") return jobs.sort((a, b) => jobDate(b).localeCompare(jobDate(a)) || fit(a, b));
  if (sort === "loc") return jobs.sort((a, b) => (a.loc_tier ?? 5) - (b.loc_tier ?? 5) || fit(a, b));
  return jobs.sort((a, b) => fit(a, b) || (a.loc_tier ?? 5) - (b.loc_tier ?? 5));
}

function groupKey(j) {
  const sort = $("#sort").value;
  if (sort === "date") {
    const d = jobDate(j);
    return d ? new Date(d + (d.length === 10 ? "T12:00:00" : "")).toLocaleDateString("tr-TR", { weekday: "long", day: "numeric", month: "long" }) : "Tarihsiz";
  }
  if (sort === "loc") return LOC[j.loc_tier] || "Diğer";
  return CAT[j.category] || "Diğer";
}

function renderFilters() {
  document.querySelectorAll(".chips[data-group]").forEach((box) => {
    const g = box.dataset.group;
    box.querySelectorAll(".chip").forEach((c) => {
      const on = Array.isArray(F[g]) ? F[g].includes(c.dataset.v) : F[g] === c.dataset.v;
      c.setAttribute("aria-pressed", on);
    });
  });
  // one-line summary of the active filters, shown on the collapsed panel
  const label = (g, v) => document.querySelector(`.chips[data-group="${g}"] .chip[data-v="${v}"]`)?.textContent || v;
  const parts = [];
  const def = DEFAULT_FILTERS();
  parts.push(F.cats.length === Object.keys(CAT).length || !F.cats.length ? "tüm kategoriler" : F.cats.map((v) => label("cats", v)).join(", "));
  for (const g of ["loc", "exp", "edu", "mode", "fam"]) if (F[g].length) parts.push(F[g].map((v) => label(g, v)).join(", "));
  if (F.date !== def.date) parts.push(label("date", F.date));
  if (F.intern !== def.intern) parts.push(`staj: ${label("intern", F.intern).toLocaleLowerCase("tr")}`);
  $("#fcount").textContent = "· " + parts.join(" · ");
  document.querySelectorAll("[data-cat-only]").forEach((b) => b.classList.toggle("active", F.cats.length === 1 && F.cats[0] === b.dataset.catOnly));
}

function render() {
  renderFilters();
  const pool = allJobs();
  const jobs = pool.filter((j) => inView(j) && passesFilters(j));
  const list = $("#list");
  if (view === "apps" || view === "followup") {
    const groups = PIPELINE.map((st) => [st, jobs.filter((j) => stageOf(j) === st)]).filter(([, js]) => js.length);
    $("#count").textContent = `${jobs.length} kayıt${view === "followup" ? " · takip zamanı gelenler" : ""}`;
    list.innerHTML = groups.length
      ? groups.map(([st, js]) => `<div class="group">${esc(STAGE_LABEL[st])} (${js.length})</div>` +
          js.sort((a, b) => (entry(b.id).updated || "").localeCompare(entry(a.id).updated || "")).map(card).join("")).join("")
      : `<div class="empty">${view === "followup" ? "Takip zamanı gelen başvuru yok." : "Henüz başvuru yok. Bir ilanın durumunu “Kaydedildi” veya “Başvuruldu” yap, ya da “+ İlan ekle” ile başka sitelerden bulduğun ilanları ekle."}</div>`;
  } else {
    sortJobs(jobs);
    $("#count").textContent = `${jobs.length} ilan gösteriliyor`;
    let html = "", prev = null;
    for (const j of jobs) {
      const k = groupKey(j);
      if (k !== prev) {
        const n = jobs.filter((x) => groupKey(x) === k).length;
        html += `<div class="group">${esc(k)} (${n})</div>`;
        prev = k;
      }
      html += card(j);
    }
    const hiddenLow = pool.filter((j) => inView(j) && j.category === "dusuk").length;
    const hint = !F.cats.includes("dusuk") && hiddenLow ? ` “Düşük uygunluk” kategorisinde ${hiddenLow} ilan gizli.` : "";
    list.innerHTML = html || `<div class="empty">Bu filtrelerle ilan yok.${hint}</div>`;
  }
  const scan = pool.filter((j) => j.source !== "manual" && !["gizli", "basvuruldu", "mulakat"].includes(stageOf(j)));
  for (const c of Object.keys(CAT)) $(`#st-${c}`).textContent = scan.filter((j) => j.category === c).length;
  $("#st-active").textContent = pool.filter((j) => ["basvuruldu", "mulakat"].includes(stageOf(j))).length;
  $("#st-follow").textContent = pool.filter(followDue).length;
  document.querySelectorAll(".seg button").forEach((b) => b.setAttribute("aria-pressed", b.dataset.view === view));
}

function setFilters(next) {
  F = { ...F, ...next };
  ls.set(LS_FILTERS, F);
  render();
}

// ------------------------------------------------------------------ dialogs
function toast(msg) {
  const t = document.createElement("div");
  t.className = "toast";
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 2200);
}
const dlg = () => $("#dlg");
function openDialog(html) { $("#dlg-body").innerHTML = html; dlg().showModal(); }

function showLetter(j, L) {
  openDialog(`
    <h2>${esc(j.title)}</h2><div class="meta">${esc(j.company)}${j.location ? " · " + esc(j.location) : ""}</div>
    <h3>E-posta konusu</h3><pre id="l-sub">${esc(L.subject)}</pre>
    <button class="btn" data-copy="l-sub">Konuyu kopyala</button>
    <h3>Ön yazı</h3><pre id="l-body">${esc(L.cover_letter)}</pre>
    <div class="actions"><button class="btn primary" data-copy="l-body">Ön yazıyı kopyala</button>
      <button class="btn" data-regen="${esc(j.id)}">Yeniden yaz</button></div>
    <h3>CV'de öne çıkar</h3><ul class="why">${(L.cv_highlights || []).map((h) => `<li class="p">${esc(h)}</li>`).join("")}</ul>
    <p class="hint">Göndermeden önce oku: yazı CV'ndeki bilgilere dayanıyor ama son kontrol senin.</p>
    <div class="actions"><button class="btn" data-close>Kapat</button></div>`);
}

let PROFILE_INFO = null;
async function profileInfo() {
  if (!PROFILE_INFO) {
    const res = await fetch("profile.json", { cache: "no-store" });
    if (!res.ok) throw new Error(`profile.json: HTTP ${res.status}`);
    PROFILE_INFO = await res.json();
  }
  return PROFILE_INFO;
}

function claudePrompt(j, info) {
  const fit = j.category ? [
    `Fit category (rule-based): ${CAT[j.category]}`,
    `Education requirement: ${j.education?.label || "-"}; experience requirement: ${j.experience?.label || "-"}`,
    `Matching skills: ${(j.matches || []).join(", ") || "-"}; not in profile: ${(j.gaps || []).join(", ") || "-"}`,
  ].join("\n") : "";
  return [
    info.instructions,
    "",
    info.profile,
    "",
    `<job>\nTitle: ${j.title}\nCompany: ${j.company}\nLocation: ${j.location || ""}\nURL: ${j.url || ""}\n${fit}\nDescription:\n${j.description || "(ilan metni yok - başlık ve şirkete göre yaz)"}\n</job>`,
    "",
    "Yanıtını tam olarak şu biçimde ver, başka bir şey ekleme:",
    "KONU: <e-posta konusu>",
    "ÖN YAZI:",
    "<ön yazı metni>",
    "CV'DE ÖNE ÇIKAR:",
    "- <madde>",
  ].join("\n");
}

// Parse the answer pasted back from claude.ai (format requested in claudePrompt).
function parsePasted(text) {
  const t = text.replace(/\r/g, "").trim();
  const subject = (t.match(/^\s*KONU:\s*(.+)$/im) || [])[1]?.trim() || "";
  const body = (t.match(/ÖN YAZI:\s*\n([\s\S]*?)(?:\n\s*CV'DE ÖNE ÇIKAR:|$)/i) || [])[1]?.trim() || t;
  const hl = (t.match(/CV'DE ÖNE ÇIKAR:\s*\n([\s\S]*)$/i) || [])[1] || "";
  const cv_highlights = hl.split("\n").map((l) => l.replace(/^\s*[-•*]\s*/, "").trim()).filter(Boolean).slice(0, 5);
  return { subject, cover_letter: body, cv_highlights };
}

// Generic "copy prompt -> claude.ai -> paste the answer back" dialog (the user's own subscription, no API).
function promptDialog({ title, j, intro, prompt, placeholder, onSave }) {
  openDialog(`<h2>${esc(title)}</h2>
    <div class="meta">${esc(j.title)} · ${esc(j.company)}</div>
    <p class="hint">${esc(intro)} Kendi Claude hesabınla yazdırıyoruz (ek ücret yok).</p>
    <h3>1. İstemi kopyala, Claude'a yapıştır</h3>
    <div class="actions"><button class="btn primary" data-claude-copy>İstemi kopyala ve Claude'u aç</button></div>
    <h3>2. Claude'un cevabını buraya yapıştır</h3>
    <form class="form" id="paste-form">
      <textarea name="answer" rows="8" placeholder="${esc(placeholder || "")}" required></textarea>
      <div class="actions"><button class="btn primary" type="submit">Kaydet</button><button class="btn" type="button" data-close>Kapat</button></div>
    </form>`);
  $("[data-claude-copy]").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(prompt); toast("İstem kopyalandı ✓ - Claude'da yapıştır"); }
    catch { toast("Kopyalanamadı - tarayıcı izin vermedi"); }
    window.open("https://claude.ai/new", "_blank", "noopener");
  });
  $("#paste-form").addEventListener("submit", (ev) => {
    ev.preventDefault();
    onSave(new FormData(ev.target).get("answer").replace(/\r/g, "").trim());
  });
}

function showText(j, title, text, kind) {
  openDialog(`<h2>${esc(title)}</h2><div class="meta">${esc(j.title)} · ${esc(j.company)}</div>
    <pre id="t-body">${esc(text)}</pre>
    <div class="actions"><button class="btn primary" data-copy="t-body">Kopyala</button>
      <button class="btn" data-redo="${esc(kind)}" data-job="${esc(j.id)}">Yeniden yaz</button>
      <button class="btn" data-close>Kapat</button></div>`);
}

function jobBlock(j) {
  return `<job>\nTitle: ${j.title}\nCompany: ${j.company}\nLocation: ${j.location || ""}\nURL: ${j.url || ""}\nDescription:\n${j.description || "(ilan metni yok)"}\n</job>`;
}

function claudeDialog(j, info) {
  promptDialog({
    title: "Ön yazı", j, placeholder: "KONU: …\nÖN YAZI:\n…",
    intro: "CV'n, tercihlerin, ilan metni ve uygunluk analizi hazır bir istemde birleşti.",
    prompt: claudePrompt(j, info),
    onSave: (text) => { saveEntry(j.id, { letter: parsePasted(text) }); render(); showLetter(j, letterOf(j)); },
  });
}

function followupPrompt(j, info) {
  const e = entry(j.id);
  return [
    "Write a short, polite follow-up email for a job application I already sent. Language: the language of the job ad (Turkish ad -> Turkish).",
    "Max 120 words. Mention the role and when I applied, restate my interest in one sentence, and add ONE concrete, relevant item",
    "from my CV that fits the role (only facts from the CV). No pressure, no generic filler. Give a subject line first.",
    `I applied on: ${e.applied_at || "(unknown)"}. Contact person (if any): ${e.contact || "-"}.`,
    "", info.profile, "", jobBlock(j),
    "", "Format:", "KONU: <subject>", "<email body>",
  ].join("\n");
}

function interviewPrompt(j, info) {
  return [
    "Help me prepare for a job interview for the role below. Answer in Turkish (technical terms may stay in English).",
    "1) 10 likely technical questions for this role (FEA, design, manufacturing - whatever the ad needs) with short model answers",
    "   built ONLY from my CV experience; mark questions where my CV has a gap and suggest how to answer honestly.",
    "2) 5 behavioural questions with STAR-format answers drawn from my internships, Formula Student, TEKNOFEST and projects.",
    "3) 5 smart questions I can ask the interviewer about this company/role.",
    "4) A 60-second 'tell me about yourself' tailored to this role.",
    "", info.profile, "", jobBlock(j),
  ].join("\n");
}

async function openPromptTool(kind, j, redo = false) {
  let info;
  try { info = await profileInfo(); } catch (e) { toast(`Profil yüklenemedi: ${e.message}`); return; }
  const e = entry(j.id);
  if (kind === "followup") {
    if (e.followup_msg && !redo) return showText(j, "Takip mesajı", e.followup_msg, "followup");
    return promptDialog({
      title: "Takip mesajı", j, placeholder: "KONU: …\n…",
      intro: "Başvurudan ~1 hafta sonra iletişim kişisine ya da İK'ya gönderilecek kısa ve kibar bir takip e-postası.",
      prompt: followupPrompt(j, info),
      onSave: (text) => { saveEntry(j.id, { followup_msg: text }); render(); showText(j, "Takip mesajı", text, "followup"); },
    });
  }
  if (e.interview_prep && !redo) return showText(j, "Mülakat notları", e.interview_prep, "interview");
  return promptDialog({
    title: "Mülakat hazırlığı", j, placeholder: "Claude'un hazırladığı soru-cevaplar…",
    intro: "İlana ve CV'ne göre olası teknik ve davranışsal sorular, STAR örnekleri ve soracağın sorular.",
    prompt: interviewPrompt(j, info),
    onSave: (text) => { saveEntry(j.id, { interview_prep: text }); render(); showText(j, "Mülakat notları", text, "interview"); },
  });
}

async function generateLetter(j) {
  try {
    claudeDialog(j, await profileInfo());   // letters are written with the user's own claude.ai subscription
  } catch (e) {
    toast(`Profil yüklenemedi: ${e.message}`);
  }
}

function openAdd() {
  const sel = (name, obj) => `<select name="${name}">${Object.entries(obj).map(([v, l]) => `<option value="${v}">${esc(l)}</option>`).join("")}</select>`;
  openDialog(`<h2>İlan ekle</h2>
    <p class="hint">Kariyer.net, şirket siteleri, e-posta ile gelen ilanlar… Tarayıcının bulamadığı ilanları buraya ekleyip başvurularınla birlikte takip edebilirsin. Elle eklenen ilanlar otomatik sınıflandırılmaz; şartları aşağıdan seçebilirsin.</p>
    <form class="form" id="add-form">
      <label>Pozisyon *<input name="title" required maxlength="200"></label>
      <div class="grid2">
        <label>Şirket *<input name="company" required maxlength="120"></label>
        <label>Konum<input name="location" maxlength="120" placeholder="İstanbul"></label>
      </div>
      <label>İlan linki<input name="url" type="url" placeholder="https://…"></label>
      <label>İlan metni (ön yazı için yapıştır)<textarea name="description" rows="6" maxlength="12000"></textarea></label>
      <div class="grid2">
        <label>Deneyim şartı${sel("exp", { belirtilmemis: "Belirtilmemiş", iyi: "Yeni mezun / junior", yakin: "1-2 yıl", zor: "3-4 yıl", uzak: "5+ yıl" })}</label>
        <label>Eğitim şartı${sel("edu", { belirtilmemis: "Belirtilmemiş", lisans: "Lisans", lisans_veya_yl: "Lisans veya YL", yl_zorunlu: "YL şartı" })}</label>
        <label>Lokasyon önceliği${sel("loc_tier", { 1: "İstanbul", 2: "Sanayi şehri", 3: "Diğer Türkiye", 4: "Uzaktan", 5: "Yurt dışı" })}</label>
        <label>Çalışma şekli${sel("work_mode", { belirtilmemis: "Belirtilmemiş", ofiste: "Ofiste", hibrit: "Hibrit", uzaktan: "Uzaktan" })}</label>
        <label>Durum<select name="stage">${STAGES.filter(([v]) => v && v !== "gizli").map(([v, l]) => `<option value="${v}">${l}</option>`).join("")}</select></label>
      </div>
      <div class="actions"><button class="btn primary" type="submit">Ekle</button><button class="btn" type="button" data-close>Vazgeç</button></div>
    </form>`);
  $("#add-form").addEventListener("submit", (ev) => {
    ev.preventDefault();
    const f = Object.fromEntries(new FormData(ev.target));
    const id = `manual:${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
    S.manual[id] = { id, title: f.title.trim(), company: f.company.trim(), location: f.location.trim(), url: f.url.trim(),
      description: f.description.trim(), exp: f.exp, edu: f.edu, loc_tier: Number(f.loc_tier), work_mode: f.work_mode,
      added: nowIso(), updated: nowIso() };
    const patch = { stage: f.stage };
    if (f.stage === "basvuruldu") Object.assign(patch, { applied_at: today(), followup_at: nextFollowup() });
    saveEntry(id, patch);
    dlg().close();
    view = "apps";
    render();
    toast("İlan eklendi");
  });
}

function openSettings() {
  openDialog(`<h2>Ayarlar</h2>
    <p class="hint">Başvuru durumların, notların ve elle eklediğin ilanlar bu tarayıcıda saklanır. Telefonla bilgisayar arasında aktarmak için bir cihazda yedeği indir, diğerinde yükle (ikisi birleştirilir, hiçbir şey silinmez).</p>
    <h3>Yedek</h3>
    <div class="actions">
      <button class="btn" data-export>Yedeği indir (.json)</button>
      <label class="btn">Yedek yükle<input type="file" accept="application/json" data-import hidden></label>
    </div>
    <p class="hint">Takipte ${Object.keys(S.entries).length} kayıt, elle eklenmiş ${Object.values(S.manual).filter((m) => !m.deleted).length} ilan var.</p>
    <div class="actions"><button class="btn" data-close>Kapat</button></div>`);
}

// ------------------------------------------------------------------ events
document.addEventListener("click", async (ev) => {
  const t = ev.target.closest("button, [data-go], .stat") || ev.target;
  if (t.matches?.(".seg button")) { view = t.dataset.view; render(); return; }
  if (t.dataset?.go) { view = t.dataset.go; render(); window.scrollTo({ top: $(".bar").offsetTop, behavior: "smooth" }); return; }
  if (t.dataset?.catOnly) {
    const only = F.cats.length === 1 && F.cats[0] === t.dataset.catOnly;
    view = "jobs";
    setFilters({ cats: only ? DEFAULT_FILTERS().cats : [t.dataset.catOnly] });
    window.scrollTo({ top: $(".bar").offsetTop, behavior: "smooth" });
    return;
  }
  if (t.matches?.(".chip")) {
    const box = t.closest(".chips");
    const g = box.dataset.group;
    const v = t.dataset.v;
    if (box.hasAttribute("data-single")) setFilters({ [g]: v });
    else setFilters({ [g]: F[g].includes(v) ? F[g].filter((x) => x !== v) : [...F[g], v] });
    return;
  }
  if (t.id === "freset") { setFilters(DEFAULT_FILTERS()); return; }
  if (t.id === "btn-add") return openAdd();
  if (t.id === "btn-settings" || t.hasAttribute?.("data-open-settings")) return openSettings();
  if (t.hasAttribute?.("data-close") || ev.target === dlg()) { dlg().close(); return; }
  if (t.hasAttribute?.("data-export")) {
    const blob = new Blob([JSON.stringify(S, null, 1)], { type: "application/json" });
    const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: `is-radari-yedek-${today()}.json` });
    a.click();
    URL.revokeObjectURL(a.href);
    return;
  }
  if (t.dataset?.copy) {
    const text = document.getElementById(t.dataset.copy).textContent;
    try { await navigator.clipboard.writeText(text); toast("Kopyalandı ✓"); }
    catch {
      const r = document.createRange();
      r.selectNodeContents(document.getElementById(t.dataset.copy));
      getSelection().removeAllRanges();
      getSelection().addRange(r);
      toast("Metin seçildi - kopyala");
    }
    return;
  }
  if (t.dataset?.redo) {
    const j = allJobs().find((x) => x.id === t.dataset.job);
    dlg().close();
    return openPromptTool(t.dataset.redo, j, true);
  }
  if (t.dataset?.regen) {
    const j = allJobs().find((x) => x.id === t.dataset.regen);
    dlg().close();
    return generateLetter(j);
  }
  const act = t.dataset?.act;
  if (!act || act === "stage" || act === "notes" || act === "contact") return;
  const id = t.closest("[data-id]").dataset.id;
  const j = allJobs().find((x) => x.id === id);
  if (act === "letter") {
    const L = letterOf(j);
    return L ? showLetter(j, L) : generateLetter(j);
  }
  if (act === "followup-msg") return openPromptTool("followup", j);
  if (act === "interview") return openPromptTool("interview", j);
  if (act === "more") { expanded.has(id) ? expanded.delete(id) : expanded.add(id); render(); return; }
  if (act === "note") { openNotes.has(id) ? openNotes.delete(id) : openNotes.add(id); render(); return; }
  if (act === "followed") { saveEntry(id, { followup_at: nextFollowup() }); render(); toast(`${FOLLOWUP_BDAYS} iş günü sonra tekrar hatırlatılacak`); return; }
  if (act === "delete") {
    S.manual[id] = { id, deleted: true, updated: nowIso() };
    saveEntry(id, { stage: "", deleted: true });
    render();
    toast("Silindi");
  }
});

document.addEventListener("change", async (ev) => {
  const t = ev.target;
  if (t.dataset?.act === "stage") {
    const id = t.closest("[data-id]").dataset.id;
    const e = entry(id);
    const patch = { stage: t.value };
    if (["basvuruldu", "mulakat"].includes(t.value) && !e.applied_at) {
      Object.assign(patch, { applied_at: today(), followup_at: nextFollowup() });
    }
    saveEntry(id, patch);
    render();
    if (t.value === "basvuruldu") toast(`Başvurularım'a taşındı - ${FOLLOWUP_BDAYS} iş günü sonra takip hatırlatması`);
    if (t.value === "gizli") toast("Gizlendi - Başvurularım'dan değil, bu listeden kaldırıldı");
  } else if (t.hasAttribute?.("data-import") && t.files[0]) {
    try {
      const imported = JSON.parse(await t.files[0].text());
      S = mergeState(S, imported);
      ls.set(LS_STATE, S);
      render();
      toast("Yedek yüklendi");
    } catch { toast("Dosya okunamadı"); }
  }
});

let noteTimer = null;
document.addEventListener("input", (ev) => {
  const t = ev.target;
  if (t.id === "q") return render();
  if (t.dataset?.act === "notes" || t.dataset?.act === "contact") {
    const id = t.closest("[data-id]").dataset.id;
    const field = t.dataset.act;
    clearTimeout(noteTimer);
    noteTimer = setTimeout(() => saveEntry(id, { [field]: t.value }), 600);
  }
});
$("#sort").addEventListener("change", render);

function renderSkills() {
  const rows = DATA.insights?.skill_gaps || [];
  const el = $("#skills");
  if (!rows.length) { el.innerHTML = `<p class="hint">Henüz yeterli veri yok.</p>`; return; }
  el.innerHTML = `<p class="hint">Son 30 günde Doğrudan uygun / Uygun / Stretch ilanlarda en sık istenen, profilinde görünmeyen araçlar.
    Birini öğrendiğinde <code>config.yaml</code> → <code>profile.skills</code> listesine ekle; ilanlardaki ✗ işaretleri ✓'ye döner.</p>
    <div class="skills">${rows.map((r) => `
      <div class="skill-row">
        <div class="skill-head"><b>${esc(r.label)}</b><span>${r.count} ilan · %${Math.round(r.share * 100)}</span></div>
        <div class="skill-bar"><span style="width:${Math.max(4, Math.round(r.share * 100))}%"></span></div>
        ${(r.resources || []).length ? `<div class="skill-res">${r.resources.map((x) => `<a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.label)}</a>`).join(" · ")}</div>` : ""}
      </div>`).join("")}</div>`;
}

// ------------------------------------------------------------------ boot
async function boot() {
  try {
    DATA = await (await fetch("data.json", { cache: "no-store" })).json();
  } catch {
    $("#sub").textContent = "Tarama verisi yüklenemedi (data.json) - elle eklenen ilanlar yine de çalışır.";
  }
  const jobs = DATA.jobs || [];
  const last = DATA.last_run || {};
  lastDay = jobs.map((j) => (j.first_seen || "").slice(0, 10)).sort().pop() || "";
  if (DATA.generated_at) {
    $("#sub").textContent = `Son tarama: ${new Date(DATA.generated_at).toLocaleString("tr-TR", { dateStyle: "medium", timeStyle: "short" })} · ${last.fetched ?? 0} ilan tarandı, ${last.relevant ?? jobs.length} ilgili · listede ${jobs.length} ilan`;
  }
  const warn = [];
  if (last.failed_sources?.length) warn.push(`Son taramada sonuç vermeyen kaynak: ${last.failed_sources.join(", ")}`);
  if (warn.length) { $("#warn").textContent = warn.join(" · "); $("#warn").hidden = false; }
  $("#runs tbody").innerHTML = (DATA.runs || []).slice().reverse().map((r) => {
    const c = r.by_category || {};
    return `<tr><td>${esc(r.date)}</td><td>${r.fetched ?? "-"}</td><td>${r.new ?? "-"}</td><td>${r.relevant ?? r.candidates ?? "-"}</td><td>${c.dogrudan ?? "-"}</td><td>${c.uygun ?? "-"}</td><td>${c.stretch ?? "-"}</td><td>${c.dusuk ?? "-"}</td><td>${r.scored ?? 0}</td><td>$${(r.cost_usd || 0).toFixed(2)}</td><td>${esc((r.failed_sources || []).join(", ") || "-")}</td></tr>`;
  }).join("");
  renderSkills();
  render();
}
boot();
