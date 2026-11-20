"""Yoğun diyalog (konsol + OBS modu, Türkçe ses açık): gerçek motor, gerçek OCR ve hazır çeviri, sahte OBS.

Oyun gibi art arda gelen altyazılar (1,6-3,5 sn'lik satırlar, kısa aralar, bir parlamada kaybolup geri gelen satır,
arada OBS'in bir kez geç cevap vermesi) oynatılır ve şunlar ölçülür:
- her satır ekrana (overlay olayları) geldi mi ve yeterince kaldı mı,
- kaybolup geri gelen satır yeniden gösterildi mi,
- satırların ne kadarı sesli okundu (Türkçe okuma çalma süresi kadar sürer; yetişemeyen satır atlanır),
- OBS bir an cevap vermeyince bağlantı kendini toparlıyor mu.
Bir test kullanıcısının 2.4.1'de bildirdiği "altyazı kökten gitti, ses arada bir konuşup susuyor" şikâyeti üzerine yazıldı.
"""
import os
import queue
import time

import yardimci  # noqa: F401
from yardimci import altyazi, sahne, test_ayari

SATIRLAR = [  # (başlangıç sn, süre sn, İngilizce)
    (0.5, 2.6, "Lucia, get in the car.\nThe cops are right behind us!"),
    (3.3, 2.2, "Relax, I know a shortcut through the swamp."),
    (5.7, 1.8, "Are you out of your mind?"),
    (7.7, 2.8, "Trust me. I have done this a hundred times."),
    (10.7, 2.0, "That is exactly what worries me."),
    (12.9, 3.2, "Hold on tight, this road is about to get rough."),
    (16.3, 1.6, "Watch out for the truck!"),
    (18.1, 2.6, "I see it. Stop yelling and let me drive."),
    (20.9, 2.4, "We need to find a place to hide the money."),
    (23.5, 3.0, "My cousin has a garage two blocks from here."),
    (26.7, 2.0, "Can we trust your cousin?"),
    (28.9, 2.8, "He owes me a favor. He will keep his mouth shut."),
]
PARLAMA = (13.7, 15.0)   # bu aralıkta altyazı görünmez (patlama/parlama), sonra aynı satır geri gelir
TAKILMA = (21.5, 6.5)    # (an, süre): OBS bu anda gelen bir isteğe çok geç cevap verir (zaman aşımı 5 sn)
TOPLAM = 33.0


