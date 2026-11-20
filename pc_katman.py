"""Bilgisayar oyunu modu: ekran yakalama + oyunun üstünde saydam Türkçe altyazı penceresi.

Katman penceresi:
- saydam (renk anahtarı) ve çerçevesiz, her zaman üstte
- tıklamaları oyuna geçirir (WS_EX_TRANSPARENT), odak çalmaz, görev çubuğunda görünmez
- ekran yakalamaya GÖRÜNMEZ (SetWindowDisplayAffinity WDA_EXCLUDEFROMCAPTURE, Windows 10 2004+).
  Bu olmazsa program kendi yazdığı Türkçeyi tekrar okurdu.
Oyun "Kenarlıksız pencere" modunda olmalı; "Özel tam ekran" (exclusive) modunda hiçbir pencere üstte görünmez.
"""
import ctypes
from ctypes import wintypes
import sys
import threading
import time

import cv2
import numpy as np

WINDOWS = sys.platform.startswith("win")
GWL_EXSTYLE = -20
WS_EX_LAYERED, WS_EX_TRANSPARENT, WS_EX_TOOLWINDOW = 0x80000, 0x20, 0x80
WS_EX_NOACTIVATE, WS_EX_APPWINDOW = 0x8000000, 0x40000
WDA_NONE, WDA_EXCLUDEFROMCAPTURE = 0x0, 0x11
HWND_TOPMOST = -1
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE, SWP_SHOWWINDOW = 0x1, 0x2, 0x10, 0x40
ANAHTAR_RENK = (1, 0, 1)  # bu renk saydam olur; yazı gölgesi siyah olduğu için kenarlarda iz bırakmaz

if WINDOWS:
    u32 = ctypes.windll.user32
    u32.GetWindowLongW.restype = ctypes.c_long
    u32.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                                 ctypes.c_int, ctypes.c_int, ctypes.c_uint]


def _mss():
    import mss
    return (getattr(mss, "MSS", None) or mss.mss)()


def ekranlar():
    """[{no, x, y, genislik, yukseklik, ana}] — no: 1'den başlar (mss sırası). Koordinatlar fiziksel piksel."""
    with _mss() as s:
        liste = []
        for i, m in enumerate(s.monitors[1:], start=1):
            liste.append({"no": i, "x": m["left"], "y": m["top"], "genislik": m["width"],
                          "yukseklik": m["height"], "ana": m["left"] == 0 and m["top"] == 0})
        return liste


def ekran_goruntusu(no):
    with _mss() as s:
        if not 1 <= no < len(s.monitors):
            raise RuntimeError(f"{no} numaralı ekran bulunamadı. Ekran kablosu çıkmış olabilir; "
                               "panelden oyunun ekranını yeniden seçin.")
        return cv2.cvtColor(np.array(s.grab(s.monitors[no])), cv2.COLOR_BGRA2BGR)


def yakalamadan_gizle(hwnd, gizle=True):
    """Pencereyi ekran yakalamaya görünmez yapar (pencere ekranda görünmeye devam eder). Başarılıysa True."""
    if not WINDOWS or not hwnd:
        return False
    return bool(u32.SetWindowDisplayAffinity(ctypes.c_void_p(hwnd), WDA_EXCLUDEFROMCAPTURE if gizle else WDA_NONE))


_yazi_tipleri = None


def yuklu_yazi_tipleri():
    """Bilgisayarda yüklü yazı tipi adları (simge yazı tipleri hariç), alfabetik. Bir kez okunur."""
    global _yazi_tipleri
    if _yazi_tipleri is not None or not WINDOWS:
        return _yazi_tipleri or []

    class LOGFONTW(ctypes.Structure):
        _fields_ = [("lfHeight", wintypes.LONG), ("lfWidth", wintypes.LONG), ("lfEscapement", wintypes.LONG),
                    ("lfOrientation", wintypes.LONG), ("lfWeight", wintypes.LONG), ("lfItalic", wintypes.BYTE),
                    ("lfUnderline", wintypes.BYTE), ("lfStrikeOut", wintypes.BYTE), ("lfCharSet", wintypes.BYTE),
                    ("lfOutPrecision", wintypes.BYTE), ("lfClipPrecision", wintypes.BYTE),
                    ("lfQuality", wintypes.BYTE), ("lfPitchAndFamily", wintypes.BYTE),
                    ("lfFaceName", wintypes.WCHAR * 32)]

    GERI = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.POINTER(LOGFONTW), ctypes.c_void_p, wintypes.DWORD, wintypes.LPARAM)
    adlar = set()

    def geri(lf, _olcu, _tur, _lp):
        ad = lf.contents.lfFaceName
        if ad and not ad.startswith("@") and lf.contents.lfCharSet != 2:  # 2: SYMBOL_CHARSET (Wingdings vb.)
            adlar.add(ad)
        return 1

    gdi = ctypes.windll.gdi32
    u32.GetDC.restype = ctypes.c_void_p
    u32.GetDC.argtypes = [ctypes.c_void_p]
    u32.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    gdi.EnumFontFamiliesExW.argtypes = [ctypes.c_void_p, ctypes.POINTER(LOGFONTW), GERI, wintypes.LPARAM, wintypes.DWORD]
    dc = u32.GetDC(None)
    try:
        lf = LOGFONTW()
        lf.lfCharSet = 1  # DEFAULT_CHARSET: bütün yazı tipleri
        gdi.EnumFontFamiliesExW(dc, ctypes.byref(lf), GERI(geri), 0, 0)
    finally:
        u32.ReleaseDC(None, dc)
    _yazi_tipleri = sorted(adlar, key=str.casefold)
    return _yazi_tipleri


