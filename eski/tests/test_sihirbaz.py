"""Uygulama arayüzü uçtan uca (Playwright + sahte OBS): sihirbazın tüm adımları
(şifresiz otomatik OBS bağlantısı, capture card tahmini, altyazıyı otomatik bulma,
Türkçe katman + projektör, çeviri, Türkçe ses), ardından kontrol paneli.
Ekran görüntüleri tests/cikti/ klasörüne yazılır. Gerçek ayar klasörüne yazmaz (CTA_VERI),
hoparlörden ses çalmaz."""
import json
import os
import time

import yardimci  # noqa: F401  (sys.path + CTA_VERI ayarı)
from yardimci import ornek_kare

import sahte_obs

TEMA = os.environ.get("CTA_TEMA", "light")  # CTA_TEMA=dark: koyu temada çalıştır, görüntüler cikti_koyu'ya
CIKTI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cikti" + ("_koyu" if TEMA == "dark" else ""))


def test_sihirbaz(obs_port=4462, overlay_port=8797):
    from playwright.sync_api import sync_playwright

    import ceviri
    import obs_yardim
    import seslendirme
    import uygulama
    import veri

    os.makedirs(CIKTI, exist_ok=True)
    for ad in os.listdir(veri.VERI_KLASORU):  # temiz kurulum
        if ad.endswith(".json") or ad == "overlay_surumu.txt":
            os.remove(os.path.join(veri.VERI_KLASORU, ad))
    kare = ornek_kare()
    srv, d = sahte_obs.baslat(lambda: kare, obs_port)

    # --- sahte dünya ---
    class Sahte:  # ağsız çeviri; yanlış anahtar 401 gibi davranır
        def __init__(self, anahtar):
            self.anahtar = anahtar

        def cevir(self, m, b):
            if self.anahtar != "dogru-anahtar":
                raise ceviri.CeviriHatasi("Google Gemini anahtarı geçersiz. Ayarlar → Çeviri'den anahtarı kontrol edin.")
            time.sleep(0.05)
            return "Lucia, bin arabaya. Aynasızlar tam arkamızda!" if "Lucia" in m else "[TR] " + m

    gercek_tek_motor = ceviri.tek_motor  # anahtarsız çevrimdışı motor gerçek modelle çalışsın
    ceviri.tek_motor = lambda ad, c, s: gercek_tek_motor(ad, c, s) if ad == "cevrimdisi" else Sahte(c.get("anahtarlar", {}).get(ad, ""))
    ws_durum = {"etkin": False}  # önce kullanıcı WebSocket'i açmamış gibi
    obs_yardim.obs_kurulu_mu = lambda: True
    obs_yardim.obs_acik_mi = lambda: True
    obs_yardim.websocket_ayari = lambda *a: {"etkin": ws_durum["etkin"], "port": obs_port,
                                             "sifre": sahte_obs.SIFRE, "sifre_gerekli": True}
    calinan = []
    seslendirme.Seslendirici._winsound_cal = staticmethod(lambda wav: (calinan.append(len(wav)), time.sleep(0.3)))

    varsayilan = veri.ayar_yukle()
    varsayilan["goruntu"]["port"] = overlay_port
    veri.ayar_kaydet(varsayilan)
    uyg = uygulama.Uygulama()
    uyg.ayar["ocr"]["motor"] = yardimci.VARSAYILAN_OCR
    belirtec = "test-belirtec"
    ws = uygulama.api_sunucusu(uyg, belirtec)
    adres = f"http://127.0.0.1:{ws.server_address[1]}"

    import urllib.request
    try:  # belirteçsiz istek reddedilmeli
        urllib.request.urlopen(urllib.request.Request(adres + "/api/durum", data=b"{}", method="POST"))
        raise AssertionError("belirteçsiz API isteği kabul edildi")
    except urllib.error.HTTPError as e:
        assert e.code == 403

    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1180, "height": 820}, color_scheme=TEMA)
        hatalar = []
        pg.on("pageerror", lambda e: hatalar.append(str(e)))
        pg.goto(f"{adres}/#{belirtec}")
        pg.wait_for_timeout(500)

        def foto(ad, tam=False):
            pg.screenshot(path=os.path.join(CIKTI, f"{ad}.png"), full_page=tam)

        def bekle_ki(kosul, sn=8):
            for _ in range(int(sn * 10)):
                if kosul():
                    return True
                pg.wait_for_timeout(100)
            return False

        # 0: senaryo
        assert pg.is_disabled("#ileri"), "senaryo seçmeden ilerlenebiliyor"
        assert "kapali" not in pg.get_attribute("[data-senaryo=pc]", "class")  # bilgisayar modu: test_sihirbaz_pc
        pg.click("[data-senaryo=konsol_obs]")
        foto("01_baslangic")
        pg.click("#ileri")

        # 1: OBS — WebSocket kapalıyken yardım çıkmalı, açılınca kendiliğinden bağlanmalı
        assert bekle_ki(lambda: pg.is_visible("#ws-yardim")), "WebSocket yardımı görünmedi"
        assert pg.is_disabled("#ileri")
        foto("02_obs_bekliyor")
        ws_durum["etkin"] = True  # kullanıcı OBS'te kutuyu işaretledi
        assert bekle_ki(lambda: not pg.is_disabled("#ileri")), "şifresiz otomatik bağlanmadı"
        assert "ok" in pg.get_attribute("#k-bag", "class")
        foto("03_obs_baglandi")
        pg.click("#ileri")

        # 2: capture card kendiliğinden seçilmeli
        assert bekle_ki(lambda: pg.locator(".kaynak.secili").count() == 1)
        assert pg.inner_text(".kaynak.secili").startswith("Capture Card"), "capture card önerilmedi"
        assert pg.locator(".kaynak").count() == 2, "ses kaynağı filtrelenmeli"
        foto("04_kaynak")
        pg.click("#ileri")

        # 3: altyazıyı otomatik bul
        pg.wait_for_timeout(800)
        pg.click("#otomatik-bul")
        assert bekle_ki(lambda: "Lucia" in (pg.inner_text("#okunan") or ""), 15), "otomatik bulma okumadı"
        assert "buldum" in pg.inner_text("#okuma-durum")
        foto("05_alan")
        pg.click("#ileri")

        # 4: katman eklenmeli, 2. monitöre projektör
        assert bekle_ki(lambda: pg.locator(".monitor").count() == 2)
        assert [o["sourceName"] for o in d.ogeler][-1] == "Türkçe Altyazı", "Türkçe katman eklenmedi"
        assert "Atla" in pg.inner_text("#ileri")
        pg.locator(".monitor").nth(1).click(); pg.wait_for_timeout(500)
        assert d.projektorler and d.projektorler[-1]["monitorIndex"] == 1
        foto("06_oyun_ekrani")
        pg.click("#ileri")

        # 5: çeviri — anahtarsız "Hazır çeviri" seçili ve hazır olmalı
        pg.wait_for_timeout(300)
        assert "secili" in pg.get_attribute(".motor[data-id=cevrimdisi]", "class")
        assert not pg.is_disabled("#ileri"), "anahtarsız çeviriyle ilerlenemiyor"
        assert not pg.is_visible("[data-anahtar]"), "anahtarsız motorda anahtar kutusu görünmemeli"
        pg.click("[data-dene]")
        if not bekle_ki(lambda: "arabaya" in (pg.inner_text("[data-sonuc] span") or "").lower(), 20):  # OCR "cops"u bilerek bozuk okuyabilir
            raise AssertionError("çevrimdışı model çevirmedi: " + pg.inner_text("[data-mesaj]") + " | " + pg.inner_text("[data-sonuc]"))
        print("  çevrimdışı:", pg.inner_text("[data-sonuc]").replace("\n", " -> "))
        foto("07a_ceviri_hazir", tam=True)
        pg.click(".motor[data-id=gemini]"); pg.wait_for_timeout(300)
        assert pg.is_visible("[data-anahtar]")
        pg.fill("[data-anahtar]", "yanlis"); pg.click("[data-dene]"); pg.wait_for_timeout(500)
        assert "geçersiz" in pg.inner_text("[data-mesaj]")
        assert uyg.ayar["ceviri"]["motor"] == "cevrimdisi" and not uyg.ayar["ceviri"].get("anahtarlar", {}).get("gemini"), \
            "başarısız deneme çalışan çeviriyi ve anahtarı değiştirmemeli"
        assert pg.is_disabled("#ileri"), "çalışmayan motorla ilerlenebiliyor"
        pg.fill("[data-anahtar]", "dogru-anahtar"); pg.click("[data-dene]"); pg.wait_for_timeout(600)
        assert "Aynasızlar" in pg.inner_text("[data-sonuc]")
        assert uyg.ayar["ceviri"]["motor"] == "gemini" and uyg.ayar["ceviri"]["anahtarlar"]["gemini"] == "dogru-anahtar"
        foto("07_ceviri", tam=True)
        pg.click("#ileri")

        # 6: Türkçe ses — "Sadece altyazı" hazır seçili, ses kısma varsayılan kapalı
        pg.wait_for_timeout(800)
        assert "secili" in pg.get_attribute("[data-dublaj='0']", "class"), "Sadece altyazı seçili gelmedi"
        assert not pg.is_disabled("#ileri")
        pg.click("[data-dublaj='1']"); pg.wait_for_timeout(400)
        turkce_var = bool(seslendirme.turkce_sesler())
        if turkce_var:
            assert pg.is_visible("#ses-var")
            assert pg.is_visible("label:has(#kis)") and pg.is_checked("#kis"), "okurken oyunun sesini kısma varsayılan açık olmalı"
            pg.click("#dinle"); pg.wait_for_timeout(1200)
            assert calinan, "Dinle ses üretmedi"
        else:
            assert pg.is_visible("#ses-yok")
        foto("08_ses")
        pg.click("#ileri"); pg.wait_for_timeout(300)
        foto("09_hazir")
        assert "Açık" in pg.inner_text("#ozet")

        # 7: Başlat -> panel, motor çalışıyor
        pg.click("#bitir")
        assert bekle_ki(lambda: "/panel" in pg.url)
        if not bekle_ki(lambda: "Aynasızlar" in pg.inner_text("#akis"), 15):
            foto("HATA_panel")
            raise AssertionError("panelde canlı çeviri görünmedi: " + str(hatalar) + " " + pg.text_content("#durum-aciklama")
                                 + " | " + json.dumps(uyg.motor_ozet(None), ensure_ascii=False)[:400])
        assert "Çalışıyor" in pg.text_content("#durum-yazi")
        # Program güncellenmiş olabilir: OBS'te açık kalan eski altyazı sayfası bir kez yeniletilir
        assert d.dugmeler == [("Türkçe Altyazı", "refreshnocache")], d.dugmeler
        pg.wait_for_timeout(1500)
        foto("10_panel_calisiyor")
        if turkce_var:
            assert len(calinan) >= 2, "çeviri sesli okunmadı"
            assert bekle_ki(lambda: d.ses_gecmisi[-2:] == [-14.0, 0.0], 5), f"oyun sesi kısılıp açılmadı: {d.ses_gecmisi}"
        pg.click("nav button[data-bolum=gorunum]"); pg.wait_for_timeout(300)
        pg.locator("#boyut").fill("60"); pg.wait_for_timeout(600)
        foto("11_gorunum")
        pg.click("nav button[data-bolum=ses]"); pg.wait_for_timeout(600)
        if turkce_var:
            assert pg.is_visible("#d-karakter-kart") and pg.is_checked("#d-karakter"), "karakter sesleri kartı/varsayılanı"
            assert pg.locator("#d-profiller button").count() == 7, "ses profilleri listelenmedi"
            pg.locator("#d-profiller button").nth(4).click(); pg.wait_for_timeout(1200)  # Kadın 1'i dinle
            n = len(calinan)
            assert n >= 3, "profil dinleme ses üretmedi"
        foto("12_ses", True)
        pg.click("nav button[data-bolum=ayarlar]"); pg.wait_for_timeout(300)
        pg.click("#projektor"); pg.wait_for_timeout(500)
        assert len(d.projektorler) == 2, "panelden oyun ekranı açılmadı"
        foto("13_ayarlar")
        pg.click("nav button[data-bolum=ana]"); pg.click("#guc"); pg.wait_for_timeout(1500)
        assert "Kapalı" in pg.text_content("#durum-yazi")
        b.close()
    assert not hatalar, f"JS hataları: {hatalar}"
    with open(veri.ayar_yolu(), encoding="utf-8") as f:
        a = json.load(f)
    assert a["kurulum_tamam"] and a["obs"]["kaynak_adi"] == "Capture Card" and a["kaynak"]["tip"] == "obs"
    assert a["ceviri"]["anahtarlar"]["gemini"] == "dogru-anahtar"
    assert a["goruntu"]["yazi_boyutu"] == 60 and a["obs"]["projektor_monitor"] == 1
    assert a["dublaj"]["acik"] is True and a["senaryo"] == "konsol_obs"
    assert d.ses.get("Capture Card", 0.0) == 0.0, "oyun sesi kısık kaldı"
    assert len(d.dugmeler) == 1, f"OBS sayfası sürüm başına bir kez yenilenmeli: {d.dugmeler}"
    uyg.kapat(); ws.shutdown(); srv.shutdown()
    print(f"  ✓ test_sihirbaz (ekran görüntüleri: {CIKTI})")


if __name__ == "__main__":
    test_sihirbaz()
