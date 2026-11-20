"""Bilgisayar oyununda Türkçe ses okurken öteki uygulamaların (oyunun) sesini kısar, okuma bitince geri açar.

Windows her uygulamanın ses seviyesini ayrı tutar (Ses Karıştırıcısı'ndaki sürgüler). Okuma başlarken kendi
sürecimiz dışındaki ses oturumlarının seviyesi `carpan` ile çarpılır (-14 dB ≈ beşte bir), okuma bitince eski
değerine döner. İniş hızlı (~0,1 sn), çıkış yumuşaktır (~0,35 sn): TV'deki lektör gibi.

Dikkat edilenler:
- Windows uygulama seviyesini KALICI saklar: program ses kısıkken çökerse oyun kısık kalır. Bu yüzden eski
  seviyeler kısmadan ÖNCE ses_geri_al_pc.json'a yazılır; `yarim_kalani_duzelt` bir sonraki açılışta (ve her
  kısmadan önce) bunları geri yükler. Uygulama o an açık değilse kayıt bekletilir, açılınca düzeltilir.
- Sesli sohbet uygulamaları (SOHBET) kısılmaz: arkadaşların sesi oyunun sesi değildir.
- Sistem sesleri ve kendi sürecimiz (Türkçe okuma) kısılmaz.
- COM çağrılarının hepsi tek iş parçacığında yapılır; kis()/ac() yalnızca hedefi değiştirir, beklemez.

Konsol + OBS düzeninde bunun yerine seslendirme.ObsSesKisici kullanılır (oyunun sesi OBS'ten geçer).
"""
import atexit
import ctypes
import json
import os
import sys
import threading
import time
from ctypes import POINTER, byref, c_float, c_int, c_uint, c_void_p, wintypes

import com_yardim
import veri

SOHBET = {"discord.exe", "discordptb.exe", "discordcanary.exe", "teamspeak.exe", "ts3client_win64.exe",
          "ts3client_win32.exe", "mumble.exe", "ms-teams.exe", "teams.exe", "zoom.exe", "skype.exe", "slack.exe",
          "whatsapp.exe", "telegram.exe", "signal.exe", "guilded.exe", "ventrilo.exe", "element.exe"}
INIS_SN, CIKIS_SN, ADIM_SN = 0.10, 0.35, 0.025
KAYIT_OMRU = 7 * 86400  # sn — bu kadar eski "geri alınacak" kaydı artık uygulanmaz
EN_DUSUK_CARPAN = 0.06  # -24 dB: bundan fazla kısılmaz (kalıntı tanıma eşiği de buna göre)


def destekleniyor():
    """CTA_SES_KISMA_YOK: testler kullanıcının gerçek ses seviyelerine dokunmasın diye (tests/yardimci.py)."""
    return sys.platform.startswith("win") and not os.environ.get("CTA_SES_KISMA_YOK")


def carpan_db(db):
    """Desibel -> genlik çarpanı (-14 dB -> 0,2)."""
    return max(EN_DUSUK_CARPAN, min(1.0, 10.0 ** (float(db) / 20.0)))


# ---------- Windows ses oturumları (Core Audio, comtypes) ----------
_arayuz_onbellek = None


