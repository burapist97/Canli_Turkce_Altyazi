# Microsoft Store sayfası — Türkçe (tr-TR) — sürüm 2.7.6

Partner Center → Canlı Türkçe Altyazı → Store listings → Turkish (Türkiye). Görseller: `magaza/gorseller/` (`magaza/gorsel_uret.py` üretir).
Kural: marka adı (oyun, film, dizi, yayın servisi adları) ve gerçek oyun/film görüntüsü KULLANILMAZ.
Yapılacak: kaynak kod deposu açılınca Description'daki "AÇIK KAYNAK" bölümüne "Kaynak kodu: https://..." satırı eklenecek (AGPL gereği).

## Description

Ekrandaki İngilizce altyazıyı okur, anında Türkçeye çevirir ve üstüne yazar. Film, dizi, video ve oyunlarda çalışır.

NASIL ÇALIŞIR
1. İngilizce altyazının ekranda çıktığı yeri bir kez gösterirsiniz.
2. Program altyazıyı çıktığı anda okur ve Türkçeye çevirir (hazır çeviri internetsiz ve ücretsizdir).
3. Türkçe altyazı, İngilizcesinin yerinde ya da ekranda seçtiğiniz yerde görünür; İngilizcesi kalkınca o da kalkar.

NERELERDE ÇALIŞIR
• Film, dizi ve videolar: tarayıcıda ya da oynatıcıda, tam ekranda da.
• Bilgisayar oyunları: Türkçe altyazı oyunun üstünde görünür, fare tıklamaları oyuna gider. Oyunun "Kenarlıksız pencere" (Borderless) modunda olması gerekir.
• Konsol oyunları: PlayStation veya Xbox görüntüsünü capture card ve OBS ile bilgisayara aktarıyorsanız Türkçe altyazı OBS'e katman olarak eklenir; yayında ve kayıtta da görünür.

ÇEVİRİ
• Hazır çeviri uygulamayla gelir: anahtar gerekmez, internet gerekmez, sınırı yoktur.
• İsterseniz kendi ücretsiz Google Gemini veya Groq anahtarınızı girebilirsiniz; DeepL, Claude ve bilgisayarınızda çalışan yerel modeller de desteklenir.
• Seçtiğiniz servisin kotası dolar veya anahtarın süresi biterse altyazı kesilmez; çeviri hazır motorla devam eder ve sizi uyarır.

ALTYAZIYI İSTEDİĞİNİZ GİBİ AYARLAYIN
Yazı tipi (bilgisayarınızdaki bütün yazı tipleri), boyut, kalınlık, renk, kenar çizgisi, gölge; istediğiniz renkte, saydamlığı ayarlanan arka plan. Hazır görünümlerden birine dokunmanız yeter. Türkçe yazıyı ekranda istediğiniz yere sürükleyebilir ya da İngilizcesinin tam üstüne yazdırabilirsiniz. Önizlemede gördüğünüz, ekranda gördüğünüzle aynıdır.

BİRDEN FAZLA ALAN VE TÜM EKRAN
Altyazının yanında görev yazısı, mesaj kutusu ya da ipuçları gibi başka İngilizce yazılar da varsa her biri için bir alan çizin; hepsi kendi yerinde çevrilir ve her alanın görünümü ayrı ayarlanır. "Tüm ekran" seçeneğinde ekranın tamamı aralıklı okunur ve bulunan İngilizce yazıların Türkçesi yerlerine yazılır (menüler, web sayfaları, program arayüzleri için).

HEP ELİNİZİN ALTINDA
Pencereyi küçültünce program saatin yanındaki simgeye iner ve çalışmaya devam eder; simgeye sağ tıklayıp altyazıyı başlatabilir, durdurabilir, boyutunu ve görünümünü değiştirebilirsiniz. Pencereyi kapatınca program tamamen kapanır.

TÜRKÇE SESLENDİRME (GELİŞTİRİLİYOR)
Çevrilen altyazı isterseniz Türkçe sesli de okunur; sesler bilgisayarınızda üretilir, yapaydır. Bu özellik geliştirme aşamasındadır: şimdiden deneyebilirsiniz, ancak ses bazen altyazının gerisinde kalabilir ve bazı sesler yapay duyulabilir. Güncellemelerle iyileştirilecek. Altyazı bundan etkilenmez.

GİZLİLİK
Hesap yok, reklam yok, kullanım takibi yok. Ekran görüntüsü yalnızca bilgisayarınızda işlenir; kaydedilmez, hiçbir yere gönderilmez.

AÇIK KAYNAK
Uygulama özgür yazılımdır (AGPL-3.0).

GEREKSİNİMLER
• Windows 10 (1809 veya üzeri) ya da Windows 11, 64 bit; Windows 10 sürüm 2004 veya üzeri önerilir
• Yaklaşık 2,5 GB boş disk alanı
• Ekranda İngilizce altyazının açık olması
• Konsol için: capture card ve OBS Studio 28 veya üzeri (ücretsiz)

Bu uygulama herhangi bir film, dizi, oyun, yayın servisi veya yayıncıyla bağlantılı değildir.

