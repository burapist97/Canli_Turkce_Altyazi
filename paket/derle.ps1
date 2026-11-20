#  Canlı Türkçe Altyazı - Microsoft Store (MSIX) derlemesi
#
#  powershell -ExecutionPolicy Bypass -File paket\derle.ps1            -> paket\cikti\*.msix
#  powershell -ExecutionPolicy Bypass -File paket\derle.ps1 -Kur       -> derle + bu bilgisayara kur (Geliştirici modu gerekir)
#  powershell -ExecutionPolicy Bypass -File paket\derle.ps1 -MsixAtla  -> yalnız kurulum programı (Store paketi üretilmez)
#
#  Gerekenler: .venv (requirements-gelistirme.txt), Windows 10/11 SDK (makeappx, makepri),
#              doğal sesler için .venv-ses + model (paket\hafif_ses\ortam_hazirla.ps1)
#
#  -MsixAtla        : MSIX (Store paketi) adımları atlanır; paket\cikti\msix klasörüne dokunulmaz
#  -SesSiz          : doğal ses motoru (Pocket TTS, ~900 MB) pakete konmaz
#  -SesYenidenDerle : ses sunucusu değişmemiş olsa da yeniden derlenir
#  -DenemeAtla      : duman testi atlanır

param([switch]$Kur, [switch]$DenemeAtla, [switch]$MsixAtla, [switch]$SesSiz, [switch]$SesYenidenDerle)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$PAKET = $PSScriptRoot
$PROJE = Split-Path $PAKET -Parent
$CIKTI = Join-Path $PAKET 'cikti'
$PY = Join-Path $PROJE '.venv\Scripts\python.exe'

function Adim($m) { Write-Host ""; Write-Host "== $m" -ForegroundColor Cyan }
function Dur($m)  { Write-Host "[X] $m" -ForegroundColor Red; exit 1 }

if (-not (Test-Path $PY)) { Dur ".venv bulunamadı. Önce: py -3.13 -m venv .venv; .venv\Scripts\pip install -r requirements-gelistirme.txt" }
if ($Kur -and $MsixAtla) { Dur "-Kur, Store paketini kaydeder; -MsixAtla ile birlikte kullanılamaz." }

# Doğal sesler (hafif motor): ayrı ortamda derlenen ses sunucusu + model + sesler
$PY_SES = Join-Path $PROJE '.venv-ses\Scripts\python.exe'
$SES_MODEL = Join-Path $PROJE 'modeller\pocket-tts-turkish'
$SES_SESLER = Join-Path $PROJE 'hafif_ses\sesler'
if (-not $SesSiz) {
    if (-not (Test-Path $PY_SES) -or -not (Test-Path (Join-Path $SES_MODEL 'model.safetensors'))) {
        Dur "Doğal ses ortamı yok. Önce: powershell -ExecutionPolicy Bypass -File paket\hafif_ses\ortam_hazirla.ps1   (doğal sessiz derlemek için: -SesSiz)"
    }
    if (-not (Test-Path (Join-Path $SES_SESLER 'uyum.json'))) {
        Dur "hafif_ses\sesler\uyum.json yok. Önce: .venv\Scripts\python.exe paket\hafif_ses\uyum_hazirla.py"
    }
}

# Windows SDK araçları
if (-not $MsixAtla) {
    $sdk = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin\10.*\x64\makeappx.exe" -ErrorAction SilentlyContinue | Sort-Object FullName | Select-Object -Last 1
    if (-not $sdk) { Dur "Windows SDK (makeappx.exe) bulunamadı. Visual Studio Installer'dan Windows 10/11 SDK kurun." }
    $MAKEAPPX = $sdk.FullName
    $MAKEPRI = Join-Path $sdk.DirectoryName 'makepri.exe'
}

