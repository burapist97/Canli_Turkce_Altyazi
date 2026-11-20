"""Ses uyarlama: oyunda duyulan konuşmacının perdesine ve tınısına en yakın dublaj sesini ve ayarını bulur.

Her konuşmacı için oyunun sesinden ölçülür (konusmaci.py):
  - perde (F0, Hz): sesli çerçevelerin ortancası (YIN benzeri, aşağıda)
  - ses izi (TitaNet, 192 boyut): tını / "kalınlık" benzerliği için
Elimizdeki her ses (Windows profilleri ya da doğal sesler) bir kez örnek cümleyle üretilir; her örnek birkaç
kaydırma oranıyla (KAYDIRMALAR) yeniden örneklenir. Kaydırma perdeyi ve tınıyı (formantları) birlikte oynatır:
oran > 1 sesi inceltir, < 1 kalınlaştırır. Her aday (ses, oran) için puan:
    puan = ses izi benzerliği − PERDE_AGIRLIGI × |log2(aday perdesi / konuşmacı perdesi)|
En yüksek puanlı aday seçilir. Aynı cinsiyetin sesleri arasında seçilir (cinsiyeti konusmaci.py belirler).
Okurken oran, Windows sesinde SSML perdesine ve tını kaydırmasına, doğal seste çıkan PCM'in yeniden
örneklenmesine uygulanır.
"""
import numpy as np

KAYDIRMALAR = (0.88, 0.94, 1.0, 1.06, 1.12)
PERDE_AGIRLIGI = 1.2
MIN_PERDE_ORNEGI = 3  # konuşmacıdan en az bu kadar satır ölçülmüş olsun


def perde_olc(x, sr=16000, alt=60.0, ust=420.0):
    """Sesli çerçevelerin perdesi (Hz) ortancası; ölçülemezse None. YIN'in birikimli ortalama farkı,
    bütün çerçeveler için birden (FFT ile çapraz ilinti)."""
    x = np.asarray(x, np.float32)
    n = int(sr * 0.04)
    adim = n // 2
    tmin, tmax = int(sr / ust), int(sr / alt)
    if len(x) < n + tmax + 1:
        return None
    F = np.lib.stride_tricks.sliding_window_view(x, n + tmax + 1)[::adim].astype(np.float64)
    enerji = np.sqrt((F[:, :n] ** 2).mean(1))
    if not len(enerji) or enerji.max() < 1e-3:
        return None
    F = F[enerji > max(enerji.max() * 0.15, 2e-3)]
    if len(F) < 5:
        return None
    a = F[:, :n]
    L = 1 << int(np.ceil(np.log2(F.shape[1] + n)))
    capraz = np.fft.irfft(np.conj(np.fft.rfft(a, L)) * np.fft.rfft(F, L), L)[:, 1:tmax + 1]  # sum a[i]*F[i+t]
    kare = np.cumsum(np.pad(F ** 2, ((0, 0), (1, 0))), axis=1)
    t = np.arange(1, tmax + 1)
    kayan = kare[:, t + n] - kare[:, t]  # sum F[t:t+n]^2
    d = (a ** 2).sum(1, keepdims=True) + kayan - 2 * capraz
    cm = d * t / np.maximum(np.cumsum(d, axis=1), 1e-12)
    sonuc = []
    for satir in cm:
        aday = np.where(satir[tmin - 1:] < 0.15)[0]
        if not len(aday):
            continue
        k = aday[0] + tmin - 1
        while k + 1 < len(satir) and satir[k + 1] < satir[k]:
            k += 1
        sonuc.append(sr / (k + 1))
    return float(np.median(sonuc)) if len(sonuc) >= 5 else None


def kaydir(x, oran):
    """Yeniden örnekleyerek perdeyi ve tınıyı `oran` kadar kaydırır (süre 1/oran olur)."""
    if abs(oran - 1.0) < 0.005 or not len(x):
        return np.asarray(x, np.float32)
    x = np.asarray(x, np.float32)
    if oran > 1:  # örtüşmeyi azalt
        k = max(3, int(round(oran * 2)) | 1)
        x = np.convolve(x, np.ones(k, np.float32) / k, "same") * 0.5 + x * 0.5
    return np.interp(np.arange(0, len(x) - 1, oran), np.arange(len(x)), x).astype(np.float32)


