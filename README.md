# Canlı Türkçe Altyazı

Ekrandaki İngilizce altyazıyı okur (OCR), bilgisayarda Türkçeye çevirir ve görüntünün üstüne yazar. Filmlerde, dizilerde, videolarda, bilgisayar oyunlarında ve capture card + OBS ile konsol oyunlarında çalışır. İsteğe bağlı olarak Türkçe seslendirme de yapar; bu özellik henüz geliştirme aşamasındadır.

- **Microsoft Store:** "Canlı Türkçe Altyazı" (Appic Studio), ücretsiz.
- **Lisans:** [GNU AGPL-3.0](LICENSE) (ya da daha sonraki bir sürümü). Program **hiçbir garanti verilmeden** dağıtılır.
- **Üçüncü taraf modeller ve kaynaklar:** [NOTICE](NOTICE).
- **İletişim:** appic.studio@outlook.com

Bu program herhangi bir film, dizi, oyun, yayın servisi veya yayıncıyla bağlantılı değildir.

## Sürümler

Her yayımlanan sürümün kaynağı bir etiketle işaretlidir (ör. `v2.7.6`). Store'daki ve kurulum programındaki sürüm, aynı numaralı etiketin kaynağından derlenmiştir. Sürüm sayfasında (Releases) o sürümün modeller paketi de bulunur.

## Kaynaktan derleme (Windows 10/11, 64 bit)

Gerekenler: Python 3.13, Git. Kurulum programı için Inno Setup 6, Store paketi için Windows SDK (makeappx, makepri).

```powershell
py -3.13 -m venv .venv
.venv\Scripts\pip install -r requirements-kilit.txt   # bu sürümün tam paket sürümleri (yalnız ana paketler: requirements-gelistirme.txt)
```

**Modeller** (`modeller\` klasörü, depoda yoktur):
- En kolayı: sürüm sayfasındaki `modeller-<sürüm>.zip` dosyasını proje klasörüne açın.
- Ya da kaynağından üretin:
  - Çeviri modeli: `powershell -ExecutionPolicy Bypass -File paket\model_hazirla.ps1`
  - Doğal sesler: `paket\hafif_ses\ortam_hazirla.ps1`, ardından `paket\hafif_ses\model_indir.py`
  - Konuşmacı modelleri: kaynakları için [NOTICE](NOTICE) dosyasına bakın.

Çalıştırma ve derleme:

```powershell
.venv\Scripts\python.exe uygulama.py                       # geliştirme sırasında çalıştırma
.venv\Scripts\python.exe tests\calistir.py                 # otomatik testler
powershell -ExecutionPolicy Bypass -File paket\derle.ps1   # paket\cikti\: kurulum programı (exe) + Store paketi (msix)
```

Store paketinin kimlik bilgileri (`paket\magaza.json`) Appic'in Store kaydına aittir. Kendi derlediğiniz bir sürümü dağıtacaksanız kendi kimliğinizi ve farklı bir ad kullanın.

## Gizlilik

Hesap, reklam ve kullanım takibi yoktur. Ekran görüntüsü yalnızca bilgisayarın belleğinde işlenir; kaydedilmez, gönderilmez. Hazır çeviri internete çıkmaz. Kullanıcı kendi anahtarıyla bir çeviri servisi (Gemini, Groq, DeepL, Claude) seçerse yalnızca okunan altyazı metni o servise gider. Ayrıntılar: [magaza/gizlilik/index.html](magaza/gizlilik/index.html).
