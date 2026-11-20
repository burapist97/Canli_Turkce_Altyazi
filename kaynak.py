"""Görüntü kaynakları: OBS (WebSocket), ekran yakalama (bilgisayar oyunu) ya da kamera aygıtı."""
import sys
import threading
import time

import cv2
import numpy as np


class KameraKaynagi:
    """OBS Sanal Kamera'yı okur. Ayrı bir thread hep en son kareyi tutar,
    böylece OCR yavaş kalsa bile görüntü geride kalmaz."""

    def __init__(self, index, genislik=1920, yukseklik=1080):
        api = cv2.CAP_DSHOW if sys.platform.startswith("win") else cv2.CAP_ANY
        self.cap = cv2.VideoCapture(index, api)
        if not self.cap.isOpened():
            raise RuntimeError(
                f"Kamera {index} açılamadı. OBS'te 'Sanal Kamerayı Başlat'a bastınız mı? "
                "Doğru numarayı bulmak için: python ayarla.py --kameralar"
            )
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, genislik)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, yukseklik)
        self._kare = None
        self._kilit = threading.Lock()
        self._calisiyor = True
        self._thread = threading.Thread(target=self._dongu, daemon=True)
        self._thread.start()

    def _dongu(self):
        while self._calisiyor:
            ok, kare = self.cap.read()
            if not ok:
                time.sleep(0.01)
                continue
            with self._kilit:
                self._kare = kare

    def kare_al(self):
        with self._kilit:
            return None if self._kare is None else self._kare.copy()

    def kapat(self):
        self._calisiyor = False
        self._thread.join(timeout=1)
        self.cap.release()


class EkranKaynagi:
    """Bilgisayar oyunu modu: oyunun olduğu monitörü yakalar (mss).
    Türkçe katman penceresi yakalamaya görünmez yapılır (pc_katman), kendi yazımızı okumayız.
    mss nesnesi oluşturulduğu thread'de kullanılmalı: motor thread'i oluşturur ve okur."""

    def __init__(self, ekran_no=1):
        from pc_katman import _mss

        self.sct = _mss()
        if not 1 <= ekran_no < len(self.sct.monitors):
            raise RuntimeError(f"{ekran_no} numaralı ekran bulunamadı. Panel → Kaynak ve alan'dan oyunun "
                               "ekranını yeniden seçin.")
        self.monitor = self.sct.monitors[ekran_no]
        self.son_kare_ms = 0

    def kare_al(self):
        t0 = time.time()
        img = np.array(self.sct.grab(self.monitor))
        self.son_kare_ms = (time.time() - t0) * 1000
        return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

    def kesitler_al(self, bolgeler):
        """Yalnızca verilen (0-1 arası) bölgeleri kapsayan dikdörtgeni yakalar; her bölgenin kesitini döner.
        Tam ekranı alıp kesmekten hızlıdır (4K ekranda onlarca ms): altyazı daha erken görülür."""
        m = self.monitor
        w, h = m["width"], m["height"]
        kutular = [(max(0, int(b["x"] * w)), max(0, int(b["y"] * h)),
                    min(w, int((b["x"] + b["w"]) * w)), min(h, int((b["y"] + b["h"]) * h))) for b in bolgeler]
        x1, y1 = min(k[0] for k in kutular), min(k[1] for k in kutular)
        x2, y2 = max(k[2] for k in kutular), max(k[3] for k in kutular)
        if x2 <= x1 or y2 <= y1:
            return None
        t0 = time.time()
        img = np.array(self.sct.grab({"left": m["left"] + x1, "top": m["top"] + y1, "width": x2 - x1, "height": y2 - y1}))
        self.son_kare_ms = (time.time() - t0) * 1000
        bgr = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        return [bgr[a - y1:c - y1, b - x1:d - x1] for b, a, d, c in kutular]

    def kapat(self):
        self.sct.close()


class ObsKaynagi:
    """Görüntüyü doğrudan OBS'ten (WebSocket ile) alır. Sadece seçilen
    capture card kaynağını görür; facecam ve Türkçe altyazı karışmaz.
    Sanal kamera gerekmez."""

    def __init__(self, port, sifre, kaynak_adi, genislik=None, fps=10):
        from obs_baglanti import OBS

        if not kaynak_adi:
            raise RuntimeError("OBS kaynağı seçilmemiş. Önce kurulum sihirbazını çalıştırın.")
        self.obs = OBS(port=port, sifre=sifre)
        self.kaynak_adi, self.genislik, self.aralik = kaynak_adi, genislik, 1.0 / fps
        ilk = self.obs.goruntu(kaynak_adi)  # kaynak var mı, hemen kontrol et
        # 4K capture card'da her kareyi 4K istemek OBS'i ve bizi yavaşlatır; 1920 altyazı için yeter.
        # Yalnızca küçült (720p kaynağı büyütmek boşuna iş).
        if not self.genislik and ilk is not None and ilk.shape[1] > 1920:
            self.genislik = 1920
        self.son_kare_ms = 0
        self._kare = None
        self._kilit = threading.Lock()
        self._calisiyor = True
        self.hata = None
        self._thread = threading.Thread(target=self._dongu, daemon=True)
        self._thread.start()

    def _dongu(self):
        while self._calisiyor:
            t0 = time.time()
            try:
                kare = self.obs.goruntu(self.kaynak_adi, self.genislik)
                self.son_kare_ms = (time.time() - t0) * 1000
                with self._kilit:
                    self._kare = kare
                self.hata = None
            except Exception as e:  # OBS kapanırsa vb.
                if self.hata is None:
                    print(f"[OBS görüntü alınamadı] {e}")
                self.hata = e
                time.sleep(1)
            kalan = self.aralik - (time.time() - t0)
            if kalan > 0:
                time.sleep(kalan)

    def kare_al(self):
        with self._kilit:
            return None if self._kare is None else self._kare.copy()

    def kapat(self):
        self._calisiyor = False
        self._thread.join(timeout=2)
        self.obs.kapat()


def kaynak_olustur(ayar):
    k = ayar["kaynak"]
    if k["tip"] == "obs":
        o = ayar.get("obs", {})
        return ObsKaynagi(o.get("port", 4455), o.get("sifre", ""), o.get("kaynak_adi", ""),
                          o.get("goruntu_genislik"), min(ayar["tespit"].get("fps", 8), 20) + 2)
    if k["tip"] == "ekran":
        return EkranKaynagi(k.get("ekran_no", 1))
    return KameraKaynagi(k.get("kamera_index", 0), k.get("genislik", 1920), k.get("yukseklik", 1080))


def bolge_kes(kare, bolge):
    """Normalleştirilmiş (0-1) bölgeyi kareden keser."""
    h, w = kare.shape[:2]
    x1 = int(bolge["x"] * w)
    y1 = int(bolge["y"] * h)
    x2 = int((bolge["x"] + bolge["w"]) * w)
    y2 = int((bolge["y"] + bolge["h"]) * h)
    return kare[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]
