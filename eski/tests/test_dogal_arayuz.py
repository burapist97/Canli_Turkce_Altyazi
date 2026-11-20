"""Doğal seslerin arayüzü (Playwright): kontrol panelinin Türkçe ses sayfası ve sihirbazın Türkçe ses adımı.

Gerçek model yüklenmez: ses sunucusu süreci yerine sahte hafif sunucu (test_dogal_ses._SahteHafif) kullanılır ve
"hoparlör" sessizdir. Bakılanlar:
- doğal sesler programla geldiği için kart açık gelir; ses sunucusu çalışmıyorken rozet "Beklemede" der,
- bir sese tıklamak ses sunucusunu açar ve hazır olunca çalar (düğmeler kapalıyken de tıklanır),
- anahtar kapatılınca sunucu kapatılır (bellek boşalsın), açılınca yeniden başlar,
- Doğal Ses Paketi (güçlü motor) de kuruluysa "Ses modeli" seçimi görünür; seçim ayara yazılır, öteki motorun
  sunucusu kapatılır, ses listesi yeni motorun sesleri olur,
- sihirbazda "Dinle" doğal sesle okur; doğal ses açılamazsa nedeni yazılır ve Windows sesiyle okunur.
"""
import os
import tempfile
import threading
import time
from http.server import ThreadingHTTPServer

import yardimci  # noqa: F401  (sys.path + CTA_VERI ayarı)
from test_dogal_ses import _hafif_paket, _paket, _SahteHafif, _SahteSurec

TEMA = os.environ.get("CTA_TEMA", "light")
CIKTI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cikti" + ("_koyu" if TEMA == "dark" else ""))


