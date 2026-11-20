"""Doğal Türkçe sesler: yapay zekâ ses sunucusuyla konuşan istemci. İki motor var; ikisi de AYRI SÜREÇTE çalışır
ve aynı yerel HTTP arayüzünü sunar (aynı anda yalnız biri):

- **hafif** (varsayılan): Pocket TTS Turkish (hafif_ses/sunucu.py). Uygulamayla birlikte gelir, ekran kartı
  istemez, tek işlemci çekirdeği ve ~2 GB bellek kullanır, 24 kHz. Ölçüm (Ryzen 5 5600X): ilk ses 100-160 ms,
  1 sn sesi 0,36-0,47 sn'de üretir. Sesler: hafif_ses/sesler (6 hazır ses + kendi tasarladığımız 6 ses).
- **güçlü** (isteğe bağlı): audio.cpp + VoxCPM2, ekran kartında, 48 kHz, ~5 GB bellek. Ayrıca kurulan
  "Doğal Ses Paketi" ister (aşağıda). Kullanıcı panelden seçerse kullanılır.

Sunucu yoksa, başlayamazsa ya da yanıt vermezse dublaj Windows sesiyle (seslendirme.py) devam eder.

Güçlü motor neden ayrı paket: model ~3 GB, ekran kartında çalışır; Store kuralı gereği uygulama
çalıştırılabilir kod indirmez. Kullanıcı "Doğal Ses Paketi"ni ayrıca kurar (paket/dogal_ses/kur.ps1).

Güçlü paketin klasörü (KURULUM_KLASORLERI'nden ilk bulunan):
  motor\\audiocpp_server.exe (+ DLL'ler)   audio.cpp v0.9.5 (Apache 2.0)
  model\\voxcpm2-q8_0.gguf                 OpenBMB VoxCPM2 (Apache 2.0)
  sesler\\<id>\\referans.wav + ses.json     yapay (tasarlanmış) karakter sesleri; ses.json'da
                                           ad, cinsiyet (kadin/erkek), referans_metni, tohum
  paket.json                               {"backend": "vulkan"|"cuda", "surum": ...}
Uygulama bu klasöre yalnızca sunucu.json ve sunucu.log yazar.

Sunucu: http://127.0.0.1:38767 (38765 overlay; 8765/8766 bu bilgisayarda başka programlarda).
İstek: POST /v1/audio/speech {model, input, voice (ön ayar adı), seed, response_format: pcm,
stream_format: audio, options: {retry_badcase: false}} -> 16 bit mono PCM akışı (48 kHz).
"""
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

import numpy as np

# CTA_SES_KAPISI: denemelerde başka kapı (program açıkken derleme denemesi onun ses sunucusuyla çakışmasın)
PORT = int(os.environ.get("CTA_SES_KAPISI") or 38767)
# Açılışta her sesle bir kez üretilen cümle: hem sesin referansını ısıtır hem de ses uyarlaması (ses_uyum.py)
# için o sesin perdesi ve ses izi bundan ölçülür.
ORNEK_CUMLE = "Bak, sana söylüyorum, bu iş göründüğü kadar kolay değil. Hadi, arabaya bin."
HARF_SN = 15.0  # bu seslerde saniyede ~14-17 harf: süre tahmini (ön tampon ve kesilme denetimi için)
MODEL_ID = "voxcpm2"
ORNEK_HIZI = 48000  # VoxCPM2 çıkışı; hafif motor 24 kHz verir (sunucu /health'te bildirir: DogalSes.ornek_hizi)
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
MOTOR_ADLARI = {"hafif": "Hafif (her bilgisayarda çalışır)", "guclu": "Güçlü (ekran kartı gerekir)"}
HAFIF_SUNUCU_ADI = "pocket-tts-turkish"  # hafif sunucu /health'te kendini böyle tanıtır (hafif_ses/sunucu.py MOTOR)
# Hafif motor ~1,7 GB ayırır, 12 sesle ~2,3 GB'a çıkar (ölçüldü); sistem için pay bırakılır
HAFIF_BOS_BELLEK_GB = 2.8


_is_nesnesi = None


def _bizimle_kapansin(surec):
    """Sunucuyu bir Windows iş nesnesine (Job Object, KILL_ON_JOB_CLOSE) bağlar: uygulama çökse ya da
    görev yöneticisinden kapatılsa bile ses sunucusu arkada kalıp ekran kartı belleğini tutmaz."""
    global _is_nesnesi
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateJobObjectW.restype = wintypes.HANDLE
        k32.OpenProcess.restype = wintypes.HANDLE
        k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        if _is_nesnesi is None:
            class _Temel(ctypes.Structure):
                _fields_ = [("a", ctypes.c_int64), ("b", ctypes.c_int64), ("LimitFlags", wintypes.DWORD),
                            ("c", ctypes.c_size_t), ("d", ctypes.c_size_t), ("e", wintypes.DWORD),
                            ("f", ctypes.c_size_t), ("g", wintypes.DWORD), ("h", wintypes.DWORD)]

            class _Genis(ctypes.Structure):
                _fields_ = [("Temel", _Temel), ("Io", ctypes.c_uint64 * 6), ("i", ctypes.c_size_t * 4)]
            bilgi = _Genis()
            bilgi.Temel.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            is_ = k32.CreateJobObjectW(None, None)
            if not is_ or not k32.SetInformationJobObject(is_, 9, ctypes.byref(bilgi), ctypes.sizeof(bilgi)):
                return
            _is_nesnesi = is_
        tutamac = k32.OpenProcess(0x0101, False, surec.pid)  # PROCESS_SET_QUOTA | PROCESS_TERMINATE
        if tutamac:
            k32.AssignProcessToJobObject(_is_nesnesi, tutamac)
            k32.CloseHandle(tutamac)
    except Exception as e:
        print(f"[doğal ses] iş nesnesi kurulamadı: {e}", flush=True)


