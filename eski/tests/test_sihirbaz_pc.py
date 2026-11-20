"""Sihirbaz — bilgisayar oyunu modu (Playwright): OBS ve projektör adımları atlanır, ekran seçilir,
altyazı ekran görüntüsünden otomatik bulunur, panel bilgisayar moduna göre açılır ve motor ekrandan okur.
Ekran yakalama ve katman penceresi sahtedir (gerçeği için: tests/elle_pc_katman.py)."""
import os
import time

import yardimci  # noqa: F401  (sys.path + CTA_VERI ayarı)
from yardimci import ornek_kare

TEMA = os.environ.get("CTA_TEMA", "light")  # CTA_TEMA=dark: koyu temada çalıştır, görüntüler cikti_koyu'ya
CIKTI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cikti" + ("_koyu" if TEMA == "dark" else ""))


def test_sihirbaz_pc(overlay_port=8796):
    from playwright.sync_api import sync_playwright

    import kaynak
    import pc_katman
    import uygulama
    import veri

    os.makedirs(CIKTI, exist_ok=True)
    for ad in os.listdir(veri.VERI_KLASORU):  # temiz kurulum
        if ad.endswith(".json"):
            os.remove(os.path.join(veri.VERI_KLASORU, ad))

    # --- sahte dünya: 2 ekran, oyun 2. ekranda ---
    oyun = ornek_kare()
    h, w = oyun.shape[:2]
    # ekranın sol üstünde ikinci bir İngilizce yazı (görev yazısı): ek çeviri alanı bununla denenir
    import cv2
    for kalinlik, renk in ((8, (0, 0, 0)), (2, (255, 255, 255))):
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
            time.sleep(0.05)
            return oyun.copy()

        def kapat(self):
            pass

    kaynak.EkranKaynagi = SahteEkran

    # Türkçe ses hoparlörden çalmasın; okurken oyunun sesini kısma gerçek uygulamalara dokunmasın (sahte "oyun")
    import ses_kisici
    import seslendirme
    calinan = []
    seslendirme.Seslendirici._winsound_cal = staticmethod(lambda wav: (calinan.append(len(wav)), time.sleep(0.4)))

    class SahteOturum:
        kimlik, ornek, pid, uygulama, sistem = "aygit|oyun.exe", "aygit|oyun.exe|4321", 4321, "oyun.exe", False

        def __init__(self):
            self.v, self.gecmis = 1.0, []

        def seviye(self):
            return self.v

        def ayarla(self, s):
            self.v = s
            self.gecmis.append(round(s, 3))

    sahte_oyun = SahteOturum()
    ses_kisici.destekleniyor = lambda: True
    ses_kisici.oturumlari_listele = lambda: [sahte_oyun]

    varsayilan = veri.ayar_yukle()
    varsayilan["goruntu"]["port"] = overlay_port
    veri.ayar_kaydet(varsayilan)
    uyg = uygulama.Uygulama()
    uyg.ayar["ocr"]["motor"] = yardimci.VARSAYILAN_OCR
    ws = uygulama.api_sunucusu(uyg, "b")
    adres = f"http://127.0.0.1:{ws.server_address[1]}"

    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1180, "height": 820}, color_scheme=TEMA)
        hatalar = []
        pg.on("pageerror", lambda e: hatalar.append(str(e)))
        pg.goto(f"{adres}/#b")
        pg.wait_for_timeout(500)

        def bekle_ki(kosul, sn=10):
            for _ in range(int(sn * 10)):
                if kosul():
                    return True
                pg.wait_for_timeout(100)
            return False

        def baslik():
            return pg.text_content(".adim.aktif h2:visible") if pg.is_visible(".adim.aktif h2:visible") else ""

        # 0: senaryo — bilgisayar oyunu artık seçilebilir
        assert "kapali" not in pg.get_attribute('[data-senaryo="pc"]', "class")
        pg.click('[data-senaryo="pc"]')
        assert bekle_ki(lambda: not pg.is_disabled("#ileri"))
        assert not pg.is_visible("#adim-listesi li:nth-child(2)"), "OBS adımı listede görünüyor"
        assert not pg.is_visible("#adim-listesi li:nth-child(5)"), "Oyun ekranı (projektör) adımı görünüyor"
        pg.click("#ileri")

        # 2: ekran (OBS adımı atlandı)
        assert bekle_ki(lambda: baslik() == "Oyun hangi ekranda?"), baslik()
        assert pg.text_content(".adim.aktif .ust-yazi") == "Adım 1"
        assert bekle_ki(lambda: pg.locator("#ekranlar .kaynak").count() == 2)
        assert pg.is_disabled("#ileri"), "ekran seçmeden ilerlenebiliyor"
        pg.click('#ekranlar .kaynak[data-no="2"]')
        assert bekle_ki(lambda: not pg.is_disabled("#ileri"))
        assert uyg.ayar["kaynak"] == {**uyg.ayar["kaynak"], "tip": "ekran", "ekran_no": 2}
        pg.screenshot(path=os.path.join(CIKTI, "pc_1_ekran.png"))
        pg.click("#ileri")

        # 3: altyazı yeri — ekrandan otomatik bul
        assert bekle_ki(lambda: pg.is_visible("#sonra-bul")), "Oynarken bul düğmesi yok"
        pg.click("#otomatik-bul")
        assert bekle_ki(lambda: "Lucia" in (pg.text_content("#okunan") or ""), 20), pg.text_content("#okuma-durum")
        pg.screenshot(path=os.path.join(CIKTI, "pc_2_alan.png"))
        pg.click("#ileri")

        # 4 (projektör) atlandı -> 5: çeviri (anahtarsız hazır)
        assert bekle_ki(lambda: baslik() == "Çeviriyi kim yapsın?"), baslik()
        pg.click("#geri")
        assert bekle_ki(lambda: baslik() == "Altyazının yerini bulalım"), "Geri, projektör adımına gitti"
        pg.click("#ileri")
        assert bekle_ki(lambda: not pg.is_disabled("#ileri"))
        pg.click("#ileri")

        # 6: Türkçe ses — okurken oyunun sesini kısma bilgisayar oyununda da var ve açık geliyor
        assert bekle_ki(lambda: baslik() == "Türkçe sesli de okuyayım mı?")
        pg.click('[data-dublaj="1"]')
        pg.wait_for_timeout(300)
        if seslendirme.turkce_sesler():
            assert pg.is_visible("label:has(#kis)") and pg.is_checked("#kis"), "okurken oyunun sesini kısma açık gelmeli"
        pg.click('[data-dublaj="0"]')
        pg.click("#ileri")

        # 7: hazır
        assert bekle_ki(lambda: "2. ekran" in (pg.text_content("#ozet") or ""))
        pg.screenshot(path=os.path.join(CIKTI, "pc_3_hazir.png"))
        pg.click("#bitir")
        assert bekle_ki(lambda: "/panel" in pg.url)

        # panel: bilgisayar modu
        assert bekle_ki(lambda: "Bilgisayar" in (pg.text_content("#g-kaynak") or ""))
        assert "pc" in pg.get_attribute("body", "class")
        assert bekle_ki(lambda: uyg.motor and uyg.motor.durum == "calisiyor", 20), uyg.motor and uyg.motor.hata
        assert okunan_ekran == [2], okunan_ekran
        assert bekle_ki(lambda: "arabaya" in (pg.text_content("#akis") or "").lower(), 20), pg.text_content("#akis")
        assert bekle_ki(lambda: "okuma:" in (pg.text_content("#hiz-bilgi") or ""))
        pg.screenshot(path=os.path.join(CIKTI, "pc_4_panel.png"))
        # Görünüm bilgisayar oyununda da aynı: bütün kutu seçenekleri var (katman penceresi yarı saydamı gösterebiliyor,
        # tests/elle_katman_gorunum.py ölçer), yazının yeri seçilebiliyor
        pg.click('#nav [data-bolum="gorunum"]')
        assert bekle_ki(lambda: pg.is_visible('#g-kutu button[data-deger="koyu"]'))
        assert pg.is_visible('#g-kutu button[data-deger="yari"]'), "bilgisayar modunda yarı saydam kutu seçeneği görünmüyor"
        pg.click('#g-konum button[data-deger="ust"]')
        assert bekle_ki(lambda: uyg.ayar["goruntu"]["konum"] == "serbest" and uyg.ayar["goruntu"]["konum_y"] == 0.1)
        pg.screenshot(path=os.path.join(CIKTI, "pc_4b_gorunum.png"))
        pg.click('#g-konum button[data-deger="orijinal"]')
        assert bekle_ki(lambda: uyg.ayar["goruntu"]["konum"] == "orijinal")
        pg.click('#nav [data-bolum="ayarlar"]')
        assert pg.is_visible("#a-ekran") and not pg.is_visible("#projektor")
        pg.screenshot(path=os.path.join(CIKTI, "pc_5_kaynak.png"))

        # --- ek çeviri alanı: görüntüyü al, kutu çiz, adını değiştir, dene; motor iki alanla yeniden başlar
        assert pg.is_disabled("#alan-yeni"), "görüntü alınmadan alan çizilememeli"
        pg.click("#alan-goruntu")
        assert bekle_ki(lambda: pg.get_attribute("#alan-resim", "src") and not pg.is_disabled("#alan-yeni"))
        pg.wait_for_timeout(300)
        pg.click("#alan-yeni")
        pg.locator("#alan-tuval").scroll_into_view_if_needed()
        kutu = pg.locator("#alan-tuval").bounding_box()
        pg.mouse.move(kutu["x"] + kutu["width"] * 0.04, kutu["y"] + kutu["height"] * 0.07)
        pg.mouse.down()
        pg.mouse.move(kutu["x"] + kutu["width"] * 0.30, kutu["y"] + kutu["height"] * 0.12, steps=4)
        pg.mouse.move(kutu["x"] + kutu["width"] * 0.52, kutu["y"] + kutu["height"] * 0.19, steps=4)
        pg.mouse.up()
        assert bekle_ki(lambda: len(uyg.ayar.get("ek_bolgeler") or []) == 1), uyg.ayar.get("ek_bolgeler")
        alan = uyg.ayar["ek_bolgeler"][0]
        assert abs(alan["x"] - 0.04) < 0.02 and abs(alan["y"] - 0.07) < 0.02 and abs(alan["w"] - 0.48) < 0.03, alan
        assert pg.locator("#alan-tuval .alan-kutu").count() == 2, "altyazı + yeni alan kutusu çizilmeli"
        pg.fill("#alan-liste input[type=text]", "Görev yazısı")
        pg.keyboard.press("Tab")
        assert bekle_ki(lambda: uyg.ayar["ek_bolgeler"][0]["ad"] == "Görev yazısı")
        pg.click("#alan-liste button:has-text('Dene')")
        assert bekle_ki(lambda: "hidden key" in (pg.text_content("#alan-liste .okunan") or "")), pg.text_content("#alan-liste .okunan")
        assert bekle_ki(lambda: uyg.motor and uyg.motor.durum == "calisiyor", 20), "motor iki alanla yeniden başlamadı"
        assert bekle_ki(lambda: any(g.get("alan") == 1 for g in uyg.motor.gecmis), 20), list(uyg.motor.gecmis)
        ek = next(g for g in uyg.motor.gecmis if g.get("alan") == 1)
        assert "anahtar" in ek["tr"].lower(), ek
        assert uyg.yayinci.son_satirlar.get(1, {}).get("alan") == 1 and 0 in uyg.yayinci.son_satirlar, uyg.yayinci.son_satirlar
        pg.locator("#alan-kart").scroll_into_view_if_needed()
        pg.screenshot(path=os.path.join(CIKTI, "pc_6_alanlar.png"))

        # --- ana ekran: mod seçimi (yalnızca altyazı / altyazı + ses / yalnızca ses)
        pg.click('#nav [data-bolum="ana"]')
        assert bekle_ki(lambda: "Görev yazısı" in (pg.text_content("#akis") or ""), 10), "ek alanın satırı canlı listede yok"
        assert "secili" in pg.get_attribute('#mod [data-mod="altyazi"]', "class")
        if seslendirme.turkce_sesler():
            pg.click('#mod [data-mod="ses"]')
            assert bekle_ki(lambda: uyg.ayar["dublaj"]["acik"] and uyg.ayar["goruntu"]["altyazi_goster"] is False)
            assert "secili" in pg.get_attribute('#mod [data-mod="ses"]', "class")
            pg.click('#mod [data-mod="ikisi"]')
            assert bekle_ki(lambda: uyg.ayar["dublaj"]["acik"] and uyg.ayar["goruntu"]["altyazi_goster"] is True)
            pg.screenshot(path=os.path.join(CIKTI, "pc_7_mod.png"))
            # Türkçe ses okunurken "oyun"un sesi kısılmalı, okuma bitince eski seviyesine dönmeli
            assert bekle_ki(lambda: calinan and sahte_oyun.gecmis and min(sahte_oyun.gecmis) < 0.25, 30), \
                f"okurken oyunun sesi kısılmadı: okunan {len(calinan)}, seviyeler {sahte_oyun.gecmis}"
            assert bekle_ki(lambda: sahte_oyun.v == 1.0, 10), f"oyunun sesi geri açılmadı: {sahte_oyun.v}"
            # panelden kapatılınca oyunun sesine dokunulmaz
            pg.click('#nav [data-bolum="ses"]')
            assert bekle_ki(lambda: pg.is_visible("label:has(#d-kis)") and pg.is_checked("#d-kis") and pg.is_visible("#d-kis-duzey")), "panelde ses kısma ayarı görünmüyor"
            pg.locator("label:has(#d-kis)").click()
            assert bekle_ki(lambda: uyg.ayar["dublaj"]["okurken_kis"] is False)
            assert not pg.is_visible("#d-kis-duzey"), "kısma kapalıyken düzey seçimi görünmemeli"
            pg.screenshot(path=os.path.join(CIKTI, "pc_8_ses.png"), full_page=True)
            assert bekle_ki(lambda: uyg.motor and uyg.motor.durum == "calisiyor" and uyg.motor.seslendirici
                            and uyg.motor.seslendirici.kisici is None, 20), "kısma kapatılınca kısıcı kalkmalı"
            pg.click('#nav [data-bolum="ana"]')
        pg.click('#mod [data-mod="altyazi"]')
        assert bekle_ki(lambda: not uyg.ayar["dublaj"]["acik"] and uyg.ayar["goruntu"]["altyazi_goster"] is True)
        assert bekle_ki(lambda: uyg.motor and uyg.motor.durum == "calisiyor", 20)
        assert bekle_ki(lambda: "Çalışıyor" in (pg.text_content("#durum-yazi") or ""), 10)  # panel de güncellensin
        pg.click('#nav [data-bolum="ana"]')
        pg.click("#guc")
        assert bekle_ki(lambda: uyg.motor.durum == "durdu")
        assert not hatalar, hatalar
        b.close()
    ws.shutdown()
    print("  ✓ test_sihirbaz_pc")


if __name__ == "__main__":
    test_sihirbaz_pc()
