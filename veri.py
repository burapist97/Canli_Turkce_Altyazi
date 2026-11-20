"""Dosya yolları ve ayarlar.

Program dosyaları (KLASOR) salt okunurdur: Microsoft Store (MSIX) paketinde
uygulama kendi klasörüne yazamaz. Kullanıcıya ait her şey (ayarlar, çeviri
önbelleği, sözlük) VERI_KLASORU'nde tutulur:
  Windows: %LOCALAPPDATA%\\CanliTurkceAltyazi
  Diğer:   ~/.canli-turkce-altyazi
Testler ve geliştirme için CTA_VERI ortam değişkeniyle değiştirilebilir.
"""
import copy
import json
import os
import shutil
import sys

UYGULAMA_ADI = "Canlı Türkçe Altyazı"
SURUM = "2.7.6"

# Altyazı görünümünün kabul edilen değerleri (config.goruntu). altyazi_stil.js'teki SECENEK / SINIR / RENK_ALANLARI
# ile aynı olmalı; tests/test_arayuz.py ikisini karşılaştırır.
GORUNUM_SECENEKLERI = {
    "yazi_tipi": ("standart", "oyun", "sade", "genis", "sinema", "kitap", "daktilo", "eglenceli", "darbe", "ozel"),
    "kutu_bicimi": ("sar", "serit"),
    "hizalama": ("orta", "sol", "sag"),
    "konum": ("orijinal", "serbest"),  # orijinal: oyunun altyazısının yeri; serbest: (konum_x, konum_y) yazının ortası
    "gecis": ("yok", "yumusak"),
}
GORUNUM_SINIRLARI = {
    "yazi_boyutu": (16, 120), "yazi_kalinligi": (300, 900), "kenar": (0, 4), "golge": (0, 3),
    "kutu_saydamlik": (0, 1), "kutu_kose": (0, 1), "kutu_bosluk": (0, 1), "harf_araligi": (-0.03, 0.2),
    "satir_araligi": (1, 1.8), "genislik": (0.3, 0.96), "ingilizce_oran": (0.4, 1), "konum_x": (0.2, 0.8),
    "konum_y": (0.06, 0.94), "kapak_saydamlik": (0, 1),
}
GORUNUM_RENKLERI = ("yazi_rengi", "kenar_rengi", "kutu_rengi", "ingilizce_rengi", "kapak_rengi")
GORUNUM_ACKAPA = ("italik", "buyuk_harf", "ingilizce_ustte", "orijinali_kapat", "ingilizce_goster", "altyazi_goster")
ESKI_KUTU = {"yok": 0.0, "yari": 0.55, "koyu": 0.88}  # 2.6 ve öncesinin "kutu" ayarı -> kutu_saydamlik

# Tek dokunuşla seçilen hazır görünümler (boyut ve konuma dokunmaz). Arayüz ve tepsi menüsü aynı listeyi kullanır.
_KENARLI = {"italik": False, "kenar_rengi": "#000000", "kutu_saydamlik": 0}
_KUTULU = {"italik": False, "kenar": 0, "golge": 0}
HAZIR_GORUNUMLER = [
    {"id": "klasik", "ad": "Klasik", "ayar": {"yazi_tipi": "standart", "yazi_kalinligi": 700, "yazi_rengi": "#ffffff",
                                              "kenar": 2, "golge": 1, **_KENARLI}},
    {"id": "sinema", "ad": "Sinema", "ayar": {"yazi_tipi": "sinema", "yazi_kalinligi": 700, "yazi_rengi": "#ffe04a",
                                              "kenar": 2, "golge": 1, **_KENARLI}},
    {"id": "cam", "ad": "Buzlu cam", "ayar": {"yazi_tipi": "standart", "yazi_kalinligi": 600, "yazi_rengi": "#ffffff",
                                              "kutu_rengi": "#000000", "kutu_saydamlik": 0.5, "kutu_bicimi": "sar",
                                              "kutu_kose": 0.35, "kutu_bosluk": 0.4, **_KUTULU}},
    {"id": "serit", "ad": "Şerit", "ayar": {"yazi_tipi": "sade", "yazi_kalinligi": 700, "yazi_rengi": "#ffffff",
                                            "kutu_rengi": "#000000", "kutu_saydamlik": 0.7, "kutu_bicimi": "serit",
                                            "kutu_kose": 0, "kutu_bosluk": 0.3, **_KUTULU}},
    {"id": "oyun", "ad": "Oyun", "ayar": {"yazi_tipi": "oyun", "yazi_kalinligi": 800, "yazi_rengi": "#ffffff",
                                          "kenar": 3, "golge": 2, **_KENARLI}},
    {"id": "gece", "ad": "Gece mavisi", "ayar": {"yazi_tipi": "standart", "yazi_kalinligi": 700, "yazi_rengi": "#9fd8ff",
                                                 "kutu_rengi": "#14213d", "kutu_saydamlik": 0.78, "kutu_bicimi": "sar",
                                                 "kutu_kose": 0.3, "kutu_bosluk": 0.4, **_KUTULU}},
    {"id": "kagit", "ad": "Kâğıt", "ayar": {"yazi_tipi": "kitap", "yazi_kalinligi": 600, "yazi_rengi": "#101014",
                                            "kutu_rengi": "#ffffff", "kutu_saydamlik": 0.86, "kutu_bicimi": "sar",
                                            "kutu_kose": 0.2, "kutu_bosluk": 0.4, **_KUTULU}},
    {"id": "yumusak", "ad": "Yumuşak", "ayar": {"yazi_tipi": "kitap", "yazi_kalinligi": 400, "yazi_rengi": "#f6ecd6",
                                                "kenar": 1, "golge": 2, "kenar_rengi": "#000000", "kutu_saydamlik": 0,
                                                "italik": True}},
]

