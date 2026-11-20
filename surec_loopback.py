"""Hoparlöre giden sesi KENDİ sürecimiz hariç yakalar (WASAPI süreç loopback'i, Windows 10 2004+).

Bilgisayar oyunu modunda oyunun sesini dinlerken bizim Türkçe okumamız kayda karışmasın diye:
ActivateAudioInterfaceAsync("VAD\\Process_Loopback") + PROCESS_LOOPBACK_MODE_EXCLUDE_TARGET_PROCESS_TREE
ve hedef olarak kendi süreç kimliğimiz. Böylece oyun, müzik ve diğer her şey duyulur; biz duyulmayız.

Kullanım:  k = SurecLoopback(16000); k.baslat(); ... k.oku() -> float32 mono (yeni gelen örnekler) ...; k.durdur()
Desteklenmiyorsa (eski Windows) baslat() hata fırlatır; çağıran normal loopback'e döner.
"""
import ctypes
import os
import sys
import threading
from ctypes import POINTER, Structure, Union, byref, c_int, c_uint, c_ushort, c_void_p, wintypes

import numpy as np


def destekleniyor():
    if not sys.platform.startswith("win"):
        return False
    try:
        return sys.getwindowsversion().build >= 19041
    except Exception:
        return False


def _arayuzler():
    import com_yardim
    comtypes = com_yardim.comtypes_al()  # düz "import comtypes" COM'u başka kipte açmış iş parçacığında düşer
    from comtypes import COMMETHOD, GUID, HRESULT, IUnknown

    class IAudioCaptureClient(IUnknown):
        _iid_ = GUID("{C8ADBD64-E71E-48A0-A4DE-185C395CD317}")
        _methods_ = [
            # İşaretçiler elle verilir: comtypes'ın "out" dönüşü BYTE** için adresi değil ilk baytı verebiliyor
            COMMETHOD([], HRESULT, "GetBuffer", (["in"], POINTER(c_void_p), "veri"),
                      (["in"], POINTER(c_uint), "kare"), (["in"], POINTER(wintypes.DWORD), "bayrak"),
                      (["in"], c_void_p, "konum"), (["in"], c_void_p, "zaman")),
            COMMETHOD([], HRESULT, "ReleaseBuffer", (["in"], c_uint, "kare")),
            COMMETHOD([], HRESULT, "GetNextPacketSize", (["in"], POINTER(c_uint), "kare")),
        ]

    class IAudioClient(IUnknown):
        _iid_ = GUID("{1CB9AD4C-DBFA-4C32-B178-C2F568A703B2}")
        _methods_ = [
            COMMETHOD([], HRESULT, "Initialize", (["in"], c_int, "paylasim"), (["in"], wintypes.DWORD, "bayrak"),
                      (["in"], ctypes.c_longlong, "tampon"), (["in"], ctypes.c_longlong, "donem"),
                      (["in"], c_void_p, "bicim"), (["in"], c_void_p, "oturum")),
            COMMETHOD([], HRESULT, "GetBufferSize", (["out"], POINTER(c_uint), "boy")),
            COMMETHOD([], HRESULT, "GetStreamLatency", (["out"], POINTER(ctypes.c_longlong), "g")),
            COMMETHOD([], HRESULT, "GetCurrentPadding", (["out"], POINTER(c_uint), "p")),
            COMMETHOD([], HRESULT, "IsFormatSupported", (["in"], c_int, "a"), (["in"], c_void_p, "b"),
                      (["out"], POINTER(c_void_p), "c")),
            COMMETHOD([], HRESULT, "GetMixFormat", (["out"], POINTER(c_void_p), "b")),
            COMMETHOD([], HRESULT, "GetDevicePeriod", (["out"], POINTER(ctypes.c_longlong), "a"),
                      (["out"], POINTER(ctypes.c_longlong), "b")),
            COMMETHOD([], HRESULT, "Start"),
            COMMETHOD([], HRESULT, "Stop"),
            COMMETHOD([], HRESULT, "Reset"),
            COMMETHOD([], HRESULT, "SetEventHandle", (["in"], wintypes.HANDLE, "olay")),
            COMMETHOD([], HRESULT, "GetService", (["in"], POINTER(GUID), "iid"), (["out"], POINTER(c_void_p), "s")),
        ]

    class IActivateAudioInterfaceAsyncOperation(IUnknown):
        _iid_ = GUID("{72A22D78-CDE4-431D-B8CC-843A71199B6D}")
        _methods_ = [
            COMMETHOD([], HRESULT, "GetActivateResult", (["out"], POINTER(HRESULT), "sonuc"),
                      (["out"], POINTER(POINTER(IUnknown)), "arayuz")),
        ]

    class IActivateAudioInterfaceCompletionHandler(IUnknown):
        _iid_ = GUID("{41D949AB-9862-444A-80F6-C261334DA5EB}")
        _methods_ = [
            COMMETHOD([], HRESULT, "ActivateCompleted",
                      (["in"], POINTER(IActivateAudioInterfaceAsyncOperation), "islem")),
        ]

    class IAgileObject(IUnknown):  # geri çağrı başka iş parçacığından gelir: serbest iş parçacıklı nesne
        _iid_ = GUID("{94EA2B94-E9CC-49E0-C0FF-EE64CA8F5B90}")
        _methods_ = []

    class Tamamlayici(comtypes.COMObject):
        _com_interfaces_ = [IActivateAudioInterfaceCompletionHandler, IAgileObject]

        def __init__(self):
            super().__init__()
            self.bitti = threading.Event()

        def ActivateCompleted(self, islem):
            self.bitti.set()
            return 0

    return comtypes, GUID, IUnknown, IAudioClient, IAudioCaptureClient, \
        IActivateAudioInterfaceAsyncOperation, IActivateAudioInterfaceCompletionHandler, Tamamlayici


