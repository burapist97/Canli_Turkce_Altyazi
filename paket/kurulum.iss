; Canlı Türkçe Altyazı — tek dosyalık Windows kurulum programı (Store dışı dağıtım için)
; derle.ps1 çağırır:  ISCC /DSurum=2.2.0 /DKaynak=<dist klasörü> /DCikti=<çıktı klasörü> kurulum.iss
; Yönetici izni istemez; kullanıcının kendi klasörüne kurar. Ayarlar %LOCALAPPDATA%\CanliTurkceAltyazi'de
; durduğu için güncellemede/kaldırmada kaybolmaz.

#ifndef Surum
  #define Surum "0.0.0"
#endif

[Setup]
AppId={{6F3C2B7A-9E41-4D8B-A1C5-3B7E2F90D6A4}
AppName=Canlı Türkçe Altyazı
AppVersion={#Surum}
AppVerName=Canlı Türkçe Altyazı {#Surum}
AppPublisher=Appic
DefaultDirName={localappdata}\Programs\CanliTurkceAltyazi
DefaultGroupName=Canlı Türkçe Altyazı
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
PrivilegesRequired=lowest
OutputDir={#Cikti}
OutputBaseFilename=CanliTurkceAltyazi_Kurulum_{#Surum}
SetupIconFile=gorseller\uygulama.ico
UninstallDisplayIcon={app}\CanliTurkceAltyazi.exe
UninstallDisplayName=Canlı Türkçe Altyazı
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
WizardSizePercent=110
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
CloseApplications=yes
RestartApplications=no
; Program pencere kapatılınca tepside çalışmaya devam eder (2.7+). Açıkken kurulum/kaldırma "önce programı kapatın"
; der (uygulama.py kopya_isareti_koy aynı adla işaret bırakır): simgeye sağ tık > Çıkış.
AppMutex=CanliTurkceAltyaziCalisiyor
VersionInfoVersion={#Surum}
VersionInfoCompany=Appic
VersionInfoDescription=Canlı Türkçe Altyazı Kurulum

[Languages]
Name: "tr"; MessagesFile: "compiler:Languages\Turkish.isl"

[Tasks]
Name: "masaustu"; Description: "Masaüstüne kısayol koy"; GroupDescription: "Kısayollar:"

[Files]
Source: "{#Kaynak}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; eski sürümden kalan dosyalar karışmasın
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\Canlı Türkçe Altyazı"; Filename: "{app}\CanliTurkceAltyazi.exe"
Name: "{autodesktop}\Canlı Türkçe Altyazı"; Filename: "{app}\CanliTurkceAltyazi.exe"; Tasks: masaustu

[Registry]
; "Windows açılınca başlat" (Ayarlar) bu kaydı yazar; program kaldırılınca kayıt da silinsin
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "CanliTurkceAltyazi"; Flags: uninsdeletevalue dontcreatekey

[Run]
Filename: "{app}\CanliTurkceAltyazi.exe"; Description: "Canlı Türkçe Altyazı'yı şimdi aç"; Flags: nowait postinstall skipifsilent
