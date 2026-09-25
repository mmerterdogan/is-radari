# İş Radarı - Kurulum ve kullanım

**Ne yapar:**
- Her sabah 08:00'de ilanları tarar ve CV'ne göre puanlar.
- En iyi eşleşmeler için ön yazı hazırlar ve Telegram'a özet atar.
- Site üzerinden başvurularını takip edersin: aşamalar, notlar, takip hatırlatması, başka sitelerden elle ilan ekleme, istediğin ilana tek tıkla ön yazı.
- Telefon ve bilgisayar aynı veriyi görür.
- Bilgisayarın kapalı olsa da çalışır.

Kurulum yaklaşık 30 dakika sürer. Adımları sırayla izle.

## 1. GitHub'a yükle (özel repo)

1. github.com'da **Private** yeni bir repo aç (ör. `is-radari`). Repo özel olmalı, çünkü içinde CV'n var.
2. Bu klasörde:
   ```powershell
   git init
   git add .
   git commit -m "İş Radarı"
   git branch -M main
   git remote add origin https://github.com/<kullanıcı-adın>/is-radari.git
   git push -u origin main
   ```

## 2. GitHub gizli anahtarları (günlük tarama için)

Repo → **Settings → Secrets and variables → Actions**

| Tür | Ad | Değer |
|---|---|---|
| Secret (isteğe bağlı) | `ANTHROPIC_API_KEY` | console.anthropic.com → API Keys. Kredi yüklemek gerekir. Eklemezsen aşağıya bak. |
| Secret | `TELEGRAM_TOKEN` | Bülten botunla aynı: `C:\Users\muham\.claude\bulten\.env` |
| Secret | `TELEGRAM_CHAT_ID` | Aynı dosyadan |
| Variable | `SITE_URL` | 3. adımdan sonra sitenin adresi (ör. `https://is-radari.pages.dev`) |

**`ANTHROPIC_API_KEY` isteğe bağlı.** Eklemezsen her şey çalışır. Farkları şunlar: puanlar anahtar kelimeye dayalı olur, ön yazıyı ise site senin Claude aboneliğinle yazdırır. Buton CV'n ve ilanla hazır bir istemi kopyalar ve claude.ai'yi açar; sen yapıştırırsın, gelen cevabı siteye geri yapıştırırsın. Ek ücret yok.

## 3. Siteyi yayınla (Cloudflare Pages, ücretsiz)

1. **Site şifresi üret.** Başvuru takibini ve ön yazı butonunu korur:
   ```powershell
   python -c "import secrets; print(secrets.token_urlsafe(24))"
   ```
2. dash.cloudflare.com → **Storage & Databases → KV → Create** → adı `is-radari`.
3. **Workers & Pages → Create → Pages → Connect to Git** → repoyu seç.
   - Build command: `npm install --omit=dev`
   - Build output directory: `site`
4. Deploy tamamlanınca projenin **Settings** sayfasına git:
   - **Variables and Secrets:** `RADAR_TOKEN` (1. adımdaki şifre) ekle, **Secret** olarak. API kullanacaksan `ANTHROPIC_API_KEY`'i de ekle (isteğe bağlı).
   - **Bindings → KV namespace:** Variable name `RADAR_KV`, namespace `is-radari`.
   - **Runtime → Compatibility date:** bugünün tarihi.
   - Değişikliklerin geçerli olması için **Deployments → Retry deployment** yap.
5. Sitenin adresini (`https://<proje-adı>.pages.dev`) 2. adımdaki `SITE_URL` değişkenine yaz.
6. **Sayfayı kilitle (önerilir).** data.json'da adın ve ilanların var. Cloudflare **Zero Trust → Access → Applications → Add an application → Self-hosted** yolunu izle: domain `<proje-adı>.pages.dev`, policy "Allow" + kendi e-postan. Bundan sonra siteye sadece e-postana gelen kodla girersin.
7. Siteyi aç → ⚙ Ayarlar → şifreyi gir → "☁ senkron" yazmalı. Aynısını telefonda da yap.

## 4. İlk çalıştırma

Repo → **Actions → Günlük tarama → Run workflow**. İlk çalıştırmada "kaç saat geriye" kutusuna **168** yaz; böylece son 7 günün ilanlarıyla dolu bir havuzla başlarsın. 15-25 dakika sürer. Bittiğinde Telegram'a mesaj gelir, site birkaç dakika içinde güncellenir. Sonrasında her gün 08:00'de kendiliğinden çalışır.

