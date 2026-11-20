"""Yeni arayüz (arayuz.html, 2.7) — uçtan uca, Playwright ile:
ilk kurulum (ekran + altyazı alanı) -> görünüm (hazır görünüm, renk, saydamlık, yazı tipi, sürükleyerek konum; oyun
üstündeki sayfaya yansıması) -> başlat / çevrilen satır / durdur -> çeviri denemesi -> ayarlar.
Tepsi menüsü (tepsi.menu_modeli) ve görünüm doğrulaması pencere açmadan denenir.
Ekran yakalama sahtedir (gerçeği için: tests/elle_pc_katman.py)."""
import json
import os
import time

import yardimci  # noqa: F401  (sys.path + CTA_VERI ayarı)
from yardimci import ornek_kare

CIKTI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cikti")


def _sahte_dunya():
    import cv2

    import kaynak
    import pc_katman

    oyun = ornek_kare()
    h, w = oyun.shape[:2]
    for kalinlik, renk in ((8, (0, 0, 0)), (2, (255, 255, 255))):  # sol üstte görev yazısı: ek alan bununla denenir
        cv2.putText(oyun, "Find the hidden key.", (120, 150), cv2.FONT_HERSHEY_DUPLEX, 1.4, renk, kalinlik, cv2.LINE_AA)
    masaustu = oyun.copy()
    masaustu[:] = (40, 40, 40)
    pc_katman.ekranlar = lambda: [
        {"no": 1, "x": 0, "y": 0, "genislik": 1920, "yukseklik": 1080, "ana": True},
        {"no": 2, "x": 1920, "y": 0, "genislik": w, "yukseklik": h, "ana": False}]
    pc_katman.ekran_goruntusu = lambda no: (oyun if no == 2 else masaustu).copy()
    okunan_ekran = []

    class SahteEkran:
        def __init__(self, no):
            okunan_ekran.append(no)
            self.son_kare_ms = 1

        def kare_al(self):
            time.sleep(0.03)
            return oyun.copy()

        def kapat(self):
            pass

    kaynak.EkranKaynagi = SahteEkran
    return okunan_ekran


def _temiz_uygulama(overlay_port):
    import uygulama
    import veri

    for ad in os.listdir(veri.VERI_KLASORU):  # temiz kurulum
        if ad.endswith(".json"):
            os.remove(os.path.join(veri.VERI_KLASORU, ad))
    varsayilan = veri.ayar_yukle()
    varsayilan["goruntu"]["port"] = overlay_port
    veri.ayar_kaydet(varsayilan)
    uyg = uygulama.Uygulama()
    uyg.ayar["ocr"]["motor"] = yardimci.VARSAYILAN_OCR
    return uyg


def test_gorunum_dogrulama():
    """gorunum_kaydet: sınır dışı değer sınıra çekilir, geçersiz değer yok sayılır; eski 'kutu' ayarı taşınır."""
    import veri
    uyg = _temiz_uygulama(8791)
    g = uyg.gorunum_kaydet({"yazi_boyutu": 500, "kutu_saydamlik": "0.42", "kutu_rengi": "#14213D", "yazi_rengi": "kırmızı",
                            "kenar": -3, "yazi_kalinligi": 649, "kutu_bicimi": "serit", "hizalama": "yamuk",
                            "italik": 1, "etiket_rengi": "#FFE04A", "yazi_tipi": "ozel"})["goruntu"]
    assert g["yazi_boyutu"] == 120 and g["kutu_saydamlik"] == 0.42 and g["kutu_rengi"] == "#14213d", g
    assert g["yazi_rengi"] == "#ffffff" and g["kenar"] == 0 and g["yazi_kalinligi"] == 600, g
    assert g["kutu_bicimi"] == "serit" and g["hizalama"] == "orta" and g["italik"] is True, g
    assert g["etiket_rengi"] == "#ffe04a" and g["yazi_tipi"] == "standart", "özel yazı tipi adı verilmeden 'ozel' seçilemez"
    g = uyg.gorunum_kaydet({"yazi_tipi": "ozel", "yazi_tipi_ozel": 'Arial"; } body { x'})["goruntu"]
    assert g["yazi_tipi"] == "ozel" and g["yazi_tipi_ozel"] == "Arial  body  x", g["yazi_tipi_ozel"]
    assert uyg.gorunum_kaydet({"etiket_rengi": ""})["goruntu"]["etiket_rengi"] == ""
    # eski sürümün ayar dosyası: kutu "yari" -> yarı saydam siyah
    eski = json.load(open(veri.ayar_yolu(), encoding="utf-8"))
    eski["goruntu"].pop("kutu_saydamlik")
    eski["goruntu"]["kutu"] = "yari"
    veri.ayar_kaydet(eski)
    yeni = veri.ayar_yukle()["goruntu"]
    assert yeni["kutu_saydamlik"] == 0.55 and "kutu" not in yeni, yeni
    # yüklü yazı tipleri okunabiliyor
    import pc_katman
    if pc_katman.WINDOWS:
        tipler = uyg.yazi_tipleri(None)["yazi_tipleri"]
        assert "Arial" in tipler and not any(t.startswith("@") for t in tipler), tipler[:5]
    print("  ✓ görünüm doğrulaması: sınırlar, geçersiz değerler, eski ayarın taşınması, yüklü yazı tipleri")