# Sürüm: veri.py -> SURUM = "2.0.0"  (MSIX dört parça ister: 2.0.0.0)
$surum = (Select-String -Path (Join-Path $PROJE 'veri.py') -Pattern '^SURUM = "([\d.]+)"').Matches[0].Groups[1].Value
$surum4 = ($surum.Split('.') + @('0','0','0','0'))[0..3] -join '.'
$magaza = Get-Content (Join-Path $PAKET 'magaza.json') -Raw -Encoding UTF8 | ConvertFrom-Json
Write-Host "Sürüm $surum4  |  Kimlik $($magaza.kimlik_adi)  |  Yayıncı $($magaza.yayinci)"

New-Item -ItemType Directory -Force $CIKTI | Out-Null

Adim "1/6 Görseller"
& $PY (Join-Path $PAKET 'ikon_uret.py')
if ($LASTEXITCODE -ne 0) { Dur "Görseller üretilemedi." }

$v = $surum4.Replace('.', ', ')
function SurumBilgisi($dosya, $aciklama) {
@"
VSVersionInfo(
  ffi=FixedFileInfo(filevers=($v), prodvers=($v)),
  kids=[StringFileInfo([StringTable('041F04B0', [
    StringStruct('CompanyName', '$($magaza.yayinci_adi)'),
    StringStruct('FileDescription', '$aciklama'),
    StringStruct('FileVersion', '$surum4'),
    StringStruct('ProductName', '$($magaza.gorunen_ad)'),
    StringStruct('ProductVersion', '$surum4'),
    StringStruct('LegalCopyright', '(c) $((Get-Date).Year) $($magaza.yayinci_adi)')])]),
    VarFileInfo([VarStruct('Translation', [1055, 1200])])]
)
"@ | Set-Content (Join-Path $CIKTI $dosya) -Encoding UTF8
}

$SES_DIST = Join-Path $CIKTI 'dist-ses\cta_ses'
if ($SesSiz) {
    Adim "2/6 Doğal ses sunucusu: atlandı (-SesSiz)"
} else {
    Adim "2/6 Doğal ses sunucusu (hafif motor, PyInstaller .venv-ses)"
    # Girdiler değişmediyse yeniden derlenmez (PyTorch'lu derleme birkaç dakika sürer)
    $girdiler = @((Join-Path $PROJE 'hafif_ses\sunucu.py'), (Join-Path $PAKET 'HafifSes.spec'), (Join-Path $PAKET 'hafif_ses\gereksinimler.txt'))
    $damga = "$surum4|" + (($girdiler | ForEach-Object { (Get-FileHash $_ -Algorithm SHA256).Hash }) -join '|')
    $damga_dosyasi = Join-Path $CIKTI 'dist-ses\derleme.txt'
    $eski_damga = if (Test-Path $damga_dosyasi) { (Get-Content $damga_dosyasi -Raw).Trim() } else { '' }
    if (-not $SesYenidenDerle -and $eski_damga -eq $damga -and (Test-Path (Join-Path $SES_DIST 'cta_ses.exe'))) {
        Write-Host "[OK] Ses sunucusu güncel, yeniden derlenmedi (zorlamak için -SesYenidenDerle)" -ForegroundColor Green
    } else {
        SurumBilgisi 'surum_bilgisi_ses.txt' "$($magaza.gorunen_ad) (doğal ses)"
        Remove-Item $damga_dosyasi -Force -ErrorAction SilentlyContinue
        & $PY_SES -m PyInstaller --noconfirm --log-level WARN --distpath (Join-Path $CIKTI 'dist-ses') --workpath (Join-Path $CIKTI 'build-ses') (Join-Path $PAKET 'HafifSes.spec')
        if ($LASTEXITCODE -ne 0) { Dur "Ses sunucusu derlenemedi (PyInstaller)." }
        Set-Content $damga_dosyasi $damga -Encoding UTF8
        $mb = [math]::Round((Get-ChildItem $SES_DIST -Recurse -File | Measure-Object Length -Sum).Sum / 1MB)
        Write-Host "[OK] Ses sunucusu derlendi ($mb MB)" -ForegroundColor Green
    }
    # Kurulum klasöründe kullanıcı adı geçer ("C:\Users\Şükrü\..."): derlenmiş sunucu, Türkçe karakterli bir klasördeki
    # modeli açıp bütün sesleri hazırlayabiliyor mu? (2.5.0'da gerçekten bozuktu; model ~420 MB kopyalanır, ~30 sn)
    $env:PYTHONUTF8 = '1'
    & $PY (Join-Path $PROJE 'tests\test_hafif_ses.py') --turkce-yol (Join-Path $SES_DIST 'cta_ses.exe')
    $kod = $LASTEXITCODE
    Remove-Item Env:\PYTHONUTF8
    if ($kod -ne 0) { Dur "Ses sunucusu Türkçe karakterli klasördeki modeli açamadı (çıktı yukarıda)." }
}