# Sunucunun ana bellek alanları (MiB). Varsayılanların toplamı ~8,7 GB ayırıyor ama sunucu gerçekte ~3,6 GB
# kullanıyor (ölçüldü); bilgisayar doluyken bu yüzden çöküyordu ("GGML_ASSERT(ctx->mem_buffer != NULL)").
# Aşağıdaki değerler, sorunsuz çalıştığı ölçülen en küçük değerlerin (hepsi 256, yerel kodlayıcı 128, izdüşüm 64)
# 1,25 katıdır. En küçük değerlerle 7 ses, 415 harflik cümle (24 sn ses) ve art arda 12 satır denendi.
# Toplam ayrılan bellek ~9,4 GB yerine ~5,1 GB.
BELLEK_ALANLARI = {
    "voxcpm2.weight_context_mb": 320,
    "voxcpm2.lm_step_graph_arena_mb": 320,
    "voxcpm2.dit_graph_arena_mb": 320,
    "voxcpm2.audiovae_graph_arena_mb": 320,
    "voxcpm2.audiovae_encoder_graph_arena_mb": 320,
    "voxcpm2.audiovae_weight_context_mb": 320,
    "voxcpm2.local_encoder_graph_arena_mb": 160,
    "voxcpm2.projection_graph_arena_mb": 80,
}
GEREKEN_BOS_BELLEK_GB = 6.0  # sunucu ~5,1 GB ayırır + sistem için pay; altındaysa başlatılmaz (çökmek yerine Windows sesi okur)


def bos_bellek_gb():
    """Windows'un yeni programlara ayırabileceği bellek (boş RAM + takas dosyası payı), GB. Ölçülemezse None."""
    if not sys.platform.startswith("win"):
        return None
    try:
        import ctypes

        class _Durum(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        d = _Durum()
        d.dwLength = ctypes.sizeof(d)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(d)):
            return None
        return d.ullAvailPageFile / 2 ** 30
    except Exception:
        return None


def _referans_sn(yol):
    try:
        import wave
        with wave.open(yol) as w:
            return w.getnframes() / float(w.getframerate())
    except Exception:
        return 0.0


def kurulum_klasorleri():
    yerel = os.environ.get("LOCALAPPDATA", "")
    adaylar = [os.environ.get("CTA_DOGAL_SES", ""),
               os.path.join(yerel, "Programs", "CTA-DogalSes") if yerel else "",
               r"C:\CTA-DogalSes"]
    return [a for a in adaylar if a]


def kurulum_klasoru():
    """Güçlü motorun (ayrıca kurulan Doğal Ses Paketi) klasörü; kurulu değilse None."""
    if os.environ.get("CTA_DOGAL_SES_YOK"):  # testler: bu bilgisayardaki gerçek paketi kullanma
        return None
    for k in kurulum_klasorleri():
        if os.path.exists(os.path.join(k, "motor", "audiocpp_server.exe")) and \
                os.path.exists(os.path.join(k, "model", "voxcpm2-q8_0.gguf")):
            return k
    return None


def hafif_kurulumu():
    """Uygulamayla birlikte gelen hafif motor (Pocket TTS Turkish). Dönüş: {kok, komut, model, sesler} ya da None.
    - Derlenmiş uygulamada: <uygulama>\\hafif_ses\\motor\\cta_ses.exe, model\\, sesler\\ (paket\\derle.ps1 koyar)
    - Kaynaktan çalışırken: .venv-ses\\Scripts\\python.exe hafif_ses\\sunucu.py + modeller\\pocket-tts-turkish
      (paket\\hafif_ses\\ortam_hazirla.ps1 kurar)
    CTA_HAFIF_SES başka bir klasör gösterir (derlenmiş düzen). CTA_DOGAL_SES_YOK: testlerde hiçbir motor kullanılmaz."""
    if os.environ.get("CTA_DOGAL_SES_YOK"):
        return None
    import veri
    kok = os.environ.get("CTA_HAFIF_SES") or veri.kaynak("hafif_ses")
    exe, model = os.path.join(kok, "motor", "cta_ses.exe"), os.path.join(kok, "model")
    if os.path.exists(exe) and os.path.exists(os.path.join(model, "model.safetensors")):
        return {"kok": kok, "komut": [exe], "model": model, "sesler": os.path.join(kok, "sesler")}
    if getattr(sys, "frozen", False):
        return None
    py = os.path.join(veri.KLASOR, ".venv-ses", "Scripts", "python.exe")
    betik = os.path.join(veri.KLASOR, "hafif_ses", "sunucu.py")
    model = os.path.join(veri.KLASOR, "modeller", "pocket-tts-turkish")
    if all(os.path.exists(p) for p in (py, betik, os.path.join(model, "model.safetensors"))):
        return {"kok": os.path.join(veri.KLASOR, "hafif_ses"), "komut": [py, betik], "model": model,
                "sesler": os.path.join(veri.KLASOR, "hafif_ses", "sesler")}
    return None