class _SurecParam(Structure):
    _fields_ = [("TargetProcessId", wintypes.DWORD), ("ProcessLoopbackMode", c_int)]


class _EtkinlestirmeParam(Structure):
    _fields_ = [("ActivationType", c_int), ("ProcessLoopbackParams", _SurecParam)]


class _Blob(Structure):
    _fields_ = [("cbSize", wintypes.ULONG), ("pBlobData", c_void_p)]


class _PropDeger(Union):
    _fields_ = [("blob", _Blob), ("_dolgu", ctypes.c_byte * 16)]


class _PropVariant(Structure):
    _fields_ = [("vt", c_ushort), ("r1", c_ushort), ("r2", c_ushort), ("r3", c_ushort), ("deger", _PropDeger)]


class _WaveFormat(Structure):
    _pack_ = 1
    _fields_ = [("wFormatTag", c_ushort), ("nChannels", c_ushort), ("nSamplesPerSec", wintypes.DWORD),
                ("nAvgBytesPerSec", wintypes.DWORD), ("nBlockAlign", c_ushort), ("wBitsPerSample", c_ushort),
                ("cbSize", c_ushort)]


VT_BLOB = 65
AKTIVASYON_SUREC_LOOPBACK = 1
SUREC_AGACINI_HARIC_TUT = 1
AUDCLNT_STREAMFLAGS_LOOPBACK = 0x00020000
AUDCLNT_STREAMFLAGS_EVENTCALLBACK = 0x00040000
AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM = 0x80000000
AUDCLNT_STREAMFLAGS_SRC_DEFAULT_QUALITY = 0x08000000
AUDCLNT_BUFFERFLAGS_SILENT = 0x2


