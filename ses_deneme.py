"""Ses motorlarını yan yana deneme: Seslendirme > "Ses motorlarını karşılaştır".

Üç yapay zekâ ses modeli aynı cümleyi aynı (yapay) karakter sesiyle okur; kullanıcı dinleyip karşılaştırır:
  VoxCPM2 (OpenBMB) · OmniVoice (k2-fsa) · Chatterbox çok dilli (Resemble AI)
Üçü de Doğal Ses Paketi'nin motoruyla (audio.cpp; ekran kartında Vulkan — AMD/NVIDIA/Intel) çalışır; PyTorch/CUDA
gerekmez. Modeller audio.cpp'nin yayımladığı GGUF dosyalarıdır (huggingface.co/audio-cpp/audio.cpp-gguf, sabit sürüm,
SHA-256 denetimli); paketle gelen VoxCPM2 dışındakiler istenince indirilir (veri klasörü\\ses_modelleri).

Deneme sunucusu canlı seslendirmeden AYRIDIR (kapı 38768; canlı ses sunucusu 38767): aynı anda tek model yüklüdür,
model değişince sunucu yeniden başlar, 4 dakika kullanılmazsa kapanır. Altyazı çalışırken deneme YAPILMAZ
(uygulama.ses_deneme_dinle reddeder) ve canlı güçlü ses sunucusu deneme başlamadan kapatılır: ekran kartını aynı anda
iki ses sunucusu (ya da oyun + deneme) kullanınca ekran kartı sürücüsü sıfırlanabiliyor.
"""
import hashlib
import io
import json
import os
import subprocess
import threading
import time
import urllib.error
import urllib.request
import wave

import numpy as np

import dogal_ses
import veri

PORT = 38768
DEPO = "https://huggingface.co/audio-cpp/audio.cpp-gguf/resolve/b7b9aa1f16c819c3b2d69a602b51786bdfb361a3"
BOSTA_KAPAT_SN = 240
ORNEK_METIN = "Arabaya bin, polisler hemen arkamızda! Bu sefer kaçamayız, o yüzden sıkı tutun."

# kip: sunucudaki çalışma kipi (denemede hepsi cümleyi tek seferde üretir: yanıt WAV). gereken_gb: yüklenirken gereken boş bellek (ölçüm; yetmezse başlatılmaz)
MODELLER = [
    {"id": "voxcpm2", "ad": "VoxCPM2", "aile": "voxcpm2", "kip": "offline", "gereken_gb": 6.0,
     "yol": "VoxCPM2-GGUF/voxcpm2-q8_0.gguf", "boyut": 2955007488,
     "sha256": "8df1faf274e1bdeedef1fd9ddd6aba6632536f66f2e080991d2352af35ceef72",
     "aciklama": "Şu anki \"güçlü\" ses modelimiz. 48 kHz; canlı seslendirmede akış halinde üretir (ilk ses çabuk gelir).",
     "lisans": "OpenBMB, Apache 2.0"},
    {"id": "omnivoice", "ad": "OmniVoice", "aile": "omnivoice", "kip": "offline", "gereken_gb": 3.5,
     "yol": "OmniVoice-GGUF/omnivoice-q8_0.gguf", "boyut": 1350296096,
     "sha256": "0e5a721edd1b08d9067ef66f40ded609a6b14f5a8445c703f9869736cabd350a",
     "aciklama": "600'den fazla dil bilen yeni model. Cümleyi tek seferde üretir (akış yok).",
     "lisans": "k2-fsa, Apache 2.0"},
    {"id": "chatterbox", "ad": "Chatterbox (çok dilli)", "aile": "chatterbox", "kip": "offline", "gereken_gb": 4.5,
     "yol": "Chatterbox-GGUF/chatterbox-q8_0.gguf", "boyut": 2088399204,
     "sha256": "45d71d8d248ba831014813bbbbba74c7d786dd9447c02090fe05c44344f69453",
     "aciklama": "Resemble AI'nin modeli; Türkçe dahil 19 dil. Duygu abartısı ayarlanabilir. Cümleyi tek seferde üretir.",
     "lisans": "Resemble AI, MIT"},
]
_MODEL = {m["id"]: m for m in MODELLER}

