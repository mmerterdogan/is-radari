# İş Radarı - Kurulum ve kullanım

**Ne yapar:**
- Her sabah 08:00'de ilanları tarar ve CV'ne göre sınıflandırır.
- Telegram'a özet atar.
- Siteyi günceller: **https://mmerterdogan.github.io/is-radari/**
- Site üzerinden başvurularını takip edersin: aşamalar, notlar, takip hatırlatması, başka sitelerden elle ilan ekleme, istediğin ilana ön yazı.
- Her şey GitHub'da çalışır, bilgisayarın kapalı olsa da. Ücretsiz.

## Kurulum (bir kerelik)

1. **Repo açık (public) olmalı.** GitHub'ın ücretsiz planında site sadece açık repodan yayınlanır. Repo → **Settings → General → Danger Zone → Change visibility → Public**. Repoda telefon ya da e-posta yok. CV'nin içeriği (eğitim, staj, projeler) ve taranan ilanlar herkese görünür olur. Başvuru durumların ve notların repoda değil, tarayıcında durur.
2. **Siteyi aç.** Repo → **Settings → Pages → Build and deployment → Source: GitHub Actions**.
3. **Telegram:** Repo → **Settings → Secrets and variables → Actions** → `TELEGRAM_TOKEN` ve `TELEGRAM_CHAT_ID` secret'ları. Değerler bülten botundaki gibi.
4. **İlk yayın:** Repo → **Actions → Siteyi yayınla → Run workflow**. 1-2 dakika sonra site adresi açılır.
5. **İlk tarama (isteğe bağlı):** **Actions → Günlük tarama → Run workflow**. "Kaç saat geriye" kutusuna 168 yazarsan son 7 günün ilanlarıyla başlarsın. Bittiğinde siteyi de kendisi yayınlar.

**Claude API (isteğe bağlı):** `ANTHROPIC_API_KEY` secret'ını eklersen sabah taramasında Claude en umut verici 40 ilanı ayrıca değerlendirir ve 3 ön yazı yazar (ayda ~$10-20). Eklemezsen kural tabanlı eşleştirme kullanılır. Sitedeki ön yazı butonu her durumda senin Claude aboneliğinle çalışır.

## İlanlar nasıl eşleştiriliyor?

Sistem şu soruya cevap arar: *"Lisans diplomam, devam eden YL'm, teknik becerilerim ve projelerimle hangi ilanlara gerçekçi olarak başvurabilirim?"* Eğitim seviyesi **hiçbir zaman** ilanı gizlemez. Her ilan 4 kategoriden birine girer:

| Kategori | Ne demek |
|---|---|
| 🟢 **Doğrudan uygun** | Deneyim şartı yeni mezuna uygun (ya da yok), lisans kabul ediliyor, pozisyon alanı ve istenen araçlar profilinle açıkça örtüşüyor |
| 🔵 **Uygun** | Deneyim ve eğitim şartı uygun, alan makine mühendisliğiyle kesişiyor; bazı eksikler olabilir |
| 🟡 **Stretch** | 1-4 yıl deneyim isteniyor ama teknik örtüşme güçlü; ya da YL derecesi / doktora pozisyonu gibi biraz üstte şartlar var |
| ❔ **Değerlendirilemedi** | İlanın metni okunamadı (LinkedIn bazen engelliyor), şartlar bilinmiyor. Gerekçede başlığa göre tahmin yazar; sonraki taramalarda metin gelirse otomatik sınıflanır. |
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
| İlanlar | Varsayılan: Doğrudan uygun + Uygun + Stretch + Değerlendirilemedi, uygunluğa göre sıralı. Üstteki kategori kartlarına tıklayınca sadece o kategori görünür (tekrar tıklayınca geri döner). |
| Filtreler | Uygunluk, lokasyon, deneyim şartı, eğitim şartı, çalışma şekli, alan (CAE, tasarım, Ar-Ge, eklemeli, üretim, test, otomotiv…), ilan tarihi, staj. Seçim yapılmayan grup "hepsi" demektir. Filtreler cihazda hatırlanır; "Filtreleri sıfırla" varsayılana döner. |
| Sıralama | Uygunluğa göre / En yeni / Lokasyon önceliği |
| Başvuru takibi | Karttaki açılır menü: Kaydedildi → Başvuruldu → Mülakat → Teklif / Olumsuz. "Başvuruldu" dediğin ilan **Başvurularım**'a taşınır. |
| Takip hatırlatması | Başvurudan 6 iş günü sonra **Takip zamanı** olarak işaretlenir. "Takip ettim" butonu hatırlatmayı 6 iş günü öteler. |
| Takip mesajı | "Başvuruldu" durumundaki ilanda **Takip mesajı yaz**: kısa, kibar bir takip e-postası istemi (claude.ai). Kaydedilen metin kartta saklanır. |
| Mülakat hazırlığı | "Mülakat" durumunda **Mülakat hazırlığı**: ilana ve CV'ne göre olası teknik/davranışsal sorular, STAR örnekleri, soracağın sorular. |
| Not ve iletişim kişisi | "Not" altında iletişim kişisi (ad, unvan) ve serbest not. İkisi de aramaya dahil. |
| Bağlantı kur | Her kartta LinkedIn'de o şirketteki İÜC mezunlarını, mühendisleri ve İK'yı arayan hazır linkler. Yönlendirmeli başvuru için. |
| Beceri yol haritası | Sayfanın altında: son 30 günde uygun ilanların en çok istediği, profilinde görünmeyen araçlar (yüzdeyle) ve ücretsiz öğrenme kaynakları. Kaynaklar `config.yaml > learning`'de. |
| Ön yazı | **Ön yazı oluştur**: CV'n, ilan ve uygunluk analiziyle hazır bir istem kopyalar ve claude.ai'yi açar; cevabı siteye yapıştırıp kaydedersin. API ekliysen sabah hazırlanan ön yazılar da "Ön yazı" butonunda görünür. |
| Başka sitelerden ilan | **+ İlan ekle**: Kariyer.net, şirket sitesi, e-posta… Elle eklenen ilanlar otomatik sınıflandırılmaz; deneyim, eğitim, lokasyon ve çalışma şeklini formda seçebilirsin. |
| İstemediğin ilan | "İlgilenmiyorum": listeden gizlenir |
| Telefon ↔ bilgisayar | Takip verisi her tarayıcıda ayrı saklanır. Aktarmak için bir cihazda ⚙ Ayarlar → **Yedeği indir**, diğerinde **Yedek yükle** (ikisi birleştirilir). |

