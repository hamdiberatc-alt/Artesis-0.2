# Arte Terapi — Vercel bulut sürümü 3.14.0

Danışan, pilates paketleri, kişi bazlı ödemeler, haftalık program, ölçümler ve raporlar için Vercel + Turso **libSQL** sürümü. Python 3.12+ kullanır; ek Python paketi gerekmez.

Bu paket kaynak kodudur. Vercel/Turso hesabınıza otomatik bağlanmaz veya yayın yapmaz. Canlı hesapta bağlantı, plan limitleri ve gecikme doğrulaması sizin kurulumunuzda tamamlanır.

## 1. Kalıcı veritabanını oluşturun

[Turso](https://turso.tech/) hesabınızda bu uygulama için **boş bir libSQL veritabanı** oluşturun. Mevcut kayıtlarınızı taşıyacaksanız önce aşağıdaki “Mevcut kayıtları aktarma” bölümünü izleyin.

- Mümkünse Frankfurt/Avrupa bölgesi seçin. Vercel işlevi `fra1` bölgesine ayarlanmıştır. Yakın bölgeler işlem gecikmesini azaltır.
- Veritabanının **Database URL** adresini alın (`libsql://…turso.io` veya `https://…turso.io`).
- Bu veritabanı için **okuma ve yazma yetkili Database Auth Token** oluşturun. Organizasyon yönetim API anahtarını kullanmayın.
- Adresi ve anahtarı Vercel ayarlarına gireceksiniz; kaynak koda, GitHub'a veya sohbete yazmayın.

## 2. GitHub'daki dosyaları güncelleyin

ZIP'i bilgisayarınızda açın. İçindeki `arte-terapi-vercel` klasörünün **içeriğini** deponun ana dizinine yükleyin. `app.py`, `vercel.json`, `api`, `cloud` ve `web` aynı seviyede olmalı. Yalnız `.py` dosyasını yüklemek yeterli değildir.

Özellikle şu dosyaları kontrol edin:

- `api/index.py`
- `cloud/db.py`, `cloud/runtime.py`, `cloud/seed.sql`
- `web/index.html`
- `app.py`, `requirements.txt`, `vercel.json`, `.python-version`
- `tests/` ve `.github/workflows/test.yml`

Önceden GitHub'ın şablonundan oluşturduğunuz `.github/workflows/python-app.yml` yerine paketteki `test.yml` iş akışını kullanın; aynı işi yapan eski şablonu kaldırın. Depo ana dizininde eski Vercel yönlendirme ayarları varsa paketteki `vercel.json` ile değiştirin. Bu dosya tek giriş noktasını açıkça tanımlar.

## 3. Vercel ortam değişkenlerini ekleyin

Vercel projenizde **Settings → Environment Variables** bölümüne aşağıdaki üç değeri ekleyin. En az **Production** ortamını seçin.

| Ad | Değer |
| --- | --- |
| `TURSO_DATABASE_URL` | Turso'dan aldığınız veritabanı adresi |
| `TURSO_AUTH_TOKEN` | O veritabanının okuma/yazma erişim anahtarı |
| `ARTE_ADMIN_PASSWORD` | Kendiniz belirlediğiniz en az 16 karakterli güçlü yönetici parolası |

`ARTE_ADMIN_PASSWORD` boş veritabanındaki **ilk giriş parolasını** oluşturur. Daha sonra uygulamadaki Ayarlar'dan değiştirilen parolayı yeniden dağıtım sırasında ezmez. Değişkeni silmeyin; başlangıç doğrulaması için gereklidir. Gerekirse gerçek parola sıfırlama aracı aşağıdadır.

Preview ortamına gerçek klinik veritabanının anahtarlarını eklemeyin. Önizleme gerekiyorsa ayrı bir test veritabanı ve ayrı parola kullanın.

## 4. Yeniden dağıtın

- Root Directory: `app.py` ve `vercel.json` bulunan proje kökü.
- Framework Preset: **Other**.
- Önceden girdiğiniz özel Build Command / Output Directory ayarlarını temizleyin; yönlendirme ve Python girişi `vercel.json` tarafından yönetilir.
- **Deployments → Redeploy** ile yeni dosyaları ve ortam değişkenlerini kullanarak dağıtın.
- Siteyi açın; ilk istek boş veritabanını oluşturur. Girişte `ARTE_ADMIN_PASSWORD` değerini kullanın.

Telefondan aynı HTTPS adresini açabilirsiniz. Bilgisayarın açık kalması veya aynı Wi-Fi ağına bağlanmak gerekmez.

Başlangıçta 503 görülürse önce üç değişkenin Production'a kaydedildiğini, veritabanının boş/libSQL uyumlu olduğunu, anahtarın geçerli ve yazmaya yetkili olduğunu kontrol edin. Dolu fakat farklı şemalı veritabanı korunur; otomatik olarak silinmez.

## 5. İlk kullanım kontrolü

Gerçek kayıtlardan önce yapay bir danışanla:

1. Danışan, iki günlük haftalık program ve pilates paketi oluşturun.
2. Kişiye ödeme, katılım, ölçüm ve küçük bir PDF ekleyin.
3. Çıkış yapıp telefondan giriş yapın; aynı verileri görün.
4. Vercel'i yeniden dağıtın; kayıtların ve PDF'nin kaldığını kontrol edin.
5. Aşağıdaki araçla yedek alın; program, paket bakiyesi ve gelir raporunu kontrol edin.

## Yedekleme

Vercel'in yanıt boyutu/süre limitlerine takılmamak için büyük tam yedekler sunucu işlevinden indirilmez. Bilgisayarınızda Python 3.12+ kurulu iken proje klasöründe çalıştırın:

```bash
python scripts/cloud_admin.py backup yedek-2026-09-30.zip
```

Araç veritabanı adresini ve erişim anahtarını sorar; anahtar gizli girilir. `/dump` ile veritabanı anlık görüntüsünü alır, SQLite dosyası ile PDF raporlarını birlikte ZIP'e koyar. Var olan yedeği ezmez. Yedeğin içinde aktif yönetici oturumları temizlenir.

Uygulamadaki **Yedekleme** düğmesi bu komutun açıklamasını açar. Bu sürüm kendiliğinden zamanlanmış yedek oluşturmaz; düzenli tam yedek alın. Sağlayıcının kurtarma seçeneklerini ayrıca hesabınızdan kontrol edin.

## Mevcut kayıtları aktarma

Yerel kayıtlar otomatik olarak internete gönderilmez. Eski uygulamadan **tam ZIP yedeği** alın; hem veritabanı hem PDF dosyaları bulunmalıdır.

1. Mevcut dosyalara dokunmadan bir aktarım SQL'i hazırlayın:

```bash
python scripts/cloud_admin.py prepare-import eski-yedek.zip buluta-aktar.sql
```

Araç yeni bir bulut yönetici parolası sorar. Şema geçişlerini yedeğin kopyasında yapar; PDF dosyaları eksikse veya bağlantılı kayıtlar bozuksa durur. Kişi/paket/ödeme kimlikleri korunur, aktif yönetici oturumları sıfırlanır. Eski rapor dosyaları veritabanındaki kalıcı PDF parçalarına dönüştürülür.

2. [Turso CLI kurulumunu](https://docs.turso.tech/cli/installation) tamamlayıp kendi hesabınızda oturum açın. SQL'den **yeni bir veritabanı** oluşturun:

```bash
turso db create arte-terapi-aktarim --from-dump ./buluta-aktar.sql
```

3. Bu yeni veritabanının URL ve token değerlerini Vercel'e girin. `ARTE_ADMIN_PASSWORD` olarak aktarım sırasında seçtiğiniz parolayı girip yeniden dağıtın.
4. Kayıtları ve bakiyeleri karşılaştırın. Eski uygulamadaki yedeği doğrulama bitene kadar saklayın. Aktarımdan sonra iki sistem bağımsızdır; aynı anda iki tarafa kayıt girmeyin.

`buluta-aktar.sql` kişisel sağlık/ödeme kayıtları içerir. GitHub'a yüklemeyin; `.gitignore` yalnız kaynak `cloud/seed.sql` dosyasına izin verir. Tarayıcıdan elle dosya yüklerken `.gitignore` bir güvenlik filtresi değildir.

## Parola sıfırlama

Normalde uygulamanın Ayarlar bölümünü kullanın. Giriş parolası unutulursa:

```bash
python scripts/cloud_admin.py reset-password
```

Araç Turso bilgilerini ve yeni parolayı gizli olarak ister; tüm açık yönetici oturumlarını kapatır. Yalnız Vercel ortam değişkenini değiştirmek mevcut parolayı sıfırlamaz.

## Yerel çalışma

```bash
python app.py
```

`ARTE_CLOUD` ve `VERCEL` değişkenleri ayarlı değilse önceki yerel SQLite modu çalışır. Standart veri konumu Windows'ta `%APPDATA%\ArteTerapi`, diğer sistemlerde `~/.arteterapi` olarak korunur. Yerel ve bulut veritabanları otomatik eşitlenmez.

## Teknik düzen

- Vercel girişi `api/index.py` içindeki `handler` sınıfıdır. Import sırasında dinleyen sunucu başlatılmaz veya veri klasörü açılmaz.
- İş kuralları ve SQL sorguları `app.py` içindedir; uzak bağlantı Hrana HTTP v2 protokolünü kullanır.
- Her işlem kendi bağlantısını kullanır. Çok adımlı kayıtlar tek uzak transaction/baton üzerinde commit veya rollback yapar. TLS bağlantısı işlem boyunca yeniden kullanılır.
- Belirsiz ağ hatalarında yazma işlemi otomatik tekrarlanmaz. Kullanıcı son kaydı kontrol etmelidir; kayıt+program akışının işlem anahtarı korunmuştur.
- Oturumlar ve giriş denemesi sınırları kalıcı veritabanındadır. Çerezler `Secure`, `HttpOnly`, `SameSite=Strict` kullanır; yazma isteklerinde CSRF kontrolü sürer.
- Bulutta herkese açık ilk parola oluşturma yolu kapalıdır. İlk parola yalnız sunucu ortam değişkeninden hash'lenir.
- PDF'ler veritabanında 256 KB parçalar olarak saklanır. Yeni PDF yükleme sınırı **2 MB**, JSON istek sınırı **3 MB**'dır. Eski daha büyük raporların aktarımı korunur ancak Vercel yanıt sınırını aşan raporları yedekten açmak gerekebilir.
- Bulut tarihi `Europe/Istanbul` saat dilimini kullanır.
- Bulut şeması yalnız boş hedefte oluşturulur. Bilinmeyen/daha yeni bulut şeması otomatik değiştirilmez.
- Bu sürüm tek ortak yönetici hesabını korur; ayrı personel yetkilendirme sistemi eklenmemiştir.

Turso belgelerinde etkileşimli transaction süresi 5 saniye olarak belirtilir. Veritabanını uygulamaya yakın bölgede tutun. Gerçek ağ koşullarında uzun toplu kayıtlar süre sınırına ulaşırsa işlem geri alınır; limitleri ve performansı canlı testte kontrol edin. Büyük eski veri aktarımları bu nedenle tek tek uygulama API'siyle değil sağlayıcının dump aktarımıyla yapılır.

## Testler

```bash
python -m unittest discover -s tests -v
node tests/test_ui.cjs
```

Yerel iş kuralları ve aynı kuralların bulut bağlantısı üzerinden regresyon testleri, yeniden başlayan uygulama örneğinde kalıcılık, PDF/yedekleme, yetkisiz erişim, CSRF ve rollback testleri bulunur. Bulut testleri yerel bir Hrana protokol simülatörü kullanır; gerçek Turso hesabı, gerçek Vercel dağıtımı ve mobil tarayıcı testi yerine geçmez.

## Resmî başvuru kaynakları

- https://vercel.com/docs/functions/runtimes/python
- https://vercel.com/docs/project-configuration/vercel-json
- https://docs.turso.tech/sdk/http/reference
- https://docs.turso.tech/cli/db/create

Bir açık kaynak lisansı eklenmemiştir; kullanım/paylaşım koşullarını depo sahibi belirlemelidir.
