"""Uygulama simgesini (.ico) ve Microsoft Store / MSIX logolarını üretir (Pillow, derlemede çalışır).

  python paket/ikon_uret.py  -> paket/gorseller/*.png + paket/gorseller/uygulama.ico

Kaynak: paket/logo/logo_buyuk_1024.png (>48 px) ve logo_kucuk_256.png (<=48 px, görev çubuğu).
Bu iki PNG'yi paket/logo_ciz.py SVG'den üretir (logo değişince elle çalıştırılır).
"""
import os

from PIL import Image

PAKET = os.path.dirname(os.path.abspath(__file__))
KLASOR = os.path.join(PAKET, "gorseller")
BUYUK = Image.open(os.path.join(PAKET, "logo", "logo_buyuk_1024.png")).convert("RGBA")
KUCUK = Image.open(os.path.join(PAKET, "logo", "logo_kucuk_256.png")).convert("RGBA")


def simge(boy):
    """İstenen boyda logo: küçük boylarda sade/kalın sürüm, büyüklerde parıltılı sürüm."""
    kaynak = KUCUK if boy <= 48 else BUYUK
    return kaynak.resize((boy, boy), Image.LANCZOS)


def dolgulu(boy, oran, genislik=None):
    """Store kutucukları: logo saydam zeminin ortasında."""
    genislik = genislik or boy
    tuval = Image.new("RGBA", (genislik, boy), (0, 0, 0, 0))
    ic = int(boy * oran)
    s = simge(ic)
    tuval.paste(s, ((genislik - ic) // 2, (boy - ic) // 2), s)
    return tuval


def main():
    os.makedirs(KLASOR, exist_ok=True)
    BUYUK.save(os.path.join(KLASOR, "simge_1024.png"))
    # .ico: her boy için doğru sürüm (Pillow append_images'tan aynı boydakini kullanır)
    boylar = [16, 24, 32, 48, 64, 128, 256]
    simge(256).save(os.path.join(KLASOR, "uygulama.ico"), sizes=[(b, b) for b in boylar],
                    append_images=[simge(b) for b in boylar[:-1]])
    # Microsoft Store / MSIX logoları (scale-100 ve scale-200)
    for olcek in (100, 200):
        f = olcek / 100
        dolgulu(int(150 * f), 0.66).save(os.path.join(KLASOR, f"Square150x150Logo.scale-{olcek}.png"))
        dolgulu(int(44 * f), 1.0).save(os.path.join(KLASOR, f"Square44x44Logo.scale-{olcek}.png"))
        dolgulu(int(150 * f), 0.66, int(310 * f)).save(os.path.join(KLASOR, f"Wide310x150Logo.scale-{olcek}.png"))
        dolgulu(int(50 * f), 1.0).save(os.path.join(KLASOR, f"StoreLogo.scale-{olcek}.png"))
    # Görev çubuğu simgeleri (plakasız sürüm istenen yer; bizim logo kendi plakasıyla okunaklı)
    for boy in (16, 24, 32, 48, 256):
        dolgulu(boy, 1.0).save(os.path.join(KLASOR, f"Square44x44Logo.targetsize-{boy}_altform-unplated.png"))
    # Store sayfası için 300x300 (Partner Center'a elle yüklenebilir)
    simge(300).save(os.path.join(KLASOR, "magaza_logo_300.png"))
    print("Görseller üretildi:", KLASOR)


if __name__ == "__main__":
    main()
