"""Microsoft Store sürümü (veri.MAGAZA): seslendirme "geliştiriliyor" bildirimleri yalnız orada görünür; ses motoru
denemeleri ve kayıt defteriyle "Windows açılınca başlat" orada yoktur. Kurulum programı sürümünde hiçbiri görünmez.
Altyazıyla ilgili hiçbir şey sürüme göre değişmez (bu test yalnız arayüzdeki farklara bakar)."""
import os

import yardimci  # noqa: F401  (sys.path + CTA_VERI ayarı)
from test_arayuz import CIKTI, _sahte_dunya, _temiz_uygulama


def test_magaza(overlay_port=8797):
    from playwright.sync_api import sync_playwright

    import tepsi
    import uygulama
    import veri

    os.makedirs(CIKTI, exist_ok=True)
    _sahte_dunya()
    uyg = _temiz_uygulama(overlay_port)
    uyg.ayar["kurulum_tamam"] = True
    ws = uygulama.api_sunucusu(uyg, "b")
    adres = f"http://127.0.0.1:{ws.server_address[1]}"
    eski = veri.MAGAZA
    yalniz = ["#ana-ses-gelisiyor", "#d-gelisiyor", "#d-yakinda", "#a-baslangic-ac", "#nav .nav-rozet"]
    try:
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page(viewport={"width": 1240, "height": 860})
            hatalar = []
            pg.on("pageerror", lambda e: hatalar.append(str(e)))

            def ac(sayfa):
                pg.click(f'#nav button[data-sayfa="{sayfa}"]')
                pg.wait_for_selector(f"#s-{sayfa}.aktif")
                pg.wait_for_timeout(500)  # sayfa geçişi (belirme) bitsin

            def gorunenler():
                """Her sayfa açılıp Store'a özel parçalardan hangilerinin göründüğüne bakılır."""
                sonuc = {}
                for sayfa, seciciler in (("ana", ["#ana-ses-gelisiyor", "#nav .nav-rozet"]),
                                         ("ses", ["#d-gelisiyor", "#d-yakinda", "#sd-kart"]),
                                         ("ayarlar", ["#a-baslangic-ac", "#a-baslat"])):
                    ac(sayfa)
                    for s in seciciler:
                        # #a-baslat gizli bir onay kutusudur (görünen kısmı yanındaki düğme): satırına bakılır
                        sonuc[s] = pg.evaluate("s => { const e = document.querySelector(s); "
                                               "return !!(e && (s === '#a-baslat' ? e.closest('.ayar') : e).offsetParent); }", s)
                return sonuc

            # ---------- kurulum programı sürümü: Store'a özel hiçbir şey görünmez ----------
            veri.MAGAZA = False
            assert uyg.durum(None)["magaza"] is False
            pg.goto(f"{adres}/#b")
            pg.wait_for_function("document.body.dataset.hazir === '1'")
            assert not pg.evaluate("document.body.classList.contains('magaza')")
            g = gorunenler()
            assert not any(g[s] for s in yalniz), f"Store bildirimleri kurulum programı sürümünde görünüyor: {g}"
            assert g["#sd-kart"] and g["#a-baslat"], g
            assert "Türkçe seslendirme" in [o.get("ad") for o in tepsi.menu_modeli(uyg)]

            # ---------- Store sürümü ----------
            veri.MAGAZA = True
            assert uyg.durum(None)["magaza"] is True
            pg.reload()
            pg.wait_for_function("document.body.dataset.hazir === '1'")
            assert pg.evaluate("document.body.classList.contains('magaza')")
            g = gorunenler()
            assert all(g[s] for s in yalniz), f"Store sürümünde 'geliştiriliyor' bildirimleri eksik: {g}"
            assert not g["#sd-kart"] and not g["#a-baslat"], g
            ac("ses")
            assert "geliştirme aşamasında" in pg.text_content("#d-gelisiyor")
            assert pg.locator("#s-ses .rozet.magaza-yalniz:visible").count() == 2  # Türkçe seslendirme, her karaktere ayrı ses
            assert "Yakında" in pg.text_content("#d-yakinda")
            assert pg.is_enabled("#d-acik"), "seslendirme Store sürümünde de kullanılabilir (yalnız işaretlenir)"
            pg.screenshot(path=os.path.join(CIKTI, "magaza_ses.png"))
            ac("ana")
            pg.screenshot(path=os.path.join(CIKTI, "magaza_ana.png"))
            ac("ayarlar")
            pg.click("#a-baslangic-ac")  # testte pencere açılmaz (CTA_KAYIT_YOK); hata vermemeli
            pg.wait_for_timeout(300)
            pg.screenshot(path=os.path.join(CIKTI, "magaza_ayarlar.png"))
            adlar = [o.get("ad") for o in tepsi.menu_modeli(uyg)]
            assert "Türkçe seslendirme (geliştiriliyor)" in adlar and "Türkçe yazı" in adlar, adlar
            # kayıt defterine yazan ayar ve model indirme Store sürümünde çalışmaz
            assert not uyg.uygulama_ayar({"windows_ile_baslat": True})["uygulama_ayar"].get("windows_ile_baslat")
            try:
                uyg.ses_deneme_indir({"id": "omnivoice"})
                raise AssertionError("Store sürümünde model indirme başlamamalı")
            except ValueError:
                pass
            assert not hatalar, hatalar
            b.close()
    finally:
        veri.MAGAZA = eski
        uyg.kapat()
    print("  ✓ Store sürümü: seslendirme 'geliştiriliyor' bildirimleri yalnız Store paketinde; ses denemeleri ve kayıt defteri ayarı yok")


if __name__ == "__main__":
    test_magaza()