Çeviri modeli: OPUS-MT (Helsinki-NLP), CC BY 4.0. Doğal sesler: Pocket TTS Turkish (Wite Tech), CC BY 4.0. Konuşmacı tanıma: NVIDIA TitaNet-small, CC BY 4.0.

## What's new in this version

Yeni arayüz · film, dizi ve videolarda da çalışır · tüm ekran çevirisi · her alan için ayrı görünüm · saydamlığı ayarlanan arka plan · saatin yanındaki simgeden hızlı ayarlar · daha hızlı altyazı (Türkçe, İngilizcesiyle neredeyse aynı anda gelir). Türkçe seslendirme geliştirme aşamasındadır.

## Product features (her satır ayrı)

- Ekrandaki İngilizce altyazıyı canlı olarak Türkçeye çevirir
- Film, dizi, video ve oyunlarda çalışır
- Türkçe altyazı İngilizcesiyle birlikte gelir, birlikte gider
- Hazır çeviri: anahtar, hesap ve internet gerekmez
- Türkçe yazı İngilizcesinin yerinde ya da ekranda istediğiniz yerde
- Görünüm: yazı tipi, renk, boyut, kenar çizgisi, saydam ya da renkli arka plan
- Birden fazla çeviri alanı; her alanın görünümü ayrı ayarlanır
- Tüm ekran seçeneği: menüler, web sayfaları, program arayüzleri
- Bilgisayar oyunlarında oyunun üstünde çalışır; tıklamalar oyuna geçer
- Konsol + capture card + OBS ile çalışır; altyazı yayında ve kayıtta da görünür
- Saatin yanındaki simgeden başlat, durdur, hızlı ayarlar
- İsterseniz kendi Gemini, Groq, DeepL veya Claude anahtarınızla çeviri
- Kota dolarsa ya da anahtar biterse çeviri kesilmeden devam eder
- Türkçe seslendirme (geliştiriliyor)
- Açık kaynak (AGPL-3.0); hesap, reklam ve takip yok

## Short description

Ekrandaki İngilizce altyazıyı okur, anında Türkçeye çevirir ve üstüne yazar. Film, dizi, video ve oyunlarda çalışır. Hazır çeviri uygulamayla gelir; anahtar ve internet gerekmez. Türkçe seslendirme geliştirme aşamasındadır.

## Keywords (7)

türkçe altyazı · altyazı çevirici · canlı çeviri · film dizi altyazı · oyun çeviri · ekran çevirisi · türkçe seslendirme

## Screenshots (bu sırayla; her birinin "Caption" alanına yanındaki metin)

Yalnız `magaza/gorseller/` içindeki 01–08 yüklenir (`arayuz/` ve `eski/` klasörleri yüklenmez).

1. `01_giris.png` — Ekrandaki İngilizce altyazı, anında Türkçe.
2. `02_hiz.png` — Türkçe, İngilizcesiyle aynı anda gelir, aynı anda gider.
3. `03_her_yerde.png` — Film, dizi, bilgisayar oyunları ve konsol (capture card + OBS).
4. `04_internetsiz.png` — Hazır çeviri: internet, anahtar ve ücret gerekmez.
5. `05_gorunum.png` — Yazı tipi, renk, arka plan ve yer tamamen sizin elinizde.
6. `06_kurulum.png` — Altyazının yerini bir kez gösterin, gerisi otomatik.
7. `07_baslat.png` — Başlat'a basın; program saatin yanındaki simgeden yönetilir.
8. `08_gizlilik.png` — Hesap yok, reklam yok, takip yok. Açık kaynak.

Store logoları: `hero_16x9.png` (16:9 Super hero art, yazısız), `poster_9x16.png` (9:16 Poster art), `kutu_1x1.png` (1:1 Box art).

## Copyright and trademark info

© 2026 Appic Studio

## Developed by

Appic Studio

## Notes for certification (Submission options → Notes for certification; İngilizce yazılır)

This app reads English subtitles from the user's own screen (OCR), translates them to Turkish on the device and shows the Turkish text in a transparent, click-through overlay window. No account or sign-in is needed. To test: open the app, choose "Bu bilgisayarın ekranı", draw a rectangle around any English text on screen ("Ekran ve altyazı alanı"), press "Kurulumu bitir", then "Başlat" on the home page. The default translation engine is offline and needs no key.

runFullTrust: required for screen capture, the transparent always-on-top overlay window, the notification-area (tray) icon and the bundled local translation/voice engines (classic Win32 processes).

microphone: used only for the optional "character voices" feature, which listens to the game/video audio (a capture card's audio input, which Windows classifies as a microphone device) to tell speakers apart. Audio is processed in memory only; nothing is recorded or sent.

Startup task: declared disabled by default; the user can enable it in Windows Settings > Apps > Startup.

The app does not download or install executable code. Optional third-party translation services (Gemini, Groq, DeepL, Claude) are used only if the user enters their own API key.

The Turkish voice-over ("Seslendirme") feature is marked in the app as under development.
