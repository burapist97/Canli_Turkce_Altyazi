"""Kelime kelime yazılan ve yukarı kayan iki satırlı altyazı (video altyazıları): takipçi yarım cümleleri çevirmeye
göndermemeli, aynı sözleri yeniden göndermemeli; yalnız yeni gelen kısım, durulunca gider.
Kullanıcının 2.5.0 denemesinden: böyle bir videoda her kelimede yarım cümle çevriliyor, kayan satır baştan
çevriliyor ("aynı cümle 3-4 kez"), yazı kayarken okunduğu için harfler karışıyordu ("really" -> "roally")."""
import difflib

import yardimci  # noqa: F401
from yardimci import altyazi, sahne, test_ayari

import ocr
from kaynak import bolge_kes
from takip import AltyaziTakipcisi

METIN = ("so far we had not made a lot of progress towards our car so we decided to try something new "
         "robin places is a little harder than we thought so we are going to try doing some missions "
         "let us see if we can finally do something that makes us some good money")
SATIR_KELIME = 7     # bir satırda kelime
KELIME_SN = 0.28     # kelimeler arası süre
DURAK = {19: 1.2, 37: 1.0}  # bu kelimelerden sonra konuşmacı duraklar (sn)


def ekran(t):
    """t anında ekrandaki iki satır."""
    kelimeler = METIN.split()
    n, zaman = 0, 0.0
    for i in range(len(kelimeler)):
        if zaman > t:
            break
        n = i + 1
        zaman += KELIME_SN + DURAK.get(i + 1, 0.0)
    gorunen = kelimeler[:n]
    satirlar = [gorunen[i:i + SATIR_KELIME] for i in range(0, n, SATIR_KELIME)]
    return "\n".join(" ".join(s) for s in satirlar[-2:])


def test_akan_altyazi():
    ayar = test_ayari()
    tk = AltyaziTakipcisi(ayar, ocr.motor_olustur(ayar))
    gonderilen = []
    sure = len(METIN.split()) * KELIME_SN + sum(DURAK.values()) + 2.0
    t = 0.0
    while t < sure:
        metin = ekran(t)
        img = sahne(0.0, parlak_nesne=False)
        if metin:
            img = altyazi(img, metin)
        for o in tk.isle(bolge_kes(img, ayar["bolge"]), t):
            if o[0] in ("yeni", "duzelt"):
                gonderilen.append((round(t, 1), o[0], o[2]))
        t += 0.1
    for g in gonderilen:
        print("   ", g)
    yeniler = [m for _, tur, m in gonderilen if tur == "yeni"]
    birlesik = " ".join(yeniler).lower()
    oran = difflib.SequenceMatcher(None, birlesik.split(), METIN.split(), autojunk=False).ratio()  # kelime düzeyinde
    kelime = len(METIN.split())
    assert oran > 0.9, f"gönderilenler metni bir kez ve eksiksiz vermeli (benzerlik {oran:.2f}): {birlesik}"
    assert len(birlesik.split()) <= kelime * 1.12, f"aynı sözler yeniden gönderildi: {len(birlesik.split())} kelime / {kelime}"
    assert len(yeniler) <= kelime / 4, f"yarım cümleler tek tek gönderiliyor: {len(yeniler)} parça"
    print(f"  ✓ akan altyazı: {kelime} kelime {len(yeniler)} parçada, yinelemesiz gönderildi (benzerlik {oran:.2f})")


