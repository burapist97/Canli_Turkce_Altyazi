"""Altyazı gecikmesi ölçümü (bilgisayar oyunu modu): gerçek motor + gerçek OCR + hazır çeviri, sahte ekran.

    .venv\\Scripts\\python.exe tests\\olc_gecikme.py

Oyun gibi tek seferde beliren altyazılar oynatılır. Ölçülen:
- BELİRME gecikmesi: İngilizce altyazı ekrana geldiği an -> Türkçesinin overlay'e gönderildiği an
- KAYBOLMA gecikmesi: İngilizce altyazı kalktığı an -> Türkçesinin kaldırıldığı an
Hedef: ikisi de gözle fark edilmeyecek kadar kısa. test_gecikme() sınırları denetler (calistir.py).
"""
import queue
import statistics
import time

import yardimci  # noqa: F401
from yardimci import altyazi, sahne, test_ayari

SATIRLAR = [  # (başlangıç sn, süre sn, İngilizce) — bir kısmı noktasız, bir kısmı art arda (arada boşluk yok)
    (1.0, 2.2, "Lucia, get in the car.\nThe cops are right behind us!"),
    (3.6, 1.8, "Relax, I know a shortcut through the swamp"),
    (5.4, 1.5, "Are you out of your mind?"),
    (7.4, 2.4, "Trust me. I have done this a hundred times."),
    (10.2, 1.6, "That is exactly what worries me"),
    (12.2, 2.6, "Hold on tight, this road is about to get rough."),
    (14.8, 1.4, "Watch out for the truck!"),
    (16.8, 2.2, "We need to find a place to hide the money."),
    (19.4, 2.4, "My cousin has a garage two blocks from here"),
    (22.2, 1.8, "Can we trust your cousin?"),
]
TOPLAM = 25.0


def olc(yazdir=True):
    import kaynak
    import motor as motor_modulu
    import sunucu

    t0 = [None]

    def kare():
        if t0[0] is None:
            return sahne(0.0, parlak_nesne=False)
        t = time.time() - t0[0]
        img = sahne(t, parlak_nesne=False)
        for bas, sure, metin in SATIRLAR:
            if bas <= t < bas + sure:
                return altyazi(img, metin)
        return img

    class SahteEkran:
        def __init__(self, no):
            self.son_kare_ms = 1

        def kare_al(self):
            return kare()

        def kapat(self):
            pass

    asil = kaynak.EkranKaynagi
    kaynak.EkranKaynagi = SahteEkran
    ayar = test_ayari()
    ayar["senaryo"] = "pc"
    ayar["kaynak"].update({"tip": "ekran", "ekran_no": 1})
    ayar["dublaj"]["acik"] = False
    yayinci = sunucu.Yayinci(ayar["goruntu"], ayar["bolge"])
    olaylar = yayinci.abone_ol()
    m = motor_modulu.AltyaziMotoru(ayar, yayinci, yazdir=False)
    kayit = []
    try:
        m.baslat()
        for _ in range(300):
            if m.durum in ("calisiyor", "hata"):
                break
            time.sleep(0.1)
        assert m.durum == "calisiyor", m.hata
        time.sleep(1.5)
        t0[0] = time.time()
        while time.time() - t0[0] < TOPLAM:
            try:
                o = olaylar.get(timeout=0.05)
            except queue.Empty:
                continue
            if o["tip"] in ("satir", "temizle"):
                kayit.append((time.time() - t0[0], o))
    finally:
        m.durdur()
        kaynak.EkranKaynagi = asil

    belirme, kaybolma, eksik = [], [], []
    for bas, sure, metin in SATIRLAR:
        goster = next((t for t, o in kayit if o["tip"] == "satir" and bas - 0.05 <= t < bas + sure + 1.5), None)
        if goster is None:
            eksik.append(metin.replace("\n", " "))
            continue
        belirme.append(goster - bas)
        sid = next(o["id"] for t, o in kayit if o["tip"] == "satir" and t == goster)
        kalk = next((t for t, o in kayit if o["tip"] == "temizle" and o.get("id") == sid and t >= bas + sure - 0.05), None)
        if kalk is not None:
            kaybolma.append(kalk - (bas + sure))
    sonuc = {"belirme": belirme, "kaybolma": kaybolma, "eksik": eksik, "hiz": m.hiz(),
             "satir_olayi": sum(1 for _, o in kayit if o["tip"] == "satir")}
    if yazdir:
        ms = lambda d: f"ortanca {statistics.median(d) * 1000:.0f} ms, en kötü {max(d) * 1000:.0f} ms" if d else "yok"  # noqa: E731
        print(f"  belirme : {ms(belirme)}  {[round(x * 1000) for x in belirme]}")
        print(f"  kaybolma: {ms(kaybolma)}  {[round(x * 1000) for x in kaybolma]}")
        print(f"  eksik: {eksik} | satır olayı {sonuc['satir_olayi']} / {len(SATIRLAR)} | hız {sonuc['hiz']}")
    return sonuc


def test_gecikme():
    s = olc()
    assert not s["eksik"], f"bu satırlar hiç gösterilmedi: {s['eksik']}"
    assert s["satir_olayi"] <= len(SATIRLAR) + 2, f"aynı satır birden çok kez gönderildi: {s['satir_olayi']}"
    assert statistics.median(s["belirme"]) < 0.30 and max(s["belirme"]) < 0.5, s["belirme"]
    assert len(s["kaybolma"]) >= len(SATIRLAR) - 3 and max(s["kaybolma"]) < 0.25, s["kaybolma"]
    print("  ✓ gecikme: Türkçe altyazı İngilizcesiyle birlikte geliyor ve birlikte gidiyor")


if __name__ == "__main__":
    olc()
