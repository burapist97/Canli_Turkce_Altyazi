"""Konuşanı tanıma: dublajda kadına kadın sesi, farklı erkeklere farklı erkek sesi.

Üç ipucu, güvenilirlik sırasıyla:
1. Altyazıdaki ad etiketi ("JASON: ...") → aynı ad hep aynı ses.
2. Altyazının rengi (bazı oyunlar her karaktere bir renk verir) → aynı renk hep aynı ses.
3. Oyunun sesi: konuşmanın "ses parmak izi" (NVIDIA TitaNet-small, CC BY 4.0, ~40 MB ONNX,
   sherpa-onnx ile) çıkarılır; önceki konuşanlarla karşılaştırılır, benzemiyorsa yeni kişi
   sayılır. Kadın/erkek, aynı parmak izinden küçük bir doğrusal sınıflandırıcıyla tahmin edilir
   (LibriSpeech, CC BY 4.0 ile eğitildi: paket/cinsiyet_egit.py). Varsa ikinci bir görüş olarak
   ECAPA cinsiyet modeli (Jaesung Huh, voice-gender-classifier, MIT; `cinsiyet_ecapa.onnx`, 59 MB,
   VoxCeleb ile eğitilmiş, gerçek ortam seslerinde daha sağlam) da sorulur; ikisinin ortalaması alınır.

Hepsi bilgisayarda çalışır; ses kaydedilmez, gönderilmez.
"""
import json
import os
import threading

import numpy as np

import veri

BENZERLIK_ESIGI = 0.40  # TitaNet: aynı kişi 1,5 sn'de ~0,45+, farklı kişi ~0,30 altı
MIN_KONUSMA_SN = 0.6
KADIN_ESIGI = 0.6
EN_FAZLA_KISI = 12

ERKEK_SESLERI = ["erkek1", "erkek2", "erkek3", "erkek4"]
KADIN_SESLERI = ["kadin1", "kadin2", "kadin3"]

# Dublaj sesinin hedef perdesi (Hz): konuşanın oyunda ölçülen perdesi cinsiyetinin aralığına sıkıştırılır
ERKEK_PERDE = (100.0, 195.0)
KADIN_PERDE = (165.0, 265.0)
# Perdesi ölçülemeyen kişi (yalnız adından ya da yazı renginden tanınan) için profilin hedefi
VARSAYILAN_PERDE = {"erkek1": 128.0, "erkek2": 108.0, "erkek3": 150.0, "erkek4": 172.0,
                    "kadin1": 215.0, "kadin2": 240.0, "kadin3": 195.0}
PERDE_AYRIMI = 1.08          # aynı cinsiyetten iki kişinin dublaj perdeleri en az bu oranda ayrı tutulur (ayırt edilsinler)
HEDEF_SATIRLARI = (1, 3, 8)  # bu kadar ölçümde hedef (yeniden) belirlenir: kanıt arttıkça düzelir
HEDEF_FARKI = 1.10           # sonraki belirlemelerde hedef ancak bundan fazla değiştiyse güncellenir (ses sık değişmesin)


def _ayrik_perde(ham, digerleri, alt, ust):
    """`ham`a en yakın, `digerleri`nin hepsinden en az PERDE_AYRIMI oranında uzak perde ([alt, ust] içinde).
    Aralıkta yer kalmadıysa ham değer döner."""
    def uygun(p):
        return all(max(p / d, d / p) >= PERDE_AYRIMI for d in digerleri)
    if uygun(ham):
        return ham
    for adim in range(1, 70):
        for p in (ham * 1.01 ** adim, ham / 1.01 ** adim):
            if alt <= p <= ust and uygun(p):
                return p
    return ham


def model_klasoru():
    return os.path.join(veri.KLASOR, "modeller", "konusmaci")


def model_var():
    k = model_klasoru()
    return os.path.exists(os.path.join(k, "titanet_small.onnx")) and os.path.exists(os.path.join(k, "cinsiyet.json"))


