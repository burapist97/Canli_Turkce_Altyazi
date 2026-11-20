"""Tüm ekran kipi: ekranın tamamı aralıklı taranır; bulunan her İngilizce yazının Türkçesi o yazının üstüne
(kapatarak), hemen üstüne ya da hemen altına yazılır. Film/oyun altyazısı için asıl kip "seçtiğim alanlar"dır
(takip.py: daha hızlı, satır satır izler); bu kip web sayfası, oyun menüsü, uygulama gibi yazının her yerde
olabildiği ekranlar içindir.

Akış (motor saniyede ~8 kez adim() çağırır):
1. Gösterilen her kutunun altındaki görüntü değişti mi? Değiştiyse o yazı gitmiştir: kutu hemen kaldırılır.
2. Tarama zamanı geldiyse (ayar: tam_ekran.aralik) ve ekran son taramadan beri değiştiyse: bütün ekran okunur
   (yazı bulma + tanıma), satırlar paragraflara birleştirilir, İngilizce olanlar çeviri kuyruğuna girer.
3. Çevirisi gelen kutular overlay'e gönderilir: {"tip": "tam", "yerlesim", "kutular": [{id, x, y, w, h, satir, tr, en}]}.
   Aynı yazı aynı yerde durdukça kimliği değişmez (overlay'de kırpışmaz).
Seslendirme bu kipte yoktur (ekranda onlarca yazı olabilir).
"""
import difflib
import queue
import re
import threading

import cv2
import numpy as np

import ceviri_hatti
import ocr

YERLESIMLER = ("ustune", "ustunde", "altinda")


def paragraflar(satirlar):
    """[(x1, y1, x2, y2, metin)] satırları alt alta duran paragraflara birleştirir.
    Dönüş: [{"x1","y1","x2","y2","metin","satir"}] (yukarıdan aşağı). Aynı paragrafın satırları: boyları benzer, biri
    ötekinin hemen altında, yatayda üst üste biniyor ya da sol kenarları hizalı."""
    bloklar = []
    for x1, y1, x2, y2, metin in sorted(satirlar, key=lambda s: (s[1], s[0])):
        boy = y2 - y1
        hedef = None
        for b in bloklar:
            b_boy = (b["y2"] - b["y1"]) / b["satir"]
            if abs(boy - b_boy) > 0.3 * max(boy, b_boy):
                continue
            bosluk = y1 - b["y2"]
            if not -0.35 * boy <= bosluk <= 0.75 * boy:
                continue
            ortak = min(x2, b["x2"]) - max(x1, b["x1"])
            if ortak >= 0.4 * min(x2 - x1, b["x2"] - b["x1"]) or abs(x1 - b["x1"]) <= 1.5 * boy:
                hedef = b
                break
        if hedef:
            hedef.update(x1=min(hedef["x1"], x1), x2=max(hedef["x2"], x2), y2=max(hedef["y2"], y2),
                         metin=hedef["metin"] + " " + metin, satir=hedef["satir"] + 1)
        else:
            bloklar.append({"x1": x1, "y1": y1, "x2": x2, "y2": y2, "metin": metin, "satir": 1})
    return bloklar