_kilit = threading.RLock()
_surec = None
_yuklu = None          # sunucuda yüklü modelin kimliği
_son_kullanim = 0.0
_indirme = {}          # id -> {"oran": 0-1, "hata": str}
_son = {}              # id -> {"ses_sn", "uretim_sn", "ses", "zaman"} — son denemenin ölçümü
_durum = {"sunucu": "kapali", "hata": "", "calisan": None}


def motor_klasoru():
    """Doğal Ses Paketi'nin kurulu olduğu klasör (içinde motor\\audiocpp_server.exe) ya da None."""
    k = dogal_ses.kurulum_klasoru()
    if k and os.path.exists(os.path.join(k, "motor", "audiocpp_server.exe")):
        return k
    return None


def model_klasoru():
    """İndirilen modellerin durduğu klasör. CTA_SES_MODELLERI: denemelerde başka klasör göstermek için."""
    return os.environ.get("CTA_SES_MODELLERI") or veri.veri_yolu("ses_modelleri")


def model_yolu(m):
    """Model dosyası kuruluysa yolu (paketin model klasörü ya da veri klasörü), değilse None."""
    ad = os.path.basename(m["yol"])
    adaylar = [os.path.join(model_klasoru(), ad)]
    k = motor_klasoru()
    if k:
        adaylar.insert(0, os.path.join(k, "model", ad))
    for yol in adaylar:
        try:
            # paketle gelen VoxCPM2 başka bir depo sürümünden (boyutu farklı): paket klasöründekine boyut sorulmaz
            if os.path.exists(yol) and (os.path.getsize(yol) == m["boyut"] or yol != adaylar[-1]):
                return yol
        except OSError:
            pass
    return None


def sesler():
    k = motor_klasoru()
    return dogal_ses.sesleri_oku(k) if k else []


def durum():
    k = motor_klasoru()
    with _kilit:
        _saglik_guncelle()
        return {
            "motor_var": bool(k), "sunucu": _durum["sunucu"], "hata": _durum["hata"], "calisan": _durum["calisan"],
            "yuklu": _yuklu, "bos_bellek_gb": dogal_ses.bos_bellek_gb(), "ornek_metin": ORNEK_METIN,
            "sesler": [{"id": s["id"], "ad": s["ad"], "cinsiyet": s["cinsiyet"]} for s in sesler()],
            "modeller": [{"id": m["id"], "ad": m["ad"], "aciklama": m["aciklama"], "lisans": m["lisans"],
                          "boyut_gb": round(m["boyut"] / 1e9, 1), "kurulu": bool(model_yolu(m)),
                          "indirme": _indirme.get(m["id"]), "son": _son.get(m["id"])} for m in MODELLER],
        }


# ---------- indirme ----------
def indir(model_id):
    """Modeli arka planda indirir (yarıda kalırsa kaldığı yerden sürer); bitince SHA-256 denetlenir."""
    m = _MODEL.get(model_id)
    if not m:
        raise ValueError("Bilinmeyen ses modeli.")
    with _kilit:
        if model_yolu(m):
            return
        if _indirme.get(model_id, {}).get("oran") is not None and not _indirme[model_id].get("hata") \
                and not _indirme[model_id].get("bitti"):
            return  # zaten iniyor
        _indirme[model_id] = {"oran": 0.0, "hata": ""}
    threading.Thread(target=_indir, args=(m,), daemon=True).start()