def _arayuzler():
    global _arayuz_onbellek
    if _arayuz_onbellek:
        return _arayuz_onbellek
    comtypes = com_yardim.comtypes_al()  # düz "import comtypes" COM'u başka kipte açmış iş parçacığında düşer
    from comtypes import COMMETHOD, GUID, HRESULT, IUnknown

    class ISimpleAudioVolume(IUnknown):
        _iid_ = GUID("{87CE5498-68D6-44E5-9215-6DA47EF883D8}")
        _methods_ = [
            COMMETHOD([], HRESULT, "SetMasterVolume", (["in"], c_float, "seviye"), (["in"], c_void_p, "baglam")),
            COMMETHOD([], HRESULT, "GetMasterVolume", (["in"], POINTER(c_float), "seviye")),
            COMMETHOD([], HRESULT, "SetMute", (["in"], wintypes.BOOL, "sessiz"), (["in"], c_void_p, "baglam")),
            COMMETHOD([], HRESULT, "GetMute", (["in"], POINTER(wintypes.BOOL), "sessiz")),
        ]

    class IAudioSessionControl(IUnknown):
        _iid_ = GUID("{F4B1A599-7266-4319-A8CA-E70ACB11E8CD}")
        _methods_ = [
            COMMETHOD([], HRESULT, "GetState", (["in"], POINTER(c_int), "durum")),
            COMMETHOD([], HRESULT, "GetDisplayName", (["in"], POINTER(c_void_p), "ad")),
            COMMETHOD([], HRESULT, "SetDisplayName", (["in"], wintypes.LPCWSTR, "ad"), (["in"], c_void_p, "baglam")),
            COMMETHOD([], HRESULT, "GetIconPath", (["in"], POINTER(c_void_p), "yol")),
            COMMETHOD([], HRESULT, "SetIconPath", (["in"], wintypes.LPCWSTR, "yol"), (["in"], c_void_p, "baglam")),
            COMMETHOD([], HRESULT, "GetGroupingParam", (["in"], c_void_p, "grup")),
            COMMETHOD([], HRESULT, "SetGroupingParam", (["in"], c_void_p, "grup"), (["in"], c_void_p, "baglam")),
            COMMETHOD([], HRESULT, "RegisterAudioSessionNotification", (["in"], c_void_p, "olay")),
            COMMETHOD([], HRESULT, "UnregisterAudioSessionNotification", (["in"], c_void_p, "olay")),
        ]

    class IAudioSessionControl2(IAudioSessionControl):
        _iid_ = GUID("{BFB7FF88-7239-4FC9-8FA2-07C950BE9C6D}")
        _methods_ = [
            # Dizgi işaretçileri elle alınır (CoTaskMemFree ile geri verilir); comtypes "out" dönüşüne bırakılmaz
            COMMETHOD([], HRESULT, "GetSessionIdentifier", (["in"], POINTER(c_void_p), "kimlik")),
            COMMETHOD([], HRESULT, "GetSessionInstanceIdentifier", (["in"], POINTER(c_void_p), "kimlik")),
            COMMETHOD([], HRESULT, "GetProcessId", (["in"], POINTER(wintypes.DWORD), "pid")),
            COMMETHOD([], HRESULT, "IsSystemSoundsSession"),
            COMMETHOD([], HRESULT, "SetDuckingPreference", (["in"], wintypes.BOOL, "haric")),
        ]

    class IAudioSessionEnumerator(IUnknown):
        _iid_ = GUID("{E2F5BB11-0570-40CA-ACDD-3AA01277DEE8}")
        _methods_ = [
            COMMETHOD([], HRESULT, "GetCount", (["in"], POINTER(c_int), "sayi")),
            COMMETHOD([], HRESULT, "GetSession", (["in"], c_int, "sira"),
                      (["in"], POINTER(POINTER(IAudioSessionControl)), "oturum")),
        ]

    class IAudioSessionManager(IUnknown):
        _iid_ = GUID("{BFA971F1-4D5E-40BB-935E-967039BFBEE4}")
        _methods_ = [
            COMMETHOD([], HRESULT, "GetAudioSessionControl", (["in"], c_void_p, "guid"), (["in"], wintypes.DWORD, "b"),
                      (["in"], c_void_p, "oturum")),
            COMMETHOD([], HRESULT, "GetSimpleAudioVolume", (["in"], c_void_p, "guid"), (["in"], wintypes.DWORD, "b"),
                      (["in"], c_void_p, "ses")),
        ]

    class IAudioSessionManager2(IAudioSessionManager):
        _iid_ = GUID("{77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F}")
        _methods_ = [
            COMMETHOD([], HRESULT, "GetSessionEnumerator",
                      (["in"], POINTER(POINTER(IAudioSessionEnumerator)), "liste")),
            COMMETHOD([], HRESULT, "RegisterSessionNotification", (["in"], c_void_p, "b")),
            COMMETHOD([], HRESULT, "UnregisterSessionNotification", (["in"], c_void_p, "b")),
            COMMETHOD([], HRESULT, "RegisterDuckNotification", (["in"], wintypes.LPCWSTR, "k"), (["in"], c_void_p, "b")),
            COMMETHOD([], HRESULT, "UnregisterDuckNotification", (["in"], c_void_p, "b")),
        ]

    class IMMDevice(IUnknown):
        _iid_ = GUID("{D666063F-1587-4E43-81F1-B948E807363F}")
        _methods_ = [
            COMMETHOD([], HRESULT, "Activate", (["in"], POINTER(GUID), "iid"), (["in"], wintypes.DWORD, "clsctx"),
                      (["in"], c_void_p, "param"), (["in"], POINTER(c_void_p), "arayuz")),
            COMMETHOD([], HRESULT, "OpenPropertyStore", (["in"], wintypes.DWORD, "erisim"), (["in"], c_void_p, "depo")),
            COMMETHOD([], HRESULT, "GetId", (["in"], POINTER(c_void_p), "kimlik")),
            COMMETHOD([], HRESULT, "GetState", (["in"], POINTER(wintypes.DWORD), "durum")),
        ]

    class IMMDeviceCollection(IUnknown):
        _iid_ = GUID("{0BD7A1BE-7A1A-44DB-8397-CC5392387B5E}")
        _methods_ = [
            COMMETHOD([], HRESULT, "GetCount", (["in"], POINTER(c_uint), "sayi")),
            COMMETHOD([], HRESULT, "Item", (["in"], c_uint, "sira"), (["in"], POINTER(POINTER(IMMDevice)), "aygit")),
        ]

    class IMMDeviceEnumerator(IUnknown):
        _iid_ = GUID("{A95664D2-9614-4F35-A746-DE8DB63617E6}")
        _methods_ = [
            COMMETHOD([], HRESULT, "EnumAudioEndpoints", (["in"], c_int, "yon"), (["in"], wintypes.DWORD, "durum"),
                      (["in"], POINTER(POINTER(IMMDeviceCollection)), "aygitlar")),
            COMMETHOD([], HRESULT, "GetDefaultAudioEndpoint", (["in"], c_int, "yon"), (["in"], c_int, "rol"),
                      (["in"], POINTER(POINTER(IMMDevice)), "aygit")),
            COMMETHOD([], HRESULT, "GetDevice", (["in"], wintypes.LPCWSTR, "kimlik"),
                      (["in"], POINTER(POINTER(IMMDevice)), "aygit")),
            COMMETHOD([], HRESULT, "RegisterEndpointNotificationCallback", (["in"], c_void_p, "b")),
            COMMETHOD([], HRESULT, "UnregisterEndpointNotificationCallback", (["in"], c_void_p, "b")),
        ]

    _arayuz_onbellek = (comtypes, GUID, IMMDeviceEnumerator, IMMDeviceCollection, IMMDevice, IAudioSessionManager2,
                        IAudioSessionEnumerator, IAudioSessionControl, IAudioSessionControl2, ISimpleAudioVolume)
    return _arayuz_onbellek