Adim "3/6 Uygulama derleniyor (PyInstaller)"
SurumBilgisi 'surum_bilgisi.txt' $magaza.gorunen_ad
& $PY -m PyInstaller --noconfirm --log-level WARN --distpath (Join-Path $CIKTI 'dist') --workpath (Join-Path $CIKTI 'build') (Join-Path $PAKET 'CanliTurkceAltyazi.spec')
if ($LASTEXITCODE -ne 0) { Dur "PyInstaller başarısız." }
$EXE = Join-Path $CIKTI 'dist\CanliTurkceAltyazi\CanliTurkceAltyazi.exe'

if (-not $SesSiz) {
    # Doğal sesler uygulamanın içine: _internal\hafif_ses\{motor, model, sesler, LISANSLAR} (dogal_ses.hafif_kurulumu)
    $HAFIF = Join-Path $CIKTI 'dist\CanliTurkceAltyazi\_internal\hafif_ses'
    New-Item -ItemType Directory -Force (Join-Path $HAFIF 'model\voices') | Out-Null
    Copy-Item $SES_DIST (Join-Path $HAFIF 'motor') -Recurse
    foreach ($f in 'config.yaml', 'model.safetensors', 'tokenizer.model', 'kaynak.json') {
        Copy-Item (Join-Path $SES_MODEL $f) (Join-Path $HAFIF 'model')
    }
    Copy-Item (Join-Path $SES_MODEL 'voices\*.wav') (Join-Path $HAFIF 'model\voices')
    Copy-Item $SES_SESLER (Join-Path $HAFIF 'sesler') -Recurse
    # Lisans metinleri: ses sunucusuyla birlikte dağıtılan kitaplıkların kendi lisans dosyaları
    $LIS = Join-Path $HAFIF 'LISANSLAR'
    New-Item -ItemType Directory -Force $LIS | Out-Null
    Copy-Item (Join-Path $PAKET 'hafif_ses\LISANSLAR.txt') (Join-Path $LIS 'OKUBENI.txt')
    New-Item -ItemType Directory -Force (Join-Path $LIS 'libsndfile') | Out-Null
    Copy-Item (Join-Path $PROJE '.venv-ses\Lib\site-packages\_soundfile_data\COPYING') (Join-Path $LIS 'libsndfile')
    $derleme_araclari = 'pyinstaller', 'pyinstaller_hooks_contrib', 'altgraph', 'pefile', 'pywin32_ctypes', 'pip', 'setuptools'
    foreach ($d in Get-ChildItem (Join-Path $PROJE '.venv-ses\Lib\site-packages') -Directory -Filter '*.dist-info') {
        $ad = $d.Name -replace '\.dist-info$', ''
        if ($derleme_araclari -contains ($ad -replace '-[^-]+$', '')) { continue }
        $dosyalar = @(Get-ChildItem $d.FullName -File | Where-Object { $_.Name -match '^(LICEN|COPYING|NOTICE|AUTHORS)' })
        $alt = Join-Path $d.FullName 'licenses'
        if (-not $dosyalar -and -not (Test-Path $alt)) { continue }
        $hedef = Join-Path $LIS $ad
        New-Item -ItemType Directory -Force $hedef | Out-Null
        foreach ($f in $dosyalar) { Copy-Item $f.FullName $hedef }
        if (Test-Path $alt) { Copy-Item (Join-Path $alt '*') $hedef -Recurse }
    }
    $mb = [math]::Round((Get-ChildItem $HAFIF -Recurse -File | Measure-Object Length -Sum).Sum / 1MB)
    Write-Host "[OK] Doğal sesler pakete kondu ($mb MB: ses sunucusu + model + sesler)" -ForegroundColor Green
}