def test_dogal_arayuz(overlay_port=8793):
    from playwright.sync_api import sync_playwright

    import dogal_ses
    import seslendirme
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

    sunucu = ThreadingHTTPServer(("127.0.0.1", 0), _SahteHafif)
    threading.Thread(target=sunucu.serve_forever, daemon=True).start()
    hafif_klasor, guclu_klasor = tempfile.mkdtemp(), tempfile.mkdtemp()
    _hafif_paket(hafif_klasor)
    _paket(guclu_klasor)
    calinan, windows_sesi, surecler = [], [], []
    guclu_kurulu = [False]
    bos_bellek = [16.0]

    class _Sessiz:  # hoparlör yerine
        def __init__(self, ornek_hizi=0):
            self.ornek_hizi = ornek_hizi

        def cal(self, x):
            calinan.append((self.ornek_hizi, len(x)))

        def bitir(self):
            pass

    class _Surec(_SahteSurec):  # kapatılınca sahte sunucu da "hazır değil" olur
        def __init__(self, motor):
            super().__init__()
            self.motor = motor

        def terminate(self):
            super().terminate()
            if self.motor == "hafif":
                _SahteHafif.durum = "loading"

        kill = terminate

    def sahte_baslat(self):  # ses sunucusu süreci yerine: hafif motor ~1 sn sonra "hazır" der
        self.surec = _Surec(self.motor)
        surecler.append(self.surec)
        if self.motor == "hafif":
            surec = self.surec
            threading.Timer(1.0, lambda: surec.kapandi or setattr(_SahteHafif, "durum", "ok")).start()

    eski = {ad: getattr(dogal_ses, ad) for ad in ("PORT", "hafif_kurulumu", "kurulum_klasoru", "bos_bellek_gb",
                                                 "_HoparlorOynatici", "_paylasilan", "_tercih")}
    eski_sinif = dogal_ses.DogalSes._sureci_baslat, dogal_ses.DogalSes._kapi_dolu
    _SahteHafif.durum, _SahteHafif.hata, _SahteHafif.istekler = "loading", "", []
    try:
        dogal_ses.PORT = sunucu.server_port
        dogal_ses.hafif_kurulumu = lambda: {"kok": hafif_klasor, "komut": ["yok"], "model": hafif_klasor,
                                            "sesler": os.path.join(hafif_klasor, "sesler")}
        dogal_ses.kurulum_klasoru = lambda: guclu_klasor if guclu_kurulu[0] else None
        dogal_ses.bos_bellek_gb = lambda: bos_bellek[0]
        dogal_ses._HoparlorOynatici = _Sessiz
        dogal_ses._paylasilan = None
        dogal_ses.DogalSes._sureci_baslat = sahte_baslat
        dogal_ses.DogalSes._kapi_dolu = lambda self: False  # kapıda (sürecin yerine geçen) sahte sunucu hep var
        seslendirme.Seslendirici._winsound_cal = staticmethod(lambda wav: windows_sesi.append(len(wav)))

        uyg = uygulama.Uygulama()
        assert not uyg.overlay_hatasi, uyg.overlay_hatasi
        ws = uygulama.api_sunucusu(uyg, "b")
        adres = f"http://127.0.0.1:{ws.server_address[1]}"
        dublaj = uyg.ayar["dublaj"]
        assert dublaj["dogal_ses"] is True and dublaj["dogal_motor"] == "otomatik"

        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page(viewport={"width": 1180, "height": 1000}, color_scheme=TEMA)
            hatalar = []
            pg.on("pageerror", lambda e: hatalar.append(str(e)))
            pg.goto(f"{adres}/#b")
            pg.wait_for_timeout(500)

            def bekle_ki(kosul, sn=8):
                for _ in range(int(sn * 10)):
                    try:
                        if kosul():
                            return True
                    except Exception:
                        pass
                    pg.wait_for_timeout(100)
                return False

            rozet = lambda: pg.inner_text("#d-dogal-rozet").strip()  # noqa: E731
            durum_yazisi = lambda: pg.inner_text("#d-dogal-durum").strip()  # noqa: E731
            sesler = lambda: [x.strip() for x in pg.locator("#d-dogal-sesler button").all_inner_texts()]  # noqa: E731

            # --- panel: doğal sesler var ama ses sunucusu henüz çalışmıyor ---
            pg.click('button[data-bolum="ses"]')
            assert bekle_ki(lambda: rozet() == "Beklemede"), rozet()
            assert pg.evaluate("() => { const e = document.getElementById('d-dogal'); return e.checked && !e.disabled; }")
            assert sesler() == ["Elif · kadın", "Tarik · erkek"], sesler()
            assert pg.locator("#d-dogal-sesler button:disabled").count() == 0, "sesler kapalıyken de dinlenebilmeli"
            assert not pg.is_visible("#d-motor-satir"), "tek motor varken model seçimi görünmemeli"
            assert "Programla birlikte gelir" in pg.inner_text("#d-dogal-not")
            assert not surecler and dogal_ses._paylasilan.durum == "kapali"

            # --- bir sese tıklamak ses sunucusunu açar, hazır olunca çalar ---
            pg.locator("#d-dogal-sesler button", has_text="Tarik").click()
            assert bekle_ki(lambda: "açılıyor" in durum_yazisi(), 3), durum_yazisi()
            assert pg.locator("#d-dogal-sesler button:disabled").count() == 1  # dinlenen düğme meşgul
            assert bekle_ki(lambda: len(calinan) > 0, 10), (dogal_ses._paylasilan.durum, dogal_ses._paylasilan.hata)
            assert len(surecler) == 1 and _SahteHafif.istekler[-1]["voice"] == "tarik"
            assert calinan[0][0] == 24000, "hafif motorun sesi 24 kHz çalınmalı"
            assert bekle_ki(lambda: rozet() == "Hazır", 6), rozet()
            assert bekle_ki(lambda: "Bilgisayar 1 saniyelik sesi" in durum_yazisi() and "yetişiyor" in durum_yazisi(), 6), durum_yazisi()
            assert bekle_ki(lambda: pg.locator("#d-dogal-sesler button:disabled").count() == 0, 6)
            pg.locator("#b-ses").screenshot(path=os.path.join(CIKTI, "dogal_panel.png"))
            # ikinci dinleme: sunucu açık, hemen
            n = len(calinan)
            pg.locator("#d-dogal-sesler button", has_text="Elif").click()
            assert bekle_ki(lambda: len(calinan) > n, 4) and _SahteHafif.istekler[-1]["voice"] == "elif"
            assert len(surecler) == 1

            # --- anahtar kapatılınca ses sunucusu kapatılır; açılınca yeniden başlar ---
            pg.locator("label:has(#d-dogal)").click()
            assert bekle_ki(lambda: dublaj["dogal_ses"] is False and surecler[0].kapandi), (dublaj["dogal_ses"], surecler[0].kapandi)
            assert bekle_ki(lambda: rozet() == "Kapalı"), rozet()
            pg.locator("label:has(#d-dogal)").click()
            assert bekle_ki(lambda: dublaj["dogal_ses"] is True and len(surecler) == 2)
            assert bekle_ki(lambda: rozet() == "Hazır", 8), rozet()
            ayar = veri.ayar_yukle()
            assert ayar["dublaj"]["dogal_ses"] is True

            # --- Doğal Ses Paketi de kuruluysa hangi modelin kullanılacağı seçilebilir ---
            guclu_kurulu[0] = True
            assert bekle_ki(lambda: pg.is_visible("#d-motor-satir"), 6), "iki motor varken model seçimi görünmeli"
            assert pg.input_value("#d-motor") == "otomatik"
            pg.select_option("#d-motor", "guclu")
            assert bekle_ki(lambda: dublaj["dogal_motor"] == "guclu" and dogal_ses._paylasilan is not None
                            and dogal_ses._paylasilan.motor == "guclu"), dublaj
            assert surecler[1].kapandi, "öteki motorun ses sunucusu kapatılmalı"
            assert bekle_ki(lambda: len(sesler()) == 4 and rozet() == "Yükleniyor…", 6), (sesler(), rozet())
            assert pg.input_value("#d-motor") == "guclu" and veri.ayar_yukle()["dublaj"]["dogal_motor"] == "guclu"
            pg.select_option("#d-motor", "otomatik")
            assert bekle_ki(lambda: dublaj["dogal_motor"] == "otomatik" and dogal_ses._paylasilan.motor == "hafif")
            assert bekle_ki(lambda: rozet() == "Hazır" and sesler() == ["Elif · kadın", "Tarik · erkek"], 8), (rozet(), sesler())
            assert surecler[2].kapandi and surecler[2].motor == "guclu" and len(surecler) == 4
            guclu_kurulu[0] = False
            assert not hatalar, hatalar

            # --- Hakkında: sorun raporu (anahtarlar ve şifre yazılmaz)
            import zipfile
            uyg.ayar["ceviri"]["anahtarlar"]["groq"] = "gsk_cok_gizli_anahtar"
            uyg.ayar["obs"]["sifre"] = "obs_gizli_sifre"
            pg.click('button[data-bolum="hakkinda"]')
            pg.click("#h-rapor")
            assert bekle_ki(lambda: "Rapor hazır" in pg.inner_text("#h-rapor-durum"), 10), pg.inner_text("#h-rapor-durum")
            rapor = [os.path.join(os.environ["CTA_RAPOR_KLASORU"], a) for a in os.listdir(os.environ["CTA_RAPOR_KLASORU"])][-1]
            with zipfile.ZipFile(rapor) as z:
                icerik = {ad: z.read(ad).decode("utf-8", "replace") for ad in z.namelist()}
            assert {"ayarlar.json", "durum.json"} <= set(icerik), list(icerik)
            assert "gizli" not in "".join(icerik.values()), "sorun raporuna anahtar ya da şifre yazılmamalı"
            assert '"groq": "(var)"' in icerik["ayarlar.json"] and veri.SURUM in icerik["durum.json"]
            uyg.ayar["ceviri"]["anahtarlar"]["groq"] = ""
            uyg.ayar["obs"]["sifre"] = ""
            pg.click('button[data-bolum="ses"]')

            # --- sihirbaz: Türkçe ses adımında doğal sesler anlatılır, "Dinle" doğal sesle okur ---
            pg.goto(f"{adres}/kurulum?adim=6#b")
            pg.locator('[data-dublaj="1"]').click()
            assert bekle_ki(lambda: pg.is_visible("#dogal-not") and pg.is_visible("#dinle")), "doğal ses notu görünmeli"
            assert pg.inner_text("#dogal-sayi") == "2"
            turkce_var = bool(seslendirme.turkce_sesler())
            if turkce_var:
                assert pg.inner_text("#ses-etiket") == "Yedek ses (Windows)" and pg.is_visible("#ses-sec")
            else:
                assert not pg.is_visible("#ses-sec") and not pg.is_visible("#dogal-yedek")
            pg.locator("#ses-var").screenshot(path=os.path.join(CIKTI, "dogal_sihirbaz.png"))
            n, w = len(calinan), len(windows_sesi)
            pg.click("#dinle")
            assert bekle_ki(lambda: len(calinan) > n, 6), "sihirbazda Dinle doğal sesle okumalı"
            assert _SahteHafif.istekler[-1]["voice"] == "tarik" and "böyle Türkçe okuyacağım" in _SahteHafif.istekler[-1]["input"]
            assert len(windows_sesi) == w, "doğal ses okurken Windows sesi çalmamalı"
            assert bekle_ki(lambda: pg.is_enabled("#dinle"), 5)

            # doğal ses açılamazsa (ör. boş bellek yok): nedeni yazılır, Windows sesi varsa onunla okunur
            dogal_ses.kapat()
            bos_bellek[0] = 1.0
            pg.goto(f"{adres}/kurulum?adim=6#b")
            pg.locator('[data-dublaj="1"]').click()
            assert bekle_ki(lambda: pg.is_visible("#dinle"))
            n = len(calinan)
            pg.click("#dinle")
            assert bekle_ki(lambda: "yeterli boş bellek yok" in pg.inner_text("#dublaj-durum"), 6), pg.inner_text("#dublaj-durum")
            if turkce_var:
                assert bekle_ki(lambda: len(windows_sesi) > w, 6), "doğal ses açılamayınca Windows sesiyle okunmalı"
                assert "Windows sesiyle" in pg.inner_text("#dublaj-durum")
            assert len(calinan) == n
            assert not hatalar, hatalar
            b.close()
        ws.shutdown()
        uyg.kapat()
    finally:
        dogal_ses.kapat()
        for ad, deger in eski.items():
            setattr(dogal_ses, ad, deger)
        dogal_ses.DogalSes._sureci_baslat, dogal_ses.DogalSes._kapi_dolu = eski_sinif
        _SahteHafif.durum = "ok"
        sunucu.shutdown()
    print("  ✓ doğal ses arayüzü: kapalıyken dinleme sunucuyu açtı, anahtar kapatınca sunucu kapandı, model seçimi, "
          "sihirbazda doğal sesle dinleme ve Windows sesine düşme")


if __name__ == "__main__":
    test_dogal_arayuz()
