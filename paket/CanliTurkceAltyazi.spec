# PyInstaller ayarı:  pyinstaller paket/CanliTurkceAltyazi.spec  (derle.ps1 çağırır)
import os

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

PROJE = os.path.abspath(os.path.join(SPECPATH, ".."))
ARAYUZ = ["config.json", "sozluk.json", "arayuz.html", "arayuz.css", "arayuz.js", "overlay.html",
          "altyazi_stil.js"]

datas = [(os.path.join(PROJE, f), ".") for f in ARAYUZ]
datas.append((os.path.join(SPECPATH, "gorseller", "uygulama.ico"), "."))  # tepsi simgesi (tepsi.py)
datas += [(os.path.join(PROJE, f), ".") for f in ("LICENSE", "NOTICE")]  # AGPL-3.0: lisans programla birlikte dağıtılır
datas += collect_data_files("rapidocr")  # OCR modelleri (.onnx) ve ayar dosyaları
datas += collect_data_files("webview")
# Anahtarsız çevrimdışı çeviri modeli (paket\model_hazirla.ps1 üretir)
MODEL = os.path.join(PROJE, "modeller", "en-tr")
if not os.path.exists(os.path.join(MODEL, "model.bin")):
    raise SystemExit("Çeviri modeli yok. Önce: powershell -ExecutionPolicy Bypass -File paket\\model_hazirla.ps1")
datas += [(os.path.join(MODEL, f), "modeller/en-tr") for f in os.listdir(MODEL)]
# Karakter sesleri: konuşmacı parmak izi modeli (TitaNet-small) + kadın/erkek ağırlıkları (paket\cinsiyet_egit.py)
KONUSMACI = os.path.join(PROJE, "modeller", "konusmaci")
for f in ("titanet_small.onnx", "cinsiyet.json", "cinsiyet_ecapa.onnx"):
    if not os.path.exists(os.path.join(KONUSMACI, f)):
        raise SystemExit(f"Konuşmacı modeli eksik: modeller/konusmaci/{f}")
    datas.append((os.path.join(KONUSMACI, f), "modeller/konusmaci"))
binaries = collect_dynamic_libs("ctranslate2")
# sherpa-onnx kendi onnxruntime.dll'ini sherpa_onnx/lib içinde getirir (OCR'ınkiyle aynı süreçte sorunsuz, denendi)
binaries += collect_dynamic_libs("sherpa_onnx")

a = Analysis(
    [os.path.join(PROJE, "uygulama.py")],
    pathex=[PROJE],
    datas=datas,
    binaries=binaries,
    hiddenimports=["rapidocr.inference_engine.onnxruntime", "obs_baglanti", "ctranslate2", "sentencepiece",
                   # bilgisayar oyunu modu: ekran yakalama (fonksiyon içinde içe aktarılıyor)
                   "pc_katman", "mss", "mss.windows",
                   # karakter sesleri: oyun sesi (WASAPI) + konuşmacı tanıma
                   "oyun_sesi", "konusmaci", "surec_loopback", "ses_kisici", "com_yardim", "ceviri_hatti", "ses_uyum", "okunus", "dogal_ses", "soundcard", "soundcard.mediafoundation", "sherpa_onnx",
                   "comtypes", "comtypes.client",
                   # Türkçe ses (WinRT) — fonksiyon içinde içe aktarılıyor
                   "winrt.windows.media.speechsynthesis", "winrt.windows.storage.streams",
                   "winrt.windows.foundation", "winrt.windows.foundation.collections"],
    excludes=["tkinter", "matplotlib", "torch", "paddle", "openvino", "tensorrt",
              "playwright", "pytest", "IPython"],  # PIL dışlanmaz: rapidocr 3.x onu içe aktarır
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="CanliTurkceAltyazi",
    icon=os.path.join(SPECPATH, "gorseller", "uygulama.ico"),
    console=False,
    upx=False,
    version=os.path.join(SPECPATH, "cikti", "surum_bilgisi.txt"),
)
coll = COLLECT(exe, a.binaries, a.datas, name="CanliTurkceAltyazi", upx=False)
