"""Tüm ekran kipi (tam_ekran.py): ekranın tamamı okunur, her İngilizce yazının Türkçesi yerine konur.

- gerçek okuyucuyla: yazılar bulunur, alt alta satırlar paragraf olur, Türkçe yazı ve tek tük harfler atlanır,
  aynı yazı aynı yerde durdukça kimliği değişmez, ekran değişmediyse yeniden okunmaz, yazı gidince kutu hemen kalkar
- oyun üstü sayfa (overlay.html): kutular doğru yere ve seçilen yerleşime göre çizilir (Playwright)
"""
import time

import cv2
import numpy as np

import yardimci  # noqa: F401
from yardimci import test_ayari


def _yaz(img, metin, x, y, olcek=1.0, renk=(240, 240, 240)):
    cv2.putText(img, metin, (x, y), cv2.FONT_HERSHEY_DUPLEX, olcek, renk, 2, cv2.LINE_AA)


def _ekran(baslik=True):
    img = np.full((1080, 1920, 3), (48, 40, 36), np.uint8)
    if baslik:
        _yaz(img, "Welcome to the city of angels", 160, 160, 1.6)
    _yaz(img, "You need to find the hidden key", 160, 420, 1.1)       # iki satırlık paragraf
    _yaz(img, "before the guards come back.", 160, 465, 1.1)
    _yaz(img, "Press the button to open the door", 1050, 820, 1.0)
    _yaz(img, "Ayarlar menusunden dil secebilirsiniz", 1050, 300, 1.0)  # Türkçe: çevrilmemeli
    _yaz(img, "OK", 1700, 1000, 1.0)                                     # çok kısa: atlanır
    return img


def test_paragraflar():
    import tam_ekran
    satirlar = [(100, 100, 500, 130, "first line of a"), (100, 136, 480, 166, "paragraph here"),
                (900, 100, 1200, 130, "another column"), (100, 400, 400, 460, "BIG TITLE"), (100, 470, 300, 495, "small note")]
    b = tam_ekran.paragraflar(satirlar)
    assert [(x["metin"], x["satir"]) for x in b] == [("first line of a paragraph here", 2), ("another column", 1),
                                                    ("BIG TITLE", 1), ("small note", 1)], b
    assert (b[0]["x1"], b[0]["y1"], b[0]["x2"], b[0]["y2"]) == (100, 100, 500, 166)
    print("  ✓ paragraflar: alt alta satırlar birleşiyor; ayrı sütun ve farklı boydaki yazı ayrı kalıyor")


