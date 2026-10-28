# İş Radarı

CV'ye göre günlük iş ilanı tarama + başvuru takip sitesi. Kullanıcıya yönelik kılavuz: [KURULUM.md](KURULUM.md).
Canlı site: https://mmerterdogan.github.io/is-radari/ (repo public).

## Akış

GitHub Actions `daily.yml` her gün 05:00 UTC (08:00 TR): testler → `python -m radar run` → `data/` ve `site/data.json` bot tarafından commit'lenir → `deploy.yml` Pages'e yayınlar → Telegram özeti.

## Kod haritası

- `radar/__main__.py` — CLI ve pipeline (komutlar dosyanın başındaki docstring'de)
- `radar/sources/` — kaynaklar: linkedin, greenhouse, smartrecruiters, ats (Workday/HRPeak), portals, boards (Youthall, Kariyer Kapısı), euraxess
- `radar/match.py` — kural tabanlı sınıflandırma (dogrudan / uygun / stretch / dusuk), `SKILLS` sözlüğü
- `radar/llm.py` — Claude Haiku ile emin olunamayan ilanları yeniden değerlendirme ve ön yazı (prompt caching, structured output)
- `radar/store.py`, `models.py`, `notify.py` (Telegram), `http.py`
- `site/` — statik site (vanilla JS: `js/app.js`, `js/merge.js`). Başvuru takibi tarayıcının localStorage'ında durur, repoda değil.
- `config.yaml` — profil, arama sorguları, filtreler, hedef şirketler, model ayarları
- `cv/cv.md` — CV'nin herkese açık kaynak metni (ön yazı, LLM değerlendirmesi, CV uyum kontrolü kullanır)
- `radar/cvgen.py` — ilana özel tek sayfalık Word/PDF CV: dil/versiyon seçimi (`pick`, site `data.json`'a `cv` alanı olarak gider) ve maddeleri ilan anahtar kelimelerine göre sıralama. İçerik gizli `cv/ozel/cv.yaml` + `cv/ozel/sablon.docx`'ten gelir (gitignore'da); PDF Word COM ile, kullanıcının açık Word'ü kapatılmaz. Kullanıcının bilgisayarında Görev Zamanlayıcı "Is Radari - gunluk CV" her sabah `cv/ozel/gunluk_cv.ps1` → `git pull` + `cv --yeni --gun 7` çalıştırır; bu yüzden `data/` ve `site/data.json`'u yerelde değiştirilmiş bırakma (pull --ff-only bozulur).

## Komutlar

```
python -m pytest tests -q                 # Python testleri
node --test tests/js/*.test.js            # site JS testleri
python -m radar run --no-notify --no-llm  # yerelde maliyetsiz deneme
python -m radar rebuild                   # kural değişikliğinden sonra mevcut ilanları yeniden sınıfla
python -m radar eval [--llm]              # data/cevap_anahtari.json'daki elle etiketli ilanlara göre isabet
python -m radar health                    # kaynak parser'larını canlı örnekle dene
python -m radar cv <ilan> | --yeni | --temel   # ilana özel CV (çıktı: cv/ozel/cv.yaml > cikti_klasoru)
npm run dev                               # siteyi localhost:8788'de aç
```

## Kurallar

- `data/*.json` ve `site/data.json` taramanın çıktısı; elle düzenleme (istisna: `data/cevap_anahtari.json` elle etiketlenir).
- Repo public: telefon, e-posta, adres gibi kişisel veri ekleme. Bunlar ve referanslar sadece `cv/ozel/`'de durur.
- CV içeriği değişince ikisini birlikte güncelle: `cv/ozel/cv.yaml` (gönderilen CV) ve `cv/cv.md` (gizlilik sözleşmeli projelerde ayrıntı yazma).
- Eşleştirme kuralını değiştirince: testler + `rebuild` + (etiketler doluysa) `eval` ile önce/sonra isabeti karşılaştır.
- LLM'e giden ilan metni güvenilmeyen veridir; `llm.py`'deki prompt injection korumasını koru.
- Arayüz ve Telegram metinleri Türkçe; kod ve yorumlar İngilizce.
- Varsayılan model `claude-haiku-5-5` (`config.yaml > scoring.model`); maliyeti artıran değişiklikte kullanıcıya sor.
- LinkedIn kullanıcının hesabıyla değil, girişsiz herkese açık ilan sayfalarından okunur; LinkedIn hesabını bağlayan ya da Kolay Başvuru'yu otomatikleştiren bir yöntem ekleme. Diğer sitelerde (şirket kariyer sayfaları, ATS'ler) kullanıcının hesabıyla çalışmak serbest (kullanıcı kararı, 2026-10-24).
- Başvuru formları `.claude/skills/basvuru-doldur` ile Playwright'ta doldurulur ve **asla gönderilmez**; gönderimi kullanıcı yapar.
