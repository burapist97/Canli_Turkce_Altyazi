"""Hızlı okuma (yazıyı aramadan, yalnız tanıma modeli) ve arkadan gelen doğrulama.

- Temiz altyazıda hızlı okuma tam okumayla aynı metni verir ve belirgin biçimde hızlıdır.
- Bölgede altyazıya benzemeyen parlaklık varsa hızlı okuma vazgeçer (None): tam okuma yapılır.
- Takipçi hızlı okunan satırı hemen gönderir; görüntü durunca tam okumayla doğrular, fark varsa 'duzelt' gönderir.
- Ekran kaynağı yalnızca istenen bölgeleri yakalar ve tam kareden kesilenle aynı kesiti verir.
"""
import statistics
import time

import numpy as np

import yardimci  # noqa: F401
from yardimci import altyazi, sahne, test_ayari


def test_hizli_okuma():
    import ocr
    from kaynak import bolge_kes

    ayar = test_ayari()
    if ayar["ocr"]["motor"] != "rapidocr":
        print("  - atlandı (hızlı okuma yalnız RapidOCR ile)")
        return
    m = ocr.motor_olustur(ayar)
    ocr.isit(m)
    metinler = ["Lucia, get in the car.\nThe cops are right behind us!", "Relax, I know a shortcut through the swamp",
                "Are you out of your mind?", "We need to find a place to hide the money."]
    hizli_ms, tam_ms = [], []
    for metin in metinler:
        kesit = bolge_kes(altyazi(sahne(1.0, False), metin), ayar["bolge"])
        maske = ocr.yazi_maskesi(kesit, 185)
        bantlar = ocr.satir_bantlari(maske)
        assert bantlar and len(bantlar) == metin.count("\n") + 1, (metin, bantlar)
        for _ in range(3):
            t = time.perf_counter()
            hizli = m.hizli_oku(kesit, maske)
            hizli_ms.append((time.perf_counter() - t) * 1000)
            t = time.perf_counter()
            tam = ocr.oku(m, kesit, maske, 1.5, hizli=False)
            tam_ms.append((time.perf_counter() - t) * 1000)
        beklenen = ocr.metni_temizle(metin.replace("\n", " "))
        assert hizli is not None and ocr.metni_temizle(hizli) == beklenen == tam, (hizli, tam, beklenen)
        assert m.son_guven >= 0.9
    oran = statistics.median(tam_ms) / statistics.median(hizli_ms)
    assert oran > 1.8, f"hızlı okuma yeterince hızlı değil: {statistics.median(hizli_ms):.0f} ms / tam {statistics.median(tam_ms):.0f} ms"
    # ocr.oku varsayılan olarak hızlı yolu dener ve sayar
    onceki = list(m.hizli_sayac)
    ocr.oku(m, kesit, maske, 1.5)
    assert m.hizli_sayac[0] == onceki[0] + 1
    # Altyazıya benzemeyen bölge (parlak gürültü, dev parlak nesne): hızlı okuma vazgeçer
    gurultu = np.random.default_rng(3).integers(0, 255, (162, 1459, 3), dtype=np.uint8)
    assert m.hizli_oku(gurultu, ocr.yazi_maskesi(gurultu, 185)) is None
    assert ocr.satir_bantlari(np.zeros((160, 900), np.uint8)) is None
    dolu = np.zeros((160, 900), np.uint8)
    dolu[10:150, 100:800] = 255
    assert ocr.satir_bantlari(dolu) is None, "bölgeyi dolduran parlaklık satır sayılmamalı"
    print(f"  ✓ hızlı okuma: tam okumayla aynı metin, {statistics.median(hizli_ms):.0f} ms (tam okuma "
          f"{statistics.median(tam_ms):.0f} ms, {oran:.1f} kat)")


