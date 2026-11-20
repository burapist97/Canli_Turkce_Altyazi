"""Ses motorlarını karşılaştırma (ses_deneme.py) — gerçek motor ve model olmadan:
- model indirme: kaldığı yerden sürme, SHA-256 denetimi, bozuk dosyanın silinmesi (yerel sahte depo)
- üretim isteği: modele göre doğru alanlar (Türkçe dil, duygu sınırı, ses ön ayarı), WAV / ham PCM çözme, ölçüm
- motor yokken ve bellek yetmezken anlaşılır hata
Gerçek modellerle deneme elle yapılır (Seslendirme > Ses motorlarını karşılaştır); hiçbir test ses çalmaz.
"""
import hashlib
import io
import json
import os
import tempfile
import threading
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np

import yardimci  # noqa: F401


def _wav(hz=24000, sn=0.5):
    x = (np.sin(np.arange(int(hz * sn)) * 0.05) * 12000).astype(np.int16)
    tampon = io.BytesIO()
    with wave.open(tampon, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(hz)
        w.writeframes(x.tobytes())
    return tampon.getvalue()


def _sunucu(isleyici):
    s = ThreadingHTTPServer(("127.0.0.1", 0), isleyici)
    s.daemon_threads = True
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s


def test_ses_deneme():
    import ses_deneme as sd

    # ---------- çözme ----------
    x, hz = sd._coz(_wav(24000, 0.5))
    assert hz == 24000 and len(x) == 12000 and 0.3 < float(np.abs(x).max()) < 0.4
    x, hz = sd._coz((np.ones(480, np.int16) * 16384).tobytes() + b"\x01")  # ham PCM (tek bayt artık atılır)
    assert hz == 48000 and len(x) == 480 and abs(float(x[0]) - 0.5) < 1e-3

    # ---------- indirme (yerel sahte depo; bağlantı ilk seferde yarıda kopar) ----------
    icerik = os.urandom(300_000)
    istekler = []

    class Depo(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            bas = int((self.headers.get("Range") or "bytes=0-").split("=")[1].rstrip("-"))
            istekler.append(bas)
            govde = icerik[bas:]
            if len(istekler) == 1:
                govde = govde[:120_000]  # ilk bağlantı yarıda kalır
            self.send_response(206 if bas else 200)
            self.send_header("Content-Length", str(len(icerik) - bas))
            self.end_headers()
            try:
                self.wfile.write(govde)
            except OSError:
                pass

    depo = _sunucu(Depo)
    klasor = tempfile.mkdtemp(prefix="cta_sesmodel_")
    os.environ["CTA_SES_MODELLERI"] = klasor
    asil = (sd.DEPO, sd.MODELLER[:], dict(sd._MODEL), sd.motor_klasoru)
    try:
        sd.DEPO = f"http://127.0.0.1:{depo.server_address[1]}"
        sd.motor_klasoru = lambda: None
        iyi = {"id": "deneme", "ad": "Deneme", "aile": "omnivoice", "kip": "offline", "gereken_gb": 0.1,
               "yol": "X-GGUF/deneme.gguf", "boyut": len(icerik), "sha256": hashlib.sha256(icerik).hexdigest(),
               "aciklama": "", "lisans": ""}
        bozuk = dict(iyi, id="bozuk", yol="X-GGUF/bozuk.gguf", sha256="0" * 64)
        sd.MODELLER[:] = [iyi, bozuk]
        sd._MODEL.clear()
        sd._MODEL.update({m["id"]: m for m in sd.MODELLER})
        assert sd.model_yolu(iyi) is None
        sd._indirme["deneme"] = {"oran": 0.0, "hata": ""}
        sd._indir(iyi)
        assert sd._indirme["deneme"].get("bitti") and not sd._indirme["deneme"]["hata"], sd._indirme["deneme"]
        assert istekler[0] == 0 and istekler[1] == 120_000, f"kaldığı yerden sürmedi: {istekler}"
        assert open(sd.model_yolu(iyi), "rb").read() == icerik
        sd._indirme["bozuk"] = {"oran": 0.0, "hata": ""}
        sd._indir(bozuk)
        assert "bozuk" in sd._indirme["bozuk"]["hata"] and sd.model_yolu(bozuk) is None
        assert not os.path.exists(os.path.join(klasor, "bozuk.gguf.indiriliyor")), "bozuk dosya silinmedi"
        d = sd.durum()
        assert d["motor_var"] is False and [(m["id"], m["kurulu"]) for m in d["modeller"]] == [("deneme", True), ("bozuk", False)]
        try:
            sd.uret("deneme", "Merhaba", None)
            raise AssertionError("motor yokken hata vermedi")
        except RuntimeError as e:
            assert "bulunamadı" in str(e) or "Doğal Ses Paketi" in str(e), e
    finally:
        sd.DEPO, sd.motor_klasoru = asil[0], asil[3]
        sd.MODELLER[:] = asil[1]
        sd._MODEL.clear()
        sd._MODEL.update(asil[2])
        depo.shutdown()

    # ---------- üretim isteği (sahte ses sunucusu; gerçek motor başlatılmaz) ----------
    gelen = []

    class Ses(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            v = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            gelen.append(v)
            if v["input"] == "hata ver":
                govde, kod = b'{"error":{"message":"model patladi"}}', 500
            else:
                govde, kod = _wav(24000 if v["model"] != "voxcpm2" else 48000, 1.0), 200
            self.send_response(kod)
            self.send_header("Content-Length", str(len(govde)))
            self.end_headers()
            self.wfile.write(govde)

    ses_sunucusu = _sunucu(Ses)
    sesler = [{"id": "sert_erkek", "ad": "Kaan", "cinsiyet": "erkek", "referans": "r.wav", "referans_metni": "x", "tohum": 77},
              {"id": "genc_kadin", "ad": "Defne", "cinsiyet": "kadin", "referans": "k.wav", "referans_metni": "y", "tohum": 5}]
    asil = (sd.PORT, sd._baslat, sd.sesler, sd.dogal_ses.bos_bellek_gb, sd.motor_klasoru)
    baslatilan = []
    try:
        sd.PORT = ses_sunucusu.server_address[1]
        sd._baslat = lambda m, bekle_sn=150: baslatilan.append(m["id"])
        sd.sesler = lambda: sesler
        x, hz, o = sd.uret("chatterbox", "  Arabaya bin!  ", "genc_kadin", abarti=9)
        v = gelen[-1]
        assert hz == 24000 and o["ses_sn"] == 1.0 and o["ses"] == "Defne" and o["uretim_sn"] >= 0, o
        assert v["model"] == "chatterbox" and v["input"] == "Arabaya bin!" and v["voice"] == "genc_kadin" and v["seed"] == 5, v
        assert v["language"] == "tr" and v["options"]["language"] == "tr" and v["options"]["exaggeration"] == 1.5, v
        assert v["response_format"] == "wav" and "stream_format" not in v, v
        x, hz, o = sd.uret("voxcpm2", "", "yok_boyle_ses")  # boş metin: örnek cümle; bilinmeyen ses: ilk ses
        v = gelen[-1]
        assert hz == 48000 and v["input"] == sd.ORNEK_METIN and v["voice"] == "sert_erkek" and "language" not in v, v
        assert v["options"] == {"retry_badcase": False}, v
        assert sd.uret("omnivoice", "Selam", "sert_erkek")[2]["ses"] == "Kaan" and "exaggeration" not in gelen[-1].get("options", {})
        assert baslatilan == ["chatterbox", "voxcpm2", "omnivoice"]
        assert sd.durum()["modeller"][0]["son"]["ses_sn"] == 1.0
        for kotu, beklenen in (("hata ver", "model patladi"), ("x" * 401, "400 harf")):
            try:
                sd.uret("omnivoice", kotu, "sert_erkek")
                raise AssertionError("hata vermedi")
            except (RuntimeError, ValueError) as e:
                assert beklenen in str(e), e
        try:
            sd.uret("yok", "a", None)
            raise AssertionError("bilinmeyen model kabul edildi")
        except ValueError:
            pass

        # çalma: verilen oynatıcıya seviye uygulanmış örnekler gider (hoparlör kullanılmaz)
        class Sessiz:
            def __init__(self):
                self.parcalar, self.bitti = [], False

            def cal(self, x):
                self.parcalar.append(x)

            def bitir(self):
                self.bitti = True

        oynatici = Sessiz()
        o = sd.dinle("omnivoice", "Selam", "sert_erkek", seviye=0.5, oynatici=oynatici)
        assert oynatici.bitti and len(oynatici.parcalar[0]) == 24000 and float(np.abs(oynatici.parcalar[0]).max()) < 0.2, o

        # bellek yetmezse model başlatılmaz, nedenini söyler
        sd._baslat = asil[1]
        sd.motor_klasoru = lambda: tempfile.gettempdir()
        sd.model_yolu = (lambda eski: lambda m: "var.gguf")(sd.model_yolu)
        sd.dogal_ses.bos_bellek_gb = lambda: 1.0
        try:
            sd.uret("voxcpm2", "Selam", "sert_erkek")
            raise AssertionError("bellek yokken başlatıldı")
        except RuntimeError as e:
            assert "boş bellek yok" in str(e) and "6,0" not in str(e) and "6.0 GB" in str(e), e
    finally:
        import importlib
        sd.PORT, sd._baslat, sd.sesler, sd.dogal_ses.bos_bellek_gb, sd.motor_klasoru = asil
        ses_sunucusu.shutdown()
        sd.kapat()
        importlib.reload(sd)
    print("  ✓ ses deneme: indirme (kaldığı yerden, denetimli), modele göre istek, çözme, ölçüm, hata iletileri")


if __name__ == "__main__":
    test_ses_deneme()