_tercih = "otomatik"  # config.dublaj.dogal_motor: "otomatik" | "hafif" | "guclu"
# Güçlü motor (ekran kartı) canlı seslendirmeye yetişemedi: program kapanana ya da kullanıcı modeli yeniden seçene
# kadar hafif motor kullanılır (DogalSes.hafife_gec). Güçlü motor oyunla AYNI ekran kartını paylaşır; oyun kartı
# doldurunca ilk ses saniyelerce gecikir, hatta ekran kartı sürücüsü sıfırlanabilir (2026-11-20, RX 9060 XT).
_gecici_hafif = False


def tercih_ayarla(tercih):
    global _tercih
    _tercih = tercih if tercih in ("hafif", "guclu") else "otomatik"


def gecici_hafifi_sifirla():
    """Kullanıcı ses modelini kendisi yeniden seçti: güçlü motor yeniden denenir."""
    global _gecici_hafif
    _gecici_hafif = False


def motor_sec(tercih=None):
    """Kullanılacak motor: "hafif" | "guclu" | None (hiçbiri yok). Hafif motor her bilgisayarda çalıştığı için
    varsayılandır; güçlü motor yalnız kullanıcı seçtiyse (ve paketi kuruluysa) ya da hafif yoksa kullanılır."""
    tercih = tercih or _tercih
    hafif, guclu = hafif_kurulumu() is not None, kurulum_klasoru() is not None
    if tercih == "guclu" and guclu and not (_gecici_hafif and hafif):
        return "guclu"
    if hafif:
        return "hafif"
    return "guclu" if guclu else None


def var_mi():
    """Bu bilgisayarda doğal sesle okuyabilecek bir motor var mı?"""
    return motor_sec() is not None


def sesleri_oku(klasor):
    """[{id, ad, cinsiyet, referans, referans_metni, tohum}] — sesler/*/ses.json."""
    liste = []
    kok = os.path.join(klasor, "sesler")
    if not os.path.isdir(kok):
        return liste
    for ad in sorted(os.listdir(kok)):
        yol = os.path.join(kok, ad, "ses.json")
        if not os.path.exists(yol):
            continue
        try:
            with open(yol, encoding="utf-8") as f:
                k = json.load(f)
            liste.append({"id": ad, "ad": k.get("gorunen_ad") or ad, "cinsiyet": k.get("cinsiyet", "erkek"),
                          "referans": os.path.join(kok, ad, k.get("referans", "referans.wav")),
                          "referans_metni": k.get("referans_metni", ""), "tohum": int(k.get("tohum", 1234)),
                          "tanitim": k.get("tanitim", ""), "sira": int(k.get("sira", 999))})
        except Exception as e:
            print(f"[doğal ses] {yol} okunamadı: {e}", flush=True)
    # sıra: aynı cinsiyetin 1. sesi "erkek1"/"kadin1" profiline gider (ilk tanınan kişi en doğal sesi alır)
    return sorted(liste, key=lambda s: (s["sira"], s["id"]))


def oturum_ayarlari(sesler):
    ayar = {"voxcpm2.prompt_cache_slots": max(1, len(sesler)), **BELLEK_ALANLARI}
    # Referans kodlayıcının varsayılan sınırı 15 sn (16 kHz'de 240000 örnek); daha uzun referans varsa ona göre açılır
    en_uzun = max((_referans_sn(s["referans"]) for s in sesler), default=0.0)
    if en_uzun > 14.0:
        ayar["voxcpm2.audiovae_encoder_sample_capacity"] = int((en_uzun + 2.0) * 16000)
    return ayar


def sunucu_ayari_yaz(klasor, sesler, port=PORT):
    with open(os.path.join(klasor, "paket.json"), encoding="utf-8") as f:
        paket = json.load(f)
    ayar = {
        "host": "127.0.0.1", "port": port, "backend": paket.get("backend", "vulkan"), "threads": 4,
        "lazy_load": False,
        "models": [{
            "id": MODEL_ID, "family": "voxcpm2", "task": "tts", "mode": "streaming",
            "path": os.path.join(klasor, "model", "voxcpm2-q8_0.gguf"),
            "session_options": oturum_ayarlari(sesler),
            "voice_presets": {s["id"]: {"voice_ref": s["referans"], "reference_text": s["referans_metni"]}
                              for s in sesler},
        }],
    }
    if paket.get("cihaz") is not None:
        ayar["device"] = paket["cihaz"]
    yol = os.path.join(klasor, "sunucu.json")
    with open(yol, "w", encoding="utf-8") as f:
        json.dump(ayar, f, ensure_ascii=False, indent=1)
    return yol