def test_tam_ekran():
    import ceviri
    import ceviri_hatti
    import motor as motor_modulu
    import tam_ekran

    ayar = test_ayari()
    if ayar["ocr"]["motor"] != "rapidocr":
        print("  - atlandı (RapidOCR gerekir)")
        return
    if ceviri_hatti._sozluk is None and ceviri.model_var():
        import os
        ceviri_hatti.sozluk_yukle_modelden(os.path.join(ceviri.model_klasoru(), "source.spm"))
    assert ceviri_hatti.ingilizce_kesin("Press the button to open the door")
    assert not ceviri_hatti.ingilizce_kesin("Ayarlar menusunden dil secebilirsiniz")
    assert not ceviri_hatti.ingilizce_kesin("Gerçek Hayatta Açlık Oyunları") and not ceviri_hatti.ingilizce_kesin("12:45")

    ayar["tam_ekran"] = {"acik": True, "yerlesim": "altinda", "aralik": 1.0}
    yayin, cevrilen, kayit = [], [], []

    def cevir(metin):
        cevrilen.append(metin)
        return "TR(" + metin + ")"

    t = tam_ekran.TamEkranTarayici(ayar, motor_modulu.ocr_motoru_al(ayar), cevir, yayin.append, lambda en, tr: kayit.append(en))
    try:
        def calistir(kare, simdi, bekle=True):
            t.adim(kare, simdi)
            if bekle:
                for _ in range(100):  # çeviri arka planda: bitince sonraki adımda yayınlanır
                    if not t._kuyruk.qsize() and all(k["en"].lower() in t._ceviri for k in t.kutular):
                        break
                    time.sleep(0.02)
                t.adim(kare, simdi + 0.05)
            return yayin[-1] if yayin else None

        o = calistir(_ekran(), 0.0)
        assert o["tip"] == "tam" and o["yerlesim"] == "altinda", o
        metinler = sorted(k["en"] for k in o["kutular"])
        assert metinler == ["Press the button to open the door", "Welcome to the city of angels",
                            "You need to find the hidden key before the guards come back."], metinler
        par = next(k for k in o["kutular"] if k["en"].startswith("You need"))
        assert par["satir"] == 2 and par["tr"] == "TR(" + par["en"] + ")"
        assert abs(par["x"] - 160 / 1920) < 0.01 and abs(par["y"] - 395 / 1080) < 0.02 and 0.05 < par["h"] < 0.09, par
        kapi = next(k for k in o["kutular"] if k["en"].startswith("Press"))
        assert abs(kapi["x"] - 1050 / 1920) < 0.01 and abs(kapi["y"] - 797 / 1080) < 0.02, kapi
        assert sorted(kayit) == metinler and t.tarama_sayisi == 1
        kimlikler = {k["en"]: k["id"] for k in o["kutular"]}

        # ekran aynı: süre dolsa da yeniden okunmaz, yeniden çevrilmez
        n = len(yayin)
        calistir(_ekran(), 1.2, bekle=False)
        calistir(_ekran(), 2.4, bekle=False)
        assert t.tarama_sayisi == 1 and len(cevrilen) == 3 and len(yayin) == n, (t.tarama_sayisi, len(cevrilen))

        # başlık gitti: kutusu taramayı beklemeden kalkar; ötekilerin kimliği değişmez (overlay'de kırpışmaz)
        o = calistir(_ekran(baslik=False), 2.5, bekle=False)
        assert sorted(k["en"] for k in o["kutular"]) == metinler[:1] + metinler[2:], o["kutular"]
        o = calistir(_ekran(baslik=False), 3.0)
        assert {k["en"]: k["id"] for k in o["kutular"]} == {e: i for e, i in kimlikler.items() if not e.startswith("Welcome")}
        assert len(cevrilen) == 3, "aynı yazı yeniden çevrildi"

        # yeni yazı: çevrilip eklenir
        kare = _ekran(baslik=False)
        _yaz(kare, "Game saved successfully", 700, 620, 1.2)
        o = calistir(kare, 4.2)
        assert any(k["en"] == "Game saved successfully" for k in o["kutular"]) and len(cevrilen) == 4, o["kutular"]
    finally:
        t.kapat()
    assert yayin[-1] == {"tip": "tam", "yerlesim": "altinda", "kutular": []}, "kapanınca ekrandaki kutular silinmeli"
    print(f"  ✓ tüm ekran: 3 yazı bulundu (paragraf birleşti, Türkçe atlandı), kimlikler sabit, tarama {t.tarama_ms} ms")