class AkisKaydirici:
    """Parça parça gelen sesi (akış) kesintisiz yeniden örnekler: parça sınırında örnek konumu ve son örnek
    taşınır, böylece sınırda tıkırtı olmaz."""

    def __init__(self, oran):
        self.oran = float(oran or 1.0)
        self.konum = 0.0  # bir sonraki çıkış örneğinin, gelecek dizideki konumu
        self.son = None   # önceki parçanın son örneği (ara değer için başa eklenir)

    def isle(self, x):
        x = np.asarray(x, np.float32)
        if abs(self.oran - 1.0) < 0.005 or not len(x):
            return x
        if self.son is not None:
            x = np.concatenate(([self.son], x))
        konumlar = np.arange(self.konum, len(x) - 1, self.oran)
        y = np.interp(konumlar, np.arange(len(x)), x).astype(np.float32)
        sonraki = (konumlar[-1] + self.oran) if len(konumlar) else self.konum
        self.konum = sonraki - (len(x) - 1)
        self.son = x[-1]
        return y


class Uyumlayici:
    """Ses adaylarını bir kez ölçer, konuşmacıya en yakın (ses, oran) çiftini seçer."""

    def __init__(self, tanici):
        self.tanici = tanici
        self.adaylar = {}  # (ses_id, oran) -> (ses izi, perde)
        self.cinsiyet = {}  # ses_id -> "kadin"/"erkek"

    def ses_ekle(self, ses_id, cinsiyet, ornek, sr, oranlar=KAYDIRMALAR):
        """ornek: o sesle üretilmiş ~3 sn Türkçe konuşma (float32). oranlar: bu ses için izinli kaydırmalar."""
        x = np.asarray(ornek, np.float32)
        if sr != 16000:
            x = np.interp(np.arange(0, len(x), sr / 16000), np.arange(len(x)), x).astype(np.float32)
        self.cinsiyet[ses_id] = cinsiyet
        for oran in oranlar:
            y = kaydir(x, oran)
            e, _ = self.tanici.gomme(y)
            p = perde_olc(y)
            if e is not None and p:
                self.adaylar[(ses_id, oran)] = (e, p)

    def hazir_ekle(self, ses_id, cinsiyet, olcumler):
        """Önceden ölçülmüş adayları ekler (çalışırken örnek üretmeye gerek kalmaz).
        olcumler: {oran: {"iz": [192 sayı], "perde": Hz}} — `disari_ver` ile aynı biçim."""
        self.cinsiyet[ses_id] = cinsiyet
        for oran, o in (olcumler or {}).items():
            try:
                iz = np.asarray(o["iz"], np.float32)
                iz = iz / (np.linalg.norm(iz) + 1e-9)
                self.adaylar[(ses_id, float(oran))] = (iz, float(o["perde"]))
            except (KeyError, TypeError, ValueError):
                continue

    def disari_ver(self, ses_id):
        """Bir sesin ölçümleri, JSON'a yazılabilir halde: {"0.88": {"iz": [...], "perde": ...}, ...}."""
        return {f"{oran:g}": {"iz": [round(float(v), 5) for v in iz], "perde": round(float(perde), 2)}
                for (sid, oran), (iz, perde) in self.adaylar.items() if sid == ses_id}

    def hazir(self):
        return bool(self.adaylar)

    def puan(self, sid, oran, merkez, perde, kullanilan=()):
        """Bir adayın konuşmacıya uygunluğu; aday yoksa None."""
        kayit = self.adaylar.get((sid, oran))
        if not kayit:
            return None
        e, p = kayit
        puan = float(e @ merkez) if merkez is not None else 0.0
        if perde:
            puan -= PERDE_AGIRLIGI * abs(np.log2(p / perde))
        if sid in kullanilan:
            puan -= 0.15  # farklı kişiler mümkünse farklı sesler alsın
        return puan

    def sec(self, merkez, perde, cinsiyet, kullanilan=()):
        """(ses_id, oran, puan) — en uygun aday. kullanilan: başka kişilere verilmiş sesler (hafif ceza)."""
        en_iyi = None
        for (sid, oran) in self.adaylar:
            if self.cinsiyet.get(sid) != cinsiyet:
                continue
            puan = self.puan(sid, oran, merkez, perde, kullanilan)
            if en_iyi is None or puan > en_iyi[2]:
                en_iyi = (sid, oran, puan)
        return en_iyi

    def perde(self, sid, oran=1.0):
        kayit = self.adaylar.get((sid, oran))
        return kayit[1] if kayit else None
