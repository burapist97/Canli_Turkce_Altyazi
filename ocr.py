"""Altyazı bölgesindeki yazıyı okuma (OCR)."""
import re
import subprocess

import cv2
import numpy as np


_CEKIRDEK = cv2.getStructuringElement(cv2.MORPH_RECT, (11, 11))


def yazi_maskesi(kesit, esik, kontur=True):
    """Altyazı yazısı açık renkli (beyaz/renkli) ve ince çizgilerden oluşur.
    Parlak pikselleri alır; kontur=True ise sadece çevresine göre belirgin
    şekilde parlak olanları (ince, kontrastlı çizgileri) tutar. Böylece
    altyazı bölgesinden geçen büyük parlak nesneler (araba, gökyüzü) elenir."""
    parlak = kesit.max(axis=2)
    _, maske = cv2.threshold(parlak, esik, 255, cv2.THRESH_BINARY)
    if kontur:
        yerel_min = cv2.erode(parlak, _CEKIRDEK)
        kontrast = cv2.subtract(parlak, yerel_min)
        _, kontrastli = cv2.threshold(kontrast, 60, 255, cv2.THRESH_BINARY)
        maske = cv2.bitwise_and(maske, kontrastli)
    return maske


def metni_temizle(metin):
    metin = metin.replace("|", "I").replace("’", "'").replace("‘", "'")
    metin = metin.replace("“", '"').replace("”", '"')
    metin = re.sub(r"[^\w\s'\".,!?;:\-()&$%/]", "", metin)
    metin = re.sub(r"\s+", " ", metin).strip()
    metin = re.sub(r"^[-–—\s]+", "", metin)
    metin = re.sub(r"\s+([.,!?;:])", r"\1", metin)
    # Sık OCR karışıklığı: kelime içindeki/sonundaki "$" aslında "s" ("cop$" -> "cops"); "$5" gibi paraya dokunma
    metin = re.sub(r"(?<=[A-Za-z])\$(?!\d)", "s", metin)
    return metin


def anlamli_mi(metin):
    harfler = re.findall(r"[A-Za-z]", metin)
    return len(harfler) >= 3


def _islemciyi_yorma():
    """ONNX Runtime iş parçacıkları varsayılan olarak iş bittikten sonra da bir süre boşta DÖNER ("spinning": bir sonraki
    işe hemen başlamak için işlemciyi meşgul tutar). Saniyede birkaç okumada bu, okuma yokken bile 3-7 çekirdeği
    dolduruyordu (2026-11-20, kullanıcının bilgisayarında program tek başına %61 işlemci): oyun da çeviri de yavaşlıyordu.
    Kapatılınca aynı iş ~1 çekirdekle ve aynı sürede yapılıyor (ölçüm: tam okuma 98 -> 92 ms, 3,3 -> 1,15 çekirdek)."""
    try:
        from rapidocr.inference_engine.onnxruntime import main as ort_ana
        asil = ort_ana.OrtInferSession._init_sess_opts
        if getattr(asil, "_cta", False):
            return

        def ayarli(cfg):
            secenek = asil(cfg)
            secenek.add_session_config_entry("session.intra_op.allow_spinning", "0")
            secenek.add_session_config_entry("session.inter_op.allow_spinning", "0")
            return secenek

        ayarli._cta = True
        ort_ana.OrtInferSession._init_sess_opts = staticmethod(ayarli)
    except Exception as e:  # kitaplığın iç yapısı değişmiş: eski davranışla devam
        print(f"[yazı okuma] işlemci ayarı uygulanamadı: {e}", flush=True)