def _com_ac():
    com_yardim.com_ac()


def _dizgi_al(yontem):
    """LPWSTR* döndüren COM yöntemi -> str (bellek CoTaskMemFree ile geri verilir)."""
    p = c_void_p()
    yontem(byref(p))
    if not p.value:
        return ""
    try:
        return ctypes.wstring_at(p.value)
    finally:
        ctypes.windll.ole32.CoTaskMemFree(p)


def _surec_adi(pid):
    """Sürecin çalıştırılabilir dosya adı (küçük harf); bulunamazsa ''."""
    if not pid:
        return ""
    k32 = ctypes.windll.kernel32
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, POINTER(wintypes.DWORD)]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return ""
    try:
        tampon = ctypes.create_unicode_buffer(1024)
        n = wintypes.DWORD(1024)
        if not k32.QueryFullProcessImageNameW(h, 0, tampon, byref(n)):
            return ""
        return os.path.basename(tampon.value).lower()
    finally:
        k32.CloseHandle(h)


class Oturum:
    """Bir uygulamanın bir hoparlördeki ses oturumu."""

    def __init__(self, kimlik, ornek, pid, uygulama, sistem, ses):
        self.kimlik = kimlik      # kalıcı kimlik: aygıt + uygulama yolu (Windows seviyeyi bununla saklar)
        self.ornek = ornek        # bu çalışmaya özgü kimlik
        self.pid, self.uygulama, self.sistem = pid, uygulama, sistem
        self._ses = ses           # ISimpleAudioVolume

    def seviye(self):
        v = c_float()
        self._ses.GetMasterVolume(byref(v))
        return float(v.value)

    def ayarla(self, seviye):
        self._ses.SetMasterVolume(max(0.0, min(1.0, float(seviye))), None)