## İlanlar nasıl eşleştiriliyor?

Sistem şu soruya cevap arar: *"Lisans diplomam, devam eden YL'm, teknik becerilerim ve projelerimle hangi ilanlara gerçekçi olarak başvurabilirim?"* Eğitim seviyesi **hiçbir zaman** ilanı gizlemez. Her ilan 4 kategoriden birine girer:

| Kategori | Ne demek |
|---|---|
| 🟢 **Doğrudan uygun** | Deneyim şartı yeni mezuna uygun (ya da yok), lisans kabul ediliyor, pozisyon alanı ve istenen araçlar profilinle açıkça örtüşüyor |
| 🔵 **Uygun** | Deneyim ve eğitim şartı uygun, alan makine mühendisliğiyle kesişiyor; bazı eksikler olabilir |
| 🟡 **Stretch** | 1-4 yıl deneyim isteniyor ama teknik örtüşme güçlü; ya da YL derecesi / doktora pozisyonu gibi biraz üstte şartlar var |
| ⚪ **Düşük uygunluk** | 5+ yıl / kıdemli, doktora derecesi, farklı bölüm veya bilmediğin bir dil gibi temel bir uyumsuzluk var. Varsayılan olarak gizli; filtreden açılır. |

Her ilan kartında şunlar görünür:
- şirket, pozisyon ve lokasyon (öncelik etiketiyle: İstanbul > Sanayi şehri > Türkiye > Uzaktan > Yurt dışı)
- çalışma şekli, deneyim şartı, eğitim şartı (bölüm uyumuyla), ilan tarihi
- kategorinin gerekçeleri
- ana gereksinimler: ✓ profilinde var / ✗ profilinde görünmüyor

Lokasyon kategoriyi değiştirmez, sadece gösterilir ve sıralamada kullanılır.

**Claude API olmadan** bu değerlendirme kural tabanlıdır: ilan metnindeki "Bachelor's", "0-2 years", "yeni mezun", "tercih sebebi", "hybrid" gibi kalıplardan çıkarılır (`radar/match.py`). **API varsa** Claude en umut verici 40 ilanı yeniden değerlendirir ve gerekçeleri iyileştirir.

## Siteyi kullanmak

| Ne | Nasıl |
|---|---|
| İlanlar | Varsayılan: Doğrudan uygun + Uygun + Stretch, uygunluğa göre sıralı. Üstteki kategori kartlarına tıklayınca sadece o kategori görünür (tekrar tıklayınca geri döner). |
| Filtreler | Uygunluk, lokasyon, deneyim şartı, eğitim şartı, çalışma şekli, alan (CAE, tasarım, Ar-Ge, eklemeli, üretim, test, otomotiv…), ilan tarihi, staj. Seçim yapılmayan grup "hepsi" demektir. Filtreler cihazda hatırlanır; "Filtreleri sıfırla" varsayılana döner. |
| Sıralama | Uygunluğa göre / En yeni / Lokasyon önceliği |
| Başvuru takibi | Karttaki açılır menü: Kaydedildi → Başvuruldu → Mülakat → Teklif / Olumsuz. "Başvuruldu" dediğin ilan **Başvurularım**'a taşınır. |
| Takip hatırlatması | Başvurunun üzerinden 10 gün geçince **Takip zamanı** olarak işaretlenir. "Takip ettim" butonu hatırlatmayı 10 gün öteler. |
| Not | Görüşülen kişi, maaş, mülakat tarihi… Aramaya da dahil. |
| Ön yazı | **API varsa:** sabah hazır gelenler "Ön yazı" butonunda, diğer ilanlarda **Ön yazı oluştur** (~30 sn). **API yoksa:** "Ön yazı oluştur" CV'n, ilan ve uygunluk analiziyle hazır bir istem kopyalar ve claude.ai'yi açar; cevabı siteye yapıştırıp kaydedersin. |
| Başka sitelerden ilan | **+ İlan ekle**: Kariyer.net, şirket sitesi, e-posta… Elle eklenen ilanlar otomatik sınıflandırılmaz; deneyim, eğitim, lokasyon ve çalışma şeklini formda seçebilirsin. |
| İstemediğin ilan | "İlgilenmiyorum": listeden gizlenir |
| Yedek | ⚙ Ayarlar → Yedeği indir / yükle |

