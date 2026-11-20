r"""Oyun karakterleri için yapay Türkçe sesler tasarlar (VoxCPM2 "ses tasarımı": tarif + metin).

  .venv\Scripts\python.exe paket\dogal_ses\ses_tasarla.py [--aday 3] [--sadece genc_kadin,sert_erkek]

Doğal ses sunucusu (dogal_ses.py) açılır. Her tarif için birkaç tohumla aday üretilir, her aday
cinsiyet modeliyle (konusmaci.py) denetlenir; tarife uymayan elenir. Adaylar
paket\dogal_ses\adaylar\<ad>\<tohum>.wav olarak yazılır, dinleyip seçince:

  .venv\Scripts\python.exe paket\dogal_ses\ses_tasarla.py --sec genc_kadin=123456

seçilen aday paket\dogal_ses\sesler\<ad>\ (referans.wav + ses.json) olur. Okumada bu kayıt
referans verilir (tarif değil), böylece ses metinden metne değişmez.
Bu sesler bir tariften üretildi; hiçbir kişinin kaydından klonlanmadı.
"""
import argparse
import json
import os
import sys
import time

import numpy as np

KOK = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, KOK)
import dogal_ses  # noqa: E402

BURASI = os.path.dirname(os.path.abspath(__file__))
ADAYLAR = os.path.join(BURASI, "adaylar")
SESLER = os.path.join(BURASI, "sesler")

ORTAK = ("native Turkish speaker with clear Istanbul Turkish diction, natural conversational acting like a video game "
         "character, clean close-mic studio recording, no background noise, no music")
TARIFLER = {
    "genc_kadin": ("kadin", "Defne", "Yirmili yaşlarında, kendine güvenen, sokak zekâsı olan genç kadın; sıcak ve net ses.",
                   "A confident, street-smart Turkish woman in her mid-twenties with a warm, clear, bright mid-range voice, lively pace"),
    "sert_kadin": ("kadin", "Selin", "Otuzlarında, kararlı ve sert, hafif boğuk sesli kadın.",
                   "A tough, determined Turkish woman in her thirties with a slightly husky, low mid-range voice, firm and serious"),
    "olgun_kadin": ("kadin", "Leyla", "Kırklarında, sakin ve otoriter kadın; tok ve güven veren ses.",
                    "A calm, authoritative Turkish woman in her forties with a smooth, full, reassuring voice, measured pace"),
    "genc_erkek": ("erkek", "Emre", "Yirmili yaşlarının sonunda, enerjik ve rahat genç adam; net bariton.",
                   "An energetic, easy-going Turkish man in his late twenties with a clear, friendly baritone voice, casual pace"),
    "sert_erkek": ("erkek", "Kaan", "Kırklarında, sert ve tehditkâr adam; derin, pürüzlü ses.",
                   "A tough, intimidating Turkish man in his forties with a deep, gravelly, rough voice, slow and menacing"),
    "orta_erkek": ("erkek", "Murat", "Ellilerinde, sakin ve kendinden emin adam; tok ve olgun ses.",
                   "A calm, self-assured Turkish man in his fifties with a rich, mature, resonant voice, steady pace"),
    "kurnaz_erkek": ("erkek", "Can", "Otuzlarında, alaycı ve hızlı konuşan kurnaz adam; parlak tenor.",
                     "A sly, sarcastic Turkish man in his thirties with a bright, slightly nasal tenor voice, quick witty delivery"),
}
METIN = ("Bak, sana son kez söylüyorum. Bu iş göründüğü kadar kolay değil. Arabaya bin, yolda her şeyi anlatacağım. "
         "Polisler peşimizde, acele etmemiz lazım. Hazır mısın? O zaman gidelim.")


def tasarla(d, ad, aday_sayisi, tanici):
    cins, gorunen, tanitim, tarif = TARIFLER[ad]
    klasor = os.path.join(ADAYLAR, ad)
    os.makedirs(klasor, exist_ok=True)
    rng = np.random.default_rng(abs(hash(ad)) % (2 ** 32))
    sonuc = []
    for _ in range(aday_sayisi):
        tohum = int(rng.integers(1, 2 ** 31))
        t = time.time()
        parcalar = list(d.akis(f"({tarif}, {ORTAK}){METIN}", {"id": None, "tohum": tohum}, ilk_parca_sn=180, toplam_sn=600))
        x = np.concatenate(parcalar) if parcalar else np.zeros(0, np.float32)
        sure = time.time() - t
        if len(x) < 48000 * 3:
            print(f"  {ad} {tohum}: ses çok kısa ({len(x) / 48000:.1f} sn), atlandı")
            continue
        x16 = np.interp(np.arange(0, len(x), 3), np.arange(len(x)), x).astype(np.float32)
        _, _, kadin = tanici.cozumle(x16)
        uyuyor = (kadin > 0.6) == (cins == "kadin") if kadin is not None else False
        import soundfile as sf
        yol = os.path.join(klasor, f"{tohum}.wav")
        sf.write(yol, x, 48000, subtype="PCM_16")
        sonuc.append({"tohum": tohum, "kadin_olasiligi": round(kadin or 0, 2), "uyuyor": uyuyor,
                      "ses_sn": round(len(x) / 48000, 1), "uretim_sn": round(sure, 1)})
        print(f"  {ad} {tohum}: {len(x) / 48000:.1f} sn ses, {sure:.1f} sn üretim, kadın olasılığı {kadin:.2f} "
              f"{'✓' if uyuyor else '✗ tarife uymuyor'}", flush=True)
    with open(os.path.join(klasor, "adaylar.json"), "w", encoding="utf-8") as f:
        json.dump({"tarif": tarif, "metin": METIN, "adaylar": sonuc}, f, ensure_ascii=False, indent=1)
    return sonuc


def sec(ad, tohum):
    cins, gorunen, tanitim, tarif = TARIFLER[ad]
    import shutil
    hedef = os.path.join(SESLER, ad)
    os.makedirs(hedef, exist_ok=True)
    shutil.copy(os.path.join(ADAYLAR, ad, f"{tohum}.wav"), os.path.join(hedef, "referans.wav"))
    with open(os.path.join(hedef, "ses.json"), "w", encoding="utf-8") as f:
        json.dump({"gorunen_ad": gorunen, "cinsiyet": cins, "sira": list(TARIFLER).index(ad) + 1, "tanitim": tanitim, "referans": "referans.wav",
                   "referans_metni": METIN, "tohum": int(tohum), "tarif": f"{tarif}, {ORTAK}",
                   "kaynak": "Canlı Türkçe Altyazı için VoxCPM2 ile tariften tasarlandı (paket/dogal_ses/ses_tasarla.py); "
                             "yapay ses, bir kişinin kaydından klonlanmadı"}, f, ensure_ascii=False, indent=1)
    print(f"seçildi: {ad} = {tohum} -> {hedef}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--aday", type=int, default=3)
    p.add_argument("--sadece", default="")
    p.add_argument("--sec", default="", help="ad=tohum[,ad=tohum]")
    a = p.parse_args()
    if a.sec:
        for parca in a.sec.split(","):
            ad, tohum = parca.split("=")
            sec(ad.strip(), tohum.strip())
        return
    import konusmaci
    tanici = konusmaci.KonusmaciTanici()
    d = dogal_ses.DogalSes()
    if not d.baslat(300):
        sys.exit(d.hata)
    adlar = [x.strip() for x in a.sadece.split(",") if x.strip()] or list(TARIFLER)
    for ad in adlar:
        tasarla(d, ad, a.aday, tanici)


if __name__ == "__main__":
    main()