class TamEkranTarayici:
    EN_COK_KUTU = 40        # bir taramada çevrilen en çok yazı (sayfa dolusu yazıda en büyükler)
    EN_AZ_GUVEN = 0.72      # okuyucunun satır güveni
    KUTU_DEGISIM = 14.0     # kutunun altındaki görüntünün ortalama gri farkı bundan büyükse yazı gitmiştir
    EKRAN_DEGISIM = 1.2     # küçültülmüş ekranın ortalama gri farkı bundan küçükse ekran aynıdır: yeniden okunmaz
    EN_GENIS = 1920         # daha geniş ekran (4K) bu genişliğe küçültülerek okunur

    def __init__(self, ayar, ocr_motoru, cevir, yayinla, kayit=None):
        """cevir(metin) -> Türkçe ya da None (yavaş olabilir; ayrı iş parçacığında çağrılır).
        yayinla(olay): overlay'e gönderir. kayit(en, tr): çevrilen her yeni yazı için (ana sayfadaki liste)."""
        t = ayar.get("tam_ekran", {})
        self.aralik = max(0.3, min(5.0, float(t.get("aralik", 1.0))))
        self.yerlesim = t.get("yerlesim") if t.get("yerlesim") in YERLESIMLER else "ustune"
        self.en_az_harf = int(t.get("en_az_harf", 4))
        self.motor, self.cevir, self.yayinla, self.kayit = ocr_motoru, cevir, yayinla, kayit
        self.kutular = []          # [{id, en, tr, x1, y1, x2, y2 (piksel, okunan karede), satir, ref}]
        self._ceviri = {}          # küçük harfli İngilizce -> Türkçe ("" : çevrilemedi, yeniden denenmez)
        self._istenen = set()
        self._kuyruk = queue.Queue()
        self._sayac = 0
        self._kirli = False
        self._son_tarama = -1e9
        self._son_kucuk = None     # son taramadaki ekranın küçültülmüşü (ekran değişti mi?)
        self._boyut = (1, 1)
        self.tarama_sayisi = 0
        self.tarama_ms = 0
        self._calisiyor = True
        threading.Thread(target=self._cevirici, daemon=True).start()

    # ---------- çeviri (arka planda) ----------
    def _cevirici(self):
        while self._calisiyor:
            try:
                metin = self._kuyruk.get(timeout=0.3)
            except queue.Empty:
                continue
            if metin is None:
                break
            try:
                tr = self.cevir(metin) or ""
            except Exception as e:
                print(f"[tüm ekran] çevrilemedi: {e}", flush=True)
                tr = ""
            self._ceviri[metin.lower()] = tr
            if len(self._ceviri) > 3000:  # uzun oturumda sınırsız büyümesin
                for k in list(self._ceviri)[:1000]:
                    del self._ceviri[k]
            if tr and self.kayit:
                self.kayit(metin, tr)
            self._kirli = True

    def kapat(self):
        self._calisiyor = False
        self._kuyruk.put(None)
        self.yayinla({"tip": "tam", "yerlesim": self.yerlesim, "kutular": []})

    # ---------- her karede ----------
    def adim(self, kare, simdi):
        h, w = kare.shape[:2]
        gri = cv2.cvtColor(cv2.resize(kare, (w // 2, h // 2), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
        # 1) gösterilen kutuların altındaki yazı duruyor mu?
        kalan = [b for b in self.kutular if not self._degisti(b, gri)]
        dusen = len(self.kutular) - len(kalan)
        if dusen:
            self.kutular, self._kirli = kalan, True
        # 2) tarama
        gecen = simdi - self._son_tarama
        if gecen >= self.aralik or (dusen and gecen >= 0.3):
            kucuk = cv2.resize(gri, (160, 90), interpolation=cv2.INTER_AREA)
            ayni = self._son_kucuk is not None and not dusen and \
                float(np.mean(cv2.absdiff(kucuk, self._son_kucuk))) < self.EKRAN_DEGISIM
            self._son_tarama = simdi
            if not ayni:
                self._son_kucuk = kucuk
                self._tara(kare, gri)
        # 3) yeni çeviri geldiyse / kutu düştüyse overlay'i güncelle
        if self._kirli:
            self._kirli = False
            self._gonder()

    @staticmethod
    def _kirp(gri, b):
        return gri[b["y1"] // 2:max(b["y1"] // 2 + 1, b["y2"] // 2), b["x1"] // 2:max(b["x1"] // 2 + 1, b["x2"] // 2)]

    def _degisti(self, b, gri):
        simdi = self._kirp(gri, b)
        return b["ref"].shape != simdi.shape or float(np.mean(cv2.absdiff(b["ref"], simdi))) > self.KUTU_DEGISIM

    def _tara(self, kare, gri):
        import time
        t0 = time.perf_counter()
        h, w = kare.shape[:2]
        olcek = min(1.0, self.EN_GENIS / w)
        girdi = kare if olcek == 1.0 else cv2.resize(kare, None, fx=olcek, fy=olcek, interpolation=cv2.INTER_AREA)
        satirlar = []
        for kutu, metin, guven in self.motor.kutular(girdi):
            metin = ocr.metni_temizle(metin)
            if guven < self.EN_AZ_GUVEN or len(re.findall(r"[A-Za-z]", metin)) < 2:
                continue
            xs, ys = kutu[:, 0] / olcek, kutu[:, 1] / olcek
            satirlar.append((int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1, metin))
        bloklar = []
        for b in paragraflar(satirlar):
            metin = ceviri_hatti.ocr_onar(b["metin"])
            if len(re.findall(r"[A-Za-z]", metin)) < self.en_az_harf or not ceviri_hatti.ingilizce_kesin(metin):
                continue
            b["metin"] = metin
            bloklar.append(b)
        # çok yazı varsa en büyükler (başlıklar, altyazılar) önce
        bloklar.sort(key=lambda b: -((b["y2"] - b["y1"]) / b["satir"]) * (b["x2"] - b["x1"]))
        yeni = []
        for b in bloklar[:self.EN_COK_KUTU]:
            eski = self._eslesen(b)
            kimlik = eski["id"] if eski else self._yeni_kimlik()
            kayit = {"id": kimlik, "en": b["metin"], "x1": max(0, b["x1"]), "y1": max(0, b["y1"]), "x2": min(w, b["x2"]),
                     "y2": min(h, b["y2"]), "satir": b["satir"]}
            kayit["ref"] = self._kirp(gri, kayit).copy()
            yeni.append(kayit)
            anahtar = b["metin"].lower()
            if anahtar not in self._ceviri and anahtar not in self._istenen:
                self._istenen.add(anahtar)
                self._kuyruk.put(b["metin"])
        self.kutular, self._boyut, self._kirli = yeni, (w, h), True
        self.tarama_sayisi += 1
        self.tarama_ms = int((time.perf_counter() - t0) * 1000)

    def _yeni_kimlik(self):
        self._sayac += 1
        return self._sayac

    def _eslesen(self, b):
        """Önceki taramada aynı yerde aynı yazı var mıydı? (kimliği korunur: overlay'de kırpışmaz)"""
        boy = (b["y2"] - b["y1"]) / b["satir"]
        for e in self.kutular:
            if abs(e["x1"] - b["x1"]) <= 1.5 * boy and abs(e["y1"] - b["y1"]) <= 0.8 * boy and \
                    difflib.SequenceMatcher(None, e["en"].lower(), b["metin"].lower()).ratio() >= 0.85:
                return e
        return None

    def _gonder(self):
        w, h = self._boyut
        kutular = []
        for b in self.kutular:
            tr = self._ceviri.get(b["en"].lower())
            if tr:
                kutular.append({"id": b["id"], "x": round(b["x1"] / w, 4), "y": round(b["y1"] / h, 4),
                                "w": round((b["x2"] - b["x1"]) / w, 4), "h": round((b["y2"] - b["y1"]) / h, 4),
                                "satir": b["satir"], "tr": tr, "en": b["en"]})
        self.yayinla({"tip": "tam", "yerlesim": self.yerlesim, "kutular": kutular})