## Ayarlar (`config.yaml`)

- `profile.skills`: profilindeki beceriler. İlanlardaki eşleşen araçlar ✓ olarak görünür. Yeni bir araç öğrendiğinde (ör. `catia`, `abaqus`, `python`) listeye ekle. Anahtarların tamamı `radar/match.py` > `SKILLS` içinde.
- `profile.preferences`: tercihlerin. Claude (API varsa) değerlendirme ve ön yazıda bunu okur.
- `search.linkedin.queries`: arama kelimeleri, konumlar, sayfa sayısı (`pages`) ve deneyim filtresi (`experience`).
- `search.greenhouse.boards`: takip ettiğin şirketlerin Greenhouse kariyer panoları.
- `match.enrich_limit`: günde tam metni çekilecek LinkedIn ilanı sayısı. Eğitim ve deneyim şartını okuyabilmek için gerekiyor; artırırsan tarama uzar.
- `scoring.max_llm_jobs` / `letters_per_day`: Claude'un günlük değerlendireceği ilan ve yazacağı ön yazı sayısı.
- `notify.top_direct` / `top_fit` / `top_stretch`: Telegram mesajında kategori başına gösterilecek ilan sayısı.

Kuralları veya profili değiştirdikten sonra mevcut ilanları yeniden sınıflandırmak için: `python -m radar rebuild`.

**Neyin elendiğini görmek için:** her taramada, alakasız bulunup elenen ilanlar sebepleriyle birlikte `data/dropped_last.json` dosyasına yazılır ("mühendislik dışı pozisyon", "başka mühendislik disiplini", "makine mühendisliği alanıyla bağlantı bulunamadı"…). Yanlışlıkla elenen bir ilan tipi görürsen haber ver, kural güncellenir.

CV'n değişince `cv/cv.md` dosyasını da güncelle. Bir sonraki taramada Claude ve ön yazılar yeni CV'yi kullanır.

## Maliyet

| Kalem | Tahmini |
|---|---|
| GitHub Actions (özel repo) | Ücretsiz (günde ~20 dk, aylık 2000 dk kota) |
| Cloudflare Pages + KV + Access | Ücretsiz |
| Claude API (isteğe bağlı): sabah taraması (`claude-opus-5`, ≤ 40 ilan + 3 ön yazı) | Günde ~$0.3-0.5 |
| Claude API (isteğe bağlı): sitede istenen ön yazı | Yazı başına ~$0.03-0.05 |

API'siz toplam maliyet: **$0**. API ile aylık ~$10-20. Gerçek sabah harcaması sitenin altındaki "Tarama geçmişi"nde görünür. Daha ucuz istersen `config.yaml` → `scoring.model` değerini `claude-sonnet-5` yap (yaklaşık %60 daha ucuz), sonra `price_input: 2`, `price_output: 10` gir. Puanlama kalitesi biraz düşebilir.

## Kaynaklar ve sınırlar

- **LinkedIn:** Giriş yapmadan, herkese açık ilan araması. Hesabın hiç kullanılmıyor, yani kapanma riski yok. LinkedIn otomatik erişimi hoş karşılamıyor ve bazen 429 (çok fazla istek) döndürüyor; o gün atlanır, site ve Telegram uyarı gösterir. İstemezsen `search.linkedin.enabled: false` yap.
- **EURAXESS:** Avrupa Komisyonu'nun araştırma, doktora ve postdoc portalı.
- **Greenhouse:** Şirketlerin resmi, herkese açık kariyer API'si.
- **Kariyer.net, Indeed, AcademicPositions, FindAPhD:** Bot koruması olduğu için taranmıyor. Oralardan bulduğun ilanları "+ İlan ekle" ile ekle.
- **Ön yazılar** CV'ndeki bilgilere dayanır ama göndermeden önce mutlaka oku.

## Yerel geliştirme (isteğe bağlı)

```powershell
pip install -r requirements.txt; npm install
python -m radar run --no-notify          # tarama (ANTHROPIC_API_KEY .env'de ise Claude ile)
npm run dev                              # site + API: http://127.0.0.1:8788 (şifre: yerel-test)
python -m pytest tests -q; npm test      # testler
```
