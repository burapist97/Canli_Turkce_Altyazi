"""Bilgisayar oyunu modu — ELLE çalıştırılan uçtan uca test (ekranı ~15 sn kaplar, calistir.py'de yok).

  .venv\\Scripts\\python.exe tests\\elle_pc_katman.py

Sahte bir "oyun" (tam ekran, İngilizce altyazılı) açar; gerçek uygulama penceresi + Türkçe katmanla:
altyazıyı otomatik bulur, okur, çevirir; katmanın ekranı kapladığını, tıklama geçirdiğini, en üstte durduğunu,
yakalamaya görünmediğini (kendi Türkçemizi tekrar okumadığını) kontrol eder. Ekran görüntüleri tests/cikti/.
"""
import ctypes
import os
import subprocess
import sys
import tempfile
import time

KLASOR = os.path.dirname(os.path.abspath(__file__))
PROJE = os.path.dirname(KLASOR)
CIKTI = os.path.join(KLASOR, "cikti")
os.makedirs(CIKTI, exist_ok=True)
os.environ["CTA_VERI"] = tempfile.mkdtemp(prefix="cta_pc_")
sys.path.insert(0, PROJE)

OYUN = r'''
import cv2, numpy as np
k = np.zeros((1080, 1920, 3), np.uint8)
for y in range(1080): k[y, :] = (60 + y // 12, 90, 40 + y // 20)
cv2.rectangle(k, (300, 200), (900, 700), (30, 140, 200), -1)
t = "Lucia, get in the car. The cops are right behind us!"
(w, h), _ = cv2.getTextSize(t, cv2.FONT_HERSHEY_DUPLEX, 1.4, 3)
cv2.putText(k, t, ((1920 - w) // 2, 930), cv2.FONT_HERSHEY_DUPLEX, 1.4, (0, 0, 0), 9)
cv2.putText(k, t, ((1920 - w) // 2, 930), cv2.FONT_HERSHEY_DUPLEX, 1.4, (255, 255, 255), 3)
cv2.namedWindow("oyun", cv2.WINDOW_NORMAL)
cv2.setWindowProperty("oyun", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
cv2.imshow("oyun", k)
cv2.setWindowProperty("oyun", cv2.WND_PROP_TOPMOST, 1); cv2.waitKey(300)
cv2.setWindowProperty("oyun", cv2.WND_PROP_TOPMOST, 0)   # öne gelsin ama gerçek oyun gibi "en üstte" olmasın
while cv2.waitKey(50) != 27: pass
'''


def main():
    oyun = subprocess.Popen([sys.executable, "-c", OYUN])
    time.sleep(3)
    import cv2
    import webview

    import pc_katman
    import uygulama
    import veri

    a = veri.ayar_yukle()
    a.update({"kurulum_tamam": True, "senaryo": "pc"})
    a["kaynak"].update({"tip": "ekran", "ekran_no": 1})
    a["ceviri"]["motor"] = "cevrimdisi"
    veri.ayar_kaydet(a)

    uyg = uygulama.Uygulama()
    s = uygulama.api_sunucusu(uyg, "x")
    pencere = webview.create_window("Canlı Türkçe Altyazı", f"http://127.0.0.1:{s.server_address[1]}/#x",
                                    width=1000, height=700)
    uyg.ana_pencere = pencere
    uyg.katman = pc_katman.Katman(f"http://127.0.0.1:{uyg.ayar['goruntu']['port']}")
    hatalar = []

    def kontrol(kosul, mesaj):
        print(("  [OK] " if kosul else "  [X] ") + mesaj, flush=True)
        if not kosul:
            hatalar.append(mesaj)

    def is_():
        try:
            time.sleep(4)
            b = uyg.bolge_bul({})  # ana pencere oyunun önünde; yakalamadan gizlenmeli
            kontrol("get in the car" in b["metin"].lower(), f"altyazı otomatik bulundu: {b['metin']}")
            uyg.bolge_kaydet({"bolge": b["bolge"]})
            uyg.motor_baslat({})
            time.sleep(8)
            o = uyg.motor_ozet({})
            kontrol(o["durum"] == "calisiyor", f"motor çalışıyor ({o['hata']})")
            kontrol(len(o["gecmis"]) == 1 and "araba" in o["gecmis"][0]["tr"].lower(),
                    f"tek satır çevrildi, kendi Türkçemiz okunmadı: {[g['tr'] for g in o['gecmis']]}")
            print("  hız:", o["hiz"], flush=True)
            k = uyg.katman
            u32 = ctypes.windll.user32
            h = ctypes.c_void_p(k.hwnd)
            r = (ctypes.c_long * 4)()
            u32.GetWindowRect(h, r)
            e = pc_katman.ekranlar()[0]
            kontrol(list(r) == [e["x"], e["y"], e["x"] + e["genislik"], e["y"] + e["yukseklik"]],
                    f"katman oyunun ekranını kaplıyor {list(r)}")
            ex = u32.GetWindowLongW(h, -20)
            kontrol(bool(ex & 0x20) and bool(ex & 0x80000), "katman tıklamaları oyuna geçiriyor")
            kontrol(bool(ex & 0x8), "katman en üstte")
            kontrol(k.gizlenebilir is True, "katman ekran yakalamaya görünmüyor")
            cv2.imwrite(os.path.join(CIKTI, "pc_yakalanan.png"), cv2.resize(pc_katman.ekran_goruntusu(1), (960, 540)))
            # Görsel kontrol: motoru durdurmadan önce katmanı kısa süre görünür yapıp ekran görüntüsü al
            uyg.motor.durdur()
            uyg.yayinci.gonder({"tip": "satir", "id": 99, "en": "", "tr": o["gecmis"][0]["tr"], "temizlendi": False})
            pc_katman.yakalamadan_gizle(k.hwnd, False)
            time.sleep(1.5)  # DWM'nin yeni hali çizmesi zaman alıyor
            cv2.imwrite(os.path.join(CIKTI, "pc_katmanli.png"), cv2.resize(pc_katman.ekran_goruntusu(1), (960, 540)))
            uyg.motor_durdur({})
            time.sleep(1)
            kontrol(uyg.katman.pencere is None, "durdurunca katman kapandı")
        except Exception:
            import traceback
            traceback.print_exc()
            hatalar.append("istisna")
        finally:
            uyg.kapat()
            pencere.destroy()

    try:
        webview.start(is_)
    finally:
        oyun.kill()
    print(("✓ elle_pc_katman geçti" if not hatalar else f"✗ {len(hatalar)} kontrol başarısız") +
          f"  (görüntüler: {CIKTI})")
    sys.exit(1 if hatalar else 0)


if __name__ == "__main__":
    main()