def test_devam_tam_gosterilir():
    """Ekrandaki yazı öncekinin devamıysa (uzayan cümle, yukarı kayan satır) Türkçesi ekrandaki yazının TAMAMI için
    gösterilir: ne eksik ne fazla. Seslendirmeye yalnız yeni gelen kısım gider (aynı sözler iki kez okunmasın).
    Kullanıcı (2.7.2): "uzun bir cümle geldiğinde en sonunu okuyor ... tüm cümleyi altyazıda göstersin"."""
    import queue
    import time

    import ceviri
    import kaynak
    import motor as motor_modulu
    import sunucu

    # --- takipçi: devam olayında ekrandaki tam yazı da verilir; araya 'temizle' girmez ---
    ayar = test_ayari()
    tk = AltyaziTakipcisi(ayar, ocr.motor_olustur(ayar))
    sahneler = [(0.0, ""), (0.5, "We need to find a place"), (2.0, "We need to find a place\nto hide the money before"),
                (4.0, "to hide the money before\nthe cops get here tonight."), (6.5, "")]
    olaylar, t = [], 0.0
    while t < 8.0:
        metin = [m for bas, m in sahneler if bas <= t][-1]
        img = sahne(0.0, parlak_nesne=False)
        if metin:
            img = altyazi(img, metin)
        olaylar += tk.isle(bolge_kes(img, ayar["bolge"]), t)
        t += 0.05
    turler = [o[0] for o in olaylar]
    assert turler == ["yeni", "yeni", "yeni", "temizle"], olaylar
    assert len(olaylar[0]) == 3 and olaylar[0][2] == "We need to find a place"
    assert olaylar[1][2] == "to hide the money before" and olaylar[1][3] == "We need to find a place to hide the money before", olaylar[1]
    assert olaylar[2][2] == "the cops get here tonight." and         olaylar[2][3] == "to hide the money before the cops get here tonight.", olaylar[2]
    assert olaylar[3][1] == olaylar[2][1], "en son satır temizlenmeli"

    # --- uçtan uca: ekranda tam yazının çevirisi görünür, sese yalnız yeni kısım gider ---
    class SahteCeviri:
        def cevir(self, metin, baglam):
            return "TR[" + metin + "]"

    t0 = [None]

    class SahteEkran:
        def __init__(self, no):
            self.son_kare_ms = 1

        def kare_al(self):
            simdi = 0.0 if t0[0] is None else time.time() - t0[0]
            metin = [m for bas, m in sahneler if bas <= simdi][-1]
            img = sahne(0.0, parlak_nesne=False)
            return altyazi(img, metin) if metin else img

        def kapat(self):
            pass

    asil = (kaynak.EkranKaynagi, ceviri.motor_olustur)
    kaynak.EkranKaynagi = SahteEkran
    ceviri.motor_olustur = lambda ayar_, sozluk: SahteCeviri()
    ayar = test_ayari()
    ayar["senaryo"] = "pc"
    ayar["kaynak"].update({"tip": "ekran", "ekran_no": 1})
    ayar["dublaj"]["acik"] = False
    yayinci = sunucu.Yayinci(ayar["goruntu"], ayar["bolge"])
    kanal = yayinci.abone_ol()
    m = motor_modulu.AltyaziMotoru(ayar, yayinci, yazdir=False)
    kayit = []
    try:
        m.baslat()
        for _ in range(300):
            if m.durum in ("calisiyor", "hata"):
                break
            time.sleep(0.1)
        assert m.durum == "calisiyor", m.hata

        time.sleep(1.0)
        t0[0] = time.time()
        while time.time() - t0[0] < 8.5:
            try:
                o = kanal.get(timeout=0.1)
            except queue.Empty:
                continue
            if o["tip"] in ("satir", "temizle"):
                kayit.append(o)
    finally:
        m.durdur()
        kaynak.EkranKaynagi, ceviri.motor_olustur = asil
    satirlar = [o for o in kayit if o["tip"] == "satir"]
    assert [o["tr"] for o in satirlar] == [
        "TR[We need to find a place]",
        "TR[We need to find a place to hide the money before]",
        "TR[to hide the money before the cops get here tonight.]"], [o["tr"] for o in satirlar]
    assert [o["en"] for o in satirlar][1] == "We need to find a place to hide the money before"
    temizlenen = [o["id"] for o in kayit if o["tip"] == "temizle" and not o.get("hepsi")]
    assert temizlenen == [satirlar[-1]["id"]], f"devam eden yazıda araya temizleme girmemeli: {temizlenen}"

    # --- çeviri işçisi: tam yazı ekrana, yalnız yeni kısım sese ---
    gelen = []
    isci = ceviri.CeviriIscisi(SahteCeviri(), lambda sid, en, tr, sure: gelen.append((sid, en, tr, isci.son_tek)),
                               onbellek_yolu=None, motor_adi="deneme")
    isci.ekle(1, "We need to find a place")
    isci.ekle(2, "to hide the money", 0, "We need to find a place to hide the money")
    for _ in range(50):
        if len(gelen) == 2:
            break
        time.sleep(0.05)
    isci.durdur()
    assert gelen[0] == (1, "We need to find a place", "TR[We need to find a place]", None), gelen[0]
    assert gelen[1] == (2, "We need to find a place to hide the money", "TR[We need to find a place to hide the money]",
                        "TR[to hide the money]"), gelen[1]
    print("  ✓ devam eden yazı: ekranda yazının tamamının çevirisi, seste yalnız yeni kısım; araya temizleme girmiyor")


if __name__ == "__main__":
    test_akan_altyazi()
    test_devam_tam_gosterilir()