class RapidOCRMotoru:
    def __init__(self, min_guven=0.6, is_parcacigi=None):
        try:
            from rapidocr import RapidOCR  # yeni sürüm (2.x / 3.x)
            _islemciyi_yorma()
            import os
            # 4 iş parçacığı: 12'ye göre okuma yalnız ~%5 yavaş, işlemci yükü belirgin az (oyuna çekirdek kalır)
            n = int(is_parcacigi or max(2, min(4, (os.cpu_count() or 4) // 2)))
            # Hız: varsayılan ayar ince-uzun altyazı şeridini kısa kenarı 736 px olacak şekilde
            # BÜYÜTÜYOR (1460x160 -> ~6700x736) ve gereksiz döndürme sınıflandırması yapıyor: ~600 ms.
            # Uzun kenarı 1280 ile sınırlayınca aynı sonuç ~120 ms (tanıma yine asıl kareden yapılır).
            self.motor = RapidOCR(params={"Global.use_cls": False, "Det.limit_type": "max",
                                          "Det.limit_side_len": 1280, "Global.log_level": "error",
                                          "EngineConfig.onnxruntime.intra_op_num_threads": n})
        except ImportError as yeni_hata:
            try:
                from rapidocr_onnxruntime import RapidOCR  # eski sürüm (1.x)
            except ImportError:
                raise yeni_hata from None  # asıl sorunu göster, eski paket adını değil
            self.motor = RapidOCR()
        self.min_guven = min_guven
        self.son_guven = 0.0
        self._tanima = None  # (tanıma modeli, girdi sınıfı) — hızlı okuma için, ilk kullanımda
        self._hizli_yok = not hasattr(self.motor, "_load_rec_model")
        self.hizli_sayac = [0, 0]  # [hızlı okunan, tam okumaya dönülen] — günlük ve sorun raporu için
        self.son_kutu = None  # son okunan yazının kesit içindeki yeri (y1, y2, x1, x2) ya da None

    def kutular(self, img):
        """[(kutu 4x2 dizi, metin, güven)] — otomatik bölge bulma için."""
        cikti = self.motor(img)
        if isinstance(cikti, tuple):
            return [(np.array(b), t, float(s)) for b, t, s in (cikti[0] or [])]
        if getattr(cikti, "boxes", None) is None:
            return []
        return [(np.array(b), t, float(s)) for b, t, s in zip(cikti.boxes, cikti.txts, cikti.scores)]

    HIZLI_GUVEN = 0.90  # hızlı okumada her satırın en düşük güveni; altındaysa tam okumaya dönülür

    def hizli_oku(self, kesit, maske):
        """Yazı ARAMADAN okur: satırların yeri yazı maskesinden bulunur, yalnızca tanıma modeli çalışır
        (~25-35 ms; tam okuma ~120 ms, çoğu yazıyı aramaya gider). Emin olunamazsa None döner; çağıran tam okumaya
        geçer. Yalnız rapidocr 2.x/3.x'te (tanıma modeline doğrudan erişim) çalışır."""
        if self._hizli_yok or maske is None:
            return None
        bantlar = satir_bantlari(maske)
        if not bantlar:
            return None
        try:
            if self._tanima is None:
                from rapidocr.ch_ppocr_rec import TextRecInput
                self._tanima = (self.motor._load_rec_model(), TextRecInput)
            tanima, girdi = self._tanima
            kirpimlar = []
            for y1, y2, x1, x2 in bantlar:
                k = np.ascontiguousarray(kesit[y1:y2, x1:x2])
                if k.shape[0] < 44:  # tanıma modeli 48 px yükseklikle çalışır: küçük yazı keskin büyütülür
                    o = 48.0 / k.shape[0]
                    k = cv2.resize(k, None, fx=o, fy=o, interpolation=cv2.INTER_CUBIC)
                # genişlik sabit adımlara tamamlanır: model her yeni genişlikte ilk seferde yavaş çalışıyor
                adim = 2 * k.shape[0]
                eksik = -k.shape[1] % adim
                if eksik:
                    k = cv2.copyMakeBorder(k, 0, 0, 0, eksik, cv2.BORDER_REPLICATE)
                kirpimlar.append(k)
            cikti = tanima(girdi(img=kirpimlar))
            metinler, guvenler = list(cikti.txts or ()), [float(s) for s in (cikti.scores or ())]
        except Exception as e:  # iç arayüz değişmiş: bundan sonra hep tam okuma
            self._hizli_yok = True
            print(f"[yazı okuma] hızlı okuma kullanılamıyor, tam okumayla devam: {e}", flush=True)
            return None
        if len(metinler) != len(bantlar) or not all(m.strip() for m in metinler) \
                or min(guvenler) < max(self.HIZLI_GUVEN, self.min_guven):
            return None
        self.son_guven = min(guvenler)
        self.son_kutu = (min(b[0] for b in bantlar), max(b[1] for b in bantlar),
                         min(b[2] for b in bantlar), max(b[3] for b in bantlar))
        return " ".join(m.strip() for m in metinler)

    def oku(self, kesit, maske=None):
        cikti = self.motor(kesit)
        if isinstance(cikti, tuple):  # 1.x: (sonuclar, sure)
            ogeler = [(np.array(b), t, float(s)) for b, t, s in (cikti[0] or [])]
        else:  # 2.x+: nesne
            kutular = getattr(cikti, "boxes", None)
            if kutular is None:
                return ""
            ogeler = [(np.array(b), t, float(s)) for b, t, s in zip(kutular, cikti.txts, cikti.scores)]
        ogeler = [o for o in ogeler if o[2] >= self.min_guven and o[1].strip()]
        # son okumanın en düşük satır güveni: takipçi erken (kararlılığı beklemeden) okumaya yalnız yüksek güvende inanır
        self.son_guven = min((o[2] for o in ogeler), default=0.0)
        # okunan yazının yeri (y1, y2, x1, x2): takipçi arka plan oynarken yalnız burayı izler
        self.son_kutu = (int(min(o[0][:, 1].min() for o in ogeler)), int(max(o[0][:, 1].max() for o in ogeler)) + 1,
                         int(min(o[0][:, 0].min() for o in ogeler)), int(max(o[0][:, 0].max() for o in ogeler)) + 1) \
            if ogeler else None
        return satirlari_birlestir(ogeler)


class TesseractMotoru:
    def __init__(self, yol="tesseract"):
        self.yol = yol

    def oku(self, kesit, maske=None):
        if maske is None:
            maske = yazi_maskesi(kesit, 185)
        # Tesseract beyaz zemin üstünde siyah yazıyı sever
        girdi = cv2.bitwise_not(maske)
        girdi = cv2.copyMakeBorder(girdi, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)
        ok, png = cv2.imencode(".png", girdi)
        p = subprocess.run(
            [self.yol, "stdin", "stdout", "--psm", "6", "-l", "eng"],
            input=png.tobytes(), capture_output=True, timeout=5,
        )
        return p.stdout.decode("utf-8", "ignore").replace("\n", " ")


def satirlari_birlestir(ogeler):
    """OCR kutularını yukarıdan aşağı, soldan sağa sıralayıp tek cümle yapar."""
    if not ogeler:
        return ""
    kutular = []
    for kutu, metin, _ in ogeler:
        ys = kutu[:, 1]
        xs = kutu[:, 0]
        kutular.append((ys.mean(), xs.min(), ys.max() - ys.min(), metin))
    kutular.sort()
    satirlar = []
    for y, x, yuk, metin in kutular:
        if satirlar and abs(satirlar[-1][0] - y) < max(yuk, 1) * 0.6:
            satirlar[-1][1].append((x, metin))
        else:
            satirlar.append([y, [(x, metin)]])
    parcalar = []
    for _, satir in satirlar:
        satir.sort()
        parcalar.append(" ".join(m for _, m in satir))
    return " ".join(parcalar)


def altyazi_bolgesi_bul(motor, kare, ust=0.45):
    """Ekranın alt kısmındaki ortalanmış yazıyı (altyazı) bulur ve onu rahatça
    kapsayan normalleştirilmiş bölgeyi döner. Bulamazsa None.
    Dönen: ({x,y,w,h}, bulunan_metin)"""
    if not hasattr(motor, "kutular"):
        return None
    h, w = kare.shape[:2]
    y0 = int(h * ust)
    kesit = kare[y0:, :]
    olcek = min(1.0, 1280 / w)
    if olcek < 1.0:
        kesit = cv2.resize(kesit, None, fx=olcek, fy=olcek, interpolation=cv2.INTER_AREA)
    kh, kw = kesit.shape[:2]
    adaylar = []
    for kutu, metin, guven in motor.kutular(kesit):
        if guven < 0.6 or not anlamli_mi(metin):
            continue
        xs, ys = kutu[:, 0] / kw, kutu[:, 1] / kh
        merkez = (xs.min() + xs.max()) / 2
        if 0.2 <= merkez <= 0.8:  # altyazı ortalanmış olur; köşedeki HUD yazılarını ele
            adaylar.append((xs.min(), xs.max(), ys.min(), ys.max(), metin))
    if not adaylar:
        return None
    # En alttaki yazı grubunu al (altyazı genelde ekranın en altındaki ortalanmış metindir)
    adaylar.sort(key=lambda a: a[3], reverse=True)
    alt = adaylar[0]
    satir_boyu = alt[3] - alt[2]
    grup = [a for a in adaylar if a[3] >= alt[2] - satir_boyu * 3.2]
    x1, x2 = min(a[0] for a in grup), max(a[1] for a in grup)
    ya, yb = min(a[2] for a in grup), max(a[3] for a in grup)
    # normalleştir (tam kareye göre)
    oran = 1 - ust
    ya, yb = ust + ya * oran, ust + yb * oran
    # genişlik: bulunan yazıdan geniş, ortalı (daha uzun cümleler de sığsın)
    yarim = max((x2 - x1) / 2 + 0.05, 0.32)
    yarim = max(yarim, abs(0.5 - x1) + 0.04, abs(x2 - 0.5) + 0.04)
    x = max(0.0, 0.5 - yarim)
    gen = min(1.0, 0.5 + yarim) - x
    # yükseklik: en az iki satır sığsın
    pay = max(0.015, (yb - ya) * 0.25)
    y = max(0.0, ya - pay)
    yuk = max(yb + pay, y + 0.12) - y
    if y + yuk > 1.0:
        y = max(0.0, 1.0 - yuk)
    bolge = {"x": round(float(x), 4), "y": round(float(y), 4), "w": round(float(gen), 4),
             "h": round(float(min(yuk, 1.0 - y)), 4)}
    metin = " ".join(a[4] for a in sorted(grup, key=lambda a: (a[2], a[0])))
    return bolge, metni_temizle(metin)


def isit(motor):
    """İlk altyazı geç kalmasın: modelleri (tam okuma + hızlı okumanın sık görülen genişlikleri) bir kez çalıştırır."""
    try:
        bos = np.full((120, 960, 3), 40, np.uint8)
        cv2.putText(bos, "Warm up, please.", (200, 70), cv2.FONT_HERSHEY_DUPLEX, 1.2, (255, 255, 255), 2, cv2.LINE_AA)
        motor.oku(bos, None)
        if hasattr(motor, "hizli_oku"):
            for gen in (240, 480, 720, 960):
                k = bos[:, :gen]
                motor.hizli_oku(k, yazi_maskesi(k, 185))
    except Exception as e:
        print(f"[yazı okuma] ısıtma yapılamadı: {e}", flush=True)


def motor_olustur(ayar):
    o = ayar["ocr"]
    if o["motor"] == "tesseract":
        return TesseractMotoru(o.get("tesseract_yolu", "tesseract"))
    return RapidOCRMotoru(o.get("min_guven", 0.6), o.get("is_parcacigi"))


def satir_bantlari(maske):
    """Yazı maskesinden altyazı satırlarının yerini bulur: [(y1, y2, x1, x2)] (kenar payıyla), yukarıdan aşağı.
    Satır sayısı ya da boyları altyazıya benzemiyorsa (bölgede başka parlak şeyler var) None: tam okuma yapılır."""
    h, w = maske.shape[:2]
    sayim = np.count_nonzero(maske, axis=1)
    if not sayim.any():
        return None
    # yazı satırında yüzlerce piksel olur; tek tük parlak nokta (lamba, yıldız) birkaç piksel: yoğun satırlara göre ele
    satir_dolu = sayim >= max(3, 0.12 * float(np.percentile(sayim[sayim > 0], 90)))
    bantlar, bas, bosluk = [], None, 0
    for y in range(h + 1):
        dolu = y < h and satir_dolu[y]
        if dolu:
            if bas is None:
                bas = y
            bosluk = 0
        elif bas is not None:
            bosluk += 1
            if bosluk > 2 or y == h:  # 1-2 satırlık boşluk harfin içindedir (i'nin noktası, ince yatay çizgi)
                bantlar.append((bas, y - bosluk + 1))
                bas = None
    bantlar = [(a, b) for a, b in bantlar if b - a >= 6]  # tek tük parlak nokta satır değildir
    if not 1 <= len(bantlar) <= 3:
        return None
    boylar = [b - a for a, b in bantlar]
    if min(boylar) < 10 or max(boylar) > 0.62 * h or max(boylar) > 1.6 * min(boylar):
        return None  # çok küçük yazı, bölgeyi dolduran parlaklık ya da birbirine değen iki satır
    sonuc = []
    for a, b in bantlar:
        sutunlar = np.flatnonzero(np.count_nonzero(maske[a:b], axis=0))
        if sutunlar.size == 0:
            return None
        boy = b - a
        # Yazıdan uzakta (3 satır boyundan fazla boşlukla ayrılmış) duran dar parlak şeyler satıra katılmaz
        kesik = np.flatnonzero(np.diff(sutunlar) > 3 * boy)
        parcalar = np.split(sutunlar, kesik + 1)
        if len(parcalar) > 1:
            ana = max(parcalar, key=len)
            if any(len(p) > 2 * boy for p in parcalar if p is not ana):
                return None  # satırda birbirinden uzak iki ayrı yazı var: tam okuma ayırsın
            sutunlar = ana
        dikey, yatay = max(3, boy // 6), max(6, boy // 3)
        sonuc.append((max(0, a - dikey), min(h, b + dikey), max(0, int(sutunlar[0]) - yatay),
                      min(w, int(sutunlar[-1]) + 1 + yatay)))
    return sonuc


def oku(motor, kesit, maske, buyutme=1.0, hizli=True):
    if hizli and maske is not None and hasattr(motor, "hizli_oku"):
        metin = motor.hizli_oku(kesit, maske)
        motor.hizli_sayac[0 if metin is not None else 1] += 1
        if metin is not None:
            return metni_temizle(metin)
    olcek = buyutme if (buyutme and buyutme != 1.0) else 1.0
    if olcek != 1.0:
        kesit = cv2.resize(kesit, None, fx=olcek, fy=olcek, interpolation=cv2.INTER_CUBIC)
        maske = cv2.resize(maske, None, fx=olcek, fy=olcek, interpolation=cv2.INTER_NEAREST)
    metin = metni_temizle(motor.oku(kesit, maske))
    kutu = getattr(motor, "son_kutu", None)
    if kutu and olcek != 1.0:  # büyütülmüş kesitin ölçüsünden asıl kesite
        motor.son_kutu = tuple(int(v / olcek) for v in kutu)
    return metin