def oturumlari_listele():
    """Etkin bütün hoparlör aygıtlarındaki ses oturumları. COM açık bir iş parçacığından çağrılır."""
    (comtypes, GUID, IMMDeviceEnumerator, IMMDeviceCollection, IMMDevice, IAudioSessionManager2,
     IAudioSessionEnumerator, IAudioSessionControl, IAudioSessionControl2, ISimpleAudioVolume) = _arayuzler()
    sayac = comtypes.CoCreateInstance(GUID("{BCDE0395-E52F-467C-8E3D-C4579291692E}"), IMMDeviceEnumerator,
                                      comtypes.CLSCTX_INPROC_SERVER)
    aygitlar = POINTER(IMMDeviceCollection)()
    sayac.EnumAudioEndpoints(0, 1, byref(aygitlar))  # eRender, DEVICE_STATE_ACTIVE
    n = c_uint()
    aygitlar.GetCount(byref(n))
    sonuc = []
    for i in range(n.value):
        try:
            aygit = POINTER(IMMDevice)()
            aygitlar.Item(i, byref(aygit))
            ham = c_void_p()
            aygit.Activate(byref(IAudioSessionManager2._iid_), comtypes.CLSCTX_INPROC_SERVER, None, byref(ham))
            yonetici = ctypes.cast(ham, POINTER(IAudioSessionManager2))
            liste = POINTER(IAudioSessionEnumerator)()
            yonetici.GetSessionEnumerator(byref(liste))
            adet = c_int()
            liste.GetCount(byref(adet))
        except Exception as e:
            print(f"[ses kısma] aygıt {i} okunamadı: {e}", flush=True)
            continue
        for j in range(adet.value):
            try:
                denetim = POINTER(IAudioSessionControl)()
                liste.GetSession(j, byref(denetim))
                durum = c_int()
                denetim.GetState(byref(durum))
                if durum.value == 2:  # AudioSessionStateExpired
                    continue
                d2 = denetim.QueryInterface(IAudioSessionControl2)
                pid = wintypes.DWORD()
                d2.GetProcessId(byref(pid))
                sonuc.append(Oturum(_dizgi_al(d2.GetSessionIdentifier), _dizgi_al(d2.GetSessionInstanceIdentifier),
                                    int(pid.value), _surec_adi(int(pid.value)), d2.IsSystemSoundsSession() == 0,
                                    denetim.QueryInterface(ISimpleAudioVolume)))
            except Exception as e:
                print(f"[ses kısma] oturum okunamadı: {e}", flush=True)
    return sonuc


# ---------- yarım kalan kısmayı geri alma ----------
_kayit_kilidi = threading.Lock()


def _kayit_yolu():
    return veri.veri_yolu("ses_geri_al_pc.json")


def _kayit_oku():
    try:
        with open(_kayit_yolu(), encoding="utf-8") as f:
            k = json.load(f)
        return {str(a): float(b) for a, b in (k.get("oturumlar") or {}).items()}, float(k.get("zaman") or 0)
    except (OSError, ValueError, TypeError, AttributeError):
        return {}, 0.0


def _kayit_yaz(oturumlar, zaman=None):
    yol = _kayit_yolu()
    try:
        if not oturumlar:
            if os.path.exists(yol):
                os.remove(yol)
            return
        with open(yol + ".tmp", "w", encoding="utf-8") as f:
            json.dump({"zaman": zaman or time.time(), "oturumlar": oturumlar}, f, ensure_ascii=False)
        os.replace(yol + ".tmp", yol)
    except OSError as e:
        print(f"[ses kısma] kayıt yazılamadı: {e}", flush=True)


def _kalinti_mi(simdiki, eski):
    """Oturumun şimdiki seviyesi, eski seviyesinin bizim kısmamızdan kalmış hali gibi mi duruyor? Kullanıcı arada
    sürgüyü elle değiştirdiyse (eskisinden yüksek ya da bizim hiç inmeyeceğimiz kadar düşük) dokunulmaz."""
    return eski > 0 and EN_DUSUK_CARPAN * 0.85 * eski <= simdiki < eski * 0.995


