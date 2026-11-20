"""Altyazıyı özelleştirme (Playwright): paneldeki Görünüm sayfası ve oyunun üstündeki yazı (overlay.html).

Panelde yapılan her seçim (hazır görünüm, yazı tipi, kalınlık, renk, kenar çizgisi, kutu, boyut, yer, sürükleme)
ayara yazılıyor mu ve overlay sayfasındaki yazıya gerçekten yansıyor mu (tarayıcının hesapladığı stil ve konumla);
geçersiz değerler reddediliyor mu; program güncellenince açık kalan eski overlay sayfası kendini yeniliyor mu.
"""
import json
import os
import re

import yardimci  # noqa: F401  (sys.path + CTA_VERI ayarı)

TEMA = os.environ.get("CTA_TEMA", "light")
CIKTI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cikti" + ("_koyu" if TEMA == "dark" else ""))


def test_gorunum(overlay_port=8795):
    from playwright.sync_api import sync_playwright

    import uygulama
    import veri

    os.makedirs(CIKTI, exist_ok=True)
    for ad in os.listdir(veri.VERI_KLASORU):  # temiz kurulum
        if ad.endswith(".json"):
            os.remove(os.path.join(veri.VERI_KLASORU, ad))
    varsayilan = veri.ayar_yukle()
    varsayilan["goruntu"]["port"] = overlay_port
    varsayilan["kurulum_tamam"] = True
    veri.ayar_kaydet(varsayilan)
    uyg = uygulama.Uygulama()
    assert not uyg.overlay_hatasi, uyg.overlay_hatasi
    ws = uygulama.api_sunucusu(uyg, "b")
    adres = f"http://127.0.0.1:{ws.server_address[1]}"
    g = uyg.ayar["goruntu"]
    bolge = uyg.ayar["bolge"]

    # --- pakete giden varsayılanlar ile seçenek listeleri tutarlı
    s = veri.GORUNUM_SECENEKLERI
    assert g["yazi_tipi"] in s["yazi_tipi"] and g["yazi_kalinligi"] in s["yazi_kalinligi"] and g["kenar"] in s["kenar"]
    assert g["kutu"] in s["kutu"] and g["konum"] == "orijinal" and g["yazi_rengi"] == "#ffffff"

    # --- geçersiz değerler reddedilir (eski değer kalır), sayılar sınırlanır
    once = dict(g)
    uyg.gorunum_kaydet({"yazi_tipi": "<script>", "yazi_kalinligi": 123, "kenar": 9, "kutu": "x", "yazi_rengi": "red",
                        "konum": "uzay", "konum_x": 5, "konum_y": "abc"})
    assert {k: g[k] for k in once if k != "konum_x"} == {k: once[k] for k in once if k != "konum_x"}, g
    assert g["konum_x"] == s["konum_x"][1], "konum sınırlanmalı"
    uyg.gorunum_kaydet({"yazi_rengi": "#FFE04A", "konum_x": 0.5, "kenar": "3"})
    assert g["yazi_rengi"] == "#ffe04a" and g["kenar"] == 3
    uyg.gorunum_kaydet({"yazi_rengi": "#ffffff", "kenar": 2})

    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1180, "height": 900}, color_scheme=TEMA)
        ov = b.new_page(viewport={"width": 1920, "height": 1080})  # oyunun üstündeki yazı (OBS'teki sayfa)
        hatalar = []
        pg.on("pageerror", lambda e: hatalar.append("panel: " + str(e)))
        ov.on("pageerror", lambda e: hatalar.append("overlay: " + str(e)))
        ov.goto(f"http://127.0.0.1:{overlay_port}/")
        pg.goto(f"{adres}/#b")
        pg.wait_for_timeout(600)

        def bekle_ki(kosul, sn=8):
            for _ in range(int(sn * 10)):
                try:
                    if kosul():
                        return True
                except Exception:
                    pass
                pg.wait_for_timeout(100)
            return False

        def stil():
            """Overlay'deki Türkçe yazının tarayıcıca hesaplanan görünümü ve ekrandaki yeri."""
            return ov.evaluate("""() => {
                const tr = document.querySelector('.kutu .tr'), kutu = document.querySelector('.kutu'), kapak = document.querySelector('.kapak');
                const c = getComputedStyle(tr), r = tr.getBoundingClientRect();
                return { renk: c.color, tip: c.fontFamily, kalinlik: c.fontWeight, boyut: parseFloat(c.fontSize), golge: c.textShadow,
                         zemin: c.backgroundColor, gorunur: getComputedStyle(kutu).display !== 'none', metin: tr.textContent,
                         x: (r.left + r.width / 2) / innerWidth, y: (r.top + r.height / 2) / innerHeight, alt: r.bottom / innerHeight,
                         kapak: getComputedStyle(kapak).display !== 'none',
                         en: getComputedStyle(document.querySelector('.kutu .en')).display !== 'none' };
            }""")

        def ornek():
            pg.click("#ornek")
            assert bekle_ki(lambda: stil()["gorunur"]), "örnek cümle oyunun üstünde görünmedi"

        def sec(kutu, deger):
            pg.click(f'#{kutu} button[data-deger="{deger}"]')

        pg.click('#nav [data-bolum="gorunum"]')
        assert bekle_ki(lambda: pg.locator("#g-tip button").count() == 6)

        # --- seçenekler çizildi ve kod listeleri (altyazi_stil.js) ile Python doğrulaması (veri.py) aynı
        assert pg.locator("#g-kalinlik button").count() == 3 and pg.locator("#g-kenar button").count() == 4
        assert pg.locator("#g-kutu button").count() == 3 and pg.locator("#g-renk button").count() == 6
        assert pg.locator("#g-hazir button").count() == 5 and pg.locator("#g-konum button").count() == 4
        js = pg.evaluate("""() => ({ tip: Object.keys(AltyaziStil.YAZI_TIPLERI), kalinlik: AltyaziStil.KALINLIKLAR.map((k) => k[0]),
            kenar: AltyaziStil.KENARLAR.map((_, i) => i), kutu: Object.keys(AltyaziStil.KUTULAR), x: AltyaziStil.KONUM_X,
            y: AltyaziStil.KONUM_Y, varsayilan: AltyaziStil.VARSAYILAN, hazir: AltyaziStil.HAZIR, konumlar: AltyaziStil.HAZIR_KONUMLAR })""")
        assert tuple(js["tip"]) == s["yazi_tipi"] and tuple(js["kalinlik"]) == s["yazi_kalinligi"], js
        assert tuple(js["kenar"]) == s["kenar"] and tuple(js["kutu"]) == s["kutu"], js
        assert tuple(js["x"]) == s["konum_x"] and tuple(js["y"]) == s["konum_y"], js
        with open(os.path.join(yardimci.PROJE, "config.json"), encoding="utf-8") as f:
            paket = json.load(f)["goruntu"]
        assert all(paket[k] == v for k, v in js["varsayilan"].items()), (js["varsayilan"], paket)
        for h in js["hazir"] + js["konumlar"]:  # hazır görünümler de geçerli değerler taşımalı
            a = h["ayar"]
            assert a.get("yazi_tipi", "standart") in s["yazi_tipi"] and a.get("kutu", "yok") in s["kutu"], h
            assert a.get("yazi_kalinligi", 700) in s["yazi_kalinligi"] and a.get("kenar", 2) in s["kenar"], h
            assert a.get("konum", "orijinal") in s["konum"], h

        # --- baştaki görünüm: Klasik, altyazının yerinde, İngilizcenin üstü kapalı
        assert "secili" in pg.get_attribute('#g-hazir button[data-deger="klasik"]', "class")
        assert "secili" in pg.get_attribute('#g-konum button[data-deger="orijinal"]', "class")
        ornek()
        st = stil()
        assert st["renk"] == "rgb(255, 255, 255)" and st["kalinlik"] == "700" and abs(st["boyut"] - 44) < 0.6, st
        assert "Segoe UI" in st["tip"] and st["golge"] != "none" and st["zemin"] == "rgba(0, 0, 0, 0)", st
        assert st["kapak"] and bolge["y"] < st["y"] < bolge["y"] + bolge["h"] and abs(st["x"] - 0.5) < 0.02, st
        pg.screenshot(path=os.path.join(CIKTI, "gorunum_1_klasik.png"), full_page=True)

        # --- hazır görünüm: Sinema (sarı, sade yazı tipi) — ayara ve oyundaki yazıya yansır
        sec("g-hazir", "sinema")
        assert bekle_ki(lambda: g["yazi_rengi"] == "#ffe04a" and g["yazi_tipi"] == "sade"), g
        assert bekle_ki(lambda: stil()["gorunur"] and stil()["renk"] == "rgb(255, 224, 74)"), stil()
        assert stil()["tip"].startswith("Arial"), stil()
        assert "secili" in pg.get_attribute('#g-hazir button[data-deger="sinema"]', "class")
        assert "secili" not in pg.get_attribute('#g-hazir button[data-deger="klasik"]', "class")

        # --- tek tek: yazı tipi, kalınlık, kenar çizgisi, kutu, renk, boyut
        sec("g-tip", "oyun"); sec("g-kalinlik", "800"); sec("g-kenar", "0"); sec("g-kutu", "koyu")
        assert bekle_ki(lambda: (g["yazi_tipi"], g["yazi_kalinligi"], g["kenar"], g["kutu"]) == ("oyun", 800, 0, "koyu")), g
        assert bekle_ki(lambda: stil()["tip"].startswith("Bahnschrift") and stil()["kalinlik"] == "800"), stil()
        st = stil()
        assert st["golge"] == "none" and st["zemin"] == "rgba(0, 0, 0, 0.88)", st
        assert pg.locator("#g-hazir button.secili").count() == 0, "elle değiştirilince hazır görünüm seçili kalmamalı"
        sec("g-kenar", "3"); sec("g-kutu", "yok")
        assert bekle_ki(lambda: stil()["golge"] != "none" and stil()["zemin"] == "rgba(0, 0, 0, 0)"), stil()
        sec("g-renk", "#9fd8ff")
        assert bekle_ki(lambda: g["yazi_rengi"] == "#9fd8ff" and stil()["renk"] == "rgb(159, 216, 255)"), stil()
        pg.evaluate("""() => { const e = document.getElementById('g-renk-ozel'); e.value = '#12abef'; e.dispatchEvent(new Event('input', { bubbles: true })); }""")
        assert bekle_ki(lambda: g["yazi_rengi"] == "#12abef" and stil()["renk"] == "rgb(18, 171, 239)"), stil()
        assert pg.locator("#g-renk button.secili").count() == 0
        pg.locator("#boyut").fill("60")
        assert bekle_ki(lambda: g["yazi_boyutu"] == 60 and abs(stil()["boyut"] - 60) < 0.6), stil()
        assert pg.text_content("#boyut-deger") == "60 px"

        # --- önizleme oyundaki yazıyla aynı görünüyor (aynı kod): renk, yazı tipi, kalınlık
        oniz = pg.evaluate("""() => { const c = getComputedStyle(document.getElementById('o-tr')); return { renk: c.color, tip: c.fontFamily, kalinlik: c.fontWeight }; }""")
        st = stil()
        assert (oniz["renk"], oniz["tip"], oniz["kalinlik"]) == (st["renk"], st["tip"], st["kalinlik"]), (oniz, st)

        # --- yazının yeri: hazır konumlar
        sec("g-konum", "ust")
        assert bekle_ki(lambda: g["konum"] == "serbest" and g["konum_y"] == 0.1), g
        assert bekle_ki(lambda: abs(stil()["y"] - 0.1) < 0.02 and abs(stil()["x"] - 0.5) < 0.02), stil()
        assert stil()["kapak"], "üstü kapat açıkken İngilizce altyazı yine gizlenmeli"
        sec("g-konum", "orta")
        assert bekle_ki(lambda: abs(stil()["y"] - 0.5) < 0.02), stil()
        assert "secili" in pg.get_attribute('#g-konum button[data-deger="orta"]', "class")

        # --- fareyle sürükleme: önizlemede bırakılan yer, oyundaki yer olur
        def surukle(hedef_x, hedef_y):
            pg.locator("#onizleme").scroll_into_view_if_needed()
            alan, kutu = pg.locator("#onizleme").bounding_box(), pg.locator("#o-kutu").bounding_box()
            pg.mouse.move(kutu["x"] + kutu["width"] / 2, kutu["y"] + kutu["height"] / 2)
            pg.mouse.down()
            pg.mouse.move(alan["x"] + alan["width"] * (hedef_x + 0.5) / 2, alan["y"] + alan["height"] * (hedef_y + 0.5) / 2, steps=5)
            pg.mouse.move(alan["x"] + alan["width"] * hedef_x, alan["y"] + alan["height"] * hedef_y, steps=5)
            pg.mouse.up()

        surukle(0.3, 0.62)
        assert bekle_ki(lambda: abs(g["konum_x"] - 0.3) < 0.02 and abs(g["konum_y"] - 0.62) < 0.02), g
        assert bekle_ki(lambda: abs(stil()["x"] - 0.3) < 0.03 and abs(stil()["y"] - 0.62) < 0.03), stil()
        assert pg.locator("#g-konum button.secili").count() == 0 and "elle" in pg.text_content("#g-konum-not")
        pg.screenshot(path=os.path.join(CIKTI, "gorunum_2_serbest.png"), full_page=True)
        surukle(0.51, 0.3)  # ortaya yakın bırakılırsa tam ortalanır
        assert bekle_ki(lambda: g["konum_x"] == 0.5 and abs(g["konum_y"] - 0.3) < 0.02), g
        surukle(0.02, 0.99)  # kenara sürüklenirse sınırda kalır: yazı ekrandan taşmaz
        assert bekle_ki(lambda: g["konum_x"] == s["konum_x"][0] and g["konum_y"] == s["konum_y"][1]), g
        kutu = ov.evaluate("() => { const r = document.querySelector('.kutu').getBoundingClientRect(); return [r.left, r.right, innerWidth]; }")
        assert kutu[0] >= 0 and kutu[1] <= kutu[2], f"yazı kutusu ekrandan taşıyor: {kutu}"
        ov.screenshot(path=os.path.join(CIKTI, "gorunum_3_overlay.png"), animations="disabled")
        # en alta konmuş büyük ve uzun yazı ekranın altından taşmaz (kendiliğinden yukarı kayar)
        pg.locator("#boyut").fill("80")
        assert bekle_ki(lambda: g["yazi_boyutu"] == 80)
        uyg.yayinci.gonder({"tip": "satir", "id": 5, "alan": 0, "en": "", "tr": "Bu çok uzun bir altyazı satırı; ekranın kenarına "
                            "yerleştirildiğinde bile altından taşmamalı, kendiliğinden yukarı kaymalı ki hepsi okunabilsin."})

        def dikey():
            return ov.evaluate("() => { const r = document.querySelector('.kutu').getBoundingClientRect(); return [r.top, r.bottom, innerHeight, r.height]; }")
        assert bekle_ki(lambda: dikey()[3] > 300 and stil()["metin"].startswith("Bu çok uzun")), dikey()
        ust, alt, ekran, _ = dikey()
        assert ust >= 0 and alt <= ekran, f"uzun yazı ekrandan taşıyor: üst {ust:.0f}, alt {alt:.0f}, ekran {ekran}"
        ov.screenshot(path=os.path.join(CIKTI, "gorunum_4_uzun.png"), animations="disabled")
        uyg.yayinci.gonder({"tip": "temizle", "id": 5, "alan": 0})
        pg.locator("#boyut").fill("60")
        assert bekle_ki(lambda: g["yazi_boyutu"] == 60)

        # --- altyazının yerinde + üstü kapalı değil: Türkçe, İngilizcenin hemen üstünde; İngilizcesi de gösterilebilir
        sec("g-konum", "orijinal")
        pg.locator("label:has(#kapat)").click()
        assert bekle_ki(lambda: g["konum"] == "orijinal" and g["orijinali_kapat"] is False), g
        assert bekle_ki(lambda: not stil()["kapak"] and stil()["alt"] <= bolge["y"] + 0.005), (stil(), bolge)
        pg.locator("label:has(#ing)").click()
        assert bekle_ki(lambda: g["ingilizce_goster"] is True and stil()["en"]), stil()

        # --- ilk görünüme dön: yazı tipi/renk/boyut/yer sıfırlanır; "üstünü kapat" ve "İngilizcesi" seçimleri kalır
        pg.click("#g-sifirla")
        assert bekle_ki(lambda: (g["yazi_tipi"], g["yazi_rengi"], g["yazi_boyutu"], g["kenar"], g["kutu"], g["konum"])
                        == ("standart", "#ffffff", 44, 2, "yok", "orijinal")), g
        assert g["orijinali_kapat"] is False and g["ingilizce_goster"] is True
        assert "secili" in pg.get_attribute('#g-hazir button[data-deger="klasik"]', "class")
        pg.locator("label:has(#kapat)").click(); pg.locator("label:has(#ing)").click()
        assert bekle_ki(lambda: g["orijinali_kapat"] is True and g["ingilizce_goster"] is False)

        # --- ayarlar diske yazıldı; sayfa yeniden açılınca aynı görünüm gelir
        sec("g-hazir", "sinema"); sec("g-konum", "alt")
        assert bekle_ki(lambda: g["yazi_rengi"] == "#ffe04a" and g["konum_y"] == 0.9)
        pg.wait_for_timeout(400)
        with open(veri.ayar_yolu(), encoding="utf-8") as f:
            kayitli = json.load(f)["goruntu"]
        assert kayitli["yazi_rengi"] == "#ffe04a" and kayitli["konum"] == "serbest" and kayitli["konum_y"] == 0.9, kayitli
        pg.reload(); pg.wait_for_timeout(600)
        pg.click('#nav [data-bolum="gorunum"]')
        assert bekle_ki(lambda: "secili" in pg.get_attribute('#g-hazir button[data-deger="sinema"]', "class"))
        assert "secili" in pg.get_attribute('#g-konum button[data-deger="alt"]', "class")

        # --- ekranda gerçek bir altyazı varken ayar değişirse örnek cümle onun yerine geçmez
        uyg.yayinci.gonder({"tip": "satir", "id": 7, "alan": 0, "en": "Real line.", "tr": "Gerçek satır."})
        assert bekle_ki(lambda: stil()["metin"] == "Gerçek satır.")
        sec("g-kenar", "1")
        assert bekle_ki(lambda: g["kenar"] == 1)
        pg.wait_for_timeout(500)
        assert stil()["metin"] == "Gerçek satır." and stil()["gorunur"], stil()
        uyg.yayinci.gonder({"tip": "temizle", "id": 7, "alan": 0})

        # --- program güncellenince açık kalan eski overlay sayfası kendini yeniler
        assert ov.evaluate("() => SAYFA_SURUMU") == veri.SURUM
        asil_surum = veri.SURUM
        try:
            veri.SURUM = "9.9.9"
            uyg.yayinci.ayar_guncelle(uyg.ayar["goruntu"], uyg.ayar["bolge"], uyg.ayar.get("ek_bolgeler"))
            assert bekle_ki(lambda: ov.evaluate("() => SAYFA_SURUMU") == "9.9.9", 10), "eski sayfa kendini yenilemedi"
            assert bekle_ki(lambda: ov.evaluate("() => !!window.AltyaziStil && Object.keys(alanlar).length >= 1"))
        finally:
            veri.SURUM = asil_surum
        assert not hatalar, hatalar
        b.close()
    ws.shutdown()
    assert re.fullmatch(r"#[0-9a-f]{6}", uyg.ayar["goruntu"]["yazi_rengi"])
    uyg.kapat()
    print("  ✓ görünüm: hazır görünümler, yazı tipi, kalınlık, renk, kenar, kutu, boyut ve yer (sürükleme dahil) oyundaki yazıya yansıyor")


if __name__ == "__main__":
    test_gorunum()