def test_tepsi_menusu():
    """Tepsi menüsü: içerik ayarlara göre kurulur; her eylem ayarı gerçekten değiştirir (pencere açılmadan)."""
    import tepsi
    _sahte_dunya()
    uyg = _temiz_uygulama(8792)
    uyg.ayar["kurulum_tamam"] = True

    def bul(*yol):
        ogeler = tepsi.menu_modeli(uyg)
        for ad in yol:
            oge = next(o for o in ogeler if o.get("ad") == ad)
            ogeler = oge.get("alt", [])
        return oge

    adlar = [o.get("ad") for o in tepsi.menu_modeli(uyg) if not o.get("ayrac")]
    assert adlar == ["Paneli aç", "Altyazıyı başlat", "Türkçe yazı", "Türkçe seslendirme", "İngilizcesini de göster",
                     "Yazı boyutu", "Görünüm", "Arka plan", "Konum", "Çıkış"], adlar
    assert bul("Yazı boyutu", "Orta")["isaretli"] and not bul("Yazı boyutu", "Büyük")["isaretli"]
    bul("Yazı boyutu", "Büyük")["eylem"]()
    assert uyg.ayar["goruntu"]["yazi_boyutu"] == 56 and bul("Yazı boyutu", "Büyük")["isaretli"]
    bul("Arka plan", "Yarı saydam")["eylem"]()
    assert uyg.ayar["goruntu"]["kutu_saydamlik"] == 0.5 and bul("Arka plan", "Yarı saydam")["isaretli"]
    bul("Görünüm", "Sinema")["eylem"]()
    assert uyg.ayar["goruntu"]["yazi_rengi"] == "#ffe04a" and bul("Görünüm", "Sinema")["isaretli"]
    assert uyg.ayar["goruntu"]["kutu_saydamlik"] == 0, "hazır görünüm kendi arka planını ayarlamalı"
    bul("Konum", "Üstte")["eylem"]()
    assert uyg.ayar["goruntu"]["konum"] == "serbest" and uyg.ayar["goruntu"]["konum_y"] == 0.1
    assert bul("Konum", "Üstte")["isaretli"] and not bul("Konum", "Altyazının yerinde")["isaretli"]
    bul("İngilizcesini de göster")["eylem"]()
    assert uyg.ayar["goruntu"]["ingilizce_goster"] is True
    # yazı kapatılınca ses açılır (ikisi birden kapalı kalamaz); yazı yeniden açılabilir
    import dogal_ses
    import seslendirme
    seslendirme.destekleniyor = lambda: True
    seslendirme.turkce_sesler = lambda: [{"id": "x", "ad": "Tolga", "dil": "tr-TR"}]
    dogal_ses.var_mi = lambda: False
    assert bul("Türkçe yazı")["isaretli"] and not bul("Türkçe seslendirme")["isaretli"]
    bul("Türkçe seslendirme")["eylem"]()
    assert uyg.ayar["dublaj"]["acik"] and uyg.ayar["goruntu"]["altyazi_goster"]
    bul("Türkçe yazı")["eylem"]()
    assert uyg.ayar["dublaj"]["acik"] and uyg.ayar["goruntu"]["altyazi_goster"] is False
    bul("Türkçe seslendirme")["eylem"]()
    assert not uyg.ayar["dublaj"]["acik"] and uyg.ayar["goruntu"]["altyazi_goster"], "ses kapanınca yazı açık kalmalı"
    # simge dosyası bulunuyor
    assert tepsi.simge_yolu().endswith("uygulama.ico"), tepsi.simge_yolu()
    # ikinci kopya: açık olanın penceresini öne getirir
    import uygulama
    cagri = []
    uyg.yayinci.pencere_ac = lambda: cagri.append(1)
    assert uygulama.acik_kopyayi_one_getir(8792) and cagri == [1]
    assert not uygulama.acik_kopyayi_one_getir(8790), "kapalı kapıda True dönmemeli"
    print("  ✓ tepsi menüsü: boyut, arka plan, hazır görünüm, konum, yazı/ses kipleri; ikinci kopya öne getiriyor")


