# PyInstaller ayarı: hafif doğal ses sunucusu (hafif_ses\sunucu.py -> cta_ses.exe).
# derle.ps1 çağırır; ana uygulamanın .venv'iyle DEĞİL, .venv-ses ortamıyla derlenir (PyTorch orada):
#   .venv-ses\Scripts\python.exe -m PyInstaller --distpath paket\cikti\dist-ses --workpath paket\cikti\build-ses paket\HafifSes.spec
# Çıktı (cta_ses.exe + _internal) uygulamanın içine, hafif_ses\motor klasörüne kopyalanır; model ve sesler ayrı
# klasörlerdedir (hafif_ses\model, hafif_ses\sesler) ve sunucuya komut satırından verilir.
import os

from PyInstaller.utils.hooks import collect_data_files

PROJE = os.path.abspath(os.path.join(SPECPATH, ".."))

# pocket_tts adlandırılmış ayarları kendi config klasöründen okur (biz model klasöründeki config.yaml'ı veriyoruz,
# yine de eksik kalmasın). PyTorch, scipy, soundfile (libsndfile) PyInstaller'ın kendi kancalarıyla toplanır.
datas = collect_data_files("pocket_tts", includes=["config/*.yaml"])

a = Analysis(
    [os.path.join(PROJE, "hafif_ses", "sunucu.py")],
    pathex=[],
    datas=datas,
    binaries=[],
    # fonksiyon içinde içe aktarılanlar (sunucu.py yukle, pocket_tts_turkish.audio/model)
    hiddenimports=["pocket_tts_turkish", "pocket_tts", "pocket_tts.models.tts_model", "soundfile", "scipy.signal",
                   "scipy.io.wavfile", "yaml", "sentencepiece", "tokenizers", "safetensors.torch"],
    # pocket_tts'in web arayüzü ve komut satırı (pocket_tts.main) kullanılmıyor
    excludes=["tkinter", "matplotlib", "IPython", "pytest", "fastapi", "uvicorn", "starlette", "torchvision",
              "torchaudio", "tensorboard", "PyInstaller"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts,
    # UTF-8 kipi (python -X utf8): derlenmiş programda PYTHONUTF8 ortam değişkeni etkisizdir. pocket_tts model ayarını
    # (içinde model klasörünün yolu yazan geçici YAML) kodlama belirtmeden açar; UTF-8 kipi olmazsa Türkçe Windows'ta
    # cp1254 ile okunur ve kullanıcı adında Türkçe karakter olan bilgisayarda model yolu bozulur.
    [("X utf8", None, "OPTION")],
    exclude_binaries=True,
    name="cta_ses",
    icon=os.path.join(SPECPATH, "gorseller", "uygulama.ico"),
    console=True,  # çıktısı günlük dosyasına yönlendirilir; uygulama penceresiz (CREATE_NO_WINDOW) başlatır
    upx=False,
    version=os.path.join(SPECPATH, "cikti", "surum_bilgisi_ses.txt"),
)
coll = COLLECT(exe, a.binaries, a.datas, name="cta_ses", upx=False)
