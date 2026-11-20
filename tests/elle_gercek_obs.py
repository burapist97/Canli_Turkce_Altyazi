r"""ELLE çalıştırılır: GERÇEK OBS Studio ile uçtan uca (konsol + OBS modu).

    .venv\Scripts\python.exe tests\elle_gercek_obs.py <taşınabilir OBS klasörü>

Taşınabilir OBS (github.com/obsproject/obs-studio sürüm zip'i; içinde portable_mode.txt ve
config\obs-studio\user.ini + global.ini [OBSWebSocket] ServerEnabled=true ServerPort=4466 AuthRequired=false)
kendi klasöründe, simge durumunda açılır; bilgisayardaki kurulu OBS'e ve ayarlarına dokunulmaz. Bittiğinde kapatılır.

"Capture Card" adında bir resim kaynağı oyun karesi gibi kullanılır (İngilizce altyazılı kareler sırayla verilir).
Uygulamanın motoru gerçek OBS'e bağlanır, Türkçe altyazı tarayıcı kaynağını ekler; OBS'in PROGRAM görüntüsü alınıp
Türkçe yazının gerçekten çizildiğine bakılır (OBS'in kendi tarayıcısı = yayında ve projektörde görünen).
Görüntüler: tests\cikti\gercek_obs_*.png
"""
import os
import subprocess
import sys
import tempfile
import time

import cv2
import numpy as np

import yardimci  # noqa: F401
from yardimci import A, B, altyazi, sahne, test_ayari

PORT = 4466
CIKTI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cikti")


def main(obs_klasoru, eski_sayfa=None):
    import motor as motor_modulu
    import obs_baglanti
    import seslendirme
    import sunucu

    os.makedirs(CIKTI, exist_ok=True)
    gecici = tempfile.mkdtemp(prefix="cta_obs_")
    kareler = {}
    for ad, metin in (("bos", None), ("a", A), ("b", B)):
        img = sahne(2.0, parlak_nesne=False)
        if metin:
            img = altyazi(img, metin)
        kareler[ad] = os.path.join(gecici, ad + ".png")
        cv2.imwrite(kareler[ad], img)

    exe = os.path.join(obs_klasoru, "bin", "64bit", "obs64.exe")
    surec = subprocess.Popen([exe, "--portable", "--minimize-to-tray", "--disable-updater", "--disable-shutdown-check",
                              "--disable-missing-files-check", "--multi"], cwd=os.path.dirname(exe))
    m = None
    try:
        obs = None
        for _ in range(60):
            try:
                obs = obs_baglanti.OBS(port=PORT)
                break
            except obs_baglanti.OBSHatasi:
                time.sleep(1)
        assert obs, "OBS WebSocket açılmadı"
        surum = obs.istek("GetVersion")
        print(f"OBS {surum.get('obsVersion')}, WebSocket {surum.get('obsWebSocketVersion')}")
        sahne_adi = obs.aktif_sahne()
        if "Capture Card" not in {k["inputName"] for k in obs.kaynaklar()}:
            obs.istek("CreateInput", {"sceneName": sahne_adi, "inputName": "Capture Card", "inputKind": "image_source",
                                      "inputSettings": {"file": kareler["bos"]}, "sceneItemEnabled": True})
        else:
            obs.istek("SetInputSettings", {"inputName": "Capture Card", "inputSettings": {"file": kareler["bos"]}})

        def kare_ver(ad):
            obs.istek("SetInputSettings", {"inputName": "Capture Card", "inputSettings": {"file": kareler[ad]}})

        def program(ad):
            d = obs.istek("GetSourceScreenshot", {"sourceName": sahne_adi, "imageFormat": "png", "imageWidth": 1920})
            import base64
            img = cv2.imdecode(np.frombuffer(base64.b64decode(d["imageData"].split(",", 1)[1]), np.uint8), cv2.IMREAD_COLOR)
            cv2.imwrite(os.path.join(CIKTI, f"gercek_obs_{ad}.png"), img)
            return img

        seslendirme.Seslendirici._winsound_cal = staticmethod(lambda wav: time.sleep(seslendirme.wav_suresi(wav)))
        ayar = test_ayari()
        ayar["kaynak"]["tip"] = "obs"
        ayar["obs"].update({"port": PORT, "sifre": "", "kaynak_adi": "Capture Card"})
        ayar["goruntu"]["port"] = 8789
        ayar["dublaj"].update({"acik": True, "dogal_ses": False, "karakter_sesleri": False})
        yayinci = sunucu.Yayinci(ayar["goruntu"], ayar["bolge"])
        sunucu.sunucu_baslat(yayinci, ayar["goruntu"]["port"])
        if eski_sayfa:  # güncelleme senaryosu: OBS'te eski sürümün sayfası açık kalmış
            obs.altyazi_ekle("file:///" + eski_sayfa.replace("\\", "/"))
            time.sleep(2)
        obs.altyazi_ekle(f"http://127.0.0.1:{ayar['goruntu']['port']}")
        time.sleep(3)

        m = motor_modulu.AltyaziMotoru(ayar, yayinci, yazdir=True)
        m.baslat()
        for _ in range(300):
            if m.durum in ("calisiyor", "hata"):
                break
            time.sleep(0.1)
        assert m.durum == "calisiyor", m.hata
        time.sleep(3)

        def turkce_var_mi(img):
            """Altyazı bölgesinde bizim çizdiğimiz yazı var mı: OCR ile okunur."""
            import ocr
            b = ayar["bolge"]
            h, w = img.shape[:2]
            kesit = img[int(b["y"] * h):int((b["y"] + b["h"]) * h), int(b["x"] * w):int((b["x"] + b["w"]) * w)]
            return ocr.RapidOCRMotoru().oku(kesit)

        sonuc = {}
        for ad in ("a", "b"):
            kare_ver(ad)
            time.sleep(3.0)
            sonuc[ad] = turkce_var_mi(program(ad))
            print(f"  kare {ad}: OBS program görüntüsünde okunan: {sonuc[ad]!r}")
            kare_ver("bos")
            time.sleep(2.5)
        bos = turkce_var_mi(program("bos"))
        print(f"  boş kare: {bos!r}")
        print(f"  motor: okunan {m.sayac['okunan']}, çevrilen {m.sayac['cevrilen']}, hız {m.hiz()}, hata {m.hata!r}")
        for g in m.gecmis:
            print("   ", g["en"].replace("\n", " "), "->", g["tr"])
        assert m.sayac["cevrilen"] >= 2, "satırlar çevrilmedi"
        ceviriler = [g["tr"] for g in m.gecmis]
        import difflib
        for ad in ("a", "b"):
            en_yakin = max(difflib.SequenceMatcher(None, sonuc[ad].lower(), c.lower()).ratio() for c in ceviriler)
            assert en_yakin > 0.6, f"kare {ad}: OBS'in görüntüsünde Türkçe altyazı yok (okunan {sonuc[ad]!r})"
        print("[OK] Gerçek OBS'te Türkçe altyazı program görüntüsünde çiziliyor")
    finally:
        if m:
            m.durdur()
        surec.terminate()
        try:
            surec.wait(10)
        except Exception:
            surec.kill()


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
