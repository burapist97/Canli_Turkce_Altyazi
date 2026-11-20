"""Hafif doğal ses sunucusu: Pocket TTS Turkish. Ekran kartı istemez, tek işlemci çekirdeğiyle çalışır.

Ana uygulama (dogal_ses.py) bunu AYRI SÜREÇ olarak başlatır ve yerel HTTP ile konuşur. Neden ayrı süreç:
- PyTorch ile ana uygulamadaki CTranslate2 aynı OpenMP kitaplığını (libiomp5md.dll) ayrı ayrı getirir; aynı
  süreçte iki kopya çakışır.
- Model belleği (~2 GB) ana uygulamadan ayrı durur; sunucu çökerse altyazı ve Windows sesi çalışmaya devam eder.
Bu dosya ana uygulamanın ortamında (.venv) DEĞİL, .venv-ses ortamında çalışır ve ayrı derlenir (paket\\HafifSes.spec).

    cta_ses.exe --model <klasör> --sesler <klasör> [--port 38767]

GET  /health           -> {"status": "ok" | "loading" | "error", "motor": "pocket-tts-turkish", "sample_rate": 24000,
                           "voices": [...], "hazir_ses": n, "hata": ""}
                          "ok": model yüklendi, her cinsiyetin ilk sesi hazır; kalan sesler arka planda hazırlanır
                          (hazir_ses artar), henüz hazırlanmamış sesle gelen istek o sesi kendisi hazırlar (~1 sn).
POST /v1/audio/speech  {"input": metin, "voice": ses kimliği, "seed": sayı, "duygu": isteğe bağlı}
                       -> 16 bit mono PCM akışı (sample_rate Hz); üretildikçe gönderilir. İstemci bağlantıyı
                          kapatırsa üretim durur. Aynı anda tek üretim yapılır (istekler sıraya girer).

Sesler (--sesler klasörü, her ses için <kimlik>\\ses.json):
  {"hazir": "male_1"}            modelin kendi hazır sesi (yapay; metin tarifinden tasarlanmış)
  {"referans": "referans.wav"}   kısa bir kayıttan kopyalanan ses. Yalnızca KENDİ tasarladığımız yapay seslerin
                                 kayıtları konur; gerçek bir kişinin sesi kopyalanmaz.
Model: wite-tech/pocket-tts-turkish (ağırlıklar CC-BY-4.0, Kyutai Pocket TTS'ten türetilmiş); kod Apache-2.0 / MIT.
"""
import argparse
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Model yerel klasörden yüklenir. Kitaplıklar hiçbir koşulda internete çıkmasın (indirme, sürüm denetimi, kullanım
# ölçümü): çevrimdışı kipte bir indirme denemesi sessizce ağa gitmek yerine hemen hata verir.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

MOTOR = "pocket-tts-turkish"


class Durum:
    tts = None          # pocket_tts_turkish.TurkishTTS (yüklenince)
    acik = False        # model yüklendi ve ilk sesler hazır: /health "ok" der
    hata = ""
    ornek_hizi = 24000
    sesler = {}         # kimlik -> {"hazir": "male_1"} ya da {"referans": yol}; ayrıca "cinsiyet", "sira"
    adlar = {}          # kimlik -> modele verilecek ses adı (hazırlanmış olanlar)
    kilit = threading.Lock()  # ses hazırlama (kopyalama) sıraya girsin
    bekleyen = 0        # şu an işlenen okuma isteği sayısı: arka plandaki ses hazırlığı bunlara yol verir
    sayac = threading.Lock()


D = Durum()


def gunluk(*a):
    try:
        print(time.strftime("%H:%M:%S"), *a, flush=True)
    except Exception:
        pass  # çıkış akışı yoksa (penceresiz başlatma) sessizce geç


def sesleri_oku(klasor):
    sesler = {}
    if not klasor or not os.path.isdir(klasor):
        return sesler
    for kimlik in sorted(os.listdir(klasor)):
        yol = os.path.join(klasor, kimlik, "ses.json")
        if not os.path.isfile(yol):
            continue
        try:
            with open(yol, encoding="utf-8") as f:
                k = json.load(f)
        except (OSError, ValueError) as e:
            gunluk(f"{yol} okunamadı: {e}")
            continue
        if k.get("hazir"):
            ses = {"hazir": str(k["hazir"])}
        else:
            ref = os.path.join(klasor, kimlik, k.get("referans") or "referans.wav")
            if not os.path.isfile(ref):
                gunluk(f"{kimlik}: referans kaydı yok ({ref})")
                continue
            ses = {"referans": ref}
        ses["cinsiyet"] = "kadin" if k.get("cinsiyet") == "kadin" else "erkek"
        try:
            ses["sira"] = int(k.get("sira", 999))
        except (TypeError, ValueError):
            ses["sira"] = 999
        sesler[kimlik] = ses
    return sesler


def hazirlik_sirasi(sesler):
    """Seslerin hazırlanma sırası: (ilkler, sonrakiler). İlkler her cinsiyetin 1. sesidir; uygulama ilk tanıdığı
    erkeğe ve kadına onları verir (dogal_ses.ses_esle), o yüzden sunucu "hazır" demeden önce hazırlanırlar.
    Sonrakiler kullanılma sırasıyla (2. erkek, 2. kadın, …) arka planda hazırlanır."""
    sirali = sorted(sesler, key=lambda k: (sesler[k]["sira"], k))
    ilkler = []
    for cins in ("erkek", "kadin"):
        ilk = next((k for k in sirali if sesler[k]["cinsiyet"] == cins), None)
        if ilk:
            ilkler.append(ilk)
    return ilkler, [k for k in sirali if k not in ilkler]


def ses_adi(kimlik):
    """Ses kimliği -> modelin tanıdığı ses adı; gerekiyorsa ses ilk kullanımda hazırlanır."""
    tts = D.tts
    if kimlik in D.adlar:
        return D.adlar[kimlik]
    with D.kilit:
        if kimlik in D.adlar:
            return D.adlar[kimlik]
        s = D.sesler.get(kimlik)
        if s is None:
            if kimlik in tts.voices:  # doğrudan hazır ses adı da kabul edilir (deneme için)
                ad = kimlik
            elif not kimlik:
                ad = tts.default_voice
            else:
                raise KeyError(f"bilinmeyen ses: {kimlik}")
        elif "hazir" in s:
            if s["hazir"] not in tts.voices:
                raise KeyError(f"modelde {s['hazir']} sesi yok")
            ad = s["hazir"]
        else:
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")  # "duraklama bulunamadı" uyarısı: kayıt yine kullanılır
                ad = tts.voice_from_file(s["referans"], name="ozel_" + kimlik)
        D.adlar[kimlik] = ad
        return ad


def ses_hazirla(kimlik, uret=False):
    """Sesi ilk satırdan önce hazırlar (yoksa o sesle okunan ilk satır ~1 sn geç başlar). Kopyalanan sesin durumu
    ses_adi içinde hesaplanır; modelin hazır sesininki ilk üretimde hesaplandığı için kısa bir üretim yaptırılır."""
    try:
        ad = ses_adi(kimlik)
        if uret or "hazir" in D.sesler.get(kimlik, {}):
            for _ in D.tts.stream("Evet.", voice=ad, seed=1):
                pass
    except Exception as e:
        gunluk(f"{kimlik} sesi hazırlanamadı: {e}")


def turkce_yol_duzeltmesi():
    """sentencepiece Windows'ta Türkçe (ASCII dışı) karakter içeren yoldaki dosyayı açamıyor ("NOT_FOUND"). Kurulum
    klasöründe kullanıcı adı geçer ("C:\\Users\\Şükrü\\..."), yani böyle bilgisayarlarda model hiç yüklenmezdi. Pocket
    TTS sözcük ayırıcıyı yoluyla açtığı için sınıf sarılır: dosyayı Python okur, kitaplığa içeriği verilir.
    (Model ayarı için ayrıca UTF-8 kipi gerekir: paket\\HafifSes.spec "X utf8".)"""
    import sentencepiece
    asil = sentencepiece.SentencePieceProcessor
    if getattr(asil, "_cta_sarili", False):
        return

    class Islemci(asil):
        _cta_sarili = True

        def __init__(self, model_file=None, model_proto=None, **kw):
            if model_file is not None and model_proto is None:
                with open(model_file, "rb") as f:
                    model_file, model_proto = None, f.read()
            super().__init__(model_file=model_file, model_proto=model_proto, **kw)

    sentencepiece.SentencePieceProcessor = Islemci


def yukle(model_klasoru, sesler_klasoru):
    """Modeli yükler (birkaç saniye) ve her cinsiyetin ilk sesini hazırlar; ondan sonra "hazır" der. Kalan sesler
    arka planda hazırlanır (her biri ~0,5-1 sn); o sırada gelen okuma isteklerine yol verilir."""
    try:
        t0 = time.time()
        from pocket_tts_turkish import TurkishTTS
        # içe aktarmadan SONRA: derlenmiş halde sentencepiece, PyTorch'tan önce yüklenirse DLL'ini bulamıyor
        turkce_yol_duzeltmesi()
        tts = TurkishTTS.from_pretrained(model_klasoru, device="cpu")
        D.ornek_hizi = int(tts.sample_rate)
        D.sesler = sesleri_oku(sesler_klasoru)
        D.tts = tts
        gunluk(f"model yüklendi ({time.time() - t0:.1f} sn); sesler: {list(D.sesler) or tts.voices}")
        ilkler, sonrakiler = hazirlik_sirasi(D.sesler)
        for i, kimlik in enumerate(ilkler):
            ses_hazirla(kimlik, uret=not i)  # ilk üretim modeli de ısıtır
        if not D.sesler:  # ses tanımı yok (deneme): modelin varsayılan sesiyle ısıt
            for _ in tts.stream("Evet.", seed=1):
                pass
    except Exception as e:
        D.hata = f"{type(e).__name__}: {e}"
        gunluk("model yüklenemedi:", D.hata)
        return
    D.acik = True
    gunluk(f"hazır ({time.time() - t0:.1f} sn); ilk sesler: {ilkler}")
    for kimlik in sonrakiler:
        while D.bekleyen:  # okunacak satır varken araya girme (model aynı anda tek iş yapar)
            time.sleep(0.05)
        ses_hazirla(kimlik)
    gunluk(f"{len(D.adlar)} ses hazır ({time.time() - t0:.1f} sn)")


class Isleyici(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, kod, nesne):
        govde = json.dumps(nesne, ensure_ascii=False).encode("utf-8")
        self.send_response(kod)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(govde)))
        self.end_headers()
        self.wfile.write(govde)

    def do_GET(self):
        if self.path.split("?")[0] != "/health":
            return self._json(404, {"error": "bilinmeyen adres"})
        durum = "ok" if D.acik else ("error" if D.hata else "loading")
        self._json(200, {"status": durum, "motor": MOTOR, "sample_rate": D.ornek_hizi, "voices": list(D.sesler),
                         "hazir_ses": len(D.adlar), "hata": D.hata})

    def do_POST(self):
        if self.path.split("?")[0] != "/v1/audio/speech":
            return self._json(404, {"error": "bilinmeyen adres"})
        try:
            govde = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        except ValueError:
            return self._json(400, {"error": "istek anlaşılamadı"})
        if D.tts is None:
            return self._json(503, {"error": D.hata or "model yükleniyor"})
        metin = str(govde.get("input") or "").strip()
        if not metin:
            return self._json(400, {"error": "okunacak metin yok"})
        tohum = govde.get("seed")
        try:
            tohum = int(tohum) if tohum is not None else None
        except (TypeError, ValueError):
            tohum = None
        with D.sayac:
            D.bekleyen += 1  # arka plandaki ses hazırlığı bu istek bitene kadar yeni işe başlamaz
        try:
            self._oku(metin, str(govde.get("voice") or ""), govde.get("duygu") or None, tohum)
        finally:
            with D.sayac:
                D.bekleyen -= 1

    def _oku(self, metin, ses, duygu, tohum):
        try:
            ad = ses_adi(ses)
        except Exception as e:
            return self._json(400, {"error": str(e)})
        akis = None
        for d in (duygu, None):  # bilinmeyen duygu etiketi: düz sesle oku
            try:
                akis = D.tts.stream(metin, voice=ad, emotion=d, seed=tohum)
                break
            except ValueError as e:
                hata = str(e)
        if akis is None:
            return self._json(400, {"error": hata})

        import numpy as np
        t0, ornek, ilk = time.time(), 0, None
        self.send_response(200)
        self.send_header("Content-Type", "audio/pcm")
        self.send_header("X-Sample-Rate", str(D.ornek_hizi))
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        try:
            for parca in akis:
                if ilk is None:
                    ilk = time.time() - t0
                ornek += len(parca)
                self.wfile.write((np.clip(parca, -1.0, 1.0) * 32767.0).astype("<i2").tobytes())
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            pass  # istemci dinlemeyi bıraktı (yeni satır geldi): üretim aşağıda durdurulur
        except Exception as e:
            gunluk(f"üretim hatası: {type(e).__name__}: {e}")
        finally:
            akis.close()
        sure = ornek / D.ornek_hizi
        if sure:
            gunluk(f"{len(metin)} harf -> {sure:.1f} sn ses, {time.time() - t0:.2f} sn'de, ilk ses {int((ilk or 0) * 1000)} ms "
                   f"({ses or 'varsayılan'})")


def main():
    ap = argparse.ArgumentParser(description="Hafif doğal ses sunucusu (Pocket TTS Turkish)")
    ap.add_argument("--model", required=True, help="model klasörü (config.yaml, model.safetensors, tokenizer.model, voices)")
    ap.add_argument("--sesler", default="", help="ses tanımları klasörü (<kimlik>\\ses.json)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=38767)
    a = ap.parse_args()
    for akis in (sys.stdout, sys.stderr):  # günlük dosyası UTF-8 olsun (derlenmiş halde ortam değişkenleri etkisiz)
        try:
            akis.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    try:
        sunucu = ThreadingHTTPServer((a.host, a.port), Isleyici)
    except OSError as e:
        gunluk(f"{a.port} numaralı kapı açılamadı: {e}")
        return 2
    sunucu.daemon_threads = True
    threading.Thread(target=yukle, args=(a.model, a.sesler), daemon=True).start()
    gunluk(f"hafif ses sunucusu http://{a.host}:{a.port} (model yükleniyor)")
    try:
        sunucu.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
