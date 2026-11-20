"""Logo taslakları (oyuncu temalı): SVG -> PNG, büyük ve küçük boyutlar yan yana karşılaştırma sayfası.

  .venv\\Scripts\\python.exe magaza\\logo_taslak.py   -> magaza\\logo_taslak\\
"""
import os

KLASOR = os.path.dirname(os.path.abspath(__file__))
CIKTI = os.path.join(KLASOR, "logo_taslak")
os.makedirs(CIKTI, exist_ok=True)

PLAKA = """<defs>
  <linearGradient id="plaka" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#1e1636"/><stop offset="1" stop-color="#0b0914"/></linearGradient>
  <linearGradient id="lav" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#ffb03a"/><stop offset=".5" stop-color="#ff5a1f"/><stop offset="1" stop-color="#e0105a"/></linearGradient>
  <linearGradient id="neon" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#22e3ff"/><stop offset="1" stop-color="#b44dff"/></linearGradient>
  <linearGradient id="kirmizi" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#ff4b3a"/><stop offset="1" stop-color="#b3001b"/></linearGradient>
  <filter id="parilti" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="18" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
</defs>
<rect width="1024" height="1024" rx="224" fill="url(#plaka)"/>"""

GAMEPAD = ("M 300 330 C 240 330 205 372 196 430 L 150 650 C 136 728 186 790 256 790 C 304 790 334 764 360 724 "
           "L 398 666 L 626 666 L 664 724 C 690 764 720 790 768 790 C 838 790 888 728 874 650 L 828 430 "
           "C 819 372 784 330 724 330 Z")

TASLAKLAR = {
    # A: oyun kolu + içinde altyazı satırları (lav turuncusu, parıltılı)
    "A_oyun_kolu": f"""{PLAKA}
<g filter="url(#parilti)"><path d="{GAMEPAD}" fill="url(#lav)"/></g>
<g fill="#fff">
  <rect x="262" y="440" width="34" height="108" rx="8"/><rect x="225" y="477" width="108" height="34" rx="8"/>
  <circle cx="752" cy="452" r="22"/><circle cx="752" cy="540" r="22"/><circle cx="708" cy="496" r="22"/><circle cx="796" cy="496" r="22"/>
  <rect x="390" y="520" width="244" height="40" rx="20"/><rect x="430" y="588" width="164" height="40" rx="20" opacity=".85"/>
</g>""",
    # B: köşeli konuşma balonu + TR (Türk kırmızısı, oyun HUD'u gibi kesik köşeler)
    "B_TR_balon": f"""{PLAKA}
<g filter="url(#parilti)">
  <path d="M 230 250 L 794 250 L 854 310 L 854 650 L 794 710 L 470 710 L 330 820 L 360 710 L 230 710 L 170 650 L 170 310 Z" fill="url(#kirmizi)"/>
</g>
<text x="512" y="560" text-anchor="middle" font-family="Segoe UI Black, Arial Black, sans-serif" font-weight="900"
      font-style="italic" font-size="330" fill="#fff" letter-spacing="-10">TR</text>
<rect x="330" y="610" width="364" height="34" rx="17" fill="#fff" opacity=".9"/>""",
    # C: neon ekran + HUD köşeleri + altyazı (camgöbeği-mor, e-spor havası)
    "C_neon_ekran": f"""{PLAKA}
<g filter="url(#parilti)" fill="none" stroke="url(#neon)" stroke-width="44" stroke-linecap="round" stroke-linejoin="round">
  <path d="M 200 360 L 200 260 L 300 260"/><path d="M 724 260 L 824 260 L 824 360"/>
  <path d="M 824 664 L 824 764 L 724 764"/><path d="M 300 764 L 200 764 L 200 664"/>
</g>
<g filter="url(#parilti)">
  <polygon points="452,380 452,500 560,440" fill="url(#neon)"/>
  <rect x="300" y="570" width="424" height="52" rx="26" fill="#fff"/>
  <rect x="380" y="650" width="264" height="52" rx="26" fill="#fff" opacity=".85"/>
</g>""",
    # D: e-spor kalkanı + küçük oyun kolu + altyazı satırları (turuncu)
    "D_kalkan": f"""{PLAKA}
<g filter="url(#parilti)">
  <path d="M 512 150 L 830 260 L 800 600 C 780 730 650 820 512 880 C 374 820 244 730 224 600 L 194 260 Z" fill="url(#lav)"/>
</g>
<path d="M 512 210 L 772 300 L 748 590 C 732 690 630 764 512 816 C 394 764 292 690 276 590 L 252 300 Z" fill="none" stroke="#fff" stroke-opacity=".35" stroke-width="10"/>
<g fill="#fff" transform="translate(512 420) scale(0.36) translate(-512 -560)"><path d="{GAMEPAD}"/></g>
<g fill="#fff"><rect x="356" y="560" width="312" height="44" rx="22"/><rect x="406" y="630" width="212" height="44" rx="22" opacity=".85"/></g>
<g fill="#ff5a1f" transform="translate(512 420) scale(0.36) translate(-512 -560)">
  <rect x="262" y="440" width="34" height="108" rx="8"/><rect x="225" y="477" width="108" height="34" rx="8"/>
  <circle cx="752" cy="452" r="22"/><circle cx="752" cy="540" r="22"/><circle cx="708" cy="496" r="22"/><circle cx="796" cy="496" r="22"/>
</g>""",
}


def svg(icerik):
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" width="1024" height="1024">{icerik}</svg>'


def main():
    import base64

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1024, "height": 1024})
        resimler = {}
        for ad, icerik in TASLAKLAR.items():
            kod = svg(icerik)
            with open(os.path.join(CIKTI, ad + ".svg"), "w", encoding="utf-8") as f:
                f.write(kod)
            pg.set_content(f"<html><body style='margin:0;background:transparent'>{kod}</body></html>")
            yol = os.path.join(CIKTI, ad + ".png")
            pg.screenshot(path=yol, omit_background=True)
            resimler[ad] = "data:image/png;base64," + base64.b64encode(open(yol, "rb").read()).decode()
        # karşılaştırma: büyük + Başlat menüsü (64/48) + görev çubuğu (32/24/16), koyu ve açık zemin
        satirlar = ""
        for ad, veri in resimler.items():
            kucukler = "".join(f"<img src='{veri}' style='width:{s}px;height:{s}px'>" for s in (64, 48, 32, 24, 16))
            satirlar += (f"<div class=s><div class=ad>{ad.replace('_', ' ', 1).replace('_', ' ')}</div>"
                         f"<img src='{veri}' style='width:300px;height:300px'>"
                         f"<div class=z style='background:#202020'>{kucukler}</div>"
                         f"<div class=z style='background:#f3f3f3'>{kucukler}</div></div>")
        sayfa = ("<html><body style='margin:0;padding:30px;background:#14141c;font:700 30px Segoe UI;color:#fff;width:1640px'>"
                 "<style>.s{display:flex;align-items:center;gap:34px;margin-bottom:26px}.ad{width:230px}"
                 ".z{display:flex;align-items:center;gap:22px;padding:22px 26px;border-radius:14px}</style>"
                 f"{satirlar}</body></html>")
        pg.set_viewport_size({"width": 1700, "height": 1400})
        pg.set_content(sayfa)
        pg.wait_for_timeout(300)
        pg.screenshot(path=os.path.join(CIKTI, "karsilastirma.png"), full_page=True)
        b.close()
    print("Taslaklar:", CIKTI)


if __name__ == "__main__":
    main()
