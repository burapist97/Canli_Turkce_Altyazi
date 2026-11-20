"""Konsol (PlayStation / Xbox) + OBS kurulumu yeni arayüzde (2.7.2) — Playwright + sahte OBS:
görüntü kaynağı "Konsol + OBS" seçilir -> OBS'e şifre sormadan bağlanılır (WebSocket kapalıyken yardım çıkar) ->
capture card kendiliğinden seçilir -> altyazı bulunur -> Türkçe katman OBS'e eklenir, projektör açılır ->
kurulum biter -> Başlat: görüntü OBS'ten okunur, Türkçesi OBS'e eklenen sayfada görünür.
Ayrıca: pencere kapatılınca program gerçekten kapanır, küçültülünce simgeye iner (tepsi.py).
Gerçek OBS ile deneme: tests/elle_gercek_obs.py (elle)."""
import json
import os
import time

import yardimci  # noqa: F401
from yardimci import ornek_kare

import sahte_obs

CIKTI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cikti")


def test_kapat_kucult():
    """Kapatma (X): her şey durur ve pencere kapanır. Küçültme (–): simge varsa ve ayar açıksa pencere gizlenir."""
    import tepsi

    olaylar = []

    class Uyg:
        ayar = {"uygulama": {"tepsiye_kucult": True, "tepsi_bilgisi_gosterildi": True}}

        def kapat(self):
            olaylar.append("kapat")

    class Pencere:
        def hide(self):
            olaylar.append("gizle")

    class Simge:
        Visible = True

        def Dispose(self):
            olaylar.append("simge-kalkti")

    t = tepsi.Tepsi(Uyg(), Pencere())
    t.kucultuldu()  # simge kurulmamışsa pencere gizlenmez (yoksa geri getirecek bir yer kalmaz)
    time.sleep(0.1)
    assert olaylar == [], olaylar
    t.ikon = Simge()
    t.kucultuldu()
    for _ in range(20):
        if olaylar:
            break
        time.sleep(0.02)
    assert olaylar == ["gizle"], olaylar
    Uyg.ayar["uygulama"]["tepsiye_kucult"] = False
    t.kucultuldu()
    time.sleep(0.1)
    assert olaylar == ["gizle"], "ayar kapalıyken küçültünce gizlenmemeli"
    assert t.kapatiliyor() is True, "kapatma düğmesi pencereyi kapatmalı"
    assert olaylar == ["gizle", "kapat", "simge-kalkti"] and t.ikon is None and t.cikiliyor, olaylar
    print("  ✓ kapat / küçült: kapatınca altyazı durup program kapanıyor, küçültünce simgeye iniyor")