def _indir(m):
    hedef = os.path.join(model_klasoru(), os.path.basename(m["yol"]))
    gecici = hedef + ".indiriliyor"
    bilgi = _indirme[m["id"]]
    try:
        for _ in range(6):  # bağlantı koparsa kaldığı yerden
            var = os.path.getsize(gecici) if os.path.exists(gecici) else 0
            if var >= m["boyut"]:
                break
            istek = urllib.request.Request(f"{DEPO}/{m['yol']}", headers={"Range": f"bytes={var}-",
                                                                         "User-Agent": "canli-turkce-altyazi"})
            try:
                with urllib.request.urlopen(istek, timeout=60) as yanit, open(gecici, "ab") as f:
                    if var and yanit.status != 206:  # sunucu kaldığı yerden vermedi: baştan
                        f.truncate(0)
                        var = 0
                    while True:
                        parca = yanit.read(1 << 20)
                        if not parca:
                            break
                        f.write(parca)
                        var += len(parca)
                        bilgi["oran"] = min(0.999, var / m["boyut"])
            except (urllib.error.URLError, OSError, TimeoutError) as e:
                bilgi["son_hata"] = str(e)
                time.sleep(3)
        if os.path.getsize(gecici) != m["boyut"]:
            raise RuntimeError("İndirme tamamlanamadı (internet bağlantısını denetleyip yeniden deneyin). "
                               + bilgi.get("son_hata", ""))
        ozet = hashlib.sha256()
        with open(gecici, "rb") as f:
            for parca in iter(lambda: f.read(1 << 22), b""):
                ozet.update(parca)
        if ozet.hexdigest() != m["sha256"]:
            os.remove(gecici)
            raise RuntimeError("İndirilen dosya bozuk çıktı (denetim tutmadı). Yeniden deneyin.")
        os.replace(gecici, hedef)
        bilgi.update({"oran": 1.0, "bitti": True})
    except Exception as e:
        bilgi["hata"] = str(e)
        print(f"[ses deneme] {m['id']} indirilemedi: {e}", flush=True)


# ---------- sunucu ----------
def _adres():
    return f"http://127.0.0.1:{PORT}"


def _saglik(zaman_asimi=1.0):
    try:
        with urllib.request.urlopen(_adres() + "/health", timeout=zaman_asimi) as r:
            return r.status == 200
    except Exception:
        return False


def _saglik_guncelle():
    global _surec, _yuklu
    if _surec is not None and _surec.poll() is not None:  # süreç kapanmış (çöktü ya da kapatıldı)
        _surec, _yuklu = None, None
        if _durum["sunucu"] in ("hazir", "basliyor"):
            _durum.update({"sunucu": "hata", "hata": _durum["hata"] or "Ses sunucusu beklenmedik biçimde kapandı "
                           f"(ayrıntı: {gunluk_yolu()})."})


def gunluk_yolu():
    return veri.veri_yolu("ses_deneme.log")


def _ayar_yaz(m, yol, ses_listesi):
    k = motor_klasoru()
    with open(os.path.join(k, "paket.json"), encoding="utf-8") as f:
        paket = json.load(f)
    model = {"id": m["id"], "family": m["aile"], "task": "tts", "mode": m["kip"], "path": yol,
             "voice_presets": {s["id"]: {"voice_ref": s["referans"], "reference_text": s["referans_metni"]}
                               for s in ses_listesi}}
    if m["aile"] == "voxcpm2":
        model["session_options"] = dogal_ses.oturum_ayarlari(ses_listesi)
    elif m["aile"] == "chatterbox":
        model["session_options"] = {"chatterbox.conditionals_cache_slots": max(1, len(ses_listesi))}
    ayar = {"host": "127.0.0.1", "port": PORT, "backend": paket.get("backend", "vulkan"), "threads": 4,
            "lazy_load": False, "models": [model]}
    if paket.get("cihaz") is not None:
        ayar["device"] = paket["cihaz"]
    hedef = veri.veri_yolu("ses_deneme_sunucu.json")
    with open(hedef, "w", encoding="utf-8") as f:
        json.dump(ayar, f, ensure_ascii=False, indent=1)
    return hedef


