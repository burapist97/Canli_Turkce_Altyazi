"""Karakter sesleri: konuşanı tanıma ve ona göre ses seçme.

Gerçek sesle denenir: Windows'un İngilizce kadın sesi (Zira, SAPI) ve Türkçe erkek sesi (Tolga).
Oyun sesi sahtedir (hazır WAV parçası verir); Türkçe ses çalınmaz, yalnızca hangi profille
sentezlendiği kontrol edilir.
"""
import io
import os
import subprocess
import tempfile
import time
import wave

import cv2
import numpy as np

import yardimci  # noqa: F401  (proje yolu, CTA_VERI)
import konusmaci
import seslendirme


def _wav_oku(b):
    w = wave.open(io.BytesIO(b) if isinstance(b, bytes) else b)
    x = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    if w.getnchannels() > 1:
        x = x.reshape(-1, w.getnchannels()).mean(1)
    sr = w.getframerate()
    if sr != 16000:
        x = np.interp(np.arange(0, len(x), sr / 16000), np.arange(len(x)), x).astype(np.float32)
    return x


def zira(metin):
    """Windows'un İngilizce kadın sesi (SAPI 'Microsoft Zira Desktop'); yoksa None."""
    yol = os.path.join(tempfile.mkdtemp(), "z.wav")
    komut = ("Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
             "$k = $s.GetInstalledVoices() | ? { $_.VoiceInfo.Gender -eq 'Female' } | select -First 1; "
             "if (-not $k) { exit 3 }; $s.SelectVoice($k.VoiceInfo.Name); "
             f"$s.SetOutputToWaveFile('{yol}'); $s.Speak('{metin}'); $s.Dispose()")
    r = subprocess.run(["powershell", "-NoProfile", "-Command", komut], capture_output=True)
    if r.returncode != 0 or not os.path.exists(yol):
        return None
    return _wav_oku(yol)


def tolga(metin, profil="erkek1"):
    return _wav_oku(seslendirme._Sentezci().wav(metin, 1.0, 1.0, profil))


def test_yazi_rengi():
    kesit = np.zeros((80, 600, 3), np.uint8)
    cv2.putText(kesit, "Get in the car", (10, 55), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 3)
    maske = (kesit.max(2) > 185).astype(np.uint8) * 255
    assert konusmaci.yazi_rengi(kesit, maske) is None, "beyaz yazıda renk ipucu olmamalı"
    yesil = np.zeros_like(kesit)
    cv2.putText(yesil, "Get in the car", (10, 55), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (90, 220, 90), 3)
    m2 = (yesil.max(2) > 185).astype(np.uint8) * 255
    mavi = np.zeros_like(kesit)
    cv2.putText(mavi, "Get in the car", (10, 55), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (240, 190, 90), 3)
    m3 = (mavi.max(2) > 185).astype(np.uint8) * 255
    r2, r3 = konusmaci.yazi_rengi(yesil, m2), konusmaci.yazi_rengi(mavi, m3)
    assert r2 and r3 and r2 != r3, (r2, r3)
    print(f"  ✓ yazı rengi: beyaz=yok, yeşil={r2}, mavi={r3}")


def test_etiket():
    assert seslendirme.konusmaci_etiketi("JASON: Get in.") == ("JASON", "Get in.")
    assert seslendirme.konusmaci_etiketi("Lucia, get in the car.") == (None, "Lucia, get in the car.")
    assert seslendirme.konusmaci_etiketi("Note: this") == (None, "Note: this")  # büyük harfli değil
    print("  ✓ ad etiketi ayrılıyor, okunmuyor")