class SurecLoopback:
    """Kendi süreç ağacımız hariç bütün sistem sesi, 16 bit mono PCM olarak (Windows dönüştürür)."""

    def __init__(self, ornek_hizi=16000, haric_pid=None, ic_hiz=16000, kanal=1, donustur=True):
        self.ornek_hizi = ornek_hizi  # dışarı verilen
        self.ic_hiz, self.kanal, self.donustur = ic_hiz, kanal, donustur  # Windows'tan istenen biçim
        self.haric_pid = haric_pid or os.getpid()
        self._istemci = self._yakalayici = self._olay = None

    def baslat(self):
        if not destekleniyor():
            raise RuntimeError("Süreç loopback'i Windows 10 sürüm 2004 ve sonrasında var.")
        (comtypes, GUID, IUnknown, IAudioClient, IAudioCaptureClient, IOp, IHandler, Tamamlayici) = _arayuzler()
        try:
            comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
        except OSError:
            pass  # bu iş parçacığında COM zaten başka kipte açık (RPC_E_CHANGED_MODE): olduğu gibi kullan
        param = _EtkinlestirmeParam(AKTIVASYON_SUREC_LOOPBACK, _SurecParam(self.haric_pid, SUREC_AGACINI_HARIC_TUT))
        prop = _PropVariant()
        prop.vt = VT_BLOB
        prop.deger.blob.cbSize = ctypes.sizeof(param)
        prop.deger.blob.pBlobData = ctypes.cast(byref(param), c_void_p)
        self._param = param  # çağrı bitene kadar bellekte kalsın

        etkinlestir = ctypes.WinDLL("Mmdevapi.dll").ActivateAudioInterfaceAsync
        etkinlestir.argtypes = [wintypes.LPCWSTR, POINTER(GUID), c_void_p, POINTER(IHandler), POINTER(POINTER(IOp))]
        etkinlestir.restype = ctypes.HRESULT
        tamamlayici = Tamamlayici()
        islem = POINTER(IOp)()
        iid = IAudioClient._iid_
        etkinlestir("VAD\\Process_Loopback", byref(iid), byref(prop),
                    tamamlayici.QueryInterface(IHandler), byref(islem))
        if not tamamlayici.bitti.wait(5):
            raise RuntimeError("Ses arayüzü etkinleştirilemedi (zaman aşımı).")
        sonuc, arayuz = islem.GetActivateResult()
        if sonuc != 0 or not arayuz:
            raise OSError(f"Süreç loopback'i açılamadı (HRESULT {sonuc & 0xFFFFFFFF:#x}).")
        istemci = arayuz.QueryInterface(IAudioClient)

        blok = 2 * self.kanal
        bicim = _WaveFormat(1, self.kanal, self.ic_hiz, self.ic_hiz * blok, blok, 16, 0)  # PCM 16 bit
        bayrak = AUDCLNT_STREAMFLAGS_LOOPBACK | AUDCLNT_STREAMFLAGS_EVENTCALLBACK
        if self.donustur:
            bayrak |= AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM | AUDCLNT_STREAMFLAGS_SRC_DEFAULT_QUALITY
        istemci.Initialize(0, bayrak, 2_000_000, 0, ctypes.addressof(bicim), None)  # 200 ms tampon
        k32 = ctypes.WinDLL("kernel32")
        k32.CreateEventW.restype = wintypes.HANDLE
        k32.CreateEventW.argtypes = [c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
        k32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        self._k32 = k32
        self._olay = k32.CreateEventW(None, False, False, None)
        istemci.SetEventHandle(self._olay)
        yakalayici = ctypes.cast(istemci.GetService(byref(IAudioCaptureClient._iid_)), POINTER(IAudioCaptureClient))
        istemci.Start()
        self._istemci, self._yakalayici = istemci, yakalayici

    def oku(self, bekle_ms=100):
        """Gelen yeni örnekler (float32 mono, -1..1); bir şey gelmediyse boş dizi."""
        self._k32.WaitForSingleObject(self._olay, int(bekle_ms))
        parcalar = []
        paket, veri, kare, bayrak = c_uint(), c_void_p(), c_uint(), wintypes.DWORD()
        self._yakalayici.GetNextPacketSize(byref(paket))
        while paket.value:
            self._yakalayici.GetBuffer(byref(veri), byref(kare), byref(bayrak), None, None)
            n = kare.value
            if n:
                if bayrak.value & AUDCLNT_BUFFERFLAGS_SILENT or not veri.value:
                    parcalar.append(np.zeros(n, np.float32))
                else:
                    x = np.frombuffer(ctypes.string_at(veri.value, n * 2 * self.kanal), np.int16).astype(np.float32)
                    x /= 32768.0
                    parcalar.append(x.reshape(-1, self.kanal).mean(1) if self.kanal > 1 else x)
            self._yakalayici.ReleaseBuffer(n)
            self._yakalayici.GetNextPacketSize(byref(paket))
        if not parcalar:
            return np.zeros(0, np.float32)
        x = np.concatenate(parcalar)
        if self.ic_hiz != self.ornek_hizi:  # örtüşmeyi azaltan basit ortalama + doğrusal ara değer
            k = max(1, int(round(self.ic_hiz / self.ornek_hizi)))
            if k > 1:
                x = np.convolve(x, np.ones(k, np.float32) / k, "same")
            x = np.interp(np.arange(0, len(x), self.ic_hiz / self.ornek_hizi), np.arange(len(x)), x).astype(np.float32)
        return x

    def durdur(self):
        try:
            if self._istemci:
                self._istemci.Stop()
        except Exception:
            pass
        if self._olay:
            self._k32.CloseHandle(self._olay)
        self._istemci = self._yakalayici = self._olay = None