def _baslat(m, bekle_sn=150):
    """Sunucuyu bu modelle başlatır (başka model yüklüyse önce kapatır). Hazır olunca döner."""
    global _surec, _yuklu, _son_kullanim
    _son_kullanim = time.time()  # boşta kapatma sayacı: yükleme sırasında kapatılmasın
    k = motor_klasoru()
    if not k:
        raise RuntimeError("Bu denemeler için Doğal Ses Paketi (ekran kartıyla çalışan ses motoru) kurulu olmalı.")
    yol = model_yolu(m)
    if not yol:
        raise RuntimeError(f"{m['ad']} modeli henüz indirilmemiş.")
    if _surec is not None and _surec.poll() is None and _yuklu == m["id"] and _saglik():
        return
    kapat()
    # Canlı seslendirmenin güçlü sunucusu açıksa kapatılır: iki ses sunucusu ekran kartını aynı anda kullanınca
    # ekran kartı sürücüsü sıfırlanıyor (2026-11-20: Windows olay günlüğünde "görüntü sürücüsü yanıt vermeyi kesti").
    canli = dogal_ses._paylasilan
    if canli is not None and canli.motor == "guclu" and canli.surec is not None:
        canli.durdur()
        time.sleep(1.0)
    bos = dogal_ses.bos_bellek_gb()
    if bos is not None and bos < m["gereken_gb"]:
        raise RuntimeError(f"{m['ad']} için yeterli boş bellek yok ({bos:.1f} GB boş, {m['gereken_gb']:.1f} GB gerekir). "
                           "Açık programlardan birkaçını kapatıp yeniden deneyin.")
    _durum.update({"sunucu": "basliyor", "hata": "", "calisan": m["id"]})
    gunluk = open(gunluk_yolu(), "w", encoding="utf-8")
    surec = _surec = subprocess.Popen([os.path.join(k, "motor", "audiocpp_server.exe"), "--config", _ayar_yaz(m, yol, sesler())],
                              cwd=os.path.join(k, "motor"), stdout=gunluk, stderr=subprocess.STDOUT,
                              creationflags=dogal_ses.NO_WINDOW)
    dogal_ses._bizimle_kapansin(surec)
    son = time.time() + bekle_sn
    while time.time() < son:
        if surec.poll() is not None:
            _surec = None
            _durum.update({"sunucu": "hata", "calisan": None,
                           "hata": f"{m['ad']} yüklenemedi (ayrıntı: {gunluk_yolu()})."})
            raise RuntimeError(_durum["hata"])
        if _saglik(1.0):
            _yuklu = m["id"]
            _son_kullanim = time.time()
            _durum.update({"sunucu": "hazir", "hata": ""})
            return
        time.sleep(0.4)
    kapat()
    _durum.update({"sunucu": "hata", "hata": f"{m['ad']} {bekle_sn} saniyede yüklenemedi."})
    raise RuntimeError(_durum["hata"])


def kapat():
    global _surec, _yuklu
    with _kilit:
        s, _surec, _yuklu = _surec, None, None
        _durum.update({"sunucu": "kapali", "calisan": None})
    if s is not None and s.poll() is None:
        try:
            s.terminate()
            s.wait(timeout=5)
        except Exception:
            try:
                s.kill()
            except Exception:
                pass


def _bosta_kapat():
    while True:
        time.sleep(20)
        with _kilit:  # üretim sürerken kilit üretimdedir: istek ortasında kapatılmaz
            if _surec is not None and time.time() - _son_kullanim > BOSTA_KAPAT_SN:
                kapat()


threading.Thread(target=_bosta_kapat, daemon=True).start()


