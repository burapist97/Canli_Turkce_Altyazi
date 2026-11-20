# Canlı Türkçe Altyazı — Doğal Ses Paketi kurulumu (Store dışı, isteğe bağlı)
#   powershell -NoProfile -ExecutionPolicy Bypass -File paket\dogal_ses\kur.ps1 [-Kok <klasör>] [-Motor oto|vulkan|cuda]
#
# İndirir (her dosya sha256 ile doğrulanır):
#   audio.cpp v0.9.5 sunucusu (Apache-2.0, github.com/0xShug0/audio.cpp)   ~85 MB Vulkan / ~1 GB CUDA
#   VoxCPM2 q8_0 GGUF (OpenBMB, Apache-2.0, huggingface.co/audio-cpp)       2,96 GB
# Kopyalar: sesler\ (yapay Türkçe karakter sesleri; kaynağı ses.json'larda)
# Yazar:    <Kök>\paket.json (backend). Uygulama sunucuyu kendisi başlatır (dogal_ses.py).
# Sisteme bir şey kurmaz, PATH'e ve kayıt defterine dokunmaz; kaldırmak için klasörü silmek yeter.
param(
    [string]$Kok = "",
    [ValidateSet("oto", "vulkan", "cuda")]
    [string]$Motor = "oto"
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
try { [Console]::OutputEncoding = New-Object Text.UTF8Encoding $false } catch {}
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$Burasi = $PSScriptRoot

# Motor ASCII olmayan yolları açamayabiliyor (ör. kullanıcı adında Türkçe harf): o durumda C:\CTA-DogalSes
if (-not $Kok) {
    $Kok = Join-Path $env:LOCALAPPDATA "Programs\CTA-DogalSes"
    if ($Kok -match '[^\x00-\x7F]') { $Kok = "C:\CTA-DogalSes" }
}
if ($Kok -match '[^\x00-\x7F]') { throw "Kurulum klasörü yalnız İngilizce harf içermeli: $Kok" }
Write-Output "Kurulum klasörü: $Kok"

$SURUM = "v0.9.5"
$PAKETLER = @{
    vulkan = @(@{ ad = "audio-v0.9.5-bin-windows-x64-vulkan.zip"; boy = 85685046
                  sha = "dc103660e5fac85860677af2b39361154d863953777ab812d891721e6e163148" })
    cuda   = @(@{ ad = "audio-v0.9.5-bin-windows-x64-cuda12.4.zip"; boy = 469569407
                  sha = "81f38a0a62935bdf4b2605541a21d50223b2e12b661887031705dd8a369f844b" },
               @{ ad = "audio-v0.9.5-cudart-windows-x64-cuda12.4.zip"; boy = 607273675
                  sha = "fa55dfaff1d4b5c6e8fac460d64f380b9df76cd46435f187c39b05700f623a7e" })
}
$MODEL_URL = "https://huggingface.co/audio-cpp/audio.cpp-gguf/resolve/7a103b33f04120535bdfe97b5f65b79d3c90d708/VoxCPM2-GGUF/voxcpm2-q8_0.gguf"
$MODEL_SHA = "8df1faf274e1bdeedef1fd9ddd6aba6632536f66f2e080991d2352af35ceef72"
$MODEL_BOY = 2955007488

function Sha256([string]$yol) { (Get-FileHash -Algorithm SHA256 -LiteralPath $yol).Hash.ToLower() }
function Indir([string]$url, [string]$hedef, [string]$sha) {
    if ((Test-Path -LiteralPath $hedef) -and ((Sha256 $hedef) -eq $sha)) { Write-Output "  var ve doğru: $(Split-Path $hedef -Leaf)"; return }
    Write-Output "  indiriliyor: $(Split-Path $hedef -Leaf)"
    $gecici = "$hedef.part"
    curl.exe -L --fail --retry 3 --retry-delay 5 -C - --progress-bar -o $gecici $url
    if ($LASTEXITCODE -ne 0) { throw "İndirme başarısız: $url" }
    $gelen = Sha256 $gecici
    if ($gelen -ne $sha) { Remove-Item -LiteralPath $gecici -Force; throw "Dosya bozuk indi (sha256 tutmadı): $hedef" }
    Move-Item -LiteralPath $gecici -Destination $hedef -Force
    Write-Output "  tamam (sha256 doğru)"
}

# 1) Ekran kartına göre motor
if ($Motor -eq "oto") {
    $kartlar = @(Get-CimInstance Win32_VideoController | ForEach-Object { $_.Name })
    Write-Output ("Ekran kartları: " + ($kartlar -join ", "))
    $Motor = $(if ($kartlar -match "NVIDIA") { "cuda" } else { "vulkan" })
}
Write-Output "Motor: $Motor"
New-Item -ItemType Directory -Force (Join-Path $Kok "indirme"), (Join-Path $Kok "model"), (Join-Path $Kok "motor") | Out-Null

# 2) Motor (audio.cpp sunucusu)
foreach ($p in $PAKETLER[$Motor]) {
    $zip = Join-Path $Kok ("indirme\" + $p.ad)
    Indir "https://github.com/0xShug0/audio.cpp/releases/download/$SURUM/$($p.ad)" $zip $p.sha
    $ac = Join-Path $Kok "indirme\_ac"
    if (Test-Path $ac) { Remove-Item -Recurse -Force $ac }
    Expand-Archive -LiteralPath $zip -DestinationPath $ac -Force
    # zip'in içindeki klasör yapısı ne olursa olsun: exe/dll'lerin bulunduğu klasörü motor\ içine düzle
    $kaynak = Get-ChildItem $ac -Recurse -File | Where-Object { $_.Extension -in ".exe", ".dll" } |
              Select-Object -ExpandProperty DirectoryName -Unique
    foreach ($k in $kaynak) { Get-ChildItem $k -File | Copy-Item -Destination (Join-Path $Kok "motor") -Force }
    Get-ChildItem $ac -Recurse -File -Include LICENSE*, *.md, THIRD* | Copy-Item -Destination (Join-Path $Kok "motor") -Force -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force $ac
}
$sunucu = Join-Path $Kok "motor\audiocpp_server.exe"
if (-not (Test-Path $sunucu)) { throw "Paket içinde audiocpp_server.exe yok" }
Write-Output "MOTOR_OK"

# 3) Model
$model = Join-Path $Kok "model\voxcpm2-q8_0.gguf"
Indir $MODEL_URL $model $MODEL_SHA
if ((Get-Item -LiteralPath $model).Length -ne $MODEL_BOY) { throw "Model boyutu beklenen gibi değil" }
Write-Output "MODEL_OK"

# 4) Karakter sesleri
$sesHedef = Join-Path $Kok "sesler"
New-Item -ItemType Directory -Force $sesHedef | Out-Null
Copy-Item -Path (Join-Path $Burasi "sesler\*") -Destination $sesHedef -Recurse -Force
Write-Output ("SESLER_OK: " + ((Get-ChildItem $sesHedef -Directory | ForEach-Object { $_.Name }) -join ", "))

# 5) paket.json + cihaz listesi
$cihazlar = ""
try { $cihazlar = (& (Join-Path $Kok "motor\audiocpp_cli.exe") --list-devices 2>&1 | Out-String) } catch {}
if ($cihazlar) { Write-Output $cihazlar.Trim() }
$paket = [ordered]@{ backend = $Motor; surum = $SURUM; model = "voxcpm2-q8_0.gguf"; cihaz = $null;
                     kuruldu = (Get-Date -Format "yyyy-MM-dd HH:mm") }
[IO.File]::WriteAllText((Join-Path $Kok "paket.json"), (($paket | ConvertTo-Json) + "`n"), (New-Object Text.UTF8Encoding $false))
Remove-Item -Recurse -Force (Join-Path $Kok "indirme") -ErrorAction SilentlyContinue
Write-Output "KURULUM_OK: $Kok"