def test_tanima():
    if not konusmaci.model_var():
        raise AssertionError("modeller/konusmaci eksik")
    t = konusmaci.KonusmaciTanici()
    k_tolga = t.tani(tolga("Arabaya bin, hemen gitmemiz lazım. Polisler arkamızda, çabuk ol."))
    z = zira("Get in the car, we have to go right now. The cops are right behind us.")
    if z is None:
        print("  - Zira (kadın sesi) yok: kadın testi atlandı")
        return
    k_zira = t.tani(z)
    k_tolga2 = t.tani(tolga("Sakin ol, bataklığın içinden kestirme bir yol biliyorum."))
    k_zira2 = t.tani(zira("Relax, I know a shortcut through the swamp. Trust me on this one."))
    print(f"  kişiler: {t.liste()}")
    assert k_tolga.no != k_zira.no, "erkek ve kadın aynı kişi sanıldı"
    assert k_tolga2.no == k_tolga.no, "aynı erkek ikinci satırda tanınmadı"
    assert k_zira2.no == k_zira.no, "aynı kadın ikinci satırda tanınmadı"
    assert not k_tolga.kadin_mi and k_tolga.ses.startswith("erkek"), k_tolga.ozet()
    assert k_zira.kadin_mi and k_zira.ses.startswith("kadin"), k_zira.ozet()
    # ad etiketi: aynı ad hep aynı kişi, sessiz de olsa
    k_ad = t.tani(None, "ad:JASON")
    assert t.tani(None, "ad:JASON").no == k_ad.no and k_ad.no not in (k_tolga.no, k_zira.no)
    # ipucu yoksa: kimse
    assert t.tani(None, None) is None
    assert t.tani(np.zeros(16000, np.float32), None) is None, "sessizlikten kişi çıkmamalı"
    # kullanıcı elle değiştirirse kalıcı
    t.ses_degistir(k_zira.no, "kadin2")
    assert t.tani(z).ses == "kadin2"
    print("  ✓ kadın/erkek ayrıldı, aynı kişiler tekrar tanındı, ad etiketi ve elle seçim çalışıyor")


class _SahteOyunSesi:
    def __init__(self):
        self.ses = None
        self.kendi = []
        self.loopback = False
        self.ad, self.seviye, self.hata = "sahte", 0.1, ""

    def parca(self, bas, bit):
        return self.ses

    def kendi_sesimiz(self, a, b):
        self.kendi.append((a, b))

    def kapat(self):
        pass


def test_seslendirici():
    z = zira("Get in the car, we have to go right now. The cops are right behind us.")
    if z is None:
        print("  - Zira yok: atlandı")
        return
    t = konusmaci.KonusmaciTanici()
    sahte = _SahteOyunSesi()
    calinan = []
    secilen = []
    asil = seslendirme._Sentezci.wav

    def izle(self, metin, hiz=1.0, seviye=1.0, profil=None, oran=1.0, hedef=None):
        secilen.append((metin, profil))
        return asil(self, metin, hiz, seviye, profil, oran, hedef)
    seslendirme._Sentezci.wav = izle
    try:
        s = seslendirme.Seslendirici({"hiz": 1.2}, cal=calinan.append, tanici=t, oyun_sesi=sahte)
        s.DINLEME_SN = 0.2
        sahte.ses = z
        s.soyle("MIA: Arabaya bin.", bas=time.time(), en="MIA: Get in the car.")
        for _ in range(100):
            if calinan:
                break
            time.sleep(0.05)
        sahte.ses = tolga("Sakin ol, kestirme bir yol biliyorum, bana güven.")
        s.soyle("Sakin ol.", bas=time.time(), en="Relax.")
        for _ in range(100):
            if len(calinan) >= 2:
                break
            time.sleep(0.05)
        s.durdur()
    finally:
        seslendirme._Sentezci.wav = asil
    # ses uyarlamasının arka planda ürettiği örnek cümleler sayılmaz
    secilen = [x for x in secilen if x[0] != seslendirme.Seslendirici.ORNEK_CUMLE]
    print(f"  okunanlar: {secilen}")
    assert len(calinan) == 2, calinan
    assert secilen[0] == ("Arabaya bin.", "kadin1"), "ad etiketi okunmamalı, kadına kadın sesi"
    assert secilen[1][1].startswith("erkek"), secilen[1]
    assert len(sahte.kendi) == 2, "kendi okuduğumuz anlar işaretlenmeli"
    print("  ✓ Seslendirici: kadın satırı kadın sesiyle, erkek satırı erkek sesiyle okundu")


def _perdeli_ses(sentezci, metin, yuzde):
    """Aynı İngilizce cümle, yalnız perdesi değiştirilmiş (kalın/ince konuşmacı taklidi)."""
    from xml.sax.saxutils import escape
    xml = ('<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US">'
           f'<prosody pitch="{yuzde:+d}%">{escape(metin)}</prosody></speak>')

    async def al():
        a = await sentezci.s.synthesize_ssml_to_stream_async(xml)
        r = sentezci._DataReader(a.get_input_stream_at(0))
        await r.load_async(a.size)
        b = bytearray(a.size)
        r.read_bytes(b)
        return bytes(b)
    return _wav_oku(sentezci.loop.run_until_complete(al()))