def yazi_rengi(kesit, maske):
    """Altyazı yazısının rengi: renkliyse 'renk:<ton>', beyaz/griyse None."""
    import cv2
    pikseller = kesit[maske > 0]
    if len(pikseller) < 40:
        return None
    hsv = cv2.cvtColor(pikseller.reshape(-1, 1, 3).astype(np.uint8), cv2.COLOR_BGR2HSV).reshape(-1, 3)
    renkli = hsv[hsv[:, 1] > 80]
    if len(renkli) < 0.4 * len(hsv):
        return None  # beyaz/gri altyazı: renk ipucu yok
    ton = int(np.median(renkli[:, 0]))  # OpenCV tonu 0-179
    return f"renk:{int(round(ton / 15.0)) % 12 * 15}"


# ECAPA cinsiyet modelinin beklediği log-mel özellikleri (torchaudio MelSpectrogram eşdeğeri):
# 16 kHz, ön vurgu 0,97, 512 FFT, 400 örnek Hamming penceresi, 160 adım, 80 mel (20-7600 Hz, HTK), log, zamanda ortalama çıkarma
def _mel_suzgec(n_fft=512, n_mel=80, alt=20.0, ust=7600.0, sr=16000):
    mel = lambda f: 2595.0 * np.log10(1.0 + f / 700.0)  # noqa: E731
    hz = lambda m: 700.0 * (10.0 ** (m / 2595.0) - 1.0)  # noqa: E731
    frek = np.linspace(0, sr / 2, n_fft // 2 + 1)
    n = hz(np.linspace(mel(alt), mel(ust), n_mel + 2))
    s = np.zeros((n_fft // 2 + 1, n_mel), np.float32)
    for m in range(n_mel):
        s[:, m] = np.maximum(0, np.minimum((frek - n[m]) / (n[m + 1] - n[m]), (n[m + 2] - frek) / (n[m + 2] - n[m + 1])))
    return s


_MEL = None
_PENCERE = None


def log_mel(x):
    """(1, 80, kare) — 16 kHz mono için."""
    global _MEL, _PENCERE
    if _MEL is None:
        _MEL = _mel_suzgec()
        _PENCERE = np.zeros(512, np.float32)
        _PENCERE[56:456] = 0.54 - 0.46 * np.cos(2 * np.pi * np.arange(400) / 400)
    x = np.asarray(x, np.float32)
    x = np.concatenate([x[1:2], x])
    x = x[1:] - 0.97 * x[:-1]
    x = np.pad(x, (256, 256), mode="reflect")
    n = 1 + (len(x) - 512) // 160
    idx = np.arange(512)[None, :] + 160 * np.arange(n)[:, None]
    guc = np.abs(np.fft.rfft(x[idx] * _PENCERE, axis=1)) ** 2
    m = np.log(guc @ _MEL + 1e-6).T
    return (m - m.mean(1, keepdims=True))[None].astype(np.float32)


def konusma_kismi(x, sr=16000):
    """Sessiz kısımları at (20 ms çerçeveler, enerji eşiği)."""
    n = sr // 50
    if len(x) < n:
        return x[:0]
    k = len(x) // n
    c = x[:k * n].reshape(k, n)
    e = np.sqrt((c ** 2).mean(1))
    if e.max() < 0.003:
        return x[:0]
    esik = max(0.003, np.percentile(e, 90) * 0.15)
    return c[e > esik].reshape(-1)


class Konusmaci:
    def __init__(self, no, anahtar=None):
        self.no = no
        self.anahtar = anahtar  # "ad:JASON" / "renk:120" / None (yalnızca sesle tanınan)
        self.merkez = None
        self.kadin_toplam = 0.0
        self.agirlik = 0.0
        self.sayi = 0
        self.ses = None  # ses profili adı (seslendirme.SES_PROFILLERI)
        self.elle = False  # kullanıcı panelden değiştirdi: otomatik değiştirme
        self.sabit = False  # kullanıcı belirli bir ses seçti: o ses aynen kullanılır, perdeye uydurulmaz
        self.perdeler = []  # her satırda ölçülen perde (Hz)
        self.oran = 1.0  # ses uyarlamasının kaydırması (>1 ince, <1 kalın)
        self.uyarlama_sayisi = 0  # uyarlama hangi satır sayısında yapıldı
        self.hedef = None  # dublaj sesinin perdesi (Hz): konuşanın perdesine oturtulur (KonusmaciTanici._hedef_ver)
        self.hedef_sayisi = 0  # hedef kaç perde ölçümüyle belirlendi (0: ölçüm yok, profilin varsayılanı)

    @property
    def kadin_mi(self):
        # 0,6: erkeği kadın sesiyle okumak, tersinden daha rahatsız edici (LibriSpeech'te hata %0,4 / %3)
        return self.agirlik > 0 and self.kadin_toplam / self.agirlik > KADIN_ESIGI

    def ad(self):
        if self.anahtar and self.anahtar.startswith("ad:"):
            return self.anahtar[3:].title()
        if self.anahtar and self.anahtar.startswith("renk:"):
            return f"Renkli yazı {self.no}"
        return f"Kişi {self.no}"

    @property
    def perde(self):
        return float(np.median(self.perdeler)) if self.perdeler else None

    def ozet(self):
        return {"no": self.no, "ad": self.ad(), "anahtar": self.anahtar, "ses": self.ses, "sayi": self.sayi,
                "cinsiyet": ("kadın" if self.kadin_mi else "erkek") if self.agirlik else "?", "elle": self.elle,
                "perde": round(self.perde) if self.perde else None, "oran": round(self.oran, 2),
                "hedef": round(self.hedef) if self.hedef else None, "sabit": self.sabit}


class KonusmaciTanici:
    def __init__(self, model_klasoru_=None):
        import sherpa_onnx
        k = model_klasoru_ or model_klasoru()
        self.cikarici = sherpa_onnx.SpeakerEmbeddingExtractor(sherpa_onnx.SpeakerEmbeddingExtractorConfig(
            model=os.path.join(k, "titanet_small.onnx"), num_threads=1))
        with open(os.path.join(k, "cinsiyet.json"), encoding="utf-8") as f:
            c = json.load(f)
        self.c_w, self.c_b = np.array(c["w"], np.float32), float(c["b"])
        self.ecapa = None
        ecapa_yolu = os.path.join(k, "cinsiyet_ecapa.onnx")
        if os.path.exists(ecapa_yolu):
            import onnxruntime as ort
            secenek = ort.SessionOptions()
            secenek.intra_op_num_threads = 1
            self.ecapa = ort.InferenceSession(ecapa_yolu, secenek, providers=["CPUExecutionProvider"])
        self.kisiler = []
        self.kilit = threading.Lock()
        self._uyumlayici = None  # ses_uyum.Uyumlayici: Seslendirici, aktif ses motorunun örnekleriyle kurar
        # Kişilere dağıtılan ses profilleri. Windows sesinde 4 erkek + 3 kadın; doğal ses motorunda daha çok ses
        # varsa Seslendirici havuzu büyütür (havuz_ayarla), böylece bütün sesler kullanılır.
        self.erkek_sesleri, self.kadin_sesleri = list(ERKEK_SESLERI), list(KADIN_SESLERI)

    def havuz_ayarla(self, erkek, kadin):
        """Dağıtılacak profil sayıları: erkek1..erkekN, kadin1..kadinM (en az 1). Kişilerin eldeki sesleri değişmez."""
        with self.kilit:
            self.erkek_sesleri = [f"erkek{i}" for i in range(1, max(1, int(erkek)) + 1)]
            self.kadin_sesleri = [f"kadin{i}" for i in range(1, max(1, int(kadin)) + 1)]

    def profiller(self):
        return list(self.erkek_sesleri) + list(self.kadin_sesleri)

    @property
    def uyumlayici(self):
        return self._uyumlayici

    @uyumlayici.setter
    def uyumlayici(self, yeni):
        """Ses kaynağı değişince (Windows sesleri -> doğal sesler) eski uyarlamalar geçersizdir: kişiler bir sonraki
        satırlarında yeniden uyarlanır. Elle seçilmiş sesin kalınlığı korunur."""
        with self.kilit:
            self._uyumlayici = yeni
            for k in self.kisiler:
                if not k.elle:
                    k.oran, k.uyarlama_sayisi = 1.0, 0

    # ---------- ses ----------
    def gomme(self, x, sr=16000):
        """Konuşmanın parmak izi (birim vektör) ya da yeterli konuşma yoksa None."""
        x = konusma_kismi(np.asarray(x, np.float32), sr)
        if len(x) < MIN_KONUSMA_SN * sr:
            return None, 0.0
        x = x / max(1e-4, float(np.abs(x).max())) * 0.5
        s = self.cikarici.create_stream()
        s.accept_waveform(sr, x)
        s.input_finished()
        e = np.array(self.cikarici.compute(s), np.float32)
        return e / (np.linalg.norm(e) + 1e-9), len(x) / sr

    def kadin_olasiligi(self, e, konusma=None):
        """Kadın olasılığı: parmak izi sınıflandırıcısı; konuşma (16 kHz, sessizliği atılmış) verilirse
        ECAPA'nın görüşüyle ortalaması."""
        p = float(1 / (1 + np.exp(-(e @ self.c_w + self.c_b))))
        if self.ecapa is not None and konusma is not None and len(konusma) >= 8000:
            try:
                c = self.ecapa.run(None, {"feats": log_mel(konusma)})[0][0]
                p = (p + float(c[1])) / 2  # çıkış: [erkek, kadın]
            except Exception as ex:
                print(f"[konuşmacı] ECAPA: {ex}", flush=True)
        return p

    def cozumle(self, x, sr=16000):
        """(parmak izi, konuşma süresi, kadın olasılığı) ya da yeterli konuşma yoksa (None, 0, None)."""
        if sr != 16000:
            x = np.interp(np.arange(0, len(x), sr / 16000), np.arange(len(x)), x).astype(np.float32)
        e, sure = self.gomme(x, 16000)
        if e is None:
            return None, 0.0, None
        return e, sure, self.kadin_olasiligi(e, konusma_kismi(np.asarray(x, np.float32)))

    # ---------- kişiler ----------
    def _yeni(self, anahtar=None):
        if len(self.kisiler) >= EN_FAZLA_KISI:  # en az konuşan sesle tanınanı unut
            adaylar = [k for k in self.kisiler if not k.anahtar and not k.elle] or self.kisiler
            self.kisiler.remove(min(adaylar, key=lambda k: k.sayi))
        k = Konusmaci(max([0] + [k.no for k in self.kisiler]) + 1, anahtar)
        self.kisiler.append(k)
        return k

    def _ses_ver(self, kisi):
        if kisi.elle:
            return
        havuz = self.kadin_sesleri if kisi.kadin_mi else self.erkek_sesleri
        if kisi.ses in havuz:
            return
        kullanim = {s: 0 for s in havuz}
        for k in self.kisiler:
            if k is not kisi and k.ses in kullanim:
                kullanim[k.ses] += 1
        kisi.ses = min(havuz, key=lambda s: (kullanim[s], havuz.index(s)))
        kisi.oran, kisi.uyarlama_sayisi = 1.0, 0  # yeni ses: uyarlama baştan yapılır

    def _hedef_ver(self, kisi):
        """Dublaj sesinin perdesi (Hz): konuşanın ölçülen perdesi, cinsiyetinin aralığında ve aynı cinsiyetten öteki
        kişilerin hedeflerinden en az PERDE_AYRIMI kadar uzakta. Böylece kalın sesli karakter kalın, ince sesli
        karakter ince okunur ve iki karakter aynı sesle okunmaz. İlk satırda belirlenir; kanıt arttıkça
        (HEDEF_SATIRLARI) düzeltilir ama ancak belirgin fark varsa (HEDEF_FARKI): karakterin sesi sık değişmesin."""
        n = len(kisi.perdeler)
        kadin = (kisi.ses or "").startswith("kadin")
        alt, ust = KADIN_PERDE if kadin else ERKEK_PERDE
        yerinde = kisi.hedef is not None and alt * 0.97 <= kisi.hedef <= ust * 1.03  # cinsiyeti değişmediyse
        if yerinde and not any(kisi.hedef_sayisi < s <= n for s in HEDEF_SATIRLARI):
            return
        ham = min(ust, max(alt, kisi.perde)) if n else VARSAYILAN_PERDE.get(kisi.ses, (alt + ust) / 2)
        if yerinde and kisi.hedef_sayisi and max(ham / kisi.hedef, kisi.hedef / ham) < HEDEF_FARKI:
            kisi.hedef_sayisi = n  # ölçüme dayalı hedef zaten yeterince yakın: ses aynı kalsın
            return
        digerleri = [k.hedef for k in self.kisiler
                     if k is not kisi and k.hedef and (k.ses or "").startswith("kadin") == kadin]
        kisi.hedef = _ayrik_perde(ham, digerleri, alt, ust)
        kisi.hedef_sayisi = n

    def tani(self, ses=None, anahtar=None, sr=16000):
        """Bir altyazı satırının konuşanı. ses: o satır sırasında oyunun sesi (yoksa None).
        Dönüş: Konusmaci ya da hiçbir ipucu yoksa None."""
        e, sure, kadin = (self.cozumle(ses, sr) if ses is not None and len(ses) else (None, 0.0, None))
        perde = None
        if e is not None:
            import ses_uyum
            x16 = ses if sr == 16000 else np.interp(np.arange(0, len(ses), sr / 16000), np.arange(len(ses)), ses)
            perde = ses_uyum.perde_olc(konusma_kismi(np.asarray(x16, np.float32)))
        with self.kilit:
            kisi = None
            if anahtar:
                kisi = next((k for k in self.kisiler if k.anahtar == anahtar), None)
            if kisi is None and e is not None:
                adaylar = [(float(k.merkez @ e), k) for k in self.kisiler
                           if k.merkez is not None and (not anahtar or not k.anahtar)]
                if adaylar:
                    benzerlik, en_iyi = max(adaylar, key=lambda a: a[0])
                    if benzerlik >= BENZERLIK_ESIGI:
                        kisi = en_iyi
                        if anahtar and not kisi.anahtar:
                            kisi.anahtar = anahtar  # sesle bulduğumuz kişinin adı/rengi artık belli
            if kisi is None:
                if e is None and not anahtar:
                    return None
                kisi = self._yeni(anahtar)
            kisi.sayi += 1
            if e is not None:
                kisi.merkez = e if kisi.merkez is None else \
                    (lambda m: m / (np.linalg.norm(m) + 1e-9))(kisi.merkez * min(kisi.sayi, 8) + e)
                agirlik = min(sure, 3.0)
                kisi.kadin_toplam += kadin * agirlik
                kisi.agirlik += agirlik
                if perde:
                    kisi.perdeler = (kisi.perdeler + [perde])[-20:]
            self._ses_ver(kisi)
            self._uyarla(kisi)
            self._hedef_ver(kisi)
            return kisi

    UYARLAMA_SATIRLARI = (2, 6, 14)  # bu kadar ölçümde (yeniden) uyarlanır: kanıt arttıkça daha iyi seçilir
    UYARLAMA_FARKI = 0.08            # sonraki uyarlamalarda ses ancak bu kadar daha uygunsa değişir (ses sık değişmesin)

    def _uyarla(self, kisi):
        """Konuşmacının perdesine ve ses izine en yakın dublaj sesini ve kaydırma oranını seçer (ses_uyum.py)."""
        u = self.uyumlayici
        n = len(kisi.perdeler)
        if not u or not u.hazir() or kisi.elle or kisi.merkez is None or n < self.UYARLAMA_SATIRLARI[0]:
            return
        if kisi.uyarlama_sayisi and not any(kisi.uyarlama_sayisi < s <= n for s in self.UYARLAMA_SATIRLARI):
            return
        kullanilan = {k.ses for k in self.kisiler if k is not kisi}
        secim = u.sec(kisi.merkez, kisi.perde, "kadin" if kisi.kadin_mi else "erkek", kullanilan)
        if not secim:
            return
        if kisi.uyarlama_sayisi:  # daha önce uyarlandı: belirgin biçimde daha iyiyse değiştir
            simdiki = u.puan(kisi.ses, kisi.oran, kisi.merkez, kisi.perde, kullanilan)
            if simdiki is not None and secim[2] < simdiki + self.UYARLAMA_FARKI:
                kisi.uyarlama_sayisi = n
                return
        kisi.ses, kisi.oran = secim[0], secim[1]
        kisi.uyarlama_sayisi = n

    def ses_degistir(self, no, ses, oran=None):
        """Panelden elle ayar. ses: profil adı ya da "otomatik".
        - Yalnız kalınlık (aynı ses, yeni oran): ses konuşana uydurulmaya devam eder, hedef perde oranla çarpılır.
        - Başka bir profil seçilirse o ses AYNEN kullanılır (sabit): kullanıcı "bu kişi şu sesle okunsun" demiştir.
        - "otomatik": elle ayar kalkar, kişi yeniden kendiliğinden ayarlanır."""
        with self.kilit:
            for k in self.kisiler:
                if k.no != no:
                    continue
                if ses == "otomatik":
                    k.elle = k.sabit = False
                    k.oran, k.uyarlama_sayisi = 1.0, 0
                    if k.ses not in (self.kadin_sesleri if k.kadin_mi else self.erkek_sesleri):
                        k.ses = None  # elle öteki cinsiyete çevrilmişti: ölçülen cinsiyetin sesine dön
                    self._ses_ver(k)
                    self._uyarla(k)
                else:
                    if ses != k.ses:
                        k.sabit = True
                    k.ses, k.elle = ses, True
                    if oran is not None:
                        k.oran = max(0.8, min(1.25, float(oran)))
                self._hedef_ver(k)  # kadın/erkek değiştiyse hedef perde yeni aralığa taşınır

    def liste(self):
        with self.kilit:
            return [k.ozet() for k in sorted(self.kisiler, key=lambda k: k.no)]

    def sifirla(self):
        with self.kilit:
            self.kisiler = []


_paylasilan = None
_paylasilan_kilit = threading.Lock()
_yukleme_hatasi = ""


def paylasilan():
    """Süreç boyunca tek tanıyıcı: motor yeniden başlasa da kişiler ve sesleri korunur.
    Model yoksa ya da yüklenemezse None (dublaj tek sesle devam eder)."""
    global _paylasilan, _yukleme_hatasi
    with _paylasilan_kilit:
        if _paylasilan is None and not _yukleme_hatasi:
            if not model_var():
                _yukleme_hatasi = "Konuşmacı modeli bulunamadı."
            else:
                try:
                    _paylasilan = KonusmaciTanici()
                except Exception as e:
                    _yukleme_hatasi = f"Konuşmacı modeli yüklenemedi: {e}"
            if _yukleme_hatasi:
                print(f"[konuşmacı] {_yukleme_hatasi}", flush=True)
        return _paylasilan