## Ayarlar (`config.yaml`)

- `profile.skills`: profilindeki beceriler. İlanlardaki eşleşen araçlar ✓ olarak görünür. Yeni bir araç öğrendiğinde (ör. `catia`, `abaqus`, `python`) listeye ekle. Anahtarların tamamı `radar/match.py` > `SKILLS` içinde.
- `profile.preferences`: tercihlerin. Claude (API varsa) değerlendirme ve ön yazıda bunu okur.
- `search.linkedin.queries`: arama kelimeleri, konumlar, sayfa sayısı (`pages`) ve deneyim filtresi (`experience`).
- `search.greenhouse.boards`: takip ettiğin şirketlerin Greenhouse kariyer panoları.
- `match.enrich_limit`: günde tam metni çekilecek LinkedIn ilanı sayısı. Eğitim ve deneyim şartını okuyabilmek için gerekiyor; artırırsan tarama uzar.
- `scoring.max_llm_jobs` / `letters_per_day`: Claude'un günlük değerlendireceği ilan ve yazacağı ön yazı sayısı.
- `notify.top_direct` / `top_fit` / `top_stretch`: Telegram mesajında kategori başına gösterilecek ilan sayısı.

Kuralları veya profili değiştirdikten sonra mevcut ilanları yeniden sınıflandırmak için: `python -m radar rebuild`.

**Hangi arama işe yarıyor:** `data/query_stats.json` her LinkedIn sorgusunun getirdiği yeni ilan sayısını ve bunların kaçının uygun çıktığını biriktirir. Verimi düşük sorguları `config.yaml`'dan çıkarabilirsin.

**Neyin elendiğini görmek için:** her taramada, alakasız bulunup elenen ilanlar sebepleriyle birlikte `data/dropped_last.json` dosyasına yazılır ("mühendislik dışı pozisyon", "başka mühendislik disiplini", "makine mühendisliği alanıyla bağlantı bulunamadı"…). Yanlışlıkla elenen bir ilan tipi görürsen haber ver, kural güncellenir.

CV'n değişince `cv/cv.md` dosyasını da güncelle. Bir sonraki taramada Claude ve ön yazılar yeni CV'yi kullanır.

## Maliyet

| Kalem | Tahmini |
|---|---|
| GitHub Actions + GitHub Pages (açık repo) | Ücretsiz |
| Claude API (isteğe bağlı): sabah taraması (`claude-opus-5`, ≤ 40 ilan + 3 ön yazı) | Günde ~$0.3-0.5 |

API'siz toplam maliyet: **$0**. API ile aylık ~$10-20. Gerçek sabah harcaması sitenin altındaki "Tarama geçmişi"nde görünür. Daha ucuz istersen `config.yaml` → `scoring.model` değerini `claude-sonnet-5` yap (yaklaşık %60 daha ucuz), sonra `price_input: 2`, `price_output: 10` gir. Puanlama kalitesi biraz düşebilir.

## Kaynaklar ve sınırlar

- **LinkedIn:** Giriş yapmadan, herkese açık ilan araması. Hesabın hiç kullanılmıyor, yani kapanma riski yok. LinkedIn otomatik erişimi hoş karşılamıyor ve bazen 429 (çok fazla istek) döndürüyor; o gün atlanır, site ve Telegram uyarı gösterir. İstemezsen `search.linkedin.enabled: false` yap.
- **EURAXESS:** Avrupa Komisyonu'nun araştırma, doktora ve postdoc portalı.
- **Greenhouse:** Şirketlerin resmi, herkese açık kariyer API'si.
- **SmartRecruiters:** Şirketlerin resmi, herkese açık kariyer API'si (şimdilik Bosch Türkiye; `config.yaml > search.smartrecruiters.companies`'e yeni şirket eklenebilir).
- **Kapanmış ilanlar:** 5 günden eski umut verici ilanlar her gün yeniden kontrol edilir; "artık başvuru kabul etmiyor" olanlar üstü çizili görünür ve varsayılan olarak gizlenir (takibe aldıkların gizlenmez). Kartlarda LinkedIn başvuru sayısı da görünür.
- **Hata alarmı:** Tarama ya da site yayını başarısız olursa Telegram'a uyarı gelir.
- **Kariyer.net, Indeed, AcademicPositions, FindAPhD:** Bot koruması olduğu için taranmıyor. Oralardan bulduğun ilanları "+ İlan ekle" ile ekle.
- **Ön yazılar** CV'ndeki bilgilere dayanır ama göndermeden önce mutlaka oku.

## Yerel geliştirme (isteğe bağlı)

```powershell
pip install -r requirements.txt
python -m radar run --no-notify          # tarama (ANTHROPIC_API_KEY .env'de ise Claude ile)
npm run dev                              # site: http://127.0.0.1:8788
python -m pytest tests -q; npm test      # testler
```