def test_ses_uyarlama():
    """Duyulan sesin kalınlığına göre dublaj sesi: kalın konuşmacıya daha kalın, ince konuşmacıya daha ince ses."""
    import ses_uyum
    # akışta kaydırma: parça parça işlenince doğru frekans, parça sınırında sıçrama yok
    x = np.sin(2 * np.pi * 220 * np.arange(48000) / 48000).astype(np.float32)
    for oran in (0.88, 1.12):
        k = ses_uyum.AkisKaydirici(oran)
        y = np.concatenate([k.isle(x[i:i + 1777]) for i in range(0, len(x), 1777)])
        tepe = np.fft.rfftfreq(len(y), 1 / 48000)[np.argmax(np.abs(np.fft.rfft(y * np.hanning(len(y)))))]
        assert abs(tepe - 220 * oran) < 2 and np.abs(np.diff(y)).max() < 0.05, (oran, tepe)
    assert abs(ses_uyum.perde_olc(np.sin(2 * np.pi * 150 * np.arange(32000) / 16000).astype(np.float32)) - 150) < 3

    t = konusmaci.KonusmaciTanici()
    sentezci = seslendirme._Sentezci()
    TR = "Sakin ol, kestirme bir yol biliyorum. Polisler gelmeden buradan çıkmamız lazım."

    def dublaj_perdesi(profil, hedef):
        return ses_uyum.perde_olc(_wav_oku(sentezci.wav(TR, 1.15, 1.0, profil, 1.0, hedef)))

    # --- Windows sesi: taban perde ölçülür, dublaj istenen perdede çıkar (ölçerek doğrulanır)
    t0 = time.time()
    taban, egim = sentezci.kalibre()
    kalibre_sn = time.time() - t0
    assert 120 < taban < 260 and 0.004 < egim < 0.02, (taban, egim)
    assert sentezci.kalibre() == (taban, egim), "ölçüm bir kez yapılmalı"
    cikan = {}
    for profil, hedefler in (("erkek1", (110, 125, 145, 170)), ("kadin1", (185, 215, 250))):
        for hedef in hedefler:
            cikan[(profil, hedef)] = dublaj_perdesi(profil, hedef)
    print(f"  taban {taban:.0f} Hz (ölçüm {kalibre_sn * 1000:.0f} ms) | hedef -> çıkan: "
          + ", ".join(f"{h}->{p:.0f}" for (_, h), p in cikan.items()))
    for (profil, hedef), p in cikan.items():
        assert abs(np.log2(p / hedef)) < np.log2(1.07), f"{profil}: {hedef} Hz istendi, {p:.0f} Hz çıktı"
    # sınırların dışı: en yakın yapılabilir perde, hata yok
    assert dublaj_perdesi("erkek2", 70) < 120 and dublaj_perdesi("kadin2", 400) > 240

    # --- konuşmacıya göre: kalın sesli karakter kalın, ince sesli karakter ince okunur (doğal sesler yokken)
    s = seslendirme.Seslendirici.__new__(seslendirme.Seslendirici)
    s.tanici, s.ayar, s.dogal, s.oyun_sesi = t, {"dogal_ses": False}, None, None
    s._uyumlayici_kur(sentezci)
    assert t.uyumlayici is None and s.uyum_kaynagi == "windows"
    cumleler = ["Get in the car, we have to go right now.", "I know a shortcut through the swamp, trust me.",
                "The cops are right behind us, hurry up!", "We need to find a place to hide the money."]
    sonuc = {}
    for ad, yuzde in (("kalin", -40), ("ince", 20)):
        for i, m in enumerate(cumleler):
            kisi = t.tani(_perdeli_ses(sentezci, m, yuzde), "ad:" + ad.upper())
            if i == 0:
                assert kisi.hedef, "hedef perde ilk satırda belirlenmeli"
                ilk = kisi.hedef
        assert kisi.hedef == ilk, f"aynı kişinin sesi satırdan satıra değişmemeli: {ilk} -> {kisi.hedef}"
        sonuc[ad] = (kisi.perde, kisi.hedef, dublaj_perdesi(kisi.ses, kisi.hedef), kisi.ses)
    print("  konuşmacı perdesi -> hedef -> dublaj: " + " | ".join(
        f"{ad}: {a:.0f} -> {b:.0f} -> {c:.0f} Hz ({p})" for ad, (a, b, c, p) in sonuc.items()))
    for ad, (olculen, hedef, dublaj, profil) in sonuc.items():
        assert profil.startswith("erkek"), (ad, profil)
        beklenen = min(konusmaci.ERKEK_PERDE[1], max(konusmaci.ERKEK_PERDE[0], olculen))  # erkek sesi aralığında
        assert abs(np.log2(hedef / beklenen)) < np.log2(1.09), f"{ad}: hedef konuşanın perdesine yakın olmalı"
        assert abs(np.log2(dublaj / hedef)) < np.log2(1.07), f"{ad}: dublaj hedef perdede çıkmalı"
    assert sonuc["kalin"][2] < sonuc["ince"][2] / 1.2, "kalın ve ince konuşmacının dublaj sesleri belirgin ayrılmalı"

    # --- Seslendirici hedefi senteze iletir; "Sesi konuşana uydur" kapalıyken iletmez
    kalin = next(k for k in t.kisiler if k.anahtar == "ad:KALIN")
    s._profil_sec("KALIN: Sakin ol.", None, "KALIN: Relax.", None)
    assert s._hedef == kalin.hedef, (s._hedef, kalin.hedef)
    s.ayar["ses_uyarla"] = False
    s._profil_sec("KALIN: Sakin ol.", None, "KALIN: Relax.", None)
    assert s._hedef is None
    s.ayar["ses_uyarla"] = True

    # --- elle ayar: panelden "Kalın/İnce" hedefi oynatır, seçim kalıcıdır
    ince = next(k for k in t.kisiler if k.anahtar == "ad:INCE")
    t.ses_degistir(ince.no, ince.ses, 0.9)
    for m in cumleler:
        kisi = t.tani(_perdeli_ses(sentezci, m, 20), "ad:INCE")
    assert kisi.elle and not kisi.sabit and kisi.oran == 0.9, "elle seçilen kalınlık korunmalı"
    s._profil_sec("INCE: Sakin ol.", None, "INCE: Relax.", None)
    assert abs(s._hedef - kisi.hedef * 0.9) < 0.01, (s._hedef, kisi.hedef)
    # elle belirli bir ses seçilirse (burada kadın sesi) o ses AYNEN okunur: perdeye uydurulmaz
    t.ses_degistir(ince.no, "kadin1")
    assert ince.sabit and konusmaci.KADIN_PERDE[0] <= ince.hedef <= konusmaci.KADIN_PERDE[1], (ince.sabit, ince.hedef)
    okunacak, profil = s._profil_sec("INCE: Sakin ol.", None, "INCE: Relax.", None)
    assert (okunacak, profil, s._hedef) == ("Sakin ol.", "kadin1", None), (okunacak, profil, s._hedef)
    # "otomatik": elle ayar kalkar, kişi yeniden ölçülen cinsiyetine ve perdesine göre okunur
    t.ses_degistir(ince.no, "otomatik")
    assert not ince.elle and not ince.sabit and ince.oran == 1.0 and ince.ses.startswith("erkek"), ince.ozet()
    assert konusmaci.ERKEK_PERDE[0] <= ince.hedef <= konusmaci.ERKEK_PERDE[1], ince.hedef
    s._profil_sec("INCE: Sakin ol.", None, "INCE: Relax.", None)
    assert s._hedef == ince.hedef, (s._hedef, ince.hedef)

    # --- ayırt edilebilirlik: perdesi neredeyse aynı iki kişi aynı sesle okunmaz
    t2 = konusmaci.KonusmaciTanici()
    a, b, c = t2._yeni("ad:A"), t2._yeni("ad:B"), t2._yeni("ad:C")
    for k, p in ((a, 121.0), (b, 123.0), (c, 119.0)):
        k.perdeler = [p]
        t2._ses_ver(k)
        t2._hedef_ver(k)
    hedefler = sorted(k.hedef for k in (a, b, c))
    assert all(y / x >= konusmaci.PERDE_AYRIMI - 1e-6 for x, y in zip(hedefler, hedefler[1:])), hedefler
    assert all(abs(np.log2(h / 121.0)) < np.log2(1.20) for h in hedefler), f"ayrılırken perdeden çok uzaklaşmamalı: {hedefler}"
    assert len({a.ses, b.ses, c.ses}) == 3, "üç kişi üç ayrı profil almalı"
    # küçük ölçüm oynaması sesi değiştirmez; belirgin fark (yanlış ilk ölçüm) düzeltir
    eski = a.hedef
    a.perdeler = [121.0, 126.0, 118.0]
    t2._hedef_ver(a)
    assert a.hedef == eski
    a.perdeler = [121.0, 160.0, 162.0, 158.0, 161.0, 163.0, 159.0, 160.0]
    t2._hedef_ver(a)
    assert a.hedef > 145, a.hedef
    # perdesi ölçülemeyen (yalnız adından tanınan) kişiler: profilin varsayılanı, yine birbirinden ayrı
    t3 = konusmaci.KonusmaciTanici()
    adsiz = [t3.tani(None, f"ad:K{i}") for i in range(4)]
    hedefler = sorted(k.hedef for k in adsiz)
    assert all(k.hedef for k in adsiz) and all(y / x >= konusmaci.PERDE_AYRIMI - 1e-6 for x, y in zip(hedefler, hedefler[1:])), hedefler

    # --- doğal seslerde kullanılan aday seçimi (ses izi + perde) hâlâ çalışıyor
    u = ses_uyum.Uyumlayici(t)
    for profil in ("erkek1", "erkek2", "erkek4"):
        u.ses_ekle(profil, "erkek", _wav_oku(sentezci.wav(TR, 1.0, 1.0, profil)), 16000)
    assert len(u.adaylar) >= 12
    kalin_ses = _perdeli_ses(sentezci, cumleler[0], -40)
    ince_ses = _perdeli_ses(sentezci, cumleler[0], 30)
    secim = {ad: u.sec(t.gomme(x)[0], ses_uyum.perde_olc(x), "erkek") for ad, x in (("kalin", kalin_ses), ("ince", ince_ses))}
    assert u.perde(*secim["kalin"][:2]) < u.perde(*secim["ince"][:2]) - 8, secim
    print("  ✓ ses uyarlama: dublaj sesi konuşanın perdesinde çıkıyor, kişiler birbirinden ayrı, elle ayar kalıcı")