def _bekleyenleri_duzelt(listele):
    """Kayıttaki (önceki çalışmadan kısık kalmış) oturumları eski seviyesine getirir. Dönüş: düzeltilen sayısı."""
    with _kayit_kilidi:
        kayit, zaman = _kayit_oku()
        if not kayit:
            return 0
        if time.time() - zaman > KAYIT_OMRU:
            _kayit_yaz({})
            return 0
        duzelen, bitti, olmadi = 0, set(), set()
        for o in listele():
            if o.kimlik not in kayit:
                continue
            try:
                eski = kayit[o.kimlik]
                if _kalinti_mi(o.seviye(), eski):
                    o.ayarla(eski)
                    duzelen += 1
                bitti.add(o.kimlik)
            except Exception as e:
                olmadi.add(o.kimlik)
                print(f"[ses kısma] {o.uygulama or o.kimlik}: eski seviye yüklenemedi: {e}", flush=True)
        for k in bitti - olmadi:  # bir uygulamanın birden çok oturumu olabilir: hepsi düzeldiyse kayıttan çıkar
            kayit.pop(k, None)
        _kayit_yaz(kayit, zaman)
        if duzelen:
            print(f"[ses kısma] önceki oturumdan kısık kalan {duzelen} uygulamanın sesi geri açıldı", flush=True)
        return duzelen


def yarim_kalani_duzelt(bekle=False):
    """Program ses kısıkken kapandıysa/çöktüyse kalan kısıklığı geri alır. Arka planda çalışır (bekle=True: bitene
    kadar bekler). Geri alınacak bir şey yoksa hiçbir şey yapmaz, ses sistemine dokunmaz."""
    if not destekleniyor() or not os.path.exists(_kayit_yolu()):
        return

    def _is():
        try:
            _com_ac()
            _bekleyenleri_duzelt(oturumlari_listele)
        except Exception as e:
            print(f"[ses kısma] önceki oturum düzeltilemedi: {e}", flush=True)
    t = threading.Thread(target=_is, daemon=True)
    t.start()
    if bekle:
        t.join(5)


