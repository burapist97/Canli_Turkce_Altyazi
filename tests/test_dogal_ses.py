"""Doğal ses istemcisi (dogal_ses.py) ve Seslendirici'nin ona bağlanışı — sahte audio.cpp sunucusuyla.

Sahte sunucu /health ve akışlı /v1/audio/speech (ham 16 bit PCM, parça parça) verir; her ses
farklı frekansta bir ton üretir, böylece hangi sesin seçildiği çalınan sesten anlaşılır.
Kontrol: ses kataloğu, profil -> doğal ses eşlemesi (kadına kadın), akış, sunucu çökünce
Windows sesine düşme ve 30 sn bekleme.

test_hafif_istemci: uygulamayla gelen hafif motorun (Pocket TTS) istemci tarafı, sahte sunucuyla (gerçek model
tests/test_hafif_ses.py'de): motor seçimi, 24 kHz, pakette gelen ölçümlerle ısınmasız açılış, konuşana uydurmanın bu
ölçümlerle kurulması, yanlış motorun sunucusunu kullanmama, aynı anda iki başlatmada tek sunucu, model hatası.
"""
import json
import os
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np

import yardimci  # noqa: F401
import dogal_ses
import seslendirme

FREKANS = {"kadin_genc": 600, "kadin_olgun": 500, "erkek_sert": 150, "erkek_genc": 220}


class _Sahte(BaseHTTPRequestHandler):
    istekler = []
    bozuk = False
    kisa = False  # uzun cümleye çok kısa ses (modelin erken kesmesi)

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == "/health":
            govde = json.dumps({"status": "ok"}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(govde)))
            self.end_headers()
            self.wfile.write(govde)
        else:
            self.send_error(404)

    def do_POST(self):
        istek = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _Sahte.istekler.append(istek)
        if _Sahte.bozuk:
            self.send_error(500, "model çöktü")
            return
        f = FREKANS[istek["voice"]]
        t = np.arange(int(48000 * (0.2 if _Sahte.kisa else 0.6))) / 48000
        pcm = (0.3 * np.sin(2 * np.pi * f * t) * 32767).astype(np.int16).tobytes()
        self.send_response(200)
        self.send_header("Content-Type", "audio/pcm")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        for i in range(0, len(pcm), 9600):  # parça parça (akış)
            p = pcm[i:i + 9600]
            self.wfile.write(f"{len(p):X}\r\n".encode() + p + b"\r\n")
            self.wfile.flush()
            time.sleep(0.01)
        self.wfile.write(b"0\r\n\r\n")


class _SahteOynatici:
    def __init__(self):
        self.parcalar = []

    def cal(self, x):
        self.parcalar.append(x.copy())

    def bitir(self):
        pass

    def baskin_frekans(self):
        x = np.concatenate(self.parcalar)
        F = np.abs(np.fft.rfft(x))
        return float(np.fft.rfftfreq(len(x), 1 / 48000)[np.argmax(F)])


def _paket(klasor):
    os.makedirs(os.path.join(klasor, "sesler"))
    with open(os.path.join(klasor, "paket.json"), "w", encoding="utf-8") as f:
        json.dump({"backend": "vulkan"}, f)
    for ad, cins in (("kadin_genc", "kadin"), ("kadin_olgun", "kadin"), ("erkek_sert", "erkek"), ("erkek_genc", "erkek")):
        os.makedirs(os.path.join(klasor, "sesler", ad))
        with open(os.path.join(klasor, "sesler", ad, "ses.json"), "w", encoding="utf-8") as f:
            json.dump({"gorunen_ad": ad, "cinsiyet": cins, "referans_metni": "Merhaba.", "tohum": 7}, f)