def test_ses_havuzu():
    """Doğal ses motorunda daha çok ses varsa kişilere dağıtılan profil havuzu büyür: bütün sesler kullanılır."""
    t = konusmaci.KonusmaciTanici()
    assert t.profiller() == ["erkek1", "erkek2", "erkek3", "erkek4", "kadin1", "kadin2", "kadin3"]
    t.havuz_ayarla(7, 5)  # hafif doğal ses motoru: 7 erkek + 5 kadın ses
    assert len(t.profiller()) == 12 and t.profiller()[6] == "erkek7" and t.profiller()[-1] == "kadin5"
    erkekler = [t.tani(anahtar=f"ad:ERKEK{i}").ses for i in range(7)]
    assert sorted(erkekler) == [f"erkek{i}" for i in range(1, 8)], erkekler  # yedi kişi, yedi ayrı ses
    assert t.tani(anahtar="ad:ERKEK7").ses in erkekler  # sekizinci kişi: sesler yeniden kullanılır
    t.sifirla()  # (tanıyıcı en çok 12 kişi tutar)
    kadinlar = []
    for i in range(5):
        with t.kilit:
            k = t._yeni(f"ad:KADIN{i}")
            k.kadin_toplam, k.agirlik = 1.0, 1.0
            t._ses_ver(k)
        kadinlar.append(k.ses)
    assert sorted(kadinlar) == [f"kadin{i}" for i in range(1, 6)], kadinlar
    # panelden kişiye havuzdaki herhangi bir ses verilebilir; "otomatik" eski haline döndürür
    no = t.tani(anahtar="ad:ERKEK0").no
    assert next(k for k in t.liste() if k["no"] == no)["ses"] == "erkek1"
    t.ses_degistir(no, "erkek6")
    kisi = next(k for k in t.liste() if k["no"] == no)
    assert kisi["ses"] == "erkek6" and kisi["sabit"] and kisi["elle"], kisi
    t.ses_degistir(no, "otomatik")
    kisi = next(k for k in t.liste() if k["no"] == no)
    assert kisi["ses"] == "erkek6" and not kisi["sabit"] and not kisi["elle"], kisi
    # Windows sesine dönülünce (4 + 3) havuz dışında kalan ses bir sonraki satırda havuzdan yenilenir
    t.havuz_ayarla(4, 3)
    assert t.tani(anahtar="ad:ERKEK0").ses in ("erkek1", "erkek2", "erkek3", "erkek4")
    # doğal ses bir satırı okuyamazsa Windows sesi fazladan profillerle (erkek7, kadin5) de okuyabilmeli
    if seslendirme.turkce_sesler():
        sentezci = seslendirme._Sentezci()
        for profil in ("erkek7", "kadin5"):
            assert seslendirme.wav_suresi(sentezci.wav("Arabaya bin.", 1.0, 1.0, profil)) > 0.3, profil
    print("  ✓ ses havuzu: 7 erkek + 5 kadın sese büyüdü, herkes ayrı ses aldı, Windows sesine dönünce küçüldü")


def test_konusmaci():
    test_yazi_rengi()
    test_etiket()
    test_tanima()
    test_seslendirici()
    test_ses_uyarlama()
    test_ses_havuzu()


if __name__ == "__main__":
    test_konusmaci()