# ---------- kısıcı ----------
class SistemSesKisici:
    """kis(): öteki uygulamaların sesini kıs.  ac(): geri aç.  kapat(): geri aç ve iş parçacığını bitir.

    listele: ses oturumlarını veren işlev (testlerde sahtesi verilir). yalniz_pid: verilirse yalnızca bu
    süreçlerin sesi kısılır (elle denemede kullanıcının öteki uygulamalarına dokunmamak için)."""

    def __init__(self, kisma_db=-14, listele=None, kendi_pid=None, yalniz_pid=None, haric=SOHBET):
        self.carpan = carpan_db(kisma_db)
        self.listele = listele or oturumlari_listele
        self._gercek = listele is None
        self.kendi_pid = kendi_pid or os.getpid()
        self.yalniz_pid = set(yalniz_pid) if yalniz_pid else None
        self.haric = {h.lower() for h in (haric or ())}
        self.hata = ""
        self.kisilan = 0      # son kısmada sesi kısılan oturum sayısı (panel/testler için)
        # Konuşanı tanımak için dinlediğimiz ses (süreç loopback'i) uygulama seviyesinden SONRA alınıyor (ölçüldü:
        # -14 dB kısınca yakalanan ton da 0,20'ye indi). Dinleyici, bildirilen çarpanla sesi geri yükseltir.
        self.carpan_degisti = None  # f(çarpan): 1.0 = açık
        self._izlenen = []    # [(Oturum, eski seviye)]
        self._konum = 0.0     # 0 = açık, 1 = tam kısık; çarpan = carpan ** konum
        self._istek = False
        self._bitir = False
        self._olay = threading.Event()
        self._bosta = threading.Event()
        self._bosta.set()
        self._thread = threading.Thread(target=self._dongu, daemon=True)
        self._thread.start()
        atexit.register(self.kapat)

    # ----- dışarıdan (her iş parçacığından çağrılabilir, beklemez) -----
    def kis(self):
        self._istek = True
        self._bosta.clear()
        self._olay.set()

    def ac(self):
        self._istek = False
        self._bosta.clear()
        self._olay.set()

    def bekle(self, sn=2.0):
        """Geçiş (iniş ya da çıkış) bitene kadar bekler. Testler ve kapanış için."""
        return self._bosta.wait(sn)

    def kapat(self):
        """Ses hemen eski seviyesine getirilir (yumuşak çıkış beklenmez) ve iş parçacığı biter."""
        if self._bitir:
            return
        self._bitir = True
        self._olay.set()
        self._thread.join(3)
        try:
            atexit.unregister(self.kapat)
        except Exception:
            pass

    # ----- iş parçacığı -----
    def _uygun_mu(self, o):
        if o.sistem or not o.pid or o.pid == self.kendi_pid:
            return False
        if self.yalniz_pid is not None:
            return o.pid in self.yalniz_pid
        return o.uygulama not in self.haric

    def _oturumlari_al(self):
        """Kısılacak oturumları ve eski seviyelerini belirler; eski seviyeleri diske yazar."""
        _bekleyenleri_duzelt(self.listele)  # önceki çalışmadan kısık kalan varsa önce o düzelsin
        izlenen = []
        for o in self.listele():
            try:
                if not self._uygun_mu(o):
                    continue
                eski = o.seviye()
                if eski <= 0.005:
                    continue  # zaten kapalı
                izlenen.append((o, eski))
            except Exception as e:
                print(f"[ses kısma] {o.uygulama or o.pid}: seviye okunamadı: {e}", flush=True)
        if izlenen:
            with _kayit_kilidi:
                kayit, _ = _kayit_oku()
                for o, eski in izlenen:
                    kayit[o.kimlik] = max(eski, kayit.get(o.kimlik, 0.0))
                _kayit_yaz(kayit)
        self._izlenen = izlenen
        self.kisilan = len(izlenen)

    def _bildir(self, carpan):
        if self.carpan_degisti:
            try:
                self.carpan_degisti(carpan)
            except Exception:
                pass

    def _uygula(self):
        carpan = self.carpan ** self._konum
        for o, eski in self._izlenen:
            try:
                o.ayarla(eski * carpan)
            except Exception:
                pass  # uygulama kapanmış olabilir: kayıt dosyası bir sonraki açılışta düzeltir
        self._bildir(carpan)

    def _geri_yukle(self):
        """Tam açık konuma dönüldü: eski seviyeler aynen geri konur, başarılı olanlar kayıttan silinir."""
        tamam, olmadi = set(), set()
        for o, eski in self._izlenen:
            try:
                o.ayarla(eski)
                (tamam if abs(o.seviye() - eski) < 0.01 else olmadi).add(o.kimlik)
            except Exception:
                olmadi.add(o.kimlik)  # uygulama kapanmış: kayıtta kalır, yeniden açılınca düzeltilir
        with _kayit_kilidi:
            kayit, zaman = _kayit_oku()
            for k in tamam - olmadi:
                kayit.pop(k, None)
            _kayit_yaz(kayit, zaman)
        self._izlenen = []
        self._bildir(1.0)

    def _dongu(self):
        if self._gercek:
            try:
                _com_ac()
            except Exception as e:
                self.hata = f"Ses kısma kullanılamıyor: {e}"
                print(f"[ses kısma] {self.hata}", flush=True)
                self._bosta.set()
                return
        son = time.time()
        while True:
            hareketli = bool(self._izlenen) and self._konum != (1.0 if self._istek else 0.0)
            self._olay.wait(ADIM_SN if hareketli else None)
            self._olay.clear()
            simdi = time.time()
            dt, son = min(simdi - son, 0.2) if hareketli else ADIM_SN, simdi
            try:
                if self._bitir:
                    if self._izlenen:
                        self._konum = 0.0
                        self._geri_yukle()
                    break
                if self._istek and not self._izlenen:
                    self._oturumlari_al()
                    son = time.time()
                    if not self._izlenen:  # kısılacak ses yok
                        self._bosta.set()
                        continue
                if not self._izlenen:
                    self._bosta.set()
                    continue
                if self._istek:
                    self._konum = min(1.0, self._konum + dt / INIS_SN)
                else:
                    self._konum = max(0.0, self._konum - dt / CIKIS_SN)
                if self._konum <= 0.0:
                    self._geri_yukle()
                    self._bosta.set()
                else:
                    self._uygula()
                    if self._konum >= 1.0 and self._istek:
                        self._bosta.set()
            except Exception as e:
                self.hata = f"Ses kısılamadı: {e}"
                print(f"[ses kısma] {e}", flush=True)
                self._bosta.set()
        self._bosta.set()