def test_yogun_diyalog(obs_port=4471, overlay_port=8791, dogal=False):
    """dogal=True (elle: python tests/test_yogun_diyalog.py --dogal): Türkçe sesi gerçek hafif doğal ses motoru okur."""
    import motor as motor_modulu
    import oyun_sesi
    import sahte_obs
    import seslendirme
    import sunucu

    t0 = [None]
    takildi = [False]

    def kare():
        if t0[0] is None:
            return sahne(0.0)
        t = time.time() - t0[0]
        if not takildi[0] and t >= TAKILMA[0]:
            takildi[0] = True
            time.sleep(TAKILMA[1])
        img = sahne(t)
        if PARLAMA[0] <= t < PARLAMA[1]:
            return img
        for bas, sure, metin in SATIRLAR:
            if bas <= t < bas + sure:
                return altyazi(img, metin)
        return img

    obs = sahte_obs.baslat(kare, obs_port)[1]
    okunanlar = []

    def cal(wav):  # hoparlör yerine: çalma süresi kadar bekle
        sure = seslendirme.wav_suresi(wav)
        okunanlar.append((time.time() - t0[0], sure))
        time.sleep(sure)
    seslendirme.Seslendirici._winsound_cal = staticmethod(cal)

    class SessizOyun:  # oyunun sesi yok (konuşan tanınmaz, hep aynı ses)
        loopback, ad, seviye, hata = False, "sahte", 0.0, ""

        def parca(self, a, b):
            return None

        def kendi_sesimiz(self, a, b):
            pass

        def kisik_carpan(self, c):
            pass

        def kapat(self):
            pass
    asil_olustur = oyun_sesi.olustur
    oyun_sesi.olustur = lambda ayar, obs=None: SessizOyun()

    ayar = test_ayari()
    ayar["kaynak"]["tip"] = "obs"
    ayar["obs"].update({"port": obs_port, "sifre": sahte_obs.SIFRE, "kaynak_adi": "Capture Card"})
    ayar["goruntu"]["port"] = overlay_port
    ayar["dublaj"].update({"acik": True, "dogal_ses": bool(dogal), "okurken_kis": True, "karakter_sesleri": True})
    if dogal:
        import socket
        import dogal_ses
        os.environ.pop("CTA_DOGAL_SES_YOK", None)
        k = socket.socket(); k.bind(("127.0.0.1", 0)); dogal_ses.PORT = k.getsockname()[1]; k.close()

        class GercekZamanli:  # hoparlör yerine: çalma süresi kadar bekler (soundcard gibi)
            def __init__(self):
                self.ilk = None

            def cal(self, x):
                if self.ilk is None:
                    self.ilk = time.time()
                    okunanlar.append([time.time() - t0[0], 0.0])
                okunanlar[-1][1] += len(x) / 24000
                time.sleep(len(x) / 24000)

            def bitir(self):
                self.ilk = None
        seslendirme.Seslendirici._dogal_oynatici = GercekZamanli()
        d0 = dogal_ses.paylasilan()
        for _ in range(120):
            if d0 and d0.kullanilabilir():
                break
            time.sleep(0.5)
        assert d0 and d0.kullanilabilir(), getattr(d0, "hata", "doğal ses yok")
    yayinci = sunucu.Yayinci(ayar["goruntu"], ayar["bolge"])
    olaylar = yayinci.abone_ol()
    m = motor_modulu.AltyaziMotoru(ayar, yayinci, yazdir=False)
    try:
        m.baslat()
        for _ in range(300):
            if m.durum in ("calisiyor", "hata"):
                break
            time.sleep(0.1)
        assert m.durum == "calisiyor", m.hata
        time.sleep(1.0)
        t0[0] = time.time()
        while time.time() - t0[0] < TOPLAM:
            time.sleep(0.2)
        hata_sonda = m.hata
        durum_sonda = m.durum
    finally:
        m.durdur()
        if dogal:
            dogal_ses.kapat()
            seslendirme.Seslendirici._dogal_oynatici = None
        oyun_sesi.olustur = asil_olustur
        obs_ses = list(obs.ses_gecmisi)

    # --- overlay'e giden olaylardan her satırın ekranda kaldığı süre
    gosterim = {}   # id -> [tr, gösterildiği an, gizlendiği an]
    while True:
        try:
            o = olaylar.get_nowait()
        except queue.Empty:
            break
        if o["tip"] == "satir":
            gosterim.setdefault(o["id"], []).append(bool(o.get("temizlendi")))
    cevrilen = [g["en"] for g in m.gecmis]
    eksik = [s[2].replace("\n", " ") for s in SATIRLAR
             if not any(s[2].split("\n")[0][:18].lower() in c.lower() for c in cevrilen)]
    print(f"  okunan {m.sayac['okunan']}, çevrilen {m.sayac['cevrilen']}, sesli okunan {len(okunanlar)} / {len(SATIRLAR)} satır; "
          f"hız {m.hiz()}")
    for t, sure in okunanlar:
        print(f"    ses t={t:5.1f} sn, {sure:.1f} sn sürdü")
    assert durum_sonda == "calisiyor" and not hata_sonda, f"motor sonda çalışmıyor: {durum_sonda} {hata_sonda}"
    # OBS'in takıldığı anda ekranda olan satır kaçabilir; ötekilerin hepsi gelmeli
    takilan = [x[2].replace(chr(10), " ") for x in SATIRLAR if x[0] < TAKILMA[0] + TAKILMA[1] and x[0] + x[1] > TAKILMA[0]]
    eksik = [e for e in eksik if e not in takilan]
    assert not eksik, f"bu satırlar hiç çevrilmedi (ekrana gelmedi): {eksik}"
    assert any(len(g) >= 2 and g[-1] is False for g in gosterim.values()), f"parlamada kaybolup geri gelen satır yeniden gösterilmeli: {gosterim}"
    assert m.sayac["cevrilen"] >= len(SATIRLAR) - len(takilan), m.sayac
    # her okumanın, başladığı anda ekranda olan (ya da en son çıkmış) satıra göre gecikmesi
    gec = [round(t - max(b for b, _, _ in SATIRLAR if b <= t - 0.5), 1) for t, _ in okunanlar]
    print(f"  sesin satıra göre gecikmesi (sn): {gec}")
    assert len(okunanlar) >= len(SATIRLAR) - len(takilan) - 2, f"satırlar sesli okunmalı: {len(okunanlar)}/{len(SATIRLAR)}"
    assert max(gec) < 3.5, f"Türkçe ses geride kalıyor: {gec}"
    assert obs_ses and abs(obs_ses[-1]) < 0.01, f"oyunun sesi sonunda eski seviyesine dönmeli: {obs_ses[-4:]}"
    print("  ✓ yoğun diyalog: bütün satırlar ekrana geldi, çoğu sesli okundu, OBS takılınca bağlantı toparlandı")


if __name__ == "__main__":
    import sys
    test_yogun_diyalog(dogal="--dogal" in sys.argv)
