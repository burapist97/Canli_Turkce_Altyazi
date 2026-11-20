r"""Kadın/erkek sınıflandırıcısını eğitir (geliştirmede bir kez; uygulama yalnızca sonucu kullanır).

  .venv\Scripts\pip install soundfile         (yalnızca bu betik için)
  .venv\Scripts\python.exe paket\cinsiyet_egit.py <LibriSpeech klasörü> [<ek LibriSpeech klasörü> ...]
  -> modeller\konusmaci\cinsiyet.json  (192 ağırlık + sapma)

Veri: LibriSpeech dev-clean + train-clean-100'ün bir kısmı (eğitim), test-clean (sınama), CC BY 4.0, openslr.org/12.
Her konuşmacıdan 1-3 sn'lik parçalar alınır, gürültü/müzik benzeri karışımla zorlaştırılır,
TitaNet parmak izi çıkarılır, lojistik regresyon eğitilir. Sınama kişileri eğitimde yoktur.
"""
import glob
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import konusmaci  # noqa: E402

RNG = np.random.default_rng(7)
KISI_BASI = 80


def cinsiyetler(kok):
    c = {}
    for satir in open(os.path.join(kok, "SPEAKERS.TXT"), encoding="utf-8"):
        if satir.startswith(";"):
            continue
        p = [x.strip() for x in satir.split("|")]
        if len(p) >= 3:
            c[p[0]] = 1 if p[1] == "F" else 0
    return c


def bozucu(x):
    """Oyun ortamına benzet: gürültü, uğultu, müzik benzeri ton karışımı, ses seviyesi."""
    n = len(x)
    t = np.arange(n) / 16000
    secim = RNG.integers(0, 4)
    if secim == 1:
        x = x + RNG.normal(0, RNG.uniform(0.003, 0.03), n)
    elif secim == 2:  # müzik benzeri: birkaç sinüs + darbe
        m = sum(np.sin(2 * np.pi * RNG.uniform(60, 900) * t + RNG.uniform(0, 6)) for _ in range(4))
        x = x + m * RNG.uniform(0.01, 0.05)
    elif secim == 3:  # alçak frekans uğultu (motor sesi)
        x = x + np.convolve(RNG.normal(0, 1, n), np.ones(40) / 40, "same") * RNG.uniform(0.05, 0.3)
    return (x * RNG.uniform(0.2, 1.0)).astype(np.float32)


def ornekler(tanici, klasor, cins, kisi_basi=40):
    import soundfile as sf
    X, y, kim = [], [], []
    for kisi in sorted(os.listdir(klasor)):
        if kisi not in cins:
            continue
        dosyalar = sorted(glob.glob(os.path.join(klasor, kisi, "*", "*.flac")))
        RNG.shuffle(dosyalar)
        for d in dosyalar[:kisi_basi]:
            try:
                x, sr = sf.read(d, dtype="float32")
            except Exception:
                continue  # yarım indirilmiş arşivin son dosyası
            uzun = int(RNG.uniform(1.0, 3.0) * sr)
            if len(x) <= uzun:
                continue
            b = RNG.integers(0, len(x) - uzun)
            e, _ = tanici.gomme(bozucu(x[b:b + uzun]), sr)
            if e is not None:
                X.append(e), y.append(cins[kisi]), kim.append(kisi)
        print(f"  {klasor[-10:]} {kisi}: {len(X)}", end="\r", flush=True)
    print()
    return np.array(X), np.array(y, np.float32), kim


def egit(X, y, l2=1e-3, adim=2000, oran=0.5):
    w, b = np.zeros(X.shape[1], np.float32), 0.0
    for _ in range(adim):
        p = 1 / (1 + np.exp(-(X @ w + b)))
        g = p - y
        w -= oran * (X.T @ g / len(y) + l2 * w)
        b -= oran * g.mean()
    return w, b


def alt_kume(tanici, kok, ad, cins, kisi_basi):
    """Bir LibriSpeech alt kümesinin parmak izleri (önbellekli)."""
    onbellek = os.path.join(kok, f"gomme_{ad}.npz")
    if os.path.exists(onbellek):
        z = np.load(onbellek)
        return z["X"], z["y"], list(z["kim"])
    X, y, kim = ornekler(tanici, os.path.join(kok, ad), cins, kisi_basi)
    np.savez(onbellek, X=X, y=y, kim=np.array(kim))
    return X, y, kim


def main():
    kokler = sys.argv[1:]  # ilki dev-clean + test-clean içerir; diğerleri ek alt kümeler (ör. train-clean-100)
    k = konusmaci.model_klasoru()
    tanici = object.__new__(konusmaci.KonusmaciTanici)
    import sherpa_onnx
    tanici.cikarici = sherpa_onnx.SpeakerEmbeddingExtractor(sherpa_onnx.SpeakerEmbeddingExtractorConfig(
        model=os.path.join(k, "titanet_small.onnx"), num_threads=2))
    egitim = []
    tum_cins = cinsiyetler(kokler[0])  # SPEAKERS.TXT bütün alt kümeleri kapsar
    for kok in kokler:
        cins = cinsiyetler(kok) if os.path.exists(os.path.join(kok, "SPEAKERS.TXT")) else tum_cins
        for ad in sorted(os.listdir(kok)):
            if os.path.isdir(os.path.join(kok, ad)) and ad != "test-clean":
                egitim.append(alt_kume(tanici, kok, ad, cins, KISI_BASI if ad == "dev-clean" else 25))
    Xs, ys, kims = alt_kume(tanici, kokler[0], "test-clean", cinsiyetler(kokler[0]), KISI_BASI)
    Xe = np.vstack([e[0] for e in egitim])
    ye = np.concatenate([e[1] for e in egitim])
    kisi_sayisi = len({x for e in egitim for x in e[2]})
    print(f"eğitim {Xe.shape} ({kisi_sayisi} kişi), kadın oranı {ye.mean():.2f} | sınama {Xs.shape} ({len(set(kims))} kişi)")
    w, b = egit(Xe, ye)
    p = 1 / (1 + np.exp(-(Xs @ w + b)))
    esik = konusmaci.KADIN_ESIGI
    print(f"sınama, satır başına: doğruluk {((p > esik) == ys).mean():.3f}, "
          f"erkeği kadın sanma {((p > esik) & (ys == 0)).sum() / (ys == 0).sum():.3f}, "
          f"kadını erkek sanma {((p <= esik) & (ys == 1)).sum() / (ys == 1).sum():.3f}")
    dogru = []
    for kisi in set(kims):
        i = [j for j, k_ in enumerate(kims) if k_ == kisi][:3]
        dogru.append((p[i].mean() > esik) == ys[i[0]])
    print(f"sınama, kişi başına (3 satır ortalaması): {np.mean(dogru):.3f}")
    w, b = egit(np.vstack([Xe, Xs]), np.concatenate([ye, ys]))  # son model: hepsi
    with open(os.path.join(k, "cinsiyet.json"), "w", encoding="utf-8") as f:
        json.dump({"w": [round(float(v), 6) for v in w], "b": round(float(b), 6),
                   "kaynak": f"LibriSpeech (CC BY 4.0), {kisi_sayisi + len(set(kims))} kişi, TitaNet-small parmak izi"}, f)
    print("yazıldı:", os.path.join(k, "cinsiyet.json"))


if __name__ == "__main__":
    main()