def test_arayuz_obs(obs_port=4463, overlay_port=8794):
    from playwright.sync_api import sync_playwright

    import obs_yardim
    import uygulama
    import veri

    os.makedirs(CIKTI, exist_ok=True)
    for ad in os.listdir(veri.VERI_KLASORU):  # temiz kurulum
        if ad.endswith(".json") or ad == "overlay_surumu.txt":
            os.remove(os.path.join(veri.VERI_KLASORU, ad))
    kare = ornek_kare()
    srv, d = sahte_obs.baslat(lambda: kare, obs_port)
    ws_durum = {"etkin": False}  # önce kullanıcı WebSocket'i açmamış gibi
    asil = (obs_yardim.obs_kurulu_mu, obs_yardim.obs_acik_mi, obs_yardim.websocket_ayari)
    obs_yardim.obs_kurulu_mu = lambda: True
    obs_yardim.obs_acik_mi = lambda: True
    obs_yardim.websocket_ayari = lambda *a: {"etkin": ws_durum["etkin"], "port": obs_port,
                                             "sifre": sahte_obs.SIFRE, "sifre_gerekli": True}
    varsayilan = veri.ayar_yukle()
    varsayilan["goruntu"]["port"] = overlay_port
    veri.ayar_kaydet(varsayilan)
    uyg = uygulama.Uygulama()
    uyg.ayar["ocr"]["motor"] = yardimci.VARSAYILAN_OCR
    assert uyg.ayar["senaryo"] == "pc" and uyg.ayar["kaynak"]["tip"] == "ekran", "yeni kurulum bilgisayar ekranıyla başlar"
    ws = uygulama.api_sunucusu(uyg, "b")
    adres = f"http://127.0.0.1:{ws.server_address[1]}"
    try:
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page(viewport={"width": 1240, "height": 900})
            ov = b.new_page(viewport={"width": 1920, "height": 1080})  # OBS'teki "Türkçe Altyazı" tarayıcı kaynağı
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

            assert bekle_ki(lambda: pg.evaluate("document.body.dataset.hazir") == "1"), hatalar
            assert pg.is_visible("#s-alan") and pg.is_visible("#ekran-karti") and not pg.is_visible("#obs-kartlari")

            # ---------- kaynak: Konsol + OBS ----------
            pg.click('#kt-tur button[data-v="konsol_obs"]')
            assert bekle_ki(lambda: uyg.ayar["senaryo"] == "konsol_obs" and uyg.ayar["kaynak"]["tip"] == "obs")
            assert bekle_ki(lambda: pg.is_visible("#obs-kartlari") and not pg.is_visible("#ekran-karti"))
            assert not pg.is_visible("#te-kart"), "tüm ekran kipi OBS'te sunulmamalı"
            # WebSocket kapalı: ne yapılacağı söylenir, bağlanılmaz
            assert bekle_ki(lambda: pg.is_visible("#obs-ws-yardim")), pg.text_content("#obs-durum")
            assert pg.text_content("#obs-rozet") == "WebSocket kapalı"
            pg.click("#al-kaydet")  # bağlanmadan kurulum bitirilemez
            assert bekle_ki(lambda: "OBS'e bağlanılmalı" in (pg.text_content("#bildirim") or ""))
            assert not uyg.ayar.get("kurulum_tamam")
            pg.screenshot(path=os.path.join(CIKTI, "obs_1_websocket_kapali.png"))
            ws_durum["etkin"] = True  # kullanıcı OBS'te kutuyu işaretledi: şifre sormadan kendiliğinden bağlanır
            assert bekle_ki(lambda: pg.text_content("#obs-rozet") == "Bağlandı", 15), pg.text_content("#obs-durum")
            assert not pg.is_visible("#obs-ws-yardim")
            # capture card kendiliğinden seçilir (ses kaynakları listelenmez), görüntüsü gelir
            assert bekle_ki(lambda: pg.locator("#obs-kaynaklar .ekran-oge").count() == 2), pg.text_content("#obs-kaynaklar")
            assert bekle_ki(lambda: pg.locator("#obs-kaynaklar .ekran-oge.secili").count() == 1)
            assert pg.get_attribute("#obs-kaynaklar .ekran-oge.secili", "data-ad") == "Capture Card"
            assert uyg.ayar["obs"]["kaynak_adi"] == "Capture Card"
            assert bekle_ki(lambda: (pg.get_attribute("#cizim-resim", "src") or "").startswith("data:image"))
            assert pg.locator("#obs-monitorler button").count() == 2
            # altyazıyı bul
            pg.click("#al-bul")
            assert bekle_ki(lambda: "Altyazı bulundu" in (pg.text_content("#al-sonuc") or ""), 20), pg.text_content("#al-sonuc")
            # projektör: Türkçe katman da eklenir
            pg.locator("#obs-monitorler button").nth(1).click()
            assert bekle_ki(lambda: d.projektorler and d.projektorler[-1]["monitorIndex"] == 1)
            assert [o["sourceName"] for o in d.ogeler][-1] == "Türkçe Altyazı", "Türkçe katman OBS'te en üste eklenmedi"
            assert d.ayarlar["Türkçe Altyazı"]["url"] == f"http://127.0.0.1:{overlay_port}"
            assert "eklendi" in pg.text_content("#obs-katman-durum")
            pg.screenshot(path=os.path.join(CIKTI, "obs_2_baglandi.png"), full_page=True)
            pg.click("#al-kaydet")
            assert bekle_ki(lambda: uyg.ayar.get("kurulum_tamam") and pg.is_visible("#s-ana")), "kurulum bitmedi"
            kayitli = json.load(open(veri.ayar_yolu(), encoding="utf-8"))
            assert kayitli["senaryo"] == "konsol_obs" and kayitli["obs"]["kaynak_adi"] == "Capture Card" \
                and kayitli["obs"]["port"] == obs_port and kayitli["kaynak"]["tip"] == "obs", kayitli["obs"]
            assert "sifre" not in uyg.durum(None)["obs"], "OBS şifresi arayüze gönderilmemeli"

            # ---------- Başlat: görüntü OBS'ten okunur, Türkçesi OBS'e eklenen sayfada görünür ----------
            assert "OBS" in pg.text_content("#ana-aciklama")
            pg.click("#ana-dugme")
            assert bekle_ki(lambda: pg.text_content("#ana-durum") == "Çalışıyor", 60), pg.text_content("#ana-durum") + pg.text_content("#u-hata")
            assert bekle_ki(lambda: "Lucia" in (ov.text_content(".kutu .tr") or ""), 30), "çeviri OBS sayfasına gelmedi"
            assert bekle_ki(lambda: pg.locator("#satirlar .satir-oge").count() >= 1)
            assert "GetSourceScreenshot" in d.istekler
            assert uyg.katman is None  # OBS kipinde oyun üstü pencere açılmaz
            pg.screenshot(path=os.path.join(CIKTI, "obs_3_calisiyor.png"))
            pg.click("#ana-dugme")
            assert bekle_ki(lambda: pg.text_content("#ana-durum") == "Kapalı", 15)

            # ---------- yeniden açılınca ayar korunur; bilgisayar ekranına dönülebilir ----------
            uyg2 = uygulama.Uygulama.__new__(uygulama.Uygulama)
            ayar2 = veri.ayar_yukle()
            assert ayar2["senaryo"] == "konsol_obs" and ayar2["kaynak"]["tip"] == "obs"
            del uyg2
            pg.click('#nav button[data-sayfa="alan"]')
            assert bekle_ki(lambda: pg.is_visible("#obs-kartlari"))
            assert bekle_ki(lambda: pg.text_content("#obs-rozet") == "Bağlandı", 10)
            assert not hatalar, hatalar
            b.close()
    finally:
        obs_yardim.obs_kurulu_mu, obs_yardim.obs_acik_mi, obs_yardim.websocket_ayari = asil
        uyg.kapat()
        srv.shutdown()
    print("  ✓ konsol + OBS: WebSocket yardımı, şifresiz bağlantı, capture card, Türkçe katman, projektör, OBS'ten okuma")


if __name__ == "__main__":
    test_kapat_kucult()
    test_arayuz_obs()