def test_tam_ekran_overlay(port=8795):
    """Oyun üstü sayfa 'tam' olayını doğru çiziyor mu: üstüne (kapatarak), hemen üstünde, hemen altında."""
    from playwright.sync_api import sync_playwright

    import sunucu

    ayar = test_ayari()
    y = sunucu.Yayinci(ayar["goruntu"], ayar["bolge"])
    sunucu.sunucu_baslat(y, port)
    kutular = [{"id": 1, "x": 0.1, "y": 0.4, "w": 0.3, "h": 0.05, "satir": 1, "tr": "Kapıyı aç", "en": "Open the door"},
               {"id": 2, "x": 0.5, "y": 0.02, "w": 0.2, "h": 0.08, "satir": 2, "tr": "İki satırlık bir paragraf", "en": "A two line paragraph"}]
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1920, "height": 1080})
        hatalar = []
        pg.on("pageerror", lambda e: hatalar.append(str(e)))
        pg.goto(f"http://127.0.0.1:{port}/")
        pg.wait_for_timeout(400)

        def kutu(i):
            return pg.evaluate("i => { const e = document.querySelectorAll('.tam')[i]; const r = e.getBoundingClientRect(); "
                               "const s = getComputedStyle(e); return {x: r.left, y: r.top, w: r.width, h: r.height, alt: r.bottom, "
                               "yazi: e.textContent, zemin: s.backgroundColor, boyut: parseFloat(s.fontSize)}; }", i)

        y.gonder({"tip": "tam", "yerlesim": "ustune", "kutular": kutular})
        pg.wait_for_function("document.querySelectorAll('.tam').length === 2")
        k = kutu(0)
        assert k["yazi"] == "Kapıyı aç" and abs(k["x"] - 192) < 2 and abs(k["y"] - 432) < 2, k
        assert k["w"] >= 575 and k["h"] >= 53 and k["zemin"] == "rgb(8, 8, 10)", f"İngilizceyi kapatmıyor: {k}"
        assert 40 < k["boyut"] < 46, k  # yazı boyu kutunun satır yüksekliğine göre
        assert 30 < kutu(1)["boyut"] < 37, kutu(1)  # iki satırlık kutuda satır başına
        y.gonder({"tip": "tam", "yerlesim": "altinda", "kutular": kutular})
        pg.wait_for_timeout(150)
        k = kutu(0)
        assert abs(k["y"] - (432 + 54)) < 2 and k["zemin"].startswith("rgba(0, 0, 0, 0.78"), k
        y.gonder({"tip": "tam", "yerlesim": "ustunde", "kutular": kutular})
        pg.wait_for_timeout(150)
        k = kutu(0)
        assert abs(k["alt"] - 432) < 2, f"İngilizcenin hemen üstünde değil: {k}"
        assert kutu(1)["y"] >= 0, "ekranın üstünden taşan kutu aşağı alınmalı"
        # ekranın en altındaki yazının "hemen altı" ekran dışıdır: kutu yazının üstüne alınır
        y.gonder({"tip": "tam", "yerlesim": "altinda", "kutular": [dict(kutular[0], id=9, y=0.96, h=0.04)]})
        pg.wait_for_function("document.querySelectorAll('.tam').length === 1")
        assert kutu(0)["alt"] <= 1080 * 0.96 + 2, kutu(0)
        y.gonder({"tip": "tam", "yerlesim": "ustunde", "kutular": kutular})
        pg.wait_for_function("document.querySelectorAll('.tam').length === 2")
        # bir kutu gidince yalnız o silinir; ötekinin öğesi aynı kalır (kırpışma yok)
        pg.evaluate("document.querySelectorAll('.tam')[0].dataset.isaret = 'ilk'")
        y.gonder({"tip": "tam", "yerlesim": "ustunde", "kutular": kutular[:1]})
        pg.wait_for_function("document.querySelectorAll('.tam').length === 1")
        assert pg.evaluate("document.querySelector('.tam').dataset.isaret") == "ilk"
        # yeni bağlanan sayfa son kutuları hemen alır; "yalnızca ses" kipinde yazı gösterilmez; durunca hepsi silinir
        pg2 = b.new_page(viewport={"width": 1280, "height": 720})
        pg2.goto(f"http://127.0.0.1:{port}/")
        pg2.wait_for_function("document.querySelectorAll('.tam').length === 1")
        y.gonder({"tip": "temizle", "id": -1, "hepsi": True})
        pg.wait_for_function("document.querySelectorAll('.tam').length === 0")
        assert y.son_tam is None and not hatalar, hatalar
        b.close()
    print("  ✓ tüm ekran çizimi: üstüne / hemen üstüne / hemen altına doğru yerde, kutular kırpışmadan güncelleniyor")