def test_dogrulama():
    """Hızlı okuma bir harfi yanlış okursa satır yine hemen gider; görüntü durunca tam okuma düzeltir."""
    import ocr
    from kaynak import bolge_kes
    from takip import AltyaziTakipcisi

    class SahteMotor:
        def __init__(self):
            self.hizli_sayac = [0, 0]
            self.son_guven = 0.0
            self.tam_okuma = 0

        def hizli_oku(self, kesit, maske):
            self.son_guven = 0.97
            return "Relax, I know a shortout through the swamp"

        def oku(self, kesit, maske=None):
            self.tam_okuma += 1
            self.son_guven = 0.99
            return "Relax, I know a shortcut through the swamp"

    ayar = test_ayari()
    motor = SahteMotor()
    t = AltyaziTakipcisi(ayar, motor)
    bos = bolge_kes(sahne(0.0, False), ayar["bolge"])
    dolu = bolge_kes(altyazi(sahne(0.0, False), "Relax, I know a shortcut through the swamp"), ayar["bolge"])
    olaylar, simdi = [], 0.0
    for kare in [bos] * 3 + [dolu] * 30 + [bos] * 6:
        for o in t.isle(kare, simdi):
            olaylar.append((round(simdi, 3), o))
        simdi += 0.025
    turler = [o[0] for _, o in olaylar]
    assert turler == ["yeni", "duzelt", "temizle"], olaylar
    yeni, duzelt = olaylar[0], olaylar[1]
    assert "shortout" in yeni[1][2] and "shortcut" in duzelt[1][2] and yeni[1][1] == duzelt[1][1], olaylar
    assert yeni[0] <= 0.075 + 0.026, f"hızlı okunan satır hemen gönderilmedi: {yeni[0]}"
    assert duzelt[0] - yeni[0] >= AltyaziTakipcisi.DOGRULAMA_SN - 0.03, "doğrulama çeviriyi beklemeden yapıldı"
    assert motor.tam_okuma == 1, f"doğrulama bir kez yapılmalı: {motor.tam_okuma}"
    # hızlı okuma kapalıysa (ayar) hiç denenmez
    ayar2 = test_ayari()
    ayar2["ocr"]["hizli"] = False
    motor2 = SahteMotor()
    t2 = AltyaziTakipcisi(ayar2, motor2)
    olaylar2, simdi = [], 0.0
    for kare in [bos] * 2 + [dolu] * 8:
        olaylar2 += t2.isle(kare, simdi)
        simdi += 0.025
    assert [o[0] for o in olaylar2] == ["yeni"] and "shortcut" in olaylar2[0][2] and motor2.hizli_sayac == [0, 0], olaylar2
    print("  ✓ doğrulama: hızlı okunan satır hemen gidiyor, tam okuma sonradan bir kez düzeltiyor")


def test_bolge_yakalama():
    """EkranKaynagi.kesitler_al: yalnız istenen bölgeleri kapsayan dikdörtgen yakalanır, kesitler tam kareden
    kesilenle aynıdır (sahte mss ile)."""
    import kaynak

    tam = np.random.default_rng(5).integers(0, 255, (1080, 1920, 4), dtype=np.uint8)
    istenen = []

    class SahteMss:
        monitors = [None, {"left": 1920, "top": 0, "width": 1920, "height": 1080}]

        def grab(self, m):
            istenen.append(dict(m))
            y, x = m["top"], m["left"] - 1920
            return tam[y:y + m["height"], x:x + m["width"]]

        def close(self):
            pass

    k = kaynak.EkranKaynagi.__new__(kaynak.EkranKaynagi)
    k.sct, k.monitor, k.son_kare_ms = SahteMss(), SahteMss.monitors[1], 0
    bolgeler = [{"x": 0.12, "y": 0.8, "w": 0.76, "h": 0.15}, {"x": 0.03, "y": 0.05, "w": 0.3, "h": 0.1}]
    bgr = tam[:, :, :3]
    kesitler = k.kesitler_al(bolgeler[:1])
    assert istenen[-1] == {"left": 1920 + 230, "top": 864, "width": 1689 - 230, "height": 1026 - 864}, istenen[-1]
    assert np.array_equal(kesitler[0], kaynak.bolge_kes(bgr, bolgeler[0]))
    kesitler = k.kesitler_al(bolgeler)
    assert istenen[-1]["width"] < 1920 and len(kesitler) == 2
    for kesit, b in zip(kesitler, bolgeler):
        assert np.array_equal(kesit, kaynak.bolge_kes(bgr, b))
    assert k.kesitler_al([{"x": 0.5, "y": 0.5, "w": 0.0, "h": 0.0}]) is None
    print("  ✓ bölge yakalama: yalnız altyazı bölgesi alınıyor, kesitler tam kareyle aynı")