def sistem_koyu_mu():
    """Windows uygulama teması koyu mu? (Ayarlar → Kişiselleştirme → Renkler → Uygulama modu)"""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as anahtar:
            return winreg.QueryValueEx(anahtar, "AppsUseLightTheme")[0] == 0
    except Exception:
        return False


def baslik_cubugu_temasi(hwnd, koyu):
    """Pencerenin başlık çubuğunu sayfanın temasına uydurur (koyu temada beyaz çubuk kalmasın).
    DWMWA_USE_IMMERSIVE_DARK_MODE: Windows 10 2004+ için 20, daha eski yapılarda 19."""
    if not hwnd:
        return False
    try:
        deger = ctypes.c_int(1 if koyu else 0)
        dwm = ctypes.windll.dwmapi
        for ozellik in (20, 19):
            if dwm.DwmSetWindowAttribute(wintypes.HWND(hwnd), ozellik, ctypes.byref(deger), ctypes.sizeof(deger)) == 0:
                return True
    except Exception:
        pass
    return False


def pencere_kolu(pencere):
    """pywebview penceresinin Win32 kolu (hwnd)."""
    try:
        return int(pencere.native.Handle.ToInt64())
    except Exception:
        return 0


class Katman:
    """Oyunun bulunduğu ekranı kaplayan saydam altyazı penceresi (pywebview)."""

    def __init__(self, url):
        self.url = url
        self.pencere = None
        self.hwnd = 0
        self.ekran = None
        self.gizlenebilir = None  # yakalamadan gizleme çalıştı mı
        self._kilit = threading.Lock()
        self._calisiyor = False

    def ac(self, ekran):
        """ekran: ekranlar() öğesi. Açıksa sadece yerini günceller."""
        if not WINDOWS:
            raise RuntimeError("Oyun üstü altyazı yalnızca Windows'ta çalışır.")
        import webview

        with self._kilit:
            self.ekran = ekran
            if self.pencere is None:
                p = webview.create_window("Türkçe Altyazı Katmanı", self.url, transparent=True, frameless=True,
                                          on_top=True, focus=False, resizable=False,
                                          x=ekran["x"], y=ekran["y"], width=ekran["genislik"],
                                          height=ekran["yukseklik"], background_color="#010001")
                if not p.events.shown.wait(15):
                    raise RuntimeError("Altyazı penceresi açılamadı.")
                self.pencere = p
                p.events.closed += self._kapandi
                self._hazirla()
                self._calisiyor = True
                threading.Thread(target=self._ustte_tut, daemon=True).start()
            self._yerlestir()
        return self.gizlenebilir

    def _hazirla(self):
        from System import Action
        from System.Drawing import Color

        form = self.pencere.native

        def renk():
            form.BackColor = Color.FromArgb(255, *ANAHTAR_RENK)
            form.TransparencyKey = Color.FromArgb(255, *ANAHTAR_RENK)

        form.Invoke(Action(renk))
        self.hwnd = pencere_kolu(self.pencere)
        h = ctypes.c_void_p(self.hwnd)
        ex = u32.GetWindowLongW(h, GWL_EXSTYLE)
        ex = (ex | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE) & ~WS_EX_APPWINDOW
        u32.SetWindowLongW(h, GWL_EXSTYLE, ex)
        self.gizlenebilir = yakalamadan_gizle(self.hwnd)
        # görev çubuğundan düşmesi için gizle-göster (odak almadan)
        u32.ShowWindow(h, 0)
        u32.ShowWindow(h, 4)  # SW_SHOWNOACTIVATE

    def _yerlestir(self):
        e = self.ekran
        u32.SetWindowPos(ctypes.c_void_p(self.hwnd), ctypes.c_void_p(HWND_TOPMOST), e["x"], e["y"],
                         e["genislik"], e["yukseklik"], SWP_NOACTIVATE | SWP_SHOWWINDOW)

    def _ustte_tut(self):
        # Bazı oyunlar kendini en üste alır; birkaç saniyede bir yeniden en üste çık
        while self._calisiyor:
            time.sleep(2)
            if self._calisiyor and self.hwnd:
                u32.SetWindowPos(ctypes.c_void_p(self.hwnd), ctypes.c_void_p(HWND_TOPMOST), 0, 0, 0, 0,
                                 SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)

    def _kapandi(self):
        self._calisiyor = False
        self.pencere, self.hwnd = None, 0

    def kapat(self):
        with self._kilit:
            self._calisiyor = False
            p, self.pencere, self.hwnd = self.pencere, None, 0
        if p:
            try:
                p.destroy()
            except Exception:
                pass