def test_overlay_devam(port=8796):
    """Oyun üstü sayfa: devam eden yazıda yeni satır eskisinin yerini kırpışmadan alır; eski satırın geç gelen
    temizlemesi yeni satırı silmez; yeni satırın çevirisi gelmeden yazı kalkarsa ekrandaki eski satır da silinir."""
    from playwright.sync_api import sync_playwright

    import sunucu

    ayar = test_ayari()
    y = sunucu.Yayinci(ayar["goruntu"], ayar["bolge"])
    sunucu.sunucu_baslat(y, port)
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1920, "height": 1080})
        pg.goto(f"http://127.0.0.1:{port}/")
        pg.wait_for_timeout(400)
        gorunur = "getComputedStyle(document.querySelector('.kutu')).display !== 'none'"
        y.gonder({"tip": "satir", "id": 5, "en": "a", "tr": "Bir yer bulmalıyız"})
        pg.wait_for_function(gorunur)
        y.gonder({"tip": "satir", "id": 6, "en": "a b", "tr": "Parayı saklayacak bir yer bulmalıyız"})  # devam: temizle yok
        pg.wait_for_function("document.querySelector('.kutu .tr').textContent.startsWith('Parayı')")
        y.gonder({"tip": "temizle", "id": 5})  # eski satırın temizlemesi: yeni satır kalır
        pg.wait_for_timeout(500)
        assert pg.evaluate(gorunur), "eski satırın temizlemesi yeni satırı sildi"
        y.gonder({"tip": "temizle", "id": 7})  # daha yeni satır (çevirisi hiç gelmedi) kalktı: ekrandaki de silinir
        pg.wait_for_function("!(" + gorunur + ")", timeout=3000)
        # ---------- kapatma şeridinin saydamlığı: ek alanda Türkçe, İngilizcenin üstüne hafif bir arka planla ----------
        ek = [{"ad": "Görev", "x": 0.05, "y": 0.1, "w": 0.3, "h": 0.08, "gorunum": {"kapak_saydamlik": 0.35, "kapak_rengi": "#14213d"}},
              {"ad": "Mesaj", "x": 0.6, "y": 0.1, "w": 0.3, "h": 0.08}]
        y.ayar_guncelle(dict(ayar["goruntu"], kapak_saydamlik=0.0), ayar["bolge"], ek)
        y.gonder({"tip": "satir", "id": 1000001, "alan": 1, "en": "Find the key", "tr": "Anahtarı bul"})
        y.gonder({"tip": "satir", "id": 2000001, "alan": 2, "en": "New message", "tr": "Yeni mesaj"})
        y.gonder({"tip": "satir", "id": 20, "alan": 0, "en": "Hello", "tr": "Merhaba"})
        pg.wait_for_function("document.querySelectorAll('.kutu').length === 3 && "
                             "Array.from(document.querySelectorAll('.kutu')).every(k => getComputedStyle(k).display !== 'none')")
        kapaklar = pg.evaluate("Array.from(document.querySelectorAll('.kapak')).map(k => { const s = getComputedStyle(k), r = k.getBoundingClientRect(); "
                               "return [s.display, s.backgroundColor, Math.round(r.left / innerWidth * 100)]; })")
        assert ["block", "rgba(20, 33, 61, 0.35)", 5] in kapaklar, f"ek alanın kendi şerit rengi/saydamlığı uygulanmadı: {kapaklar}"
        assert ["block", "rgba(8, 8, 10, 0)", 60] in kapaklar, f"görünümü ayarlanmamış ek alan ana ayarı (saydam) izlemeli: {kapaklar}"
        assert ["block", "rgba(8, 8, 10, 0)", 12] in kapaklar, f"ana altyazıda şerit tam saydam olmalı: {kapaklar}"
        yer = pg.evaluate("(() => { const k = Array.from(document.querySelectorAll('.kutu')).find(e => e.textContent.includes('Anahtar')); "
                          "const r = k.querySelector('.tr').getBoundingClientRect(); return [(r.left + r.width / 2) / innerWidth, (r.top + r.height / 2) / innerHeight]; })()")
        assert abs(yer[0] - 0.2) < 0.02 and abs(yer[1] - 0.14) < 0.02, f"Türkçe, İngilizcenin tam üstünde değil: {yer}"
        b.close()
    print("  ✓ oyun üstü sayfa: devam eden yazı kırpışmadan değişiyor; kapatma şeridi alan başına saydamlaştırılabiliyor")


if __name__ == "__main__":
    test_overlay_devam()
    test_paragraflar()
    test_tam_ekran()
    test_tam_ekran_overlay()