# PyInstaller ile derlenmişse dosyalar _MEIPASS altındadır
KLASOR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


def _veri_klasoru():
    if os.environ.get("CTA_VERI"):
        return os.environ["CTA_VERI"]
    if sys.platform.startswith("win"):
        return os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "CanliTurkceAltyazi")
    return os.path.join(os.path.expanduser("~"), ".canli-turkce-altyazi")


VERI_KLASORU = _veri_klasoru()


def _magaza_paketi_mi():
    """Microsoft Store paketinin (MSIX) içinden mi çalışıyoruz? Windows'a sürecin paket kimliği sorulur; kurulum
    programıyla kurulan programda ve geliştirme kipinde kimlik yoktur. CTA_MAGAZA=1/0 bunu denemeler için ezer."""
    ezme = os.environ.get("CTA_MAGAZA")
    if ezme in ("0", "1"):
        return ezme == "1"
    if not sys.platform.startswith("win"):
        return False
    try:
        import ctypes
        uzunluk = ctypes.c_uint32(0)
        # 15700 = APPMODEL_ERROR_NO_PACKAGE: sürecin paket kimliği yok
        return ctypes.windll.kernel32.GetCurrentPackageFullName(ctypes.byref(uzunluk), None) != 15700
    except Exception:
        return False


# Store sürümü: altyazı kurulum programındakiyle AYNIDIR. Farklar yalnız şunlardır: seslendirme "geliştiriliyor"
# diye işaretlenir, ses motoru denemeleri (model indirme) gösterilmez, "Windows açılınca başlat" Windows'un kendi
# Başlangıç sayfasından açılır (paket içinden kayıt defterine yazılan değer Windows'a görünmez).
MAGAZA = _magaza_paketi_mi()
VARSAYILAN_AYAR = os.path.join(KLASOR, "config.json")


def kaynak(ad):
    """Program içindeki (salt okunur) bir dosyanın yolu."""
    return os.path.join(KLASOR, ad)


def veri_yolu(ad):
    os.makedirs(VERI_KLASORU, exist_ok=True)
    return os.path.join(VERI_KLASORU, ad)


def _birlestir(taban, ust):
    """Varsayılan ayarların üstüne kullanıcınınkileri yazar (iç içe)."""
    sonuc = copy.deepcopy(taban)
    for k, v in ust.items():
        if isinstance(v, dict) and isinstance(sonuc.get(k), dict):
            sonuc[k] = _birlestir(sonuc[k], v)
        else:
            sonuc[k] = v
    return sonuc


def ayar_yolu():
    return veri_yolu("config.json")


def ayar_yukle(yol=None):
    """Varsayılan ayarlar + kullanıcı ayarları. Yeni sürümde eklenen ayarlar
    eski kullanıcı dosyasında olmasa da varsayılan değeriyle gelir."""
    with open(VARSAYILAN_AYAR, encoding="utf-8") as f:
        ayar = json.load(f)
    yol = yol or ayar_yolu()
    if os.path.exists(yol):
        try:
            with open(yol, encoding="utf-8") as f:
                ayar = _birlestir(ayar, json.load(f))
        except (ValueError, OSError) as e:
            print(f"[ayar dosyası okunamadı, varsayılanlar kullanılıyor] {e}")
        # Eski sürümden kalan zamanlama değerleri (kullanıcı elle değiştirmez, dosyaya varsayılan olarak yazılmıştı):
        # 2.6.0'da altyazı İngilizcesiyle birlikte gelip gitsin diye hızlandırıldı; eskileri yenisiyle değişir.
        with open(VARSAYILAN_AYAR, encoding="utf-8") as f:
            varsayilan = json.load(f)
        if int(ayar.get("ayar_surumu") or 1) < varsayilan.get("ayar_surumu", 1) \
                or "ayar_surumu" not in _ham_oku(yol):
            for k in ("fps", "bos_temizle_sn"):
                ayar["tespit"][k] = varsayilan["tespit"][k]
            ayar["ayar_surumu"] = varsayilan.get("ayar_surumu", 1)
        # 2.6 ve öncesi: yazının arkasındaki kutu "yok/yari/koyu" idi; artık renk + saydamlık
        ham_g = _ham_oku(yol).get("goruntu", {})
        if "kutu" in ham_g and "kutu_saydamlik" not in ham_g:
            ayar["goruntu"]["kutu_saydamlik"] = ESKI_KUTU.get(ham_g["kutu"], 0.0)
        ayar["goruntu"].pop("kutu", None)
    return ayar


def _ham_oku(yol):
    try:
        with open(yol, encoding="utf-8") as f:
            return json.load(f)
    except (ValueError, OSError):
        return {}


def ayar_kaydet(ayar, yol=None):
    yol = yol or ayar_yolu()
    gecici = yol + ".tmp"
    with open(gecici, "w", encoding="utf-8") as f:
        json.dump(ayar, f, ensure_ascii=False, indent=2)
    os.replace(gecici, yol)  # yarım yazılmış dosya kalmasın


def sozluk_yolu():
    """Kullanıcı sözlüğü yoksa varsayılanı kopyalar; kullanıcı düzenleyebilsin."""
    yol = veri_yolu("sozluk.json")
    if not os.path.exists(yol):
        shutil.copyfile(kaynak("sozluk.json"), yol)
    return yol


def onbellek_yolu():
    return veri_yolu("ceviri_onbellek.json")
