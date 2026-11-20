"""Güçlü ses modeli (ekran kartı) yetişemeyince hafif doğal sese geçiş ve ses denemesi / canlı ses çakışma engeli.

2026-11-20'de kullanıcıda olan: güçlü model seçiliyken ilk ses zaman aşımına uğradı, satırları Windows sesi okudu
(kadın sesi Tolga'dan türetildiği için "robotik"), ses denemeleri canlı ses sunucusuyla aynı anda ekran kartını
kullanınca ekran kartı sürücüsü iki kez sıfırlandı. Gerçek motor kullanılmaz; hiçbir ses çalınmaz.
"""
import json
import os
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np

import yardimci  # noqa: F401


def _hafif_klasoru():
    kok = tempfile.mkdtemp(prefix="cta_hafif_")
    for i, (ad, cins) in enumerate((("tarik", "erkek"), ("elif", "kadin"))):
        os.makedirs(os.path.join(kok, "sesler", ad))
        with open(os.path.join(kok, "sesler", ad, "ses.json"), "w", encoding="utf-8") as f:
            json.dump({"gorunen_ad": ad.title(), "cinsiyet": cins, "sira": i}, f)
    return {"kok": kok, "komut": ["yok.exe"], "model": kok, "sesler": os.path.join(kok, "sesler")}


class _Sessiz:
    def cal(self, x):
        pass

    def bitir(self):
        pass