class KisaCikti(RuntimeError):
    """Model cümleyi erken bitirdi (akışta yeniden deneme yok). O satır Windows sesiyle okunur."""


class DogalSes:
    """Sunucuyu (gerekirse) başlatır, sesleri bilir, metni seçilen sesle akış halinde üretir."""

    def __init__(self, adres=None, klasor=None, motor=None):
        """motor: "hafif" | "guclu" | None (None: klasor verilmişse güçlü paket sayılır, verilmemişse tercih edilen
        motor seçilir). klasor: güçlü paketin klasörü (testlerde sahte sunucuyla)."""
        self.adres = adres or f"http://127.0.0.1:{PORT}"
        if motor is None:
            motor = "guclu" if klasor is not None else (motor_sec() or "guclu")
        self.motor = motor
        self.hafif = hafif_kurulumu() if motor == "hafif" else None
        if motor == "hafif":
            self.klasor = self.hafif["kok"] if self.hafif else None
        else:
            self.klasor = klasor if klasor is not None else kurulum_klasoru()
        self.ornek_hizi = 24000 if motor == "hafif" else ORNEK_HIZI  # sunucu /health'te bildirirse ona uyulur
        self.sesler = sesleri_oku(self.klasor) if self.klasor else []
        self.surec = None
        self.durum = "kapali"  # kapali | basliyor | hazir | hata
        self.hata = ""
        self.devre_disi_kadar = 0.0  # art arda hata olunca bir süre Windows sesine düş
        self.son_gecikme_ms = None  # ilk ses parçasına kadar geçen süre
        self.son_hiz = None  # üretim süresi / ses süresi (1'den küçükse canlıya yetişir)
        self.akis_hizi = 1.0  # ilk parçadan sonraki üretim hızı (ön tampon bundan hesaplanır)
        self.isinan = set()  # referansı işlenmiş (önbellekte) sesler
        self.ornekler = {}   # ses id -> ORNEK_CUMLE'nin o sesle üretilmiş hali (float32, 48 kHz)
        self.isinma_bitti = False  # bütün sesler hazır: o zamana kadar Windows sesi okur (satırlar beklemesin)
        self.sunucu_hazir_ses = None  # hafif sunucunun hazırladığı ses sayısı (/health "hazir_ses"); güçlüde None
        self.ust_uste_yavas = 0  # güçlü motorda art arda geç başlayan / gerçek zamana yetişmeyen satır sayısı
        self.gecis_notu = ""     # güçlü motordan hafife geçildiyse kullanıcıya gösterilecek açıklama
        self.degisim = 0         # motor her değiştiğinde artar (Seslendirici ses eşlemesini yeniden kurar)
        self._nesil = 0  # her sunucu başlatmada artar: eski sunucunun ısıtması yenisinin durumunu değiştirmesin
        self._isitilan_nesil = None
        self.kilit = threading.Lock()

    # ---------- sunucu ----------
    def saglik(self, zaman_asimi=1.0):
        """Sunucu hazır mı? Hazırsa çıkış örnek hızını da öğrenir (hafif motor bildirir; güçlü motor 48 kHz)."""
        self._sunucu_hatasi = ""
        try:
            with urllib.request.urlopen(self.adres + "/health", timeout=zaman_asimi) as r:
                bilgi = json.loads(r.read().decode("utf-8"))
        except Exception:
            return False
        if not isinstance(bilgi, dict):
            return False
        # Kapıda öteki motorun sunucusu varsa (programın açık başka bir kopyası başlatmış olabilir) bizimki değildir:
        # sesleri ve örnek hızı tutmaz
        if ("hafif" if bilgi.get("motor") == HAFIF_SUNUCU_ADI else "guclu") != self.motor:
            return False
        if bilgi.get("status") != "ok":
            self._sunucu_hatasi = str(bilgi.get("hata") or "") if bilgi.get("status") == "error" else ""
            return False
        try:
            self.ornek_hizi = int(bilgi.get("sample_rate") or ORNEK_HIZI)
        except (TypeError, ValueError):
            self.ornek_hizi = ORNEK_HIZI
        self.sunucu_hazir_ses = bilgi.get("hazir_ses") if isinstance(bilgi.get("hazir_ses"), int) else None
        return True

    def _kapi_dolu(self):
        """Sunucunun kapısını şu an bir program dinliyor mu?"""
        import socket
        try:
            port = int(self.adres.rsplit(":", 1)[-1].strip("/"))
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                return True
        except (OSError, ValueError):
            return False

    _sunucu_hatasi = ""

    def _gunluk_yolu(self):
        """Sunucunun çıktısının yazıldığı dosya. Güçlü paket kendi klasörüne yazar; hafif motor uygulama klasöründe
        (salt okunur) durduğu için kullanıcının veri klasörüne."""
        if self.motor == "hafif":
            import veri
            return veri.veri_yolu("ses_sunucusu.log")
        return os.path.join(self.klasor, "sunucu.log")

    def _sureci_baslat(self):
        gunluk = open(self._gunluk_yolu(), "w", encoding="utf-8")
        port = self.adres.rsplit(":", 1)[-1].strip("/")
        if self.motor == "hafif":
            h = self.hafif
            komut = h["komut"] + ["--model", h["model"], "--sesler", h["sesler"], "--port", port]
            cwd = os.path.dirname(h["komut"][-1])
        else:
            komut = [os.path.join(self.klasor, "motor", "audiocpp_server.exe"), "--config",
                     sunucu_ayari_yaz(self.klasor, self.sesler)]
            cwd = os.path.join(self.klasor, "motor")
        ortam = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
        self.surec = subprocess.Popen(komut, cwd=cwd, stdout=gunluk, stderr=subprocess.STDOUT, env=ortam,
                                      creationflags=NO_WINDOW)
        _bizimle_kapansin(self.surec)

    def baslat(self, bekle_sn=120):
        """Sunucu açık değilse başlatır; model yüklenene kadar bekler (hafif ~10 sn, güçlü 10-60 sn)."""
        with self.kilit:
            if self.saglik():
                self.durum = "hazir"
                self._isitmayi_baslat()  # zaten açık bir sunucu: sesleri yine de hazırla (örnekler gerekli)
                return True
            # Başka bir iş parçacığı az önce başlattıysa (panel + motor aynı anda) ikinci bir sunucu açma, onu bekle
            suruyor = self.durum == "basliyor" and self.surec is not None and self.surec.poll() is None
            if not suruyor:
                if not self.klasor:
                    self.durum, self.hata = "kapali", "Doğal sesler bu kurulumda yok."
                    return False
                self.durdur_sureci()  # önceki denemeden kalan (açılamamış) sunucumuz kapıyı tutmasın
                if self._kapi_dolu():
                    self.durum = "hata"
                    self.hata = ("Doğal sesler başlatılamadı: gereken kapıyı başka bir program kullanıyor (büyük olasılıkla "
                                 "bu programın açık başka bir kopyası). Öteki kopyayı kapatıp doğal sesleri yeniden açın. "
                                 "O zamana kadar Windows sesi okur.")
                    print(f"[doğal ses] {self.hata}", flush=True)
                    return False
                gereken = HAFIF_BOS_BELLEK_GB if self.motor == "hafif" else GEREKEN_BOS_BELLEK_GB
                bos = bos_bellek_gb()
                if bos is not None and bos < gereken:
                    self.durum = "hata"
                    self.hata = (f"Doğal sesler için yeterli boş bellek yok (şu an {bos:.1f} GB boş, en az "
                                 f"{gereken:.1f} GB gerekir). Açık programları kapatıp Türkçe ses sayfasından "
                                 "doğal sesleri yeniden açın. O zamana kadar Windows sesi okur.")
                    print(f"[doğal ses] {self.hata}", flush=True)
                    return False
                self.durum = "basliyor"
                self._nesil += 1
                self.isinma_bitti, self.isinan, self.ornekler, self.sunucu_hazir_ses = False, set(), {}, None
                try:
                    self._sureci_baslat()
                except Exception as e:
                    self.durum, self.hata = "hata", f"Doğal ses sunucusu başlatılamadı: {e}"
                    return False
            surec = self.surec
        son = time.time() + bekle_sn
        while time.time() < son:
            if self.surec is not surec:  # bu arada durduruldu ya da yeniden başlatıldı: sonucu o çağrı belirler
                return self.durum == "hazir"
            if surec.poll() is not None:
                self.durum, self.hata = "hata", (f"Doğal ses sunucusu kapandı (kod {surec.returncode}). "
                                                 f"Ayrıntı: {self._gunluk_yolu()}")
                return False
            if self.saglik():
                self.durum, self.hata = "hazir", ""
                self._isitmayi_baslat()
                return True
            if self._sunucu_hatasi:  # sunucu açıldı ama modeli yükleyemedi
                self.durum, self.hata = "hata", f"Doğal ses modeli yüklenemedi: {self._sunucu_hatasi}"
                self.durdur_sureci()
                return False
            time.sleep(0.5)
        self.durum, self.hata = "hata", "Doğal ses sunucusu zamanında açılmadı."
        return False

    def _isitmayi_baslat(self):
        """Seslerin ısıtmasını (bu sunucu için) bir kez başlatır."""
        if self.isinma_bitti or self._isitilan_nesil == self._nesil:
            return
        self._isitilan_nesil = self._nesil
        threading.Thread(target=self._isit, args=(self._nesil,), daemon=True).start()

    def durdur_sureci(self):
        if self.surec and self.surec.poll() is None:
            self.surec.terminate()
            try:
                self.surec.wait(5)
            except Exception:
                self.surec.kill()
        self.surec = None

    def _isit(self, nesil=None):
        """Her sesin referans kaydı ilk kullanımda işlenir (~5 sn). Açılışta sırayla, örnek cümleyle yapılır;
        bitene kadar `kullanilabilir()` False döner ve satırları Windows sesi okur. Her cinsiyetin ilk sesleri önce.
        Hafif motorda gerekmez: ölçümler pakette hazırdır, sesleri sunucu kendisi hazırlar."""
        nesil = self._nesil if nesil is None else nesil
        def sira(ses):
            ayni = [x["id"] for x in self.sesler if x["cinsiyet"] == ses["cinsiyet"]]
            return ayni.index(ses["id"])
        try:
            # Seslerin ölçümleri pakette hazırsa (sesler\uyum.json) örnek üretmeye gerek yok: doğal ses hemen
            # kullanılır. Sunucu her sesi ilk kullanımda (~1 sn) ya da açılışta arka planda hazırlar.
            if not os.environ.get("CTA_UYUM_HAZIRLA") and self.sesler and \
                    all(s["id"] in self.uyum_verisi() for s in self.sesler):
                return
            for ses in sorted(self.sesler, key=sira):
                if self.durum != "hazir" or nesil != self._nesil:
                    return
                try:
                    parcalar = list(self.akis(ORNEK_CUMLE, ses, ilk_parca_sn=90, olcum=False))
                    if parcalar:
                        self.ornekler[ses["id"]] = np.concatenate(parcalar)
                except Exception as e:
                    print(f"[doğal ses] {ses['id']} ısıtılamadı: {e}", flush=True)
                    if self.surec is not None and self.surec.poll() is not None:
                        self.hata_oldu(e)
                        return
        finally:
            if nesil == self._nesil:  # bu arada sunucu yeniden başlatıldıysa onun ısıtması sürüyor
                self.isinma_bitti = True

    def durdur(self):
        self.durdur_sureci()
        self.durum = "kapali"

    def kullanilabilir(self):
        return self.durum == "hazir" and self.isinma_bitti and time.time() >= self.devre_disi_kadar and bool(self.sesler)

    _uyum = None

    def uyum_verisi(self):
        """Seslerin önceden ölçülmüş ses izi ve perdesi: {ses id: {oran: {"iz": [...], "perde": Hz}}} ya da {}.
        sesler\\uyum.json dosyasından okunur (paket\\hafif_ses\\uyum_hazirla.py üretir). Sesi konuşana uydurma
        (ses_uyum.Uyumlayici) bunları kullanır; yoksa açılışta her sesle örnek cümle üretilip ölçülür."""
        if self._uyum is None:
            self._uyum = {}
            try:
                with open(os.path.join(self.klasor, "sesler", "uyum.json"), encoding="utf-8") as f:
                    sesler = json.load(f).get("sesler")
                if isinstance(sesler, dict):
                    self._uyum = sesler
            except (OSError, ValueError, TypeError, AttributeError):
                pass
        return self._uyum

    # ---------- ses seçimi ----------
    def ses_esle(self, profil):
        """Windows profil adı (erkek2, kadin1...) -> aynı cinsiyetten doğal ses (aynı sırada).
        Böylece konuşmacı tanıma hangi profili verdiyse doğal seste de aynı kişi aynı sesi alır."""
        cins = "kadin" if (profil or "").startswith("kadin") else "erkek"
        havuz = [s for s in self.sesler if s["cinsiyet"] == cins] or self.sesler
        if not havuz:
            return None
        try:
            sira = int("".join(c for c in (profil or "") if c.isdigit()) or 1) - 1
        except ValueError:
            sira = 0
        return havuz[sira % len(havuz)]

    # ---------- üretim ----------
    YAVAS_ILK_SES_MS = 1500  # güçlü motorda ilk ses bundan geç geliyorsa satır "yavaş" sayılır
    YAVAS_SINIRI = 3         # art arda bu kadar yavaş satırdan sonra hafif motora geçilir

    def hafife_gec(self, neden):
        """Güçlü motor yetişemiyor ya da yanıt vermiyor: sunucusunu kapatır, bu oturum için uygulamayla gelen hafif
        motora (işlemci) geçer. Hafif motor yoksa False (o zaman Windows sesi okur)."""
        global _gecici_hafif
        h = hafif_kurulumu()
        if self.motor != "guclu" or not h:
            return False
        with self.kilit:
            self.durdur_sureci()
            self.motor, self.hafif, self.klasor, self.ornek_hizi = "hafif", h, h["kok"], 24000
            self.sesler = sesleri_oku(self.klasor)
            self.durum, self.devre_disi_kadar, self.hata = "kapali", 0.0, ""
            self.isinma_bitti, self.isinan, self.ornekler, self.sunucu_hazir_ses = False, set(), {}, None
            self._uyum, self.son_gecikme_ms, self.son_hiz, self.akis_hizi = None, None, None, 1.0
            self.ust_uste_yavas = 0
            self.degisim += 1
            self.gecis_notu = (f"Güçlü ses modeli {neden}; bu oturumda hafif modelle devam ediliyor. Güçlü model oyunla "
                               "aynı ekran kartını kullandığı için oyun sırasında gecikebilir.")
            _gecici_hafif = True
        print(f"[doğal ses] güçlü model {neden} — hafif modele geçildi", flush=True)
        threading.Thread(target=self.baslat, daemon=True).start()
        return True

    def akis(self, metin, ses, ilk_parca_sn=3.5, toplam_sn=60.0, olcum=True):
        """Metni `ses` ile üretir; PCM parçalarını (float32, self.ornek_hizi) geldikçe verir (üreteç)."""
        istek_govdesi = {"model": MODEL_ID, "input": metin, "seed": ses["tohum"], "response_format": "pcm",
                         "stream_format": "audio", "options": {"retry_badcase": False}}
        if ses.get("id"):  # ön ayarlı ses (referans kaydı + metni); yoksa ses tasarımı: tarif metnin başında
            istek_govdesi["voice"] = ses["id"]
        govde = json.dumps(istek_govdesi).encode("utf-8")
        istek = urllib.request.Request(self.adres + "/v1/audio/speech", data=govde, method="POST",
                                       headers={"Content-Type": "application/json"})
        t0 = time.time()
        kalan = b""
        ornek = 0
        ilk = True
        t_ilk = None
        ilk_ornek = 0
        with urllib.request.urlopen(istek, timeout=ilk_parca_sn) as yanit:
            while True:
                parca = yanit.read1(9600) if hasattr(yanit, "read1") else yanit.read(9600)
                if not parca:
                    break
                if ilk:
                    t_ilk = time.time()
                    if olcum:
                        self.son_gecikme_ms = int((t_ilk - t0) * 1000)
                    ilk = False
                parca = kalan + parca
                n = len(parca) // 2 * 2
                kalan = parca[n:]
                if n:
                    x = np.frombuffer(parca[:n], np.int16).astype(np.float32) / 32768.0
                    if not ornek:
                        ilk_ornek = len(x)
                    ornek += len(x)
                    yield x
                if time.time() - t0 > toplam_sn:
                    break
        if ornek and olcum:  # ısıtma istekleri ölçüme katılmaz (tek kelimede açılış payı baskın)
            self.son_hiz = round((time.time() - t0) / (ornek / self.ornek_hizi), 2)
            if self.motor == "guclu":  # yetişiyor mu? (cal() sayaca bakıp gerekirse hafife geçer)
                yavas = (self.son_gecikme_ms or 0) > self.YAVAS_ILK_SES_MS or \
                    (ornek / self.ornek_hizi > 1.0 and self.son_hiz > 1.0)
                self.ust_uste_yavas = self.ust_uste_yavas + 1 if yavas else 0
            sonraki = (ornek - ilk_ornek) / self.ornek_hizi
            if t_ilk and sonraki > 0.5:  # yumuşatılmış akış hızı
                self.akis_hizi = 0.7 * self.akis_hizi + 0.3 * ((time.time() - t_ilk) / sonraki)
        if ses.get("id"):
            self.isinan.add(ses["id"])

    def on_tampon_sn(self, tahmini_sn):
        """Çalmaya başlamadan biriktirilecek ses: üretim çalmaktan yavaşsa sonuna kadar takılmadan
        gidecek kadar (tahmini süre x (1 - 1/hız)), değilse 0,25 sn."""
        h = max(self.akis_hizi, 0.05)
        return min(tahmini_sn, max(0.25, tahmini_sn * (1 - 1 / h) + 0.25))

    def cal(self, metin, ses, seviye=1.0, oynatici=None, oran=1.0):
        """Üretirken çalar: önce kısa bir ön tampon, sonra akış. Dönüş: çalınan saniye.
        Hata fırlatırsa çağıran o satırı Windows sesiyle okur."""
        tahmini = max(0.8, len(metin) / HARF_SN)
        tampon_sn = self.on_tampon_sn(tahmini)
        bekleyen, biriken = [], 0.0
        oynat = None
        sure = 0.0
        try:
            kaydirici = None
            if abs(oran - 1.0) > 0.005:  # ses uyarlaması: perde + tını kaydırması, akışta kesintisiz
                import ses_uyum
                kaydirici = ses_uyum.AkisKaydirici(oran)
            for x in self.akis(metin, ses):
                if kaydirici:
                    x = kaydirici.isle(x)
                x = np.clip(x * seviye, -1, 1)
                sure += len(x) / self.ornek_hizi
                if oynat is None:
                    bekleyen.append(x)
                    biriken += len(x) / self.ornek_hizi
                    if biriken < tampon_sn:
                        continue
                    oynat = oynatici or _HoparlorOynatici(self.ornek_hizi)
                    for b in bekleyen:
                        oynat.cal(b)
                    bekleyen = []
                else:
                    oynat.cal(x)
            if oynat is None:  # akış ön tampon dolmadan bitti: kısa satır ya da erken kesilme
                if sure <= 0:
                    raise RuntimeError("sunucu ses üretmedi (ayrıntı: sunucu günlüğü)")
                if len(metin) >= 15 and sure < 0.35 * tahmini:
                    raise KisaCikti(f"cümle erken kesildi ({sure:.1f} sn, beklenen ~{tahmini:.1f} sn)")
                oynat = oynatici or _HoparlorOynatici(self.ornek_hizi)
                for b in bekleyen:
                    oynat.cal(b)
        finally:
            if oynat is not None:
                oynat.bitir()
        if self.motor == "guclu" and self.ust_uste_yavas >= self.YAVAS_SINIRI:
            self.hafife_gec("canlı seslendirmeye yetişemedi")
        return sure

    def hata_oldu(self, e):
        # Güçlü motor yanıt vermedi / kapandı: Windows sesine (kadın sesi Tolga'dan türetilir, robotik duyulur) düşmek
        # yerine hafif doğal seslere geçilir.
        if self.motor == "guclu" and self.hafife_gec(f"yanıt vermedi ({e})"):
            return
        self.hata = f"Doğal ses: {e}"
        self.devre_disi_kadar = time.time() + 30  # 30 sn Windows sesiyle devam, sonra tekrar dene
        print(f"[doğal ses] {e} — 30 sn Windows sesine geçildi", flush=True)
        if not self.saglik(0.5):
            self.durum = "hata"
            if self.surec is not None and self.surec.poll() is not None:  # sunucu kapanmış (çoğunlukla bellek)
                self.hata = ("Doğal ses sunucusu kapandı; büyük olasılıkla bellek yetmedi. Windows sesi okumaya devam "
                             "ediyor. Açık programları kapatıp Türkçe ses sayfasından doğal sesleri yeniden açabilirsiniz.")

    def ozet(self):
        durum = "basliyor" if (self.durum == "hazir" and not self.isinma_bitti) else self.durum
        return {"kurulu": bool(self.klasor), "durum": durum, "hata": self.hata, "not": self.gecis_notu,
                "sesler": [{k: s[k] for k in ("id", "ad", "cinsiyet", "tanitim")} for s in self.sesler],
                "gecikme_ms": self.son_gecikme_ms, "hiz": round(self.akis_hizi, 2) if self.son_hiz else None,
                "isinan": len(self.isinan), "ses_sayisi": len(self.sesler),
                "motor": self.motor, "motor_adi": MOTOR_ADLARI.get(self.motor, ""),
                # panel: güçlü paket kuruluysa iki motor arasında seçim sunulur
                "hafif_var": hafif_kurulumu() is not None, "guclu_var": kurulum_klasoru() is not None, "tercih": _tercih}