def test_dogal_ses():
    sunucu = ThreadingHTTPServer(("127.0.0.1", 0), _Sahte)
    threading.Thread(target=sunucu.serve_forever, daemon=True).start()
    klasor = tempfile.mkdtemp()
    _paket(klasor)
    d = dogal_ses.DogalSes(adres=f"http://127.0.0.1:{sunucu.server_port}", klasor=klasor)
    assert [s["id"] for s in d.sesler] == ["erkek_genc", "erkek_sert", "kadin_genc", "kadin_olgun"]
    assert d.baslat(5), d.hata
    assert not d.kullanilabilir() or d.isinma_bitti
    for _ in range(100):  # sesler ısınana kadar (sahte sunucuda anlık) doğal ses kullanılmaz
        if d.kullanilabilir():
            break
        time.sleep(0.05)
    assert d.kullanilabilir() and len(d.ornekler) == 4, (d.hata, list(d.ornekler))

    # sunucu ayarı: her ses bir ön ayar, referans ve metniyle
    yol = dogal_ses.sunucu_ayari_yaz(klasor, d.sesler, 39999)
    with open(yol, encoding="utf-8") as f:
        a = json.load(f)
    m = a["models"][0]
    assert a["port"] == 39999 and m["family"] == "voxcpm2" and m["mode"] == "streaming"
    assert set(m["voice_presets"]) == set(FREKANS) and m["voice_presets"]["kadin_genc"]["reference_text"] == "Merhaba."

    # eşleme: kadın profili kadın sesine, erkek profili erkek sesine; aynı profil hep aynı ses
    assert d.ses_esle("kadin1")["cinsiyet"] == "kadin" and d.ses_esle("kadin2")["id"] != d.ses_esle("kadin1")["id"]
    assert d.ses_esle("erkek1")["cinsiyet"] == "erkek" and d.ses_esle("erkek3")["id"] == d.ses_esle("erkek1")["id"]

    # akış + Seslendirici: kadın satırı kadın doğal sesiyle (600/500 Hz) çalınır, Windows sesi kullanılmaz
    windows = []
    s = seslendirme.Seslendirici({"hiz": 1.2, "karakter_sesleri": False, "profil": "kadin1"},
                                 cal=windows.append, dogal=d)
    oynatici = _SahteOynatici()
    s._dogal_oynatici = oynatici
    s.soyle("MIA: Arabaya bin.", en="MIA: Get in the car.")
    for _ in range(100):
        if s.okunan:
            break
        time.sleep(0.05)
    assert s.okunan == 1 and not windows, (s.okunan, len(windows), s.hata)
    assert _Sahte.istekler[-1]["input"] == "Arabaya bin." and _Sahte.istekler[-1]["voice"] == "kadin_genc"
    assert _Sahte.istekler[-1]["options"] == {"retry_badcase": False} and _Sahte.istekler[-1]["seed"] == 7
    assert abs(oynatici.baskin_frekans() - 600) < 10, oynatici.baskin_frekans()
    assert d.son_gecikme_ms is not None and d.son_hiz is not None
    print(f"  ✓ doğal ses: kadın satırı kadın sesiyle akışla çalındı (ilk parça {d.son_gecikme_ms} ms)")

    # model uzun cümleyi erken keserse: o satır Windows sesiyle, doğal ses kapanmaz
    _Sahte.kisa = True
    s.soyle("Bak, sana son kez söylüyorum, bu iş göründüğü kadar kolay değil.", en="Look.")
    for _ in range(100):
        if s.okunan >= 2:
            break
        time.sleep(0.05)
    _Sahte.kisa = False
    assert s.okunan == 2 and len(windows) == 1 and d.kullanilabilir(), (s.okunan, len(windows), d.hata)
    print("  ✓ doğal ses: erken kesilen cümle Windows sesiyle okundu, doğal ses açık kaldı")
    windows.clear()
    s.okunan = 1

    # sunucu bozulursa: satır Windows sesiyle okunur, doğal ses 30 sn devre dışı
    _Sahte.bozuk = True
    s.soyle("Sakin ol.", en="Relax.")
    for _ in range(100):
        if s.okunan >= 2:
            break
        time.sleep(0.05)
    assert s.okunan == 2 and len(windows) == 1, (s.okunan, len(windows))
    assert not d.kullanilabilir() and "Doğal ses" in d.hata
    s.durdur()
    sunucu.shutdown()
    print("  ✓ doğal ses: sunucu hata verince satır Windows sesiyle okundu, 30 sn sonra yeniden denenecek")