# ---------- üretim ----------
def uret(model_id, metin, ses_id, abarti=None):
    """Cümleyi üretir. Dönüş: (float32 örnekler, örnek hızı, {"ses_sn", "uretim_sn", "yukleme_sn"})."""
    global _son_kullanim
    m = _MODEL.get(model_id)
    if not m:
        raise ValueError("Bilinmeyen ses modeli.")
    metin = (metin or "").strip() or ORNEK_METIN
    if len(metin) > 400:
        raise ValueError("Deneme cümlesi en çok 400 harf olabilir.")
    ses_listesi = sesler()
    ses = next((s for s in ses_listesi if s["id"] == ses_id), ses_listesi[0] if ses_listesi else None)
    if not ses:
        raise RuntimeError("Karakter sesleri bulunamadı (Doğal Ses Paketi eksik).")
    with _kilit:  # aynı anda tek üretim
        t0 = time.time()
        _baslat(m)
        yukleme = time.time() - t0
        govde = {"model": m["id"], "input": metin, "voice": ses["id"], "seed": ses["tohum"], "response_format": "wav"}
        secenek = {}
        if m["aile"] == "voxcpm2":
            secenek["retry_badcase"] = False
        if m["aile"] in ("chatterbox", "omnivoice"):
            govde["language"] = "tr"
            secenek["language"] = "tr"
        if m["aile"] == "chatterbox" and abarti is not None:
            secenek["exaggeration"] = max(0.0, min(1.5, float(abarti)))
        if secenek:
            govde["options"] = secenek
        istek = urllib.request.Request(_adres() + "/v1/audio/speech", data=json.dumps(govde).encode("utf-8"),
                                       method="POST", headers={"Content-Type": "application/json"})
        t1 = time.time()
        try:
            with urllib.request.urlopen(istek, timeout=180) as yanit:
                ham = yanit.read()
        except urllib.error.HTTPError as e:
            ayrinti = e.read().decode("utf-8", "replace")[:300]
            raise RuntimeError(f"{m['ad']} ses üretemedi: {ayrinti or e}")
        except (urllib.error.URLError, OSError) as e:  # sunucu istek sırasında kapandı (çöktü ya da bellek bitti)
            kapat()
            _durum.update({"sunucu": "hata", "hata": f"{m['ad']} üretim sırasında kapandı."})
            raise RuntimeError(f"{m['ad']} üretim sırasında kapandı ({type(e).__name__}). Yeniden deneyin; "
                               f"sürerse ayrıntı: {gunluk_yolu()}")
        uretim = time.time() - t1
        _son_kullanim = time.time()
    x, hz = _coz(ham)
    if not len(x):
        raise RuntimeError(f"{m['ad']} boş ses döndürdü.")
    olcum = {"ses_sn": round(len(x) / hz, 2), "uretim_sn": round(uretim, 2), "yukleme_sn": round(yukleme, 1),
             "ses": ses["ad"], "zaman": time.strftime("%H:%M:%S")}
    _son[m["id"]] = olcum
    return x, hz, olcum


def _coz(ham):
    """Sunucunun yanıtı: WAV (başlıklı) ya da ham 16 bit PCM (48 kHz). float32 örnekler + örnek hızı."""
    if ham[:4] == b"RIFF":
        with wave.open(io.BytesIO(ham)) as w:
            hz, kanal, genislik = w.getframerate(), w.getnchannels(), w.getsampwidth()
            veri_ = w.readframes(w.getnframes())
        if genislik == 2:
            x = np.frombuffer(veri_, np.int16).astype(np.float32) / 32768.0
        elif genislik == 4:
            x = np.frombuffer(veri_, np.int32).astype(np.float32) / 2147483648.0
        else:
            raise RuntimeError(f"Beklenmeyen ses biçimi ({genislik * 8} bit).")
        if kanal > 1:
            x = x.reshape(-1, kanal).mean(axis=1)
        return x, hz
    return np.frombuffer(ham[:len(ham) // 2 * 2], np.int16).astype(np.float32) / 32768.0, dogal_ses.ORNEK_HIZI


def dinle(model_id, metin, ses_id, seviye=1.0, abarti=None, oynatici=None):
    """Üretir ve hoparlörden çalar. Dönüş: ölçüm sözlüğü."""
    x, hz, olcum = uret(model_id, metin, ses_id, abarti)
    oynat = oynatici or dogal_ses._HoparlorOynatici(hz)
    try:
        oynat.cal(np.clip(x * float(seviye), -1, 1))
    finally:
        oynat.bitir()
    return olcum