def test_ses_yedek():
    import dogal_ses
    import ses_deneme
    import uygulama

    asil = (dogal_ses.hafif_kurulumu, dogal_ses.kurulum_klasoru, dogal_ses._tercih, dogal_ses._paylasilan)
    try:
        hafif = _hafif_klasoru()
        guclu_klasor = tempfile.mkdtemp(prefix="cta_guclu_")
        dogal_ses.hafif_kurulumu = lambda: hafif
        dogal_ses.kurulum_klasoru = lambda: guclu_klasor
        dogal_ses.tercih_ayarla("guclu")
        dogal_ses.gecici_hafifi_sifirla()
        assert dogal_ses.motor_sec() == "guclu"

        # ---------- güçlü model yanıt vermedi: hafif doğal sese geçilir (Windows sesine değil) ----------
        d = dogal_ses.DogalSes(adres="http://127.0.0.1:9", klasor=guclu_klasor, motor="guclu")
        baslatildi = []
        d.baslat = lambda *a, **k: baslatildi.append(1)
        d.durum = "hazir"
        d.hata_oldu(TimeoutError("timed out"))
        assert d.motor == "hafif" and d.ornek_hizi == 24000 and [s["id"] for s in d.sesler] == ["tarik", "elif"], d.sesler
        assert d.degisim == 1 and "hafif modelle devam" in d.gecis_notu and d.devre_disi_kadar == 0.0 and d.durum == "kapali"
        assert d.ozet()["not"] == d.gecis_notu and d.ozet()["motor"] == "hafif"
        for _ in range(20):
            if baslatildi:
                break
            time.sleep(0.05)
        assert baslatildi, "hafif sunucu başlatılmadı"
        # bu oturumda güçlü yeniden seçilmez (motor yeniden başlasa da); kullanıcı modeli kendisi seçince sıfırlanır
        assert dogal_ses.motor_sec() == "hafif"
        dogal_ses.tercih_ayarla("guclu")  # motor her başlayışta çağırır: geçici geçişi BOZMAMALI
        assert dogal_ses.motor_sec() == "hafif"
        dogal_ses.gecici_hafifi_sifirla()
        assert dogal_ses.motor_sec() == "guclu"
        # ikinci kez çağrılırsa (zaten hafif) bir şey yapmaz; hafif motorun hatası eskisi gibi 30 sn Windows sesi
        assert d.hafife_gec("x") is False
        d.hata_oldu(RuntimeError("hafif de olmadı"))
        assert d.motor == "hafif" and d.devre_disi_kadar > time.time() + 20

        # hafif motor yoksa: eskisi gibi Windows sesine düşülür
        dogal_ses.hafif_kurulumu = lambda: None
        d2 = dogal_ses.DogalSes(adres="http://127.0.0.1:9", klasor=guclu_klasor, motor="guclu")
        d2.hata_oldu(TimeoutError("timed out"))
        assert d2.motor == "guclu" and d2.devre_disi_kadar > time.time() + 20 and not d2.gecis_notu
        dogal_ses.hafif_kurulumu = lambda: hafif

        # ---------- güçlü model yanıt veriyor ama yetişemiyor (ilk ses geç): 3 satırdan sonra hafife geçilir ----------
        class Yavas(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                self.rfile.read(int(self.headers["Content-Length"]))
                time.sleep(0.25)
                govde = (np.sin(np.arange(24000) * 0.05) * 9000).astype(np.int16).tobytes()
                self.send_response(200)
                self.send_header("Content-Length", str(len(govde)))
                self.end_headers()
                self.wfile.write(govde)

        sunucu = ThreadingHTTPServer(("127.0.0.1", 0), Yavas)
        sunucu.daemon_threads = True
        threading.Thread(target=sunucu.serve_forever, daemon=True).start()
        d3 = dogal_ses.DogalSes(adres=f"http://127.0.0.1:{sunucu.server_address[1]}", klasor=guclu_klasor, motor="guclu")
        d3.baslat = lambda *a, **k: None
        d3.YAVAS_ILK_SES_MS = 100  # sahte sunucu 250 ms'de yanıtlar: "yavaş"
        ses = {"id": "sert_erkek", "tohum": 1}
        for i in range(3):
            assert d3.motor == "guclu", f"{i}. satırda erken geçildi"
            d3.cal("Arabaya bin, polisler arkamızda.", ses, 1.0, _Sessiz())
        assert d3.motor == "hafif" and "yetişemedi" in d3.gecis_notu, (d3.motor, d3.gecis_notu, d3.ust_uste_yavas)
        # hızlı yanıt veren güçlü model yerinde kalır
        dogal_ses.gecici_hafifi_sifirla()
        d4 = dogal_ses.DogalSes(adres=f"http://127.0.0.1:{sunucu.server_address[1]}", klasor=guclu_klasor, motor="guclu")
        d4.baslat = lambda *a, **k: None
        for _ in range(4):
            d4.cal("Arabaya bin, polisler arkamızda.", ses, 1.0, _Sessiz())
        assert d4.motor == "guclu" and d4.ust_uste_yavas == 0, (d4.motor, d4.ust_uste_yavas)
        sunucu.shutdown()

        # ---------- ses denemesi: altyazı çalışırken yapılmaz; canlı güçlü sunucu deneme başlamadan kapatılır ----------
        class SahteMotor:
            durum = "calisiyor"

        uyg = uygulama.Uygulama.__new__(uygulama.Uygulama)
        uyg.ayar, uyg.motor = {"dublaj": {"seviye": 1.0}}, SahteMotor()
        try:
            uyg.ses_deneme_dinle({"id": "omnivoice"})
            raise AssertionError("altyazı çalışırken deneme yapıldı")
        except RuntimeError as e:
            assert "Durdur" in str(e), e

        durdurulan = []

        class SahteCanli:
            motor, surec = "guclu", object()

            def durdur(self):
                durdurulan.append(1)
                self.surec = None

        class OlenSurec:
            returncode = 1

            def poll(self):
                return 1

        sd_asil = (ses_deneme.motor_klasoru, ses_deneme.model_yolu, ses_deneme.subprocess.Popen,
                   ses_deneme.dogal_ses._bizimle_kapansin, ses_deneme.dogal_ses.bos_bellek_gb, ses_deneme._ayar_yaz)
        try:
            dogal_ses._paylasilan = SahteCanli()
            ses_deneme.motor_klasoru = lambda: guclu_klasor
            ses_deneme.model_yolu = lambda m: "model.gguf"
            ses_deneme._ayar_yaz = lambda m, yol, sesler: "ayar.json"
            ses_deneme.subprocess.Popen = lambda *a, **k: OlenSurec()
            ses_deneme.dogal_ses._bizimle_kapansin = lambda s: None
            ses_deneme.dogal_ses.bos_bellek_gb = lambda: 20.0
            try:
                ses_deneme._baslat(ses_deneme._MODEL["omnivoice"], bekle_sn=3)
                raise AssertionError("ölen süreçle başladı sayıldı")
            except RuntimeError as e:
                assert "yüklenemedi" in str(e), e
            assert durdurulan == [1], "deneme başlamadan canlı güçlü ses sunucusu kapatılmadı"
        finally:
            (ses_deneme.motor_klasoru, ses_deneme.model_yolu, ses_deneme.subprocess.Popen,
             ses_deneme.dogal_ses._bizimle_kapansin, ses_deneme.dogal_ses.bos_bellek_gb, ses_deneme._ayar_yaz) = sd_asil
            ses_deneme.kapat()

        # ---------- okuyan ses değişince bir kez günlüğe yazılır ----------
        import seslendirme
        s = seslendirme.Seslendirici.__new__(seslendirme.Seslendirici)
        s.dogal = d2
        s._okuyan("dogal:guclu")
        s._okuyan("dogal:guclu")
        s._okuyan("windows")
        assert s.son_okuyan == "windows"
    finally:
        dogal_ses.hafif_kurulumu, dogal_ses.kurulum_klasoru = asil[0], asil[1]
        dogal_ses.tercih_ayarla(asil[2])
        dogal_ses._paylasilan = asil[3]
        dogal_ses.gecici_hafifi_sifirla()
    print("  ✓ ses yedeği: güçlü model yetişemeyince hafif doğal sese geçiliyor; deneme ile canlı ses ekran kartını paylaşmıyor")


if __name__ == "__main__":
    test_ses_yedek()
