#  Çevrimdışı İngilizce -> Türkçe çeviri modelini hazırlar (bir kere, derlemeden önce).
#
#  Kaynak: Helsinki-NLP/opus-mt-tc-big-en-tr (OPUS-MT, CC BY 4.0 — ticari kullanım serbest, kaynak belirtilmeli)
#  Çıktı:  modeller\en-tr\  (CTranslate2 int8, ~230 MB; model.bin, source.spm, target.spm, README.md)
#
#  Dönüştürme araçları (torch, transformers) uygulamanın .venv'ine KURULMAZ; geçici ayrı bir ortam kullanılır.
#  powershell -ExecutionPolicy Bypass -File paket\model_hazirla.ps1

$ErrorActionPreference = 'Stop'
$PROJE = Split-Path $PSScriptRoot -Parent
$HEDEF = Join-Path $PROJE 'modeller\en-tr'
$GECICI = Join-Path $env:TEMP 'cta_model_donustur'

if (Test-Path (Join-Path $HEDEF 'model.bin')) { Write-Host "[OK] Model zaten hazır: $HEDEF"; exit 0 }

Write-Host "Geçici dönüştürme ortamı kuruluyor (torch CPU + transformers, birkaç dakika)..."
py -3.13 -m venv (Join-Path $GECICI 'venv')
$PY = Join-Path $GECICI 'venv\Scripts\python.exe'
& $PY -m pip install -q --disable-pip-version-check torch --index-url https://download.pytorch.org/whl/cpu
& $PY -m pip install -q --disable-pip-version-check transformers sentencepiece ctranslate2 sacremoses

Write-Host "Model indiriliyor ve dönüştürülüyor..."
& (Join-Path $GECICI 'venv\Scripts\ct2-transformers-converter.exe') --model Helsinki-NLP/opus-mt-tc-big-en-tr `
    --output_dir $HEDEF --quantization int8 --copy_files source.spm target.spm README.md --force
if (-not (Test-Path (Join-Path $HEDEF 'model.bin'))) { Write-Host "[X] Dönüştürme başarısız." -ForegroundColor Red; exit 1 }

Remove-Item $GECICI -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "[OK] Model hazır: $HEDEF" -ForegroundColor Green
