"""Testler için ortak yardımcılar: proje yolu, sentetik GTA tarzı kare, geçici proje kopyası."""
import json
import os
import shutil
import sys
import tempfile

import cv2
import numpy as np

PROJE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJE not in sys.path:
    sys.path.insert(0, PROJE)

A = "Lucia, get in the car.\nThe cops are right behind us!"
B = "Relax, I know a shortcut through the swamp."


def sahne(t=0.0, parlak_nesne=True):
    """Hareketli, yer yer parlak arka plan (gökyüzü/ışıklar)."""
    img = np.zeros((1080, 1920, 3), np.uint8)
    for y in range(1080):
        img[y, :] = (60 + y // 12, 90 + y // 15, 120)
    if parlak_nesne:  # altyazı bölgesinden geçen parlak nesne (zor durum)
        x = int(200 + 300 * t) % 1900
        cv2.circle(img, (x, 980), 40, (240, 240, 240), -1)
    return img


def altyazi(img, metin, alpha=1.0):
    katman = img.copy()
    for i, s in enumerate(metin.split("\n")):
        (tw, _), _ = cv2.getTextSize(s, cv2.FONT_HERSHEY_DUPLEX, 1.4, 2)
        org = ((1920 - tw) // 2, 920 + i * 55)
        cv2.putText(katman, s, org, cv2.FONT_HERSHEY_DUPLEX, 1.4, (0, 0, 0), 8, cv2.LINE_AA)
        cv2.putText(katman, s, org, cv2.FONT_HERSHEY_DUPLEX, 1.4, (255, 255, 255), 2, cv2.LINE_AA)
    return cv2.addWeighted(katman, alpha, img, 1 - alpha, 0)


def ornek_kare(metin=A, t=2.0):
    return altyazi(sahne(t), metin)


def yuz_karesi():
    img = np.full((720, 1280, 3), (200, 190, 180), np.uint8)
    cv2.circle(img, (640, 300), 120, (120, 130, 150), -1)
    cv2.ellipse(img, (640, 720), (260, 200), 0, 180, 360, (120, 130, 150), -1)
    return img


VARSAYILAN_OCR = "rapidocr" if sys.platform.startswith("win") else "tesseract"
# Testler kullanıcının gerçek ayar klasörüne yazmasın
os.environ.setdefault("CTA_VERI", tempfile.mkdtemp(prefix="altyazi_veri_"))
os.environ.setdefault("CTA_DOGAL_SES_YOK", "1")  # bilgisayarda kurulu Doğal Ses Paketi testlere karışmasın
os.environ.setdefault("CTA_RAPOR_KLASORU", tempfile.mkdtemp(prefix="altyazi_rapor_"))  # sorun raporu masaüstüne yazılmasın
os.environ.setdefault("CTA_PENCERE_ACMA", "1")  # testler Dosya Gezgini açmasın
os.environ.setdefault("CTA_KAYIT_YOK", "1")  # testler Windows başlangıç kaydına dokunmasın
os.environ.setdefault("CTA_SES_KISMA_YOK", "1")  # testler açık uygulamaların gerçek ses seviyesine dokunmasın


def test_ayari(ocr_motoru=VARSAYILAN_OCR):
    """config.json'un bir kopyası (dosyaya yazmadan). Linux/macOS'ta testler Tesseract kullanır."""
    with open(os.path.join(PROJE, "config.json"), encoding="utf-8") as f:
        a = json.load(f)
    a["ocr"]["motor"] = ocr_motoru
    return a


def gecici_proje(ocr_motoru=VARSAYILAN_OCR):
    """Projeyi geçici klasöre kopyalar (config.json'u kirletmemek için). Yolu döner."""
    hedef = os.path.join(tempfile.mkdtemp(prefix="altyazi_test_"), "proje")
    # .venv-ses (~1 GB) ve Pocket TTS modeli (~420 MB) kopyalanmaz: testlerde doğal ses motoru kullanılmaz
    shutil.copytree(PROJE, hedef, ignore=shutil.ignore_patterns(".venv", ".venv-*", "pocket-tts-turkish", "__pycache__", "tests",
                                                               "*.zip", "cikti", "adaylar", "magaza", "*.msix", "*.exe"))
    p = os.path.join(hedef, "config.json")
    with open(p, encoding="utf-8") as f:
        a = json.load(f)
    a["ocr"]["motor"] = ocr_motoru
    with open(p, "w", encoding="utf-8") as f:
        json.dump(a, f, ensure_ascii=False, indent=2)
    return hedef