def test_arayuz(overlay_port=8793):
    from playwright.sync_api import sync_playwright

    import uygulama
    import veri

    os.makedirs(CIKTI, exist_ok=True)
    okunan_ekran = _sahte_dunya()
    uyg = _temiz_uygulama(overlay_port)
    ws = uygulama.api_sunucusu(uyg, "b")
    adres = f"http://127.0.0.1:{ws.server_address[1]}"

    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1240, "height": 860})
        ov = b.new_page(viewport={"width": 1920, "height": 1080})  # oyunun üstündeki yazı (katman penceresindeki sayfa)
        hatalar = []
        pg.on("pageerror", lambda e: hatalar.append("arayüz: " + str(e)))
        ov.on("pageerror", lambda e: hatalar.append("overlay: " + str(e)))
        ov.goto(f"http://127.0.0.1:{overlay_port}/")
        pg.goto(f"{adres}/#b")

        def bekle_ki(kosul, sn=10):
            for _ in range(int(sn * 10)):
                if kosul():
                    return True
                pg.wait_for_timeout(100)
            return False

        def ayarla(secici, deger):  # kaydırıcı
            pg.eval_on_selector(secici, "(e, d) => { e.value = d; e.dispatchEvent(new Event('input')); }", deger)

        def g():
            return uyg.ayar["goruntu"]

        assert bekle_ki(lambda: pg.evaluate("document.body.dataset.hazir") == "1"), hatalar

        # ---------- ilk kurulum: yalnız "Ekran ve altyazı alanı" açık ----------
        assert pg.is_visible("#s-alan") and pg.is_visible("#kurulum-adimlar")
        assert pg.is_disabled('#nav button[data-sayfa="ana"]') and not pg.is_disabled('#nav button[data-sayfa="alan"]')
        assert pg.text_content("#al-kaydet") == "Kurulumu bitir"
        assert bekle_ki(lambda: pg.locator("#ekranlar .ekran-oge").count() == 2)
        pg.locator("#ekranlar .ekran-oge").nth(1).click()
        assert bekle_ki(lambda: uyg.ayar["kaynak"].get("ekran_no") == 2)
        assert uyg.ayar["senaryo"] == "pc" and uyg.ayar["kaynak"]["tip"] == "ekran"
        assert bekle_ki(lambda: (pg.get_attribute("#cizim-resim", "src") or "").startswith("data:image"))
        pg.click("#al-bul")
        assert bekle_ki(lambda: "Altyazı bulundu" in (pg.text_content("#al-sonuc") or "")), pg.text_content("#al-sonuc")
        assert "cops are right behind" in pg.text_content("#al-sonuc")
        pg.click("#al-dene")
        assert bekle_ki(lambda: "Okunan yazı" in (pg.text_content("#al-sonuc") or "")), pg.text_content("#al-sonuc")
        # ek alan: görev yazısının üstüne fareyle kutu çiz
        pg.click("#al-ekle")
        assert pg.locator("#alan-liste .alan-oge").count() == 2
        kutu = pg.locator("#cizim").bounding_box()
        x1, y1 = kutu["x"] + kutu["width"] * 0.04, kutu["y"] + kutu["height"] * 0.09
        x2, y2 = kutu["x"] + kutu["width"] * 0.36, kutu["y"] + kutu["height"] * 0.17
        pg.mouse.move(x1, y1)
        pg.mouse.down()
        pg.mouse.move((x1 + x2) / 2, (y1 + y2) / 2)
        pg.mouse.move(x2, y2)
        pg.mouse.up()
        pg.click("#al-dene")
        assert bekle_ki(lambda: "hidden key" in (pg.text_content("#al-sonuc") or "")), pg.text_content("#al-sonuc")
        pg.screenshot(path=os.path.join(CIKTI, "arayuz_1_alan.png"))
        pg.click("#al-kaydet")
        assert bekle_ki(lambda: uyg.ayar.get("kurulum_tamam") and pg.is_visible("#s-ana")), "kurulum bitmedi"
        assert len(uyg.ayar["ek_bolgeler"]) == 1 and abs(uyg.ayar["ek_bolgeler"][0]["w"] - 0.32) < 0.02, uyg.ayar["ek_bolgeler"]
        assert 0.7 < uyg.ayar["bolge"]["y"] < 0.9, uyg.ayar["bolge"]
        assert not pg.is_disabled('#nav button[data-sayfa="gorunum"]')
        assert json.load(open(veri.ayar_yolu(), encoding="utf-8"))["kurulum_tamam"] is True

        # ---------- görünüm ----------
        pg.click('#nav button[data-sayfa="gorunum"]')
        assert pg.locator("#g-hazir .hazir").count() == len(veri.HAZIR_GORUNUMLER)
        assert pg.locator("#g-yazi-tipi option").count() == len(veri.GORUNUM_SECENEKLERI["yazi_tipi"])
        assert "Arabaya bin" in pg.text_content("#on-kutu .tr")
        # JS ile Python aynı sınırları ve seçenekleri kullanıyor
        js = pg.evaluate("({s: AltyaziStil.SINIR, c: AltyaziStil.SECENEK, r: AltyaziStil.RENK_ALANLARI, t: Object.keys(AltyaziStil.YAZI_TIPLERI), v: AltyaziStil.VARSAYILAN})")
        assert {k: tuple(v) for k, v in js["s"].items()} == dict(veri.GORUNUM_SINIRLARI)
        assert {k: tuple(v) for k, v in js["c"].items()} == {k: v for k, v in veri.GORUNUM_SECENEKLERI.items() if k != "yazi_tipi"}
        assert tuple(js["r"]) == veri.GORUNUM_RENKLERI and tuple(js["t"]) == veri.GORUNUM_SECENEKLERI["yazi_tipi"]
        varsayilan = json.load(open(veri.VARSAYILAN_AYAR, encoding="utf-8"))["goruntu"]
        assert all(varsayilan[k] == v for k, v in js["v"].items()), "config.json ile altyazi_stil.js varsayılanları farklı"
        for h in veri.HAZIR_GORUNUMLER:  # hazır görünümler geçerli değerlerden oluşuyor
            assert uyg.gorunum_kaydet(dict(h["ayar"]))["goruntu"].items() >= h["ayar"].items(), h["id"]
        uyg.gorunum_kaydet(dict(veri.HAZIR_GORUNUMLER[0]["ayar"]))
        pg.wait_for_timeout(2700)  # arayüz dışarıdan (tepsi) yapılan değişikliği alır
        assert "secili" in pg.get_attribute('#g-hazir .hazir[data-v="klasik"]', "class")

        # hazır görünüm: Buzlu cam -> yarı saydam siyah kutu, oyunun üstündeki sayfada da
        pg.click('#g-hazir .hazir[data-v="cam"]')
        assert bekle_ki(lambda: g()["kutu_saydamlik"] == 0.5 and g()["kenar"] == 0), g()
        govde = "getComputedStyle(document.querySelector('.kutu .govde')).backgroundColor"
        # Türkçe, İngilizcenin üstünü kapatan şeridin içindeyken kutu çizilmez (kutu içinde kutu olmasın); arayüz bunu
        # söyler ve tek tıkla şeridi kaldırır
        assert pg.is_visible("#g-serit-not") and g()["orijinali_kapat"] is True
        assert ov.evaluate(govde) == "rgba(0, 0, 0, 0)", ov.evaluate(govde)
        assert ov.evaluate("getComputedStyle(document.querySelector('.kapak')).backgroundColor") == "rgb(8, 8, 10)"
        pg.click("#g-serit-kaldir")
        assert bekle_ki(lambda: g()["orijinali_kapat"] is False and not pg.is_visible("#g-serit-not")), g()
        assert bekle_ki(lambda: ov.evaluate(govde) == "rgba(0, 0, 0, 0.5)"), ov.evaluate(govde)
        assert pg.evaluate("getComputedStyle(document.querySelector('#on-kutu .govde')).backgroundColor") == "rgba(0, 0, 0, 0.5)"
        # istenen renk + saydamlık
        pg.click('.renkler[data-renk="kutu_rengi"] button[data-v="#14213d"]')
        ayarla('input[data-g="kutu_saydamlik"]', "0.8")
        assert bekle_ki(lambda: g()["kutu_rengi"] == "#14213d" and g()["kutu_saydamlik"] == 0.8), g()
        assert bekle_ki(lambda: ov.evaluate(govde) == "rgba(20, 33, 61, 0.8)"), ov.evaluate(govde)
        # renk seçiciden başka bir yazı rengi, boyut, kalınlık, italik
        pg.eval_on_selector('.renkler[data-renk="yazi_rengi"] input[type=color]',
                            "e => { e.value = '#ff8800'; e.dispatchEvent(new Event('input')); }")
        ayarla('input[data-g="yazi_boyutu"]', "60")
        ayarla('input[data-g="yazi_kalinligi"]', "900")
        pg.click('input[data-g="italik"]', force=True)
        assert bekle_ki(lambda: (g()["yazi_rengi"], g()["yazi_boyutu"], g()["yazi_kalinligi"], g()["italik"])
                        == ("#ff8800", 60, 900, True)), g()
        tr = "(() => { const s = getComputedStyle(document.querySelector('.kutu .tr')); return [s.color, s.fontSize, s.fontWeight, s.fontStyle]; })()"
        assert bekle_ki(lambda: ov.evaluate(tr) == ["rgb(255, 136, 0)", "60px", "900", "italic"]), ov.evaluate(tr)
        # bilgisayardaki bir yazı tipi
        pg.select_option("#g-yazi-tipi", "ozel")
        assert bekle_ki(lambda: pg.is_visible("#g-ozel-satir") and pg.locator("#g-ozel option").count() > 5)
        pg.select_option("#g-ozel", "Georgia")
        assert bekle_ki(lambda: g()["yazi_tipi"] == "ozel" and g()["yazi_tipi_ozel"] == "Georgia"), g()
        assert bekle_ki(lambda: ov.evaluate("getComputedStyle(document.querySelector('.kutu .tr')).fontFamily").startswith('Georgia'))
        # kenar çizgisi ve gölge
        pg.click("details.grup:nth-of-type(3) summary")
        ayarla('input[data-g="kenar"]', "3")
        pg.click('.renkler[data-renk="kenar_rengi"] button[data-v="#ffffff"]')
        assert bekle_ki(lambda: g()["kenar"] == 3 and g()["kenar_rengi"] == "#ffffff"), g()
        assert bekle_ki(lambda: "rgb(255, 255, 255)" in ov.evaluate("getComputedStyle(document.querySelector('.kutu .tr')).textShadow"))
        # şerit biçimi
        pg.click('.secim[data-g="kutu_bicimi"] button[data-v="serit"]')
        assert bekle_ki(lambda: g()["kutu_bicimi"] == "serit")
        # İngilizce satır + konuşmacı adı rengi
        pg.click("details.grup:nth-of-type(5) summary")
        pg.click('input[data-g="ingilizce_goster"]', force=True)
        pg.click('.renkler[data-renk="ingilizce_rengi"] button[data-v="#ffe04a"]')
        pg.click('.renkler[data-renk="etiket_rengi"] button[data-v="#9fd8ff"]')
        assert bekle_ki(lambda: g()["ingilizce_goster"] and g()["ingilizce_rengi"] == "#ffe04a" and g()["etiket_rengi"] == "#9fd8ff"), g()
        assert pg.evaluate("getComputedStyle(document.querySelector('#on-kutu .tr span')).color") == "rgb(159, 216, 255)"
        assert pg.text_content("#on-kutu .tr span") == "LUCIA: "
        # yazıyı sürükleyerek konum
        on = pg.locator("#onizleme").bounding_box()
        pg.mouse.move(on["x"] + on["width"] * 0.5, on["y"] + on["height"] * 0.5)
        pg.mouse.down()
        pg.mouse.move(on["x"] + on["width"] * 0.4, on["y"] + on["height"] * 0.3)
        pg.mouse.up()
        assert bekle_ki(lambda: g()["konum"] == "serbest" and abs(g()["konum_x"] - 0.4) < 0.02 and abs(g()["konum_y"] - 0.3) < 0.02), g()
        pg.screenshot(path=os.path.join(CIKTI, "arayuz_2_gorunum.png"))
        pg.click("details.grup:nth-of-type(4) summary")
        pg.click('#g-konum button[data-v="orijinal"]')
        assert bekle_ki(lambda: g()["konum"] == "orijinal")
        # kapatma şeridinin saydamlığı (Türkçe, İngilizcenin üstünde hafif bir arka planla)
        ayarla('details.grup:nth-of-type(4) input[data-g="kapak_saydamlik"]', "0.4")
        assert bekle_ki(lambda: g()["kapak_saydamlik"] == 0.4), g()
        if not g()["orijinali_kapat"]:  # şerit daha önce kaldırılmıştı: önizlemede görmek için yeniden aç
            pg.click('input[data-g="orijinali_kapat"]', force=True)
            assert bekle_ki(lambda: g()["orijinali_kapat"] is True)
        assert bekle_ki(lambda: pg.evaluate("getComputedStyle(document.querySelector('#on-kapak')).backgroundColor") == "rgba(8, 8, 10, 0.4)")
        # sıfırla: varsayılan görünüm
        pg.click("#g-sifirla")
        assert bekle_ki(lambda: g()["yazi_rengi"] == "#ffffff" and g()["kutu_saydamlik"] == 0 and g()["yazi_tipi"] == "standart"
                        and g()["ingilizce_goster"] is False and g()["etiket_rengi"] == "" and g()["orijinali_kapat"]
                        and g()["kapak_saydamlik"] == 1), g()
        assert g()["altyazi_goster"] is True and g()["port"] == overlay_port, "sıfırlama görünüm dışındaki ayarlara dokunmamalı"

        # ---------- ek alanın (2. altyazı) kendi görünümü: yeri, boyutu, rengi ana altyazıdan ayrı ----------
        def ek():
            return uyg.ayar["ek_bolgeler"][0]

        assert pg.is_visible("#g-hedef-kart") and pg.locator("#g-hedef button").count() == 2
        pg.locator("#g-hedef button").nth(1).click()
        assert bekle_ki(lambda: "secili" in pg.locator("#g-hedef button").nth(1).get_attribute("class"))
        assert pg.is_checked('input[data-g="orijinali_kapat"]'), "ayarlanmamış ek alan kendi yerinde ve üstü kapalı gelir"
        pg.click("details.grup:nth-of-type(1) summary") if not pg.is_visible('input[data-g="yazi_boyutu"]') else None
        pg.click('.renkler[data-renk="yazi_rengi"] button[data-v="#ffe04a"]')
        ayarla('input[data-g="yazi_boyutu"]', "52")
        assert bekle_ki(lambda: ek().get("gorunum", {}).get("yazi_rengi") == "#ffe04a" and ek()["gorunum"]["yazi_boyutu"] == 52), ek()
        assert g()["yazi_rengi"] == "#ffffff" and g()["yazi_boyutu"] == 44, "ek alanın ayarı ana altyazıyı değiştirmemeli"
        pg.click('#g-konum button[data-v="ust"]')
        assert bekle_ki(lambda: ek()["gorunum"].get("konum") == "serbest" and ek()["gorunum"]["konum_y"] == 0.1), ek()
        assert g()["konum"] == "orijinal"
        # oyun üstü sayfada: 2. alanın yazısı sarı, 52 px, ekranın üstünde; ana altyazı beyaz ve kendi yerinde
        uyg.yayinci.gonder({"tip": "satir", "id": 1000001, "alan": 1, "en": "Find the hidden key.", "tr": "Gizli anahtarı bul."})
        uyg.yayinci.gonder({"tip": "satir", "id": 1, "alan": 0, "en": "x", "tr": "Ana satır"})
        alan1 = ("(() => { const k = Array.from(document.querySelectorAll('.kutu')).find(e => e.textContent.includes('Gizli')); "
                 "const s = getComputedStyle(k.querySelector('.tr')), r = k.getBoundingClientRect(); "
                 "return [s.color, s.fontSize, Math.round((r.top + r.height / 2) / innerHeight * 100)]; })()")
        assert bekle_ki(lambda: ov.locator(".kutu").count() == 2 and ov.evaluate(alan1) == ["rgb(255, 224, 74)", "52px", 10]), ov.evaluate(alan1)
        ana = "getComputedStyle(Array.from(document.querySelectorAll('.kutu')).find(e => e.textContent.includes('Ana sat')).querySelector('.tr')).color"
        assert ov.evaluate(ana) == "rgb(255, 255, 255)"
        pg.screenshot(path=os.path.join(CIKTI, "arayuz_2b_ek_alan_gorunum.png"))
        # alanlar yeniden kaydedilince ek alanın görünümü kaybolmaz
        uyg.alanlar_kaydet({"ek_bolgeler": [dict(ek(), ad="Görev")]})
        assert ek()["ad"] == "Görev" and ek()["gorunum"]["yazi_rengi"] == "#ffe04a", ek()
        # geçersiz değerler alana da yazılmaz; olmayan alan reddedilir
        uyg.alan_gorunum({"no": 1, "gorunum": {"yazi_rengi": "mor", "yazi_boyutu": 999, "kutu_saydamlik": 0.4}})
        assert ek()["gorunum"] == {"yazi_boyutu": 120, "kutu_saydamlik": 0.4}, ek()["gorunum"]
        try:
            uyg.alan_gorunum({"no": 5, "gorunum": {}})
            raise AssertionError("olmayan alan kabul edildi")
        except ValueError:
            pass
        # sıfırla: alanın kendi görünümü silinir (varsayılana döner), ana altyazıya dokunulmaz
        pg.click("#g-sifirla")
        assert bekle_ki(lambda: "gorunum" not in ek()), ek()
        assert g()["yazi_boyutu"] == 44
        uyg.yayinci.gonder({"tip": "temizle", "id": -1, "hepsi": True})
        pg.locator("#g-hedef button").nth(0).click()
        assert bekle_ki(lambda: pg.input_value('input[data-g="yazi_boyutu"]') == "44")

        # ---------- başlat: satır çevrilir, oyunun üstünde görünür ----------
        pg.click('#nav button[data-sayfa="ana"]')
        pg.click("#ana-dugme")
        assert bekle_ki(lambda: pg.text_content("#ana-durum") == "Çalışıyor", 60), pg.text_content("#ana-durum") + str(hatalar)
        assert okunan_ekran and okunan_ekran[-1] == 2, okunan_ekran
        assert bekle_ki(lambda: pg.locator("#satirlar .satir-oge").count() >= 1, 20), "çevrilen satır listelenmedi"
        assert "Lucia" in pg.text_content("#satirlar")
        assert bekle_ki(lambda: "Lucia" in (ov.text_content(".kutu .tr") or ""))
        assert ov.evaluate("getComputedStyle(document.querySelector('.kutu')).display") != "none"
        assert pg.text_content("#o-okuma") != "–" and pg.text_content("#o-motor") == "Hazır çeviri"
        assert pg.text_content("#ana-dugme") == "Durdur"
        pg.screenshot(path=os.path.join(CIKTI, "arayuz_3_ana.png"))
        ov.screenshot(path=os.path.join(CIKTI, "arayuz_4_oyun_ustu.png"))
        # çalışırken görünüm değişirse yazı yerinde güncellenir
        uyg.gorunum_kaydet({"kutu_saydamlik": 0.6, "kutu_rengi": "#3a0d0d", "orijinali_kapat": False})
        assert bekle_ki(lambda: ov.evaluate(govde) == "rgba(58, 13, 13, 0.6)"), ov.evaluate(govde)
        ov.screenshot(path=os.path.join(CIKTI, "arayuz_5_oyun_ustu_kutulu.png"))
        pg.click("#ana-dugme")
        assert bekle_ki(lambda: pg.text_content("#ana-durum") == "Kapalı", 15)
        assert bekle_ki(lambda: ov.evaluate("getComputedStyle(document.querySelector('.kutu')).display") == "none")

        # ---------- tüm ekran kipi: arayüzden açılır, ekrandaki bütün İngilizce yazılar yerinde çevrilir ----------
        pg.click('#nav button[data-sayfa="alan"]')
        assert pg.is_visible("#alan-kartlari") and not pg.is_visible("#te-secenekler")
        pg.click('#te-kip button[data-v="tam"]')
        assert bekle_ki(lambda: uyg.ayar["tam_ekran"]["acik"] is True and pg.is_visible("#te-secenekler"))
        assert not pg.is_visible("#alan-kartlari"), "tüm ekran kipinde alan çizimi gizlenmeli"
        pg.click('#te-yerlesim button[data-v="altinda"]')
        pg.click('#te-aralik button[data-v="0.5"]')
        assert bekle_ki(lambda: uyg.ayar["tam_ekran"] == {"acik": True, "yerlesim": "altinda", "aralik": 0.5}), uyg.ayar["tam_ekran"]
        pg.screenshot(path=os.path.join(CIKTI, "arayuz_9_tum_ekran.png"))
        pg.click('#nav button[data-sayfa="ana"]')
        pg.click("#ana-dugme")
        assert bekle_ki(lambda: pg.text_content("#ana-durum") == "Çalışıyor", 60), pg.text_content("#ana-durum")
        assert bekle_ki(lambda: ov.locator(".tam").count() >= 2, 30), f"tüm ekran kutuları gelmedi: {ov.locator('.tam').count()}"
        tam = ov.evaluate("Array.from(document.querySelectorAll('.tam')).map(e => [e.textContent, e.dataset.en, e.getBoundingClientRect().top])")
        assert any("hidden key" in t[1] and t[2] < 300 for t in tam), tam   # sol üstteki görev yazısı, kendi yerinde
        # alttaki altyazı: "hemen altı" ekrandan taştığı için kutu yazının hemen üstüne alınır
        assert any("Lucia" in t[1] and 700 < t[2] < 900 for t in tam), tam
        assert all(t[0] and t[0] != t[1] for t in tam), tam
        assert ov.evaluate("getComputedStyle(document.querySelector('.kutu')).display") == "none", "alan kipinin yazısı da çıktı"
        assert bekle_ki(lambda: pg.locator("#satirlar .satir-oge").count() >= 2, 10)
        ov.screenshot(path=os.path.join(CIKTI, "arayuz_10_tum_ekran_ustu.png"))
        pg.click("#ana-dugme")
        assert bekle_ki(lambda: pg.text_content("#ana-durum") == "Kapalı", 15)
        assert bekle_ki(lambda: ov.locator(".tam").count() == 0), "durunca tüm ekran kutuları silinmeli"
        pg.click('#nav button[data-sayfa="alan"]')
        pg.click('#te-kip button[data-v="alan"]')
        assert bekle_ki(lambda: uyg.ayar["tam_ekran"]["acik"] is False and pg.is_visible("#alan-kartlari"))

        # ---------- çeviri ----------
        pg.click('#nav button[data-sayfa="ceviri"]')
        assert pg.locator("#motorlar .kart").count() == 6
        assert "Kullanılıyor" in pg.text_content("#motorlar .kart.secili-motor h3")
        assert "Hazır çeviri" in pg.text_content("#motorlar .kart.secili-motor h3")
        pg.fill("#c-metin", "Watch out for the truck!")
        pg.click("#c-dene")
        assert bekle_ki(lambda: "amyon" in (pg.text_content("#c-sonuc") or ""), 20), pg.text_content("#c-sonuc")
        # anahtarsız "Dene ve kullan" uyarır, motoru değiştirmez
        pg.locator("#motorlar .kart").nth(1).locator("button", has_text="Ayarla").click()
        pg.locator("#motorlar .kart").nth(1).locator("button", has_text="Dene ve kullan").click()
        assert bekle_ki(lambda: "anahtarı yapıştırın" in (pg.text_content("#bildirim") or ""))
        assert uyg.ayar["ceviri"]["motor"] == "cevrimdisi"
        # yerel model adresi yalnız bu bilgisayarı gösterebilir
        try:
            uyg.ceviri_ayarla({"llm_url": "http://ornek.com/v1/chat/completions"})
            raise AssertionError("dış adres kabul edildi")
        except ValueError:
            pass
        assert pg.is_checked("#c-yedek")
        pg.click("#c-yedek", force=True)
        assert bekle_ki(lambda: uyg.ayar["ceviri"]["yedek_motor"] == "")
        pg.click("#c-yedek", force=True)
        assert bekle_ki(lambda: uyg.ayar["ceviri"]["yedek_motor"] == "cevrimdisi")
        pg.screenshot(path=os.path.join(CIKTI, "arayuz_6_ceviri.png"))

        # ---------- seslendirme ve ayarlar sayfaları açılıyor ----------
        # ses motorlarını karşılaştır (deneme): gerçek motor yerine sahte durum; hiçbir ses çalınmaz
        import ses_deneme
        sd_durum = {"motor_var": True, "sunucu": "kapali", "hata": "", "calisan": None, "yuklu": None, "bos_bellek_gb": 12.0,
                    "ornek_metin": ses_deneme.ORNEK_METIN,
                    "sesler": [{"id": "sert_erkek", "ad": "Kaan", "cinsiyet": "erkek"}, {"id": "genc_kadin", "ad": "Defne", "cinsiyet": "kadin"}],
                    "modeller": [
                        {"id": "voxcpm2", "ad": "VoxCPM2", "aciklama": "a", "lisans": "l", "boyut_gb": 3.0, "kurulu": True, "indirme": None, "son": None},
                        {"id": "omnivoice", "ad": "OmniVoice", "aciklama": "a", "lisans": "l", "boyut_gb": 1.4, "kurulu": False,
                         "indirme": {"oran": 0.37, "hata": ""}, "son": None},
                        {"id": "chatterbox", "ad": "Chatterbox (çok dilli)", "aciklama": "a", "lisans": "l", "boyut_gb": 2.1, "kurulu": False,
                         "indirme": None, "son": None}]}
        sd_cagri = []

        def sd_dinle(model_id, metin, ses_id, seviye=1.0, abarti=None, oynatici=None):
            sd_cagri.append(("dinle", model_id, metin, ses_id, abarti))
            olcum = {"ses_sn": 5.12, "uretim_sn": 2.02, "yukleme_sn": 2.9, "ses": "Defne", "zaman": "10:00:00"}
            sd_durum["modeller"][0]["son"] = olcum
            sd_durum["yuklu"] = model_id
            return olcum

        ses_deneme.durum = lambda: sd_durum
        ses_deneme.dinle = sd_dinle
        ses_deneme.indir = lambda model_id: sd_cagri.append(("indir", model_id))
        pg.click('#nav button[data-sayfa="ses"]')
        assert bekle_ki(lambda: pg.text_content("#d-dogal-rozet") != "–")
        assert bekle_ki(lambda: pg.locator("#sd-modeller .sd-model").count() == 3)
        assert not pg.is_visible("#sd-yok") and pg.input_value("#sd-metin") == ses_deneme.ORNEK_METIN
        assert pg.input_value("#sd-ses") == "sert_erkek" and pg.locator("#sd-ses option").count() == 2
        satirlar = pg.locator("#sd-modeller .sd-model")
        assert satirlar.nth(0).locator("button").text_content() == "Dinle"
        assert "İndiriliyor %37" in satirlar.nth(1).text_content()
        assert satirlar.nth(2).locator("button").text_content() == "İndir (2,1 GB)"
        satirlar.nth(2).locator("button").click()
        assert bekle_ki(lambda: ("indir", "chatterbox") in sd_cagri)
        pg.fill("#sd-metin", "Sakin ol, kestirme bir yol biliyorum.")
        pg.select_option("#sd-ses", "genc_kadin")
        ayarla("#sd-abarti", "0.8")
        pg.locator("#sd-modeller .sd-model").nth(0).locator("button").click()
        assert bekle_ki(lambda: ("dinle", "voxcpm2", "Sakin ol, kestirme bir yol biliyorum.", "genc_kadin", 0.8) in sd_cagri), sd_cagri
        assert bekle_ki(lambda: "5,12 sn ses, 2,02 sn'de üretildi" in pg.locator("#sd-modeller .sd-model").nth(0).text_content())
        assert "Bellekte" in pg.locator("#sd-modeller .sd-model").nth(0).text_content()
        pg.screenshot(path=os.path.join(CIKTI, "arayuz_7_ses.png"))
        pg.click('#nav button[data-sayfa="ayarlar"]')
        assert pg.text_content("#a-surum") == veri.SURUM
        assert pg.is_checked("#a-tepsi")
        pg.click("#a-tepsi", force=True)
        assert bekle_ki(lambda: uyg.ayar["uygulama"]["tepsiye_kucult"] is False)
        pg.click("#a-rapor")
        assert bekle_ki(lambda: "Rapor hazır" in (pg.text_content("#a-rapor-durum") or ""), 20)
        pg.screenshot(path=os.path.join(CIKTI, "arayuz_8_ayarlar.png"))
        assert not hatalar, hatalar
        b.close()
    uyg.kapat()
    print("  ✓ arayüz: ilk kurulum, alan çizme, görünüm (renk/saydamlık/yazı tipi/kenar/konum), başlat-durdur, çeviri, ayarlar")


if __name__ == "__main__":
    test_gorunum_dogrulama()
    test_tepsi_menusu()
    test_arayuz()
