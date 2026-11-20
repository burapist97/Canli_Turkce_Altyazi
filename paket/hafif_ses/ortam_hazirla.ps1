#  Hafif doğal ses (Pocket TTS Turkish) - derleme ortamı ve model
#
#  powershell -ExecutionPolicy Bypass -File paket\hafif_ses\ortam_hazirla.ps1
#
#  Yaptıkları:
#    1. .venv-ses  : Python 3.13 + PyTorch (yalnızca işlemci) + pocket-tts + pocket-tts-turkish + PyInstaller
#                    (ana uygulamanın .venv'inden AYRI: oraya torch girmez)
#    2. modeller\pocket-tts-turkish : model dosyaları, sabit sürüm ve SHA-256 doğrulamasıyla (model_indir.py)
#  İkisi de hazırsa bir şey indirmez. Sonrasında paket\derle.ps1 ses sunucusunu derleyip pakete koyar.
#
#  -Kaynak <klasör> : model dosyaları daha önce indirildiyse oradan kopyalanır (yeniden indirilmez)

param([string]$Kaynak = "")

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$PAKET = $PSScriptRoot
$PROJE = Split-Path (Split-Path $PAKET -Parent) -Parent
$VENV = Join-Path $PROJE '.venv-ses'
$PY = Join-Path $VENV 'Scripts\python.exe'

function Adim($m) { Write-Host ""; Write-Host "== $m" -ForegroundColor Cyan }
function Dur($m)  { Write-Host "[X] $m" -ForegroundColor Red; exit 1 }

Adim "1/3 Python ortamı (.venv-ses)"
if (-not (Test-Path $PY)) {
    & py -3.13 -m venv $VENV
    if ($LASTEXITCODE -ne 0) { Dur "Python 3.13 bulunamadı (py -3.13)." }
}
& $PY -m pip install --quiet --upgrade pip
if ($LASTEXITCODE -ne 0) { Dur "pip güncellenemedi." }

Adim "2/3 Paketler (PyTorch işlemci sürümü + Pocket TTS)"
& $PY -m pip install --quiet torch==2.15.0 --index-url https://download.pytorch.org/whl/cpu
if ($LASTEXITCODE -ne 0) { Dur "PyTorch kurulamadı." }
& $PY -m pip install --quiet -r (Join-Path $PAKET 'gereksinimler.txt')
if ($LASTEXITCODE -ne 0) { Dur "Paketler kurulamadı." }
& $PY -c "import torch, pocket_tts, pocket_tts_turkish, PyInstaller; print('[OK] torch', torch.__version__, '| pocket-tts-turkish', pocket_tts_turkish.__name__, '| PyInstaller', PyInstaller.__version__)"
if ($LASTEXITCODE -ne 0) { Dur "Kurulan paketler içe aktarılamadı." }

Adim "3/3 Model (wite-tech/pocket-tts-turkish, CC-BY-4.0)"
if ($Kaynak) { & $PY (Join-Path $PAKET 'model_indir.py') $Kaynak } else { & $PY (Join-Path $PAKET 'model_indir.py') }
if ($LASTEXITCODE -ne 0) { Dur "Model hazırlanamadı." }

Write-Host ""
Write-Host "[OK] Hafif ses ortamı hazır. Şimdi: powershell -ExecutionPolicy Bypass -File paket\derle.ps1" -ForegroundColor Green