if (-not $DenemeAtla) {
    Adim "4/6 Duman testi (pencere açılıyor, kendiliğinden kapanacak)"
    $deneme = Join-Path $env:TEMP 'cta_derleme_deneme Çağrı Ünlü'  # ayar klasöründe de kullanıcı adı geçer
    Remove-Item $deneme -Recurse -Force -ErrorAction SilentlyContinue
    # Uygulama, adı Türkçe karakterli bir klasörden çalıştırılır (bağlantı noktası: dosyalar kopyalanmaz). Kurulum
    # programı kullanıcının klasörüne kurduğu için gerçek yol çoğu zaman böyledir ("C:\Users\Şükrü\AppData\...");
    # bazı kitaplıklar böyle yollardaki dosyaları açamıyor (sentencepiece: hazır çeviri hiç çalışmıyordu).
    $EXE_DENEME = $EXE
    $tr_klasor = Join-Path $env:TEMP 'cta_deneme_Şükrü Öğün ığİ'
    if (Test-Path $tr_klasor) { [IO.Directory]::Delete($tr_klasor) }  # yalnız bağlantıyı siler, hedefe dokunmaz
    try {
        New-Item -ItemType Junction -Path $tr_klasor -Target (Join-Path $CIKTI 'dist\CanliTurkceAltyazi') -ErrorAction Stop | Out-Null
        $EXE_DENEME = Join-Path $tr_klasor 'CanliTurkceAltyazi.exe'
    } catch {
        Write-Host "[!] Türkçe adlı deneme klasörü açılamadı, uygulama kendi klasöründen denenecek: $_" -ForegroundColor Yellow
    }
    $env:CTA_VERI = $deneme
    $p = Start-Process $EXE_DENEME -ArgumentList '--deneme' -PassThru
    $bitti = $p.WaitForExit(180000)
    if (-not $bitti) { Stop-Process -Id $p.Id -Force }
    Remove-Item Env:\CTA_VERI
    if ($EXE_DENEME -ne $EXE) { [IO.Directory]::Delete($tr_klasor) }
    if (-not $bitti) { Dur "Uygulama 180 sn içinde kapanmadı." }
    $gunluk = Get-Content (Join-Path $deneme 'gunluk.txt') -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
    if ($gunluk -notmatch 'DENEME_OK') { Write-Host $gunluk; Dur "Derlenen uygulama açılmadı (günlük yukarıda)." }
    # Doğal sesler pakete konduysa gerçekten denenmiş olmalı (bilgisayarda güçlü motor seçiliyse ya da hiç
    # denenmediyse deneme "tamam" dese de paketteki ses sunucusu doğrulanmamış olur)
    if (-not $SesSiz -and $gunluk -notmatch 'Doğal ses: hafif motor, \d+ ses, .* (\d+)/\1 ses hazır') {
        Write-Host $gunluk; Dur "Paketteki doğal sesler duman testinde doğrulanmadı (günlük yukarıda)."
    }
    Write-Host "[OK] $(($gunluk -split "`n" | Select-String 'DENEME_OK').Line.Trim())" -ForegroundColor Green
}

if ($MsixAtla) {
    Adim "5/6 ve 6/6 MSIX: atlandı (-MsixAtla)"
} else {
Adim "5/6 MSIX içeriği hazırlanıyor"
$ICERIK = Join-Path $CIKTI 'msix'
Remove-Item $ICERIK -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force (Join-Path $ICERIK 'Assets') | Out-Null
Copy-Item (Join-Path $CIKTI 'dist\CanliTurkceAltyazi') $ICERIK -Recurse
Get-ChildItem (Join-Path $PAKET 'gorseller') -Filter '*.png' | Where-Object { $_.Name -match '\.(scale|targetsize)-' } |
    Copy-Item -Destination (Join-Path $ICERIK 'Assets')
$manifest = Get-Content (Join-Path $PAKET 'AppxManifest.sablon.xml') -Raw -Encoding UTF8
$degerler = @{ surum4 = $surum4; kimlik_adi = $magaza.kimlik_adi; yayinci = $magaza.yayinci; yayinci_adi = $magaza.yayinci_adi
               gorunen_ad = $magaza.gorunen_ad; aciklama = $magaza.aciklama }
foreach ($k in $degerler.Keys) { $manifest = $manifest.Replace("{$k}", [Security.SecurityElement]::Escape($degerler[$k])) }
[IO.File]::WriteAllText((Join-Path $ICERIK 'AppxManifest.xml'), $manifest, (New-Object Text.UTF8Encoding $false))
# resources.pri: ölçekli logoların (scale-100/200) doğru seçilmesi için
$pricfg = Join-Path $CIKTI 'priconfig.xml'
& $MAKEPRI createconfig /cf $pricfg /dq tr-TR /o | Out-Null
& $MAKEPRI new /pr $ICERIK /cf $pricfg /of (Join-Path $ICERIK 'resources.pri') /o | Out-Null
if ($LASTEXITCODE -ne 0) { Dur "makepri başarısız." }

Adim "6/6 MSIX paketleniyor"
$MSIX = Join-Path $CIKTI "CanliTurkceAltyazi_${surum4}_x64.msix"
& $MAKEAPPX pack /d $ICERIK /p $MSIX /o | Select-Object -Last 2
if ($LASTEXITCODE -ne 0) { Dur "makeappx başarısız." }
$mb = [math]::Round((Get-Item $MSIX).Length / 1MB, 1)
Write-Host "[OK] $MSIX ($mb MB)" -ForegroundColor Green
Write-Host "     Store'a bu dosya yüklenir; imzayı Microsoft atar." -ForegroundColor Gray
}

# Store dışı dağıtım: tek dosyalık kurulum programı (çift tıkla -> kurulur, kısayol koyar, kaldırılabilir).
# Zip VERİLMEZ: kullanıcı zip'i açmadan exe'ye tıklarsa "Failed to load Python DLL" hatası alır.
Adim "Kurulum programı (Inno Setup)"
$ISCC = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
          "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($ISCC) {
    $ErrorActionPreference = 'Continue'  # ISCC uyarıları stderr'e yazar; hata sayılmasın, çıkış koduna bakılır
    & $ISCC /Q "/DSurum=$surum" "/DKaynak=$(Join-Path $CIKTI 'dist\CanliTurkceAltyazi')" "/DCikti=$CIKTI" (Join-Path $PAKET 'kurulum.iss')
    if ($LASTEXITCODE -ne 0) { Dur "Inno Setup başarısız." }
    $KURULUM_EXE = Join-Path $CIKTI "CanliTurkceAltyazi_Kurulum_$surum.exe"  # ($KUR adı -Kur parametresiyle çakışır)
    Write-Host "[OK] $KURULUM_EXE ($([math]::Round((Get-Item $KURULUM_EXE).Length / 1MB, 1)) MB)" -ForegroundColor Green
} else {
    Write-Host "[!] Inno Setup yok, kurulum programı atlandı (winget install JRSoftware.InnoSetup)" -ForegroundColor Yellow
}

if ($Kur) {
    Adim "Bu bilgisayara kuruluyor (Geliştirici modu)"
    Get-AppxPackage -Name $magaza.kimlik_adi | Remove-AppxPackage -ErrorAction SilentlyContinue
    Add-AppxPackage -Register (Join-Path $ICERIK 'AppxManifest.xml')
    Write-Host "[OK] Başlat menüsünde '$($magaza.gorunen_ad)' olarak kuruldu." -ForegroundColor Green
}
