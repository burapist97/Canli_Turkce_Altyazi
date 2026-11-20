"""Logo (neon ekran) — SVG kaynaklarından ana PNG'leri üretir. Yalnızca logo değişince çalıştırılır
(Playwright gerekir); derleme (ikon_uret.py) bu PNG'leri kullanır.

  .venv\\Scripts\\python.exe paket\\logo_ciz.py   -> paket\\logo\\logo_buyuk_1024.png, logo_kucuk_256.png, kontrol.png

İki sürüm var: büyük boylar (>=64 px) için parıltılı ve oynat işaretli; küçük boylar (<=48 px, görev çubuğu)
için kalın köşeli, parıltısız, sade — küçükte ince çizgi ve parıltı kayboluyor.
"""
import base64
import os

KLASOR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo")
os.makedirs(KLASOR, exist_ok=True)

ORTAK = """<defs>
  <linearGradient id="plaka" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#241a44"/><stop offset="1" stop-color="#0c0a17"/></linearGradient>
  <linearGradient id="neon" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#2ef0ff"/><stop offset="1" stop-color="#c04dff"/></linearGradient>
  <linearGradient id="kenar" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#2ef0ff" stop-opacity=".55"/><stop offset="1" stop-color="#c04dff" stop-opacity=".55"/></linearGradient>
  <filter id="parilti" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="20" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
</defs>"""

BUYUK = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" width="1024" height="1024">{ORTAK}
<rect x="8" y="8" width="1008" height="1008" rx="224" fill="url(#plaka)" stroke="url(#kenar)" stroke-width="10"/>
<g filter="url(#parilti)" fill="none" stroke="url(#neon)" stroke-width="56" stroke-linecap="round" stroke-linejoin="round">
  <path d="M 196 370 L 196 256 L 310 256"/><path d="M 714 256 L 828 256 L 828 370"/>
  <path d="M 828 654 L 828 768 L 714 768"/><path d="M 310 768 L 196 768 L 196 654"/>
</g>
<g filter="url(#parilti)">
  <path d="M 446 360 L 446 492 Q 446 506 458 499 L 562 437 Q 574 430 562 423 L 458 361 Q 446 354 446 360 Z" fill="url(#neon)"/>
  <rect x="290" y="566" width="444" height="60" rx="30" fill="#fff"/>
  <rect x="372" y="656" width="280" height="60" rx="30" fill="#fff" opacity=".88"/>
</g></svg>"""

KUCUK = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" width="1024" height="1024">{ORTAK}
<rect x="0" y="0" width="1024" height="1024" rx="200" fill="url(#plaka)"/>
<g fill="none" stroke="url(#neon)" stroke-width="118" stroke-linecap="round" stroke-linejoin="round">
  <path d="M 170 400 L 170 170 L 400 170"/><path d="M 624 170 L 854 170 L 854 400"/>
  <path d="M 854 624 L 854 854 L 624 854"/><path d="M 400 854 L 170 854 L 170 624"/>
</g>
<rect x="300" y="452" width="424" height="120" rx="60" fill="#fff"/>
<rect x="380" y="626" width="264" height="104" rx="52" fill="#fff" opacity=".9"/></svg>"""

# Uygulama içi küçük logo (sol üst, 36 px kutu içinde) — ortak.js LOGO_SVG ile aynı tasarım
UYGULAMA_ICI = ('<svg viewBox="0 0 24 24" fill="none" stroke-linecap="round" stroke-linejoin="round">'
                '<defs><linearGradient id="lg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#2ef0ff"/>'
                '<stop offset="1" stop-color="#c04dff"/></linearGradient></defs>'
                '<path d="M3 8V3h5M16 3h5v5M21 16v5h-5M8 21H3v-5" stroke="url(#lg)" stroke-width="2.6"/>'
                '<path d="M7.5 12.5h9M9.5 16h5" stroke="#fff" stroke-width="2.4"/></svg>')


def main():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1024, "height": 1024})
        yollar = {}
        for ad, kod, boy in [("logo_buyuk_1024", BUYUK, 1024), ("logo_kucuk_256", KUCUK, 256)]:
            with open(os.path.join(KLASOR, ad.rsplit("_", 1)[0] + ".svg"), "w", encoding="utf-8") as f:
                f.write(kod)
            pg.set_viewport_size({"width": boy, "height": boy})
            pg.set_content(f"<html><body style='margin:0;background:transparent'>"
                           f"<div style='width:{boy}px;height:{boy}px'>{kod.replace('width=\"1024\" height=\"1024\"', f'width=\"{boy}\" height=\"{boy}\"', 1)}</div></body></html>")
            yollar[ad] = os.path.join(KLASOR, ad + ".png")
            pg.screenshot(path=yollar[ad], omit_background=True)
        veri = {k: "data:image/png;base64," + base64.b64encode(open(v, "rb").read()).decode() for k, v in yollar.items()}
        # kontrol sayfası: büyük boylar büyük logodan, küçük boylar küçük logodan (gerçek kullanımdaki gibi)
        def dizi():
            return "".join(f"<img src='{veri['logo_buyuk_1024'] if s > 48 else veri['logo_kucuk_256']}' "
                           f"style='width:{s}px;height:{s}px'>" for s in (150, 64, 48, 32, 24, 16))
        uyg = (f"<div style='display:flex;gap:12px;align-items:center;background:#1a1a24;padding:14px 18px;border-radius:12px'>"
               f"<div style='width:36px;height:36px;border-radius:10px;display:grid;place-items:center;"
               f"background:linear-gradient(140deg,#241a44,#0c0a17);box-shadow:inset 0 0 0 1px rgba(46,240,255,.35)'>"
               f"<div style='width:22px;height:22px'>{UYGULAMA_ICI}</div></div>"
               f"<div style='font:700 15px Segoe UI;color:#fff'>Canlı Türkçe Altyazı</div></div>")
        sayfa = ("<html><body style='margin:0;padding:24px;background:#14141c;width:1000px'>"
                 "<style>.z{display:flex;align-items:center;gap:24px;padding:20px 24px;border-radius:14px;margin-bottom:16px}</style>"
                 f"<div class=z style='background:#202020'>{dizi()}</div>"
                 f"<div class=z style='background:#f3f3f3'>{dizi()}</div>{uyg}</body></html>")
        pg.set_viewport_size({"width": 1050, "height": 700})
        pg.set_content(sayfa)
        pg.wait_for_timeout(200)
        pg.screenshot(path=os.path.join(KLASOR, "kontrol.png"), full_page=True)
        b.close()
    print("Logo:", KLASOR)


if __name__ == "__main__":
    main()