class _SahteHafif(BaseHTTPRequestHandler):
    """Hafif sunucunun (hafif_ses/sunucu.py) arayüzü: /health kendini tanıtır, 24 kHz PCM verir."""
    durum = "ok"
    hata = ""
    istekler = []

    def log_message(self, *a):
        pass

    def do_GET(self):
        govde = json.dumps({"status": _SahteHafif.durum, "motor": "pocket-tts-turkish", "sample_rate": 24000,
                            "voices": ["tarik", "elif"], "hazir_ses": 2, "hata": _SahteHafif.hata}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(govde)))
        self.end_headers()
        self.wfile.write(govde)

    def do_POST(self):
        istek = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _SahteHafif.istekler.append(istek)
        if istek.get("voice") not in ("tarik", "elif"):
            self.send_error(400, "bilinmeyen ses")
            return
        t = np.arange(int(24000 * 0.8)) / 24000
        pcm = (0.3 * np.sin(2 * np.pi * {"tarik": 110, "elif": 230}[istek["voice"]] * t) * 32767).astype(np.int16).tobytes()
        self.send_response(200)
        self.send_header("Content-Type", "audio/pcm")
        self.send_header("Connection", "close")
        self.end_headers()
        for i in range(0, len(pcm), 4800):
            self.wfile.write(pcm[i:i + 4800])
            self.wfile.flush()
            time.sleep(0.005)


class _SahteSurec:
    """Başlatılmış ses sunucusu süreci (gerçek süreç açmadan)."""

    def __init__(self):
        self.kapandi = False
        self.returncode = None

    def poll(self):
        return 0 if self.kapandi else None

    def terminate(self):
        self.kapandi = True

    kill = terminate

    def wait(self, *a):
        return 0


def _hafif_paket(klasor):
    """Hafif motorun ses klasörü: iki ses + hazır ölçümler (sesler/uyum.json)."""
    import ses_uyum
    rng = np.random.default_rng(3)
    uyum = {}
    for ad, cins, perde, sira in (("tarik", "erkek", 110.0, 1), ("elif", "kadin", 230.0, 1)):
        os.makedirs(os.path.join(klasor, "sesler", ad))
        with open(os.path.join(klasor, "sesler", ad, "ses.json"), "w", encoding="utf-8") as f:
            json.dump({"gorunen_ad": ad.title(), "cinsiyet": cins, "hazir": "male_1", "tohum": 5, "sira": sira}, f)
        uyum[ad] = {f"{o:g}": {"iz": [round(float(v), 5) for v in rng.normal(size=192)], "perde": round(perde * o, 2)}
                    for o in ses_uyum.KAYDIRMALAR}
    with open(os.path.join(klasor, "sesler", "uyum.json"), "w", encoding="utf-8") as f:
        json.dump({"sesler": uyum}, f)