class _HoparlorOynatici:
    """Varsayılan hoparlöre akış halinde çalar (soundcard). Bizim sürecimizden çalındığı için
    süreç loopback'i bunu oyun sesi sanmaz."""

    def __init__(self, ornek_hizi=ORNEK_HIZI):
        import soundcard
        self._ic = soundcard.default_speaker().player(samplerate=int(ornek_hizi), channels=1,
                                                      blocksize=max(480, int(ornek_hizi) // 20))
        self._ic.__enter__()

    def cal(self, x):
        self._ic.play(x.reshape(-1, 1))

    def bitir(self):
        try:
            self._ic.__exit__(None, None, None)
        except Exception:
            pass


_paylasilan = None
_paylasilan_kilit = threading.Lock()


def paylasilan(baslat=True):
    """Süreç boyunca tek istemci. Hiçbir motor yoksa None. baslat=True ise sunucu arka planda açılır.
    Tercih edilen motor değiştiyse (tercih_ayarla) eski sunucu kapatılır ve yenisiyle baştan kurulur."""
    global _paylasilan
    with _paylasilan_kilit:
        if _paylasilan is not None and _paylasilan.motor != (motor_sec() or _paylasilan.motor):
            _paylasilan.durdur()
            _paylasilan = None
        if _paylasilan is None:
            d = DogalSes()
            if not d.klasor and (os.environ.get("CTA_DOGAL_SES_YOK") or not d.saglik(0.3)):
                return None
            _paylasilan = d
        d = _paylasilan
    if baslat and d.durum in ("kapali", "hata") and time.time() >= d.devre_disi_kadar:
        threading.Thread(target=d.baslat, daemon=True).start()
    return d


def kapat():
    if _paylasilan:
        _paylasilan.durdur()


if __name__ == "__main__":  # elle deneme: python dogal_ses.py "Merhaba." [ses_id]
    d = DogalSes()
    print("klasör:", d.klasor, "| sesler:", [s["id"] for s in d.sesler])
    if not d.baslat():
        sys.exit(d.hata)
    ses = next((s for s in d.sesler if len(sys.argv) > 2 and s["id"] == sys.argv[2]), d.sesler[0])
    t = time.time()
    sure = d.cal(sys.argv[1] if len(sys.argv) > 1 else "Arabaya bin, polisler peşimizde!", ses)
    print(f"{ses['id']}: {sure:.1f} sn ses, ilk parça {d.son_gecikme_ms} ms, toplam {time.time() - t:.1f} sn, hız {d.son_hiz}")
