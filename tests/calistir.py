"""Tüm testleri sırayla çalıştırır:  python tests/calistir.py

Gereken: opencv-python, numpy, requests; Linux/macOS'ta 'tesseract' komutu;
sihirbaz testi için: pip install playwright && playwright install chromium
"""
import importlib
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

TESTLER = [
    ("test_akis", "test_akis"),
    ("test_akan_altyazi", "test_akan_altyazi"),
    ("test_akan_altyazi", "test_devam_tam_gosterilir"),
    ("olc_gecikme", "test_gecikme"),
    ("test_hizli_okuma", "test_hizli_okuma"),
    ("test_hizli_okuma", "test_dogrulama"),
    ("test_hizli_okuma", "test_bolge_yakalama"),
    ("test_hizli_okuma", "test_buyuk_ekran"),
    ("test_hizli_okuma", "test_video_arka_plani"),
    ("test_obs_baglanti", "test_obs"),
    ("test_obs_yardim", "test_obs_yardim"),
    ("test_ceviri_yedek", "test_ceviri_yedek"),
    ("test_ceviri_model", "test_ceviri_model"),
    ("test_ceviri_hatti", "test_ceviri_hatti"),
    ("test_ceviri_hatti", "test_turkce_yol"),
    ("test_konusmaci", "test_konusmaci"),
    ("test_ses_kisici", "test_ses_kisici"),
    ("test_dogal_ses", "test_dogal_ses"),
    ("test_dogal_ses", "test_hafif_istemci"),
    ("test_hafif_ses", "test_hafif_ses"),  # gerçek model; .venv-ses yoksa atlanır
    ("test_tam_ekran", "test_paragraflar"),
    ("test_tam_ekran", "test_tam_ekran"),
    ("test_tam_ekran", "test_tam_ekran_overlay"),
    ("test_tam_ekran", "test_overlay_devam"),
    ("test_ses_deneme", "test_ses_deneme"),
    ("test_ses_yedek", "test_ses_yedek"),
    ("test_yogun_diyalog", "test_yogun_diyalog"),
    ("test_main_obs", "test_main_obs"),
    ("test_arayuz", "test_gorunum_dogrulama"),
    ("test_arayuz", "test_tepsi_menusu"),
    ("test_arayuz", "test_arayuz"),
    ("test_arayuz_obs", "test_kapat_kucult"),
    ("test_arayuz_obs", "test_arayuz_obs"),
    ("test_magaza", "test_magaza"),
]

basarisiz = 0
for modul, fonk in TESTLER:
    print(f"\n▶ {modul}" + ("" if fonk == modul else f" · {fonk}"))
    try:
        getattr(importlib.import_module(modul), fonk)()
    except ImportError as e:
        print(f"  - atlandı (eksik paket: {e.name})")
    except Exception:
        basarisiz += 1
        traceback.print_exc()
print("\n" + ("✓ Hepsi geçti" if not basarisiz else f"✗ {basarisiz} test başarısız"))
sys.exit(1 if basarisiz else 0)