def test_hafif_istemci():
    import ses_uyum

    # --- motor seçimi: hafif varsayılan; güçlü yalnız seçildiyse ve kuruluysa ---
    asil = dogal_ses.hafif_kurulumu, dogal_ses.kurulum_klasoru, dogal_ses._tercih
    try:
        for hafif, guclu, tercih, beklenen in ((True, True, "otomatik", "hafif"), (True, True, "guclu", "guclu"),
                                                (True, False, "guclu", "hafif"), (False, True, "otomatik", "guclu"),
                                                (False, True, "hafif", "guclu"), (False, False, "otomatik", None)):
            dogal_ses.hafif_kurulumu = lambda h=hafif: {"kok": "x"} if h else None
            dogal_ses.kurulum_klasoru = lambda g=guclu: "y" if g else None
            dogal_ses.tercih_ayarla(tercih)
            assert dogal_ses.motor_sec() == beklenen, (hafif, guclu, tercih, dogal_ses.motor_sec())
            assert dogal_ses.var_mi() == (beklenen is not None)
        dogal_ses.tercih_ayarla("saçma")
        assert dogal_ses._tercih == "otomatik"
    finally:
        dogal_ses.hafif_kurulumu, dogal_ses.kurulum_klasoru = asil[0], asil[1]
        dogal_ses.tercih_ayarla(asil[2])
    print("  ✓ hafif motor: varsayılan hafif; güçlü yalnız seçilip kuruluysa; hiçbiri yoksa doğal ses yok")

    sunucu = ThreadingHTTPServer(("127.0.0.1", 0), _SahteHafif)
    threading.Thread(target=sunucu.serve_forever, daemon=True).start()
    adres = f"http://127.0.0.1:{sunucu.server_port}"
    klasor = tempfile.mkdtemp()
    _hafif_paket(klasor)

    def istemci():
        d = dogal_ses.DogalSes(adres=adres, motor="hafif")  # testte gerçek motor yok: klasörü elle ver
        d.klasor, d.sesler = klasor, dogal_ses.sesleri_oku(klasor)
        return d

    # --- açık sunucu: 24 kHz öğrenilir; ölçümler pakette olduğu için ısıtma isteği atılmaz, hemen kullanılır ---
    _SahteHafif.durum, _SahteHafif.istekler = "ok", []
    d = istemci()
    assert d.ornek_hizi == 24000 and [x["id"] for x in d.sesler] == ["elif", "tarik"]
    assert d.baslat(5), d.hata
    for _ in range(40):
        if d.kullanilabilir():
            break
        time.sleep(0.05)
    assert d.kullanilabilir() and not d.ornekler and not _SahteHafif.istekler, (d.hata, _SahteHafif.istekler)
    assert d.ornek_hizi == 24000 and d.sunucu_hazir_ses == 2
    assert set(d.uyum_verisi()) == {"tarik", "elif"}
    ozet = d.ozet()
    assert ozet["motor"] == "hafif" and ozet["durum"] == "hazir" and ozet["ses_sayisi"] == 2, ozet

    # akış 24 kHz sayılır: 0,8 sn'lik ses 0,8 sn olarak ölçülür (48 kHz sanılsa 0,4 çıkardı)
    oynatici = _SahteOynatici()
    sure = d.cal("Arabaya bin.", d.ses_esle("erkek1"), 1.0, oynatici)
    x = np.concatenate(oynatici.parcalar)
    tepe = float(np.fft.rfftfreq(len(x), 1 / 24000)[np.argmax(np.abs(np.fft.rfft(x)))])
    assert abs(sure - 0.8) < 0.02 and abs(tepe - 110) < 5, (sure, tepe)
    assert _SahteHafif.istekler[-1]["voice"] == "tarik" and _SahteHafif.istekler[-1]["seed"] == 5
    print("  ✓ hafif motor: 24 kHz, ölçümler paketten (ısıtma yok), açılır açılmaz okudu")

    # --- konuşana uydurma, pakette gelen ölçümlerle kurulur; ses havuzu motorun ses sayısına göre ---
    class _Tanici:  # konusmaci.KonusmaciTanici'nin Seslendirici'nin kullandığı kadarı
        def __init__(self):
            self.uyumlayici, self.havuz = "eski", None

        def havuz_ayarla(self, erkek, kadin):
            self.havuz = (erkek, kadin)

        def profiller(self):
            return [f"erkek{i}" for i in range(1, self.havuz[0] + 1)] + [f"kadin{i}" for i in range(1, self.havuz[1] + 1)]

    s = seslendirme.Seslendirici.__new__(seslendirme.Seslendirici)  # okuma döngüsü başlatılmadan
    s.tanici, s.ayar, s.dogal, s.oyun_sesi = _Tanici(), {"dogal_ses": True}, d, None
    s._uyumlayici_kur(None)
    u = s.tanici.uyumlayici
    assert s.tanici.havuz == (1, 1) and isinstance(u, ses_uyum.Uyumlayici) and s.uyum_kaynagi == "dogal"
    assert len(u.adaylar) == 2 * len(ses_uyum.KAYDIRMALAR) and u.cinsiyet == {"erkek1": "erkek", "kadin1": "kadin"}
    assert abs(u.perde("erkek1", 1.0) - 110) < 0.1 and abs(u.perde("kadin1", 1.12) - 230 * 1.12) < 0.1
    assert u.sec(None, 100.0, "erkek")[:2] == ("erkek1", 0.88) and u.sec(None, 250.0, "kadin")[:2] == ("kadin1", 1.06)
    # doğal ses kapatılırsa Windows sesinin havuzuna (4 erkek + 3 kadın) dönülür
    s.ayar["dogal_ses"] = False
    s._uyumlayici_kur(None)
    assert s.tanici.havuz == (4, 3) and s.tanici.uyumlayici is None
    print("  ✓ hafif motor: konuşana uydurma pakette gelen ölçümlerle kuruldu, ses havuzu motorun seslerine göre")

    # --- kapıda öteki motorun sunucusu varsa kullanılmaz (programın başka bir kopyası açık olabilir) ---
    guclu_klasor = tempfile.mkdtemp()
    _paket(guclu_klasor)
    g = dogal_ses.DogalSes(adres=adres, klasor=guclu_klasor)
    assert g.motor == "guclu" and not g.saglik()
    baslatilan = []
    g._sureci_baslat = lambda: baslatilan.append(1)
    assert not g.baslat(2) and g.durum == "hata" and "başka bir program" in g.hata and not baslatilan, (g.durum, g.hata)
    guclu_sunucu = ThreadingHTTPServer(("127.0.0.1", 0), _Sahte)
    threading.Thread(target=guclu_sunucu.serve_forever, daemon=True).start()
    h = dogal_ses.DogalSes(adres=f"http://127.0.0.1:{guclu_sunucu.server_port}", motor="hafif")
    assert not h.saglik()
    guclu_sunucu.shutdown()
    print("  ✓ hafif motor: kapıdaki öteki motorun sunucusu kullanılmadı, neden anlaşılır yazıldı")

    # --- panel ve motor aynı anda başlatırsa tek sunucu açılır, ikisi de onu bekler ---
    _SahteHafif.durum = "loading"
    d2 = istemci()
    sayac = []

    def sahte_baslat():
        sayac.append(1)
        d2.surec = _SahteSurec()
    d2._sureci_baslat, d2._kapi_dolu = sahte_baslat, lambda: False
    sonuclar = []
    isler = [threading.Thread(target=lambda: sonuclar.append(d2.baslat(10))) for _ in range(2)]
    for i in isler:
        i.start()
    time.sleep(0.8)
    assert d2.durum == "basliyor" and len(sayac) == 1 and not d2.kullanilabilir(), (d2.durum, sayac)
    assert d2.ozet()["durum"] == "basliyor"
    _SahteHafif.durum = "ok"
    for i in isler:
        i.join(10)
    assert sonuclar == [True, True] and len(sayac) == 1 and d2.durum == "hazir", (sonuclar, sayac, d2.durum)
    surec = d2.surec
    d2.durdur()
    assert surec.kapandi and d2.durum == "kapali" and not d2.kullanilabilir()
    print("  ✓ hafif motor: aynı anda iki başlatmada tek sunucu açıldı")

    # --- sunucu açıldı ama modeli yükleyemedi: nedeni kullanıcıya, süreç kapatılır ---
    _SahteHafif.durum, _SahteHafif.hata = "error", "FileNotFoundError: model.safetensors"
    d3 = istemci()
    d3._kapi_dolu = lambda: False
    d3._sureci_baslat = lambda: setattr(d3, "surec", _SahteSurec())
    assert not d3.baslat(5) and d3.durum == "hata" and "model.safetensors" in d3.hata and d3.surec is None, (d3.durum, d3.hata)
    _SahteHafif.durum, _SahteHafif.hata = "ok", ""
    sunucu.shutdown()
    print("  ✓ hafif motor: model yüklenemeyince neden gösterildi, sunucu kapatıldı")


if __name__ == "__main__":
    test_dogal_ses()
    test_hafif_istemci()
