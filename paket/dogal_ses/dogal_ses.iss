; Canlı Türkçe Altyazı — Doğal Ses Paketi kurucusu (Store dışı, isteğe bağlı)
;   ISCC paket\dogal_ses\dogal_ses.iss   -> paket\cikti\CanliTurkceAltyazi_DogalSes_Kurulum.exe (küçük)
; Kurulum sırasında kur.ps1 çalışır: audio.cpp sunucusu (ekran kartına göre Vulkan/CUDA) ve VoxCPM2
; modeli (~3 GB) indirilir, sha256 ile doğrulanır; karakter sesleri kopyalanır. Yönetici izni istemez.
; Uygulama paketi kendisi bulur ve sunucuyu kendisi başlatır (dogal_ses.py).

[Setup]
AppId={{B2E7F1C4-5A93-4E6D-9C21-7D84A3F0E516}
AppName=Canlı Türkçe Altyazı — Doğal Ses Paketi
AppVersion=1.0.0
AppPublisher=Appic
DefaultDirName={localappdata}\Programs\CTA-DogalSes
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\cikti
OutputBaseFilename=CanliTurkceAltyazi_DogalSes_Kurulum
SetupIconFile=..\gorseller\uygulama.ico
UninstallDisplayName=Canlı Türkçe Altyazı — Doğal Ses Paketi
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
VersionInfoVersion=1.0.0
VersionInfoCompany=Appic
VersionInfoDescription=Canlı Türkçe Altyazı Doğal Ses Paketi Kurulum

[Languages]
Name: "tr"; MessagesFile: "compiler:Languages\Turkish.isl"

[Messages]
tr.WelcomeLabel2=Bu paket, Canlı Türkçe Altyazı'nın Türkçe sesli okumasına gerçek insan gibi kadın ve erkek karakter sesleri ekler.%n%nKurulum sırasında yaklaşık 3 GB indirilir (birkaç dakika sürer). Ekran kartı gerekir (NVIDIA ya da güncel AMD). Sesler yapay zekâ ile tasarlanmıştır; hiçbir gerçek kişinin sesi değildir.%n%nPaket yoksa ya da ekran kartı yetişemezse uygulama Windows'un Türkçe sesiyle okumaya devam eder.

[Files]
Source: "kur.ps1"; DestDir: "{app}\kurulum"; Flags: ignoreversion
Source: "sesler\*"; DestDir: "{app}\kurulum\sesler"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "LISANSLAR.txt"; DestDir: "{app}"; Flags: ignoreversion

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
Type: filesandordirs; Name: "C:\CTA-DogalSes"

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
var
  Kod: Integer;
begin
  if CurStep = ssPostInstall then
  begin
    WizardForm.StatusLabel.Caption := 'Ses motoru ve model indiriliyor (yaklaşık 3 GB). Açılan pencereyi kapatmayın...';
    if not Exec('powershell.exe',
        '-NoProfile -ExecutionPolicy Bypass -File "' + ExpandConstant('{app}\kurulum\kur.ps1') + '"',
        '', SW_SHOW, ewWaitUntilTerminated, Kod) or (Kod <> 0) then
      MsgBox('İndirme tamamlanamadı (kod ' + IntToStr(Kod) + '). İnternet bağlantınızı kontrol edip kurulumu yeniden çalıştırın; '
        + 'inen dosyalar doğrulanır, kaldığı yerden devam eder.', mbError, MB_OK);
  end;
end;