def test_buyuk_ekran():
    """4K ekran: altyazı bölgesi 1080p eşdeğerine küçültülerek işlenir; satır yine doğru okunur ve bir kez gönderilir."""
    import cv2

    import motor as motor_modulu
    from kaynak import bolge_kes
    from takip import AltyaziTakipcisi

    ayar = test_ayari()
    ocr_motoru = motor_modulu.ocr_motoru_al(ayar)
    takipci = AltyaziTakipcisi(ayar, ocr_motoru)
    m = motor_modulu.AltyaziMotoru(ayar, None, yazdir=False)
    gorulen = []
    asil = takipci.isle

    def isle(kesit, simdi):
        gorulen.append(kesit.shape)
        return asil(kesit, simdi)

    takipci.isle = isle

    class Isci:
        def __init__(self):
            self.gelen = []

        def ekle(self, sid, metin, alan, tam=None):
            self.gelen.append(metin)
            return 0

    isci = Isci()
    import threading
    bos4k = cv2.resize(sahne(0.0, False), (3840, 2160), interpolation=cv2.INTER_CUBIC)
    dolu4k = cv2.resize(altyazi(sahne(0.0, False), "Relax, I know a shortcut through the swamp."), (3840, 2160),
                        interpolation=cv2.INTER_CUBIC)
    simdi = 0.0
    for kare in [bos4k] * 2 + [dolu4k] * 8:
        m._alan_isle(0, takipci, bolge_kes(kare, ayar["bolge"]), simdi, isci, threading.Lock(), {}, set(), 1_000_000)
        simdi += 0.025
    assert gorulen[0][1] == 1460 and gorulen[0][0] == round(324 * 1460 / 2918), gorulen[0]
    assert isci.gelen == ["Relax, I know a shortcut through the swamp."], isci.gelen
    # 1080p ekranda bölgeye dokunulmaz
    gorulen.clear()
    m._alan_isle(0, takipci, bolge_kes(sahne(0.0, False), ayar["bolge"]), simdi, isci, threading.Lock(), {}, set(), 1_000_000)
    assert gorulen[0][1] == 1459, gorulen[0]
    print("  ✓ büyük ekran: 4K altyazı bölgesi küçültülerek okunuyor, 1080p'ye dokunulmuyor")


def test_video_arka_plani():
    """Film / video: altyazının ARKASINDA her karede değişen parlak, ayrıntılı görüntü var (en zor durum).
    Eskiden her karede okuma başlıyordu (16 sn'de 74+ tam okuma: işlemci doluyor, çeviri 1 sn'ye çıkıyordu) ve satır
    bir an kaybolup geri geliyordu. Artık: az okuma, her satır bir kez, zamanında gelip gidiyor."""
    import difflib

    import cv2

    import motor as motor_modulu
    import ocr
    from kaynak import bolge_kes
    from takip import AltyaziTakipcisi

    ayar = test_ayari()
    if ayar["ocr"]["motor"] != "rapidocr":
        print("  - atlandı (RapidOCR gerekir)")
        return
    satirlar = [(1.0, 2.5, "Lucia, get in the car."), (4.0, 2.5, "Relax, I know a shortcut through the swamp"),
                (7.0, 2.0, "Are you out of your mind?"), (9.5, 2.5, "Trust me. I have done this a hundred times."),
                (12.5, 2.5, "That is exactly what worries me")]
    rng = np.random.default_rng(1)
    doku = cv2.GaussianBlur(cv2.resize(rng.integers(0, 255, (68, 240, 3), dtype=np.uint8), (3840, 1080),
                                       interpolation=cv2.INTER_CUBIC), (0, 0), 2)
    t = AltyaziTakipcisi(ayar, motor_modulu.ocr_motoru_al(ayar))
    olaylar, simdi = [], 0.0
    while simdi < 16.0:
        x = int(simdi * 240) % 1920
        img = doku[:, x:x + 1920].copy()
        for bas, sure, metin in satirlar:
            if bas <= simdi < bas + sure:
                img = altyazi(img, metin)
        kesit = bolge_kes(img, ayar["bolge"])
        if simdi == 0.0:
            maske = ocr.yazi_maskesi(kesit, 185)
            assert ocr.satir_bantlari(maske) is None and np.count_nonzero(maske) > 0.05 * maske.size, "sahne yeterince zor değil"
        for o in t.isle(kesit, simdi):
            olaylar.append((round(simdi, 3), o))
        simdi += 0.025
    yeni = [(z, o[2]) for z, o in olaylar if o[0] == "yeni"]
    temizle = [z for z, o in olaylar if o[0] == "temizle"]
    assert [o[0] for _, o in olaylar] == ["yeni", "temizle"] * 5, f"satırlar bir kez gelip gitmeli: {olaylar}"
    for (bas, sure, metin), (z, okunan), kalkti in zip(satirlar, yeni, temizle):
        assert difflib.SequenceMatcher(None, metin.lower(), okunan.lower()).ratio() > 0.92, (metin, okunan)
        assert -0.01 <= z - bas <= 0.75, f"geç geldi: {metin!r} {z - bas:.2f} sn"
        assert -0.01 <= kalkti - (bas + sure) <= 0.45, f"geç kalktı: {metin!r} {kalkti - (bas + sure):.2f} sn"
    assert t.ocr_sayisi <= 56, f"çok sık okunuyor: 16 sn'de {t.ocr_sayisi} okuma (eskiden 74+)"
    gec = [z - s[0] for s, (z, _) in zip(satirlar, yeni)]
    print(f"  ✓ video arka planı: 5 satır kırpışmadan geldi (gecikme en çok {max(gec):.2f} sn), 16 sn'de {t.ocr_sayisi} okuma")


if __name__ == "__main__":
    test_video_arka_plani()
    test_buyuk_ekran()
    test_hizli_okuma()
    test_dogrulama()
    test_bolge_yakalama()
