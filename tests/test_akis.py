"""Altyazı takip hattı: belirme (fade-in), değişme, kaybolma, tekrar engelleme ve SSE yayını."""
import json
import threading
import time
import urllib.request

import yardimci  # noqa: F401  (sys.path ayarı)
from yardimci import A, B, altyazi, sahne, test_ayari

import ceviri
import ocr
import sunucu
from kaynak import bolge_kes
from takip import AltyaziTakipcisi


def zaman_cizelgesi():
    for i in range(60):  # 8 fps, 7.5 sn
        t = i / 8
        if t < 1: yield t, None, 1
        elif t < 1.25: yield t, A, 0.4      # fade-in
        elif t < 3.5: yield t, A, 1
        elif t < 5.5: yield t, B, 1
        else: yield t, None, 1


def test_akis(port=8799):
    ayar = test_ayari()
    yayinci = sunucu.Yayinci(ayar["goruntu"], ayar["bolge"])
    sunucu.sunucu_baslat(yayinci, port)
    sse = []

    def dinle():
        for satir in urllib.request.urlopen(f"http://127.0.0.1:{port}/olaylar"):
            satir = satir.decode().strip()
            if satir.startswith("data:"):
                sse.append(json.loads(satir[5:]))
    threading.Thread(target=dinle, daemon=True).start()
    time.sleep(0.3)

    class Sahte:
        def cevir(self, m, b):
            time.sleep(0.1)
            return f"[TR] {m}"

    temiz = set()
    isci = ceviri.CeviriIscisi(Sahte(), lambda sid, en, tr, s: yayinci.gonder(
        {"tip": "satir", "id": sid, "en": en, "tr": tr, "temizlendi": sid in temiz}), 4, onbellek_yolu=None)
    tk = AltyaziTakipcisi(ayar, ocr.motor_olustur(ayar))
    sayac = {"ocr": 0}
    asil = tk.motor.oku
    def say(*a, **k):
        sayac["ocr"] += 1
        return asil(*a, **k)
    tk.motor.oku = say

    olaylar = []
    for t, m, a in zaman_cizelgesi():
        img = sahne(t)
        if m:
            img = altyazi(img, m, a)
        for o in tk.isle(bolge_kes(img, ayar["bolge"]), t):
            olaylar.append((t, o))
            if o[0] == "yeni":
                isci.ekle(o[1], o[2])
            else:
                temiz.add(o[1])
                yayinci.gonder({"tip": "temizle", "id": o[1]})
    time.sleep(0.8)
    isci.durdur()

    yeniler = [o for _, o in olaylar if o[0] == "yeni"]
    for t, o in olaylar:
        print(f"  t={t:.3f} {o}")
    print(f"  OCR çağrısı: {sayac['ocr']} / 60 kare")
    assert len(yeniler) == 2, f"2 satır bekleniyordu, {len(yeniler)} geldi (tekrar engelleme bozuk olabilir)"
    assert "shortcut" in yeniler[1][2]
    assert sayac["ocr"] <= 10, "OCR gereğinden sık çalışıyor"
    son_temizle = max(t for t, o in olaylar if o[0] == "temizle")
    assert 5.5 < son_temizle <= 6.25, f"altyazı kaybolunca temizleme gecikti: {son_temizle}"
    assert any(e["tip"] == "satir" for e in sse) and any(e["tip"] == "temizle" for e in sse), "SSE olayları gelmedi"
    print("  ✓ test_akis")


if __name__ == "__main__":
    test_akis()
