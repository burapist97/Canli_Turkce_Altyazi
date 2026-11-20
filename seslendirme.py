"""Türkçe sesli okuma ("dublaj"): çevrilen altyazıyı Windows'un Türkçe sesiyle okur.

TV'lerdeki "lektör" gibi çalışır; istenirse okurken OBS'teki oyun sesi biraz kısılır.
Karakter sesleri: konusmaci.py konuşanı tanır (ad etiketi, yazı rengi, oyunun sesi);
her kişiye bir ses profili verilir. Windows'ta tek Türkçe ses (Tolga, erkek) olduğundan
profiller ondan türetilir: perde SSML <prosody pitch> ile, tını (formant) yeniden
örnekleyerek kaydırılır. Kadın profilleri perdeyi ve tınıyı birlikte yükseltir.

Windows'un yerleşik sesleri kullanılır (ücretsiz, internetsiz). Türkçe ses yoksa
Ayarlar → Zaman ve dil → Konuşma → "Ses ekle" → Türkçe ile kurulur.
"""
import asyncio
import io
import json
import os
import queue
import re
import sys
import threading
import time
import wave
from xml.sax.saxutils import escape

import ceviri_hatti
import okunus
import veri

SES_AYARLARI_URL = "ms-settings:speech"

# ad: (perde %, tını çarpanı, görünen ad). Tını > 1 sesi inceltir (kadın/genç), < 1 kalınlaştırır.
SES_PROFILLERI = {
    "erkek1": (0, 1.0, "Erkek 1 (doğal)"),
    "erkek2": (-4, 0.90, "Erkek 2 (kalın)"),
    "erkek3": (-12, 1.08, "Erkek 3 (genç)"),
    "erkek4": (14, 1.0, "Erkek 4 (tiz)"),
    "kadin1": (20, 1.22, "Kadın 1"),
    "kadin2": (34, 1.15, "Kadın 2"),
    "kadin3": (26, 1.28, "Kadın 3 (genç)"),
}
VARSAYILAN_PROFIL = "erkek1"
# Türetilmiş sesin toplam tını kaydırması bu aralıkta kalır (dışında ses çizgi film gibi ya da boğuk olur)
TINI_SINIRI = (0.82, 1.30)

# --- Sesi konuşana uydurma (Windows sesi): dublaj sesi, konuşanın oyunda ölçülen perdesine (Hz) oturtulur ---
# Ölçüm (Microsoft Tolga, 18.11.2026): SSML perdesi %0'da 166,7 Hz; her %10 ≈ 1/12 oktav (2^(yüzde/120));
# ±%50'de doyar (125–221 Hz); konuşma süresi değişmez. Tını kaydırması (yeniden örnekleme) perdeyi de aynı oranda
# oynatır; ikisi birlikte ~105–285 Hz arasını verir. Başka seslerde değerler açılışta ölçülür (_Sentezci.kalibre).
PERDE_SINIRI = 50
VARSAYILAN_KALIBRASYON = (166.7, 1 / 120.0)  # (taban Hz, yüzde başına log2 oran)
KALIBRASYON_CUMLESI = "Bak, sana söylüyorum, bu iş göründüğü kadar kolay değil. Hadi, arabaya bin."
# Hedef perdeye göre tını: kalın ses -> büyük gövde (düşük tını), ince ses -> küçük gövde. (perde aralığı, tını aralığı)
HEDEF_TINI = {"erkek": ((100.0, 180.0), (0.86, 1.04)), "kadin": ((170.0, 260.0), (1.14, 1.28))}
# Aynı perdede bile iki kişi ayırt edilsin: profile göre küçük tını farkı. (erkek5+ ve kadin4+: doğal ses motorunda
# daha çok ses olduğunda dağıtılan profiller; o satır Windows sesine düşerse bunlar kullanılır.)
TINI_FARKI = {"erkek1": 0.0, "erkek2": -0.04, "erkek3": 0.04, "erkek4": -0.02, "erkek5": 0.02, "erkek6": -0.03,
              "erkek7": 0.03, "kadin1": 0.0, "kadin2": -0.04, "kadin3": 0.03, "kadin4": -0.02, "kadin5": 0.02}
_kalibrasyon = {}  # ses kimliği -> (taban Hz, yüzde başına log2 oran)
_KONUSMACI = re.compile(r"^\s*([A-Z][A-Za-z0-9 .'\-]{0,24}?)\s*:\s+(?=\S)")


def konusmaci_etiketi(metin):
    """("JASON", "Arabaya bin.") — satır konuşmacı adıyla başlıyorsa; yoksa (None, metin).
    Kural çeviridekiyle aynıdır (ceviri_hatti.etiket_ayir); burada ad sayılmaz."""
    onceki = dict(ceviri_hatti._gorulen_etiket)
    try:
        return ceviri_hatti.etiket_ayir(metin or "")
    finally:
        ceviri_hatti._gorulen_etiket.clear()
        ceviri_hatti._gorulen_etiket.update(onceki)


def _tini_kaydir(wav, carpan):
    """Perdeyi ve tınıyı birlikte `carpan` kadar kaydırır (süre 1/carpan olur; sentezde telafi edilir)."""
    if abs(carpan - 1.0) < 0.01:
        return wav
    import numpy as np
    w = wave.open(io.BytesIO(wav))
    p = w.getparams()
    x = np.frombuffer(w.readframes(p.nframes), np.int16).astype(np.float32)
    if p.nchannels > 1:
        x = x.reshape(-1, p.nchannels).mean(1)
    if carpan > 1:  # örtüşmeyi (aliasing) azaltmak için hafif alçak geçiren
        k = int(round(carpan * 2)) | 1
        x = np.convolve(x, np.ones(k) / k, "same") * 0.5 + x * 0.5
    y = np.interp(np.arange(0, len(x) - 1, carpan), np.arange(len(x)), x)
    o = io.BytesIO()
    v = wave.open(o, "wb")
    v.setnchannels(1)
    v.setsampwidth(2)
    v.setframerate(p.framerate)
    v.writeframes(np.clip(y, -32768, 32767).astype(np.int16).tobytes())
    v.close()
    return o.getvalue()


def wav_suresi(wav):
    try:
        w = wave.open(io.BytesIO(wav))
        return w.getnframes() / float(w.getframerate())
    except Exception:
        return 0.0


def _winrt():
    from winrt.windows.media.speechsynthesis import SpeechSynthesizer
    from winrt.windows.storage.streams import DataReader
    return SpeechSynthesizer, DataReader


def destekleniyor():
    if not sys.platform.startswith("win"):
        return False
    try:
        _winrt()
        return True
    except Exception:
        return False


def sesler():
    """[{'id','ad','dil'}] — bilgisayardaki tüm sesler, Türkçeler önce."""
    if not destekleniyor():
        return []
    SpeechSynthesizer, _ = _winrt()
    liste = [{"id": v.id, "ad": v.display_name, "dil": v.language} for v in SpeechSynthesizer.all_voices]
    return sorted(liste, key=lambda s: (not s["dil"].lower().startswith("tr"), s["ad"]))


def turkce_sesler():
    return [s for s in sesler() if s["dil"].lower().startswith("tr")]


class _Sentezci:
    """WinRT SpeechSynthesizer sarmalayıcı: metin -> WAV baytları."""

    def __init__(self, ses_id=""):
        SpeechSynthesizer, self._DataReader = _winrt()
        self.s = SpeechSynthesizer()
        secilen = [v for v in SpeechSynthesizer.all_voices if v.id == ses_id] or \
                  [v for v in SpeechSynthesizer.all_voices if v.language.lower().startswith("tr")]
        if not secilen:
            raise RuntimeError("Bilgisayarda Türkçe ses yok. Ayarlar → Konuşma → Ses ekle → Türkçe ile kurabilirsiniz.")
        self.s.voice = secilen[0]
        self.loop = asyncio.new_event_loop()

    def _ssml_wav(self, metin, perde, hiz_duzelt=0):
        """SSML perde (%) ve hız düzeltmesiyle (%) ham WAV."""
        ssml = (f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="tr-TR">'
                f'<prosody pitch="{int(perde):+d}%" rate="{int(hiz_duzelt):+d}%">{escape(metin)}</prosody></speak>')

        async def _al():
            akis = await self.s.synthesize_ssml_to_stream_async(ssml)
            okuyucu = self._DataReader(akis.get_input_stream_at(0))
            n = akis.size
            await okuyucu.load_async(n)
            b = bytearray(n)
            okuyucu.read_bytes(b)
            return bytes(b)
        return self.loop.run_until_complete(_al())

    def kalibre(self):
        """(taban perde Hz, SSML perde yüzdesi başına log2 oran) — bu ses için bir kez ölçülür (üç kısa sentez)."""
        kimlik = self.s.voice.id
        if kimlik not in _kalibrasyon:
            try:
                import math

                import numpy as np

                import ses_uyum
                olcum = {}
                for yuzde in (0, -40, 40):
                    w = wave.open(io.BytesIO(self._ssml_wav(KALIBRASYON_CUMLESI, yuzde)))
                    x = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
                    sr = w.getframerate()
                    if sr != 16000:
                        x = np.interp(np.arange(0, len(x), sr / 16000), np.arange(len(x)), x).astype(np.float32)
                    olcum[yuzde] = ses_uyum.perde_olc(x)
                taban, egim = olcum[0], math.log2(olcum[40] / olcum[-40]) / 80.0
                if not (60.0 < taban < 400.0 and 0.002 < egim < 0.03):
                    raise ValueError(f"beklenmeyen ölçüm: {olcum}")
                _kalibrasyon[kimlik] = (float(taban), float(egim))
            except Exception as e:
                print(f"[ses uyarlama] sesin perdesi ölçülemedi, varsayılan değerler kullanılıyor: {e}", flush=True)
                _kalibrasyon[kimlik] = VARSAYILAN_KALIBRASYON
        return _kalibrasyon[kimlik]

    def hedefe_gore(self, profil, hedef):
        """Dublaj sesi `hedef` perdesinde (Hz) çıksın diye gereken (SSML perde %, tını çarpanı).
        Çıkan perde = taban × 2^(yüzde × eğim) × tını. Sınırlara takılırsa en yakın değer verilir."""
        import math
        taban, egim = self.kalibre()
        (alt, ust), (t_alt, t_ust) = HEDEF_TINI["kadin" if (profil or "").startswith("kadin") else "erkek"]
        konum = min(1.0, max(0.0, (float(hedef) - alt) / (ust - alt)))
        tini = t_alt + konum * (t_ust - t_alt) + TINI_FARKI.get(profil, 0.0)
        tini = max(TINI_SINIRI[0], min(TINI_SINIRI[1], tini))
        yuzde = math.log2(float(hedef) / (taban * tini)) / egim
        return int(round(max(-PERDE_SINIRI, min(PERDE_SINIRI, yuzde)))), tini

    def wav(self, metin, hiz=1.0, seviye=1.0, profil=None, oran=1.0, hedef=None):
        """oran: ses uyarlamasının kaydırması; profilin tınısıyla çarpılır (perde ve formant birlikte).
        hedef: verilirse (Hz) ses bu perdeye oturtulur (sesi konuşana uydurma); profil yalnız kadın/erkek ve
        küçük tını farkı için kullanılır, oran yok sayılır."""
        # doğal ses motorunun fazladan profilleri (erkek5, kadin4...) Windows sesinde yok: cinsiyetin ilk profili
        if profil not in SES_PROFILLERI:
            profil_w = "kadin1" if (profil or "").startswith("kadin") else VARSAYILAN_PROFIL
        else:
            profil_w = profil
        perde, tini, _ = SES_PROFILLERI[profil_w]
        if hedef:
            perde, tini = self.hedefe_gore(profil or VARSAYILAN_PROFIL, hedef)
        else:
            tini = max(TINI_SINIRI[0], min(TINI_SINIRI[1], tini * (oran or 1.0)))
        try:
            self.s.options.speaking_rate = max(0.5, min(3.0, hiz))
            self.s.options.audio_volume = max(0.0, min(1.0, seviye))
        except Exception:
            pass  # eski Windows: varsayılan hız/ses
        hiz_duzelt = int(round((1 / tini - 1) * 100))  # tını kaydırması hızlandırır/yavaşlatır: telafi
        return _tini_kaydir(self._ssml_wav(metin, perde, hiz_duzelt), tini)


class Seslendirici:
    """Kuyruk her zaman en yeni satırı tutar; geride kalırsa hızlanır.
    Karakter sesleri açıksa her satırın konuşanı tanınır ve ona ayrılmış sesle okunur."""

    DINLEME_SN = 1.0  # altyazı çıktıktan sonra konuşanı tanımak için dinlenen süre (1,4 idi: her satır geç başlıyordu)
    BAYAT_SN = 7.0    # bu kadar önce çıkmış satır artık okunmaz (ekrandan çoktan kalktı; ilgisiz anda konuşmasın)
    EN_COK_HIZ = 1.9

    def _hiz(self, bas, atlanan):
        """Okuma hızı: ayardaki hız + geride kalındıkça artan pay. Türkçe okuma çoğu zaman İngilizce konuşmadan
        uzun sürer; hız sabit kalırsa her satır bir öncekinden daha geç başlar ve satırlar atlanır."""
        hiz = float(self.ayar.get("hiz", 1.15)) + (0.25 if atlanan else 0)
        if bas:
            hiz += min(0.45, max(0.0, time.time() - bas - 1.2) * 0.25)
        return min(self.EN_COK_HIZ, hiz)

    def __init__(self, ayar, kisici=None, cal=None, tanici=None, oyun_sesi=None, dogal=None):
        self.ayar = ayar  # config["dublaj"]
        self.dogal = dogal  # dogal_ses.DogalSes: hazırsa karakterler doğal yapay zekâ sesleriyle okunur
        self.kisici = kisici
        self._cal = cal or self._winsound_cal
        self.tanici = tanici
        self.oyun_sesi = oyun_sesi
        self.kuyruk = queue.Queue()
        self.hata = ""
        self.okunan = 0
        self.son_kisi = None
        self._thread = threading.Thread(target=self._dongu, daemon=True)
        self._thread.start()

    @staticmethod
    def _winsound_cal(wav):
        import winsound
        winsound.PlaySound(wav, winsound.SND_MEMORY | winsound.SND_NODEFAULT)

    def soyle(self, metin, bas=None, en=None, renk=None):
        """metin: Türkçe satır. bas: altyazının ekranda belirdiği an (time.time()).
        en: İngilizce asıl (ad etiketi için). renk: konusmaci.yazi_rengi()."""
        atlanan = 0
        while True:  # bekleyen eski satırları at: oyunun gerisinde kalmayalım
            try:
                self.kuyruk.get_nowait()
                atlanan += 1
            except queue.Empty:
                break
        self.kuyruk.put((metin, atlanan, bas, en, renk))

    def karakter_sesleri(self):
        return bool(self.tanici) and self.ayar.get("karakter_sesleri", True)

    def _profil_sec(self, metin, bas, en, renk):
        """(okunacak metin, ses profili)."""
        etiket, _ = konusmaci_etiketi(en or "")
        etiket_tr, okunacak = konusmaci_etiketi(metin)
        etiket = etiket or etiket_tr
        self._oran, self._hedef = 1.0, None
        if not self.karakter_sesleri():
            return okunacak, self.ayar.get("profil") or VARSAYILAN_PROFIL
        ses = None
        anahtar = f"ad:{etiket.upper()}" if etiket else renk
        taninan = bool(anahtar) and any(k.anahtar == anahtar and k.agirlik > 0 for k in list(self.tanici.kisiler))
        if self.oyun_sesi and bas and taninan:  # adından/renginden belli: beklemeden o ana kadarki sesi kullan
            ses = self.oyun_sesi.parca(bas - 0.4, time.time())
        elif self.oyun_sesi and bas:
            bitis = bas + self.DINLEME_SN
            bekle = bitis - time.time()
            if bekle > 0:
                time.sleep(min(bekle, self.DINLEME_SN))
                if not self.kuyruk.empty():
                    return None, None  # beklerken yeni satır geldi: bunu atla
            ses = self.oyun_sesi.parca(bas - 0.4, min(time.time(), bitis))
        try:
            kisi = self.tanici.tani(ses, anahtar)
        except Exception as e:
            print(f"[konuşmacı] {e}", flush=True)
            kisi = None
        self.son_kisi = kisi.ozet() if kisi else None
        self._oran = kisi.oran if kisi else 1.0
        # Windows sesi için hedef perde: konuşanın perdesi; elle "Kalın/İnce" ayarı hedefi de oynatır.
        # Kullanıcı kişiye belirli bir ses seçtiyse (sabit) o profil aynen okunur, perdeye uydurulmaz.
        if kisi and kisi.hedef and not kisi.sabit and self.ayar.get("ses_uyarla", True):
            self._hedef = kisi.hedef * (kisi.oran if kisi.elle else 1.0)
        return okunacak, (kisi.ses if kisi and kisi.ses else VARSAYILAN_PROFIL)

    _oran = 1.0
    _hedef = None
    ORNEK_CUMLE = KALIBRASYON_CUMLESI

    def _uyumlayici_kur(self, sentezci):
        """Sesi konuşana uydurmanın hazırlığı.
        - Windows sesi: perde doğrudan ayarlanabildiği için aday seçilmez; sesin taban perdesi bir kez ölçülür
          (_Sentezci.kalibre) ve her kişi kendi hedef perdesiyle (Konusmaci.hedef) okunur.
        - Doğal sesler (ısındıysa): her sesin açılışta üretilen örneği ölçülür; kişiye ses izi ve perdesi en yakın
          ses ve kaydırma oranı seçilir (ses_uyum.Uyumlayici)."""
        if not self.tanici:
            return
        import konusmaci
        import ses_uyum
        dogal = self.dogal if (self.dogal and self.ayar.get("dogal_ses", True) and self.dogal.kullanilabilir()) else None
        # Kişilere dağıtılacak profil sayısı: doğal ses motorunda kaç erkek/kadın sesi varsa o kadar (hepsi
        # kullanılsın); Windows sesinde 4 + 3.
        if dogal and dogal.sesler:
            self.tanici.havuz_ayarla(sum(1 for s in dogal.sesler if s["cinsiyet"] == "erkek"),
                                     sum(1 for s in dogal.sesler if s["cinsiyet"] == "kadin"))
        else:
            self.tanici.havuz_ayarla(len(konusmaci.ERKEK_SESLERI), len(konusmaci.KADIN_SESLERI))
        if not self.ayar.get("ses_uyarla", True):
            self.tanici.uyumlayici = None  # kapalı: kişiler sırayla verilen sesle, kaydırmasız okunur
            return
        hazir_olcum = dogal.uyum_verisi() if dogal else {}  # pakette gelen ölçümler (hafif motor)
        if not dogal or not (hazir_olcum or getattr(dogal, "ornekler", None)):
            self.tanici.uyumlayici = None
            self.uyum_kaynagi = "windows"
            if sentezci is not None:
                taban, egim = sentezci.kalibre()
                print(f"[ses uyarlama] Windows sesi konuşana uyduruluyor (taban {taban:.0f} Hz, "
                      f"ayarlanabilir aralık {taban * 2 ** (-PERDE_SINIRI * egim) * TINI_SINIRI[0]:.0f}–"
                      f"{taban * 2 ** (PERDE_SINIRI * egim) * TINI_SINIRI[1]:.0f} Hz)", flush=True)
            return
        u = ses_uyum.Uyumlayici(self.tanici)
        for profil in self.tanici.profiller():
            try:
                ses = dogal.ses_esle(profil)
                if not ses:
                    continue
                cins = "kadin" if profil.startswith("kadin") else "erkek"
                if ses["id"] in hazir_olcum:
                    u.hazir_ekle(profil, cins, hazir_olcum[ses["id"]])
                elif dogal.ornekler.get(ses["id"]) is not None:
                    u.ses_ekle(profil, cins, dogal.ornekler[ses["id"]], dogal.ornek_hizi)
            except Exception as e:
                print(f"[ses uyarlama] {profil} ölçümü alınamadı: {e}", flush=True)
        self.tanici.uyumlayici = u if u.hazir() else None
        self.uyum_kaynagi = "dogal"
        print(f"[ses uyarlama] {len(u.adaylar)} aday hazır (doğal sesler: {len(u.cinsiyet)} ses"
              f"{', ölçümler paketten' if hazir_olcum else ''})", flush=True)

    uyum_kaynagi = None

    def _dogal_oku(self, metin, profil):
        """Doğal ses sunucusu hazırsa onunla okur (True). Değilse ya da hata olursa False: Windows sesi okur."""
        d = self.dogal
        if not d or not self.ayar.get("dogal_ses", True) or not d.kullanilabilir():
            return False
        ses = d.ses_esle(profil)
        if not ses:
            return False
        t0 = time.time()
        try:
            if self.kisici:
                self.kisici.kis()
            motor = d.motor
            d.cal(metin, ses, float(self.ayar.get("seviye", 1.0)), self._dogal_oynatici, oran=self._oran)
            self.son_dogal_ses = ses["id"]
            self._okuyan("dogal:" + motor)
            return True
        except Exception as e:
            if type(e).__name__ == "KisaCikti":  # tek satırlık model hatası: sunucuyu kapatmaya gerek yok
                print(f"[doğal ses] {e}; bu satır Windows sesiyle", flush=True)
                return False
            d.hata_oldu(e)
            return False
        finally:
            if self.oyun_sesi:
                self.oyun_sesi.kendi_sesimiz(t0, time.time())

    son_okuyan = ""  # son satırı okuyan: "dogal:hafif" | "dogal:guclu" | "windows"
    _gorulen_degisim = 0

    def _okuyan(self, kim):
        """Okuyan ses değişince günlüğe yazar (ana sayfada da görünür): "kadın sesi robotik" gibi bir şikâyette hangi
        sesin okuduğu bilinsin. Windows sesi yalnız yedektir (doğal ses hazır değilken)."""
        if kim != self.son_okuyan:
            self.son_okuyan = kim
            d = self.dogal
            neden = f" (doğal ses durumu: {d.durum}{', ' + d.hata if d.hata else ''})" if (kim == "windows" and d) else ""
            print(f"[dublaj] okuyan ses: {kim}{neden}", flush=True)

    atlanan_bayat = 0
    _dogal_oynatici = None  # testlerde sahte oynatıcı verilir; None = hoparlör
    son_dogal_ses = None

    def _dongu(self):
        try:
            sentezci = _Sentezci(self.ayar.get("ses", ""))
        except Exception as e:
            self.hata = str(e)
            print(f"[dublaj kullanılamıyor] {e}", flush=True)
            sentezci = None
        if self.tanici:
            # Ses uyarlaması arka planda kurulur, satırlar beklemez. Önce Windows sesleriyle (hemen); doğal sesler
            # ısınınca (en çok ~3 dk beklenir) onların örnekleriyle yeniden.
            def _kur():
                try:
                    if sentezci is not None:
                        self._uyumlayici_kur(_Sentezci(self.ayar.get("ses", "")))
                    if self.dogal and self.ayar.get("dogal_ses", True):
                        for i in range(360):
                            if self.dogal.kullanilabilir() or (self.dogal.durum in ("hata", "kapali") and i > 20):
                                break
                            time.sleep(0.5)
                        if self.dogal.kullanilabilir():
                            self._uyumlayici_kur(None)
                except Exception as e:
                    print(f"[ses uyarlama] kurulamadı: {e}", flush=True)
            threading.Thread(target=_kur, daemon=True).start()
        while True:
            is_ = self.kuyruk.get()
            if is_ is None:
                break
            if sentezci is None and not (self.dogal and self.ayar.get("dogal_ses", True)):
                continue  # ne Windows sesi ne doğal ses: okunamaz
            metin, atlanan, bas, en, renk = is_
            try:
                if bas and time.time() - bas > self.BAYAT_SN:
                    self.atlanan_bayat += 1
                    continue
                okunacak, profil = self._profil_sec(metin, bas, en, renk)
                if okunacak is None or not okunacak.strip():
                    continue
                hiz = self._hiz(bas, atlanan)
                okunacak = okunus.okunus(okunacak)  # sayılar ve simgeler yazıyla
                d = self.dogal
                if d and getattr(d, "degisim", 0) != self._gorulen_degisim and d.kullanilabilir():
                    self._gorulen_degisim = d.degisim  # ses motoru değişti (güçlü -> hafif): ses eşlemesi yenilenir
                    try:
                        self._uyumlayici_kur(None)
                    except Exception as e:
                        print(f"[ses uyarlama] yenilenemedi: {e}", flush=True)
                if self._dogal_oku(okunacak, profil):
                    self.okunan += 1
                    self.hata = ""
                    continue
                if sentezci is None:
                    continue  # doğal ses bu satırı okuyamadı, Windows sesi de yok
                wav = sentezci.wav(okunacak, hiz, float(self.ayar.get("seviye", 1.0)), profil, self._oran, self._hedef)
                if self.kisici:
                    self.kisici.kis()
                if self.oyun_sesi:
                    t = time.time()
                    self.oyun_sesi.kendi_sesimiz(t, t + wav_suresi(wav))
                self._cal(wav)
                self.okunan += 1
                self._okuyan("windows")
            except Exception as e:
                self.hata = f"Sesli okuma hatası: {e}"
                print(f"[dublaj] {e}", flush=True)
            finally:
                # Arkadan yeni satır gelmişse sesi açıp kısmakla uğraşma
                if self.kisici and self.kuyruk.empty():
                    time.sleep(0.25)
                    if self.kuyruk.empty():
                        self.kisici.ac()

    def durdur(self):
        self.kuyruk.put(None)
        try:
            import winsound
            winsound.PlaySound(None, 0)
        except Exception:
            pass
        self._thread.join(timeout=3)
        if self.kisici:
            self.kisici.kapat()  # oyunun sesi hemen eski seviyesine
        if self.oyun_sesi:
            self.oyun_sesi.kapat()


class ObsSesKisici:
    """Türkçe ses okurken OBS'teki oyun sesini kısar, bitince eski seviyesine getirir.
    Eski seviye diske de yazılır: program o sırada çökerse bir sonraki açılışta düzeltilir."""

    def __init__(self, obs, kaynak, kisma_db=-14):
        self.obs, self.kaynak, self.kisma_db = obs, kaynak, kisma_db
        self.eski = None
        self.kilit = threading.Lock()
        self.carpan_degisti = None  # f(çarpan): hoparlörden dinleyen (oyun_sesi) kısık sesi telafi etsin

    @staticmethod
    def _kayit():
        return veri.veri_yolu("ses_geri_al.json")

    def _bildir(self, carpan):
        if self.carpan_degisti:
            try:
                self.carpan_degisti(carpan)
            except Exception:
                pass

    def kis(self):
        with self.kilit:
            if self.eski is not None:
                return
            try:
                self.eski = self.obs.ses_al(self.kaynak)
                with open(self._kayit(), "w", encoding="utf-8") as f:
                    json.dump({"kaynak": self.kaynak, "db": self.eski}, f)
                self.obs.ses_ayarla(self.kaynak, self.eski + self.kisma_db)
                self._bildir(10.0 ** (self.kisma_db / 20.0))
            except Exception as e:
                print(f"[oyun sesi kısılamadı] {e}", flush=True)
                self.eski = None

    def ac(self):
        with self.kilit:
            if self.eski is None:
                return
            try:
                self.obs.ses_ayarla(self.kaynak, self.eski)
                os.remove(self._kayit())
            except Exception as e:
                print(f"[oyun sesi geri açılamadı] {e}", flush=True)
            self.eski = None
            self._bildir(1.0)

    kapat = ac  # ses_kisici.SistemSesKisici ile aynı arayüz

    @classmethod
    def yarim_kalani_duzelt(cls, obs):
        """Önceki oturum oyun sesini kısık bıraktıysa geri aç."""
        yol = cls._kayit()
        if not os.path.exists(yol):
            return
        try:
            with open(yol, encoding="utf-8") as f:
                k = json.load(f)
            obs.ses_ayarla(k["kaynak"], k["db"])
            os.remove(yol)
        except Exception as e:
            print(f"[önceki oturumun sesi düzeltilemedi] {e}", flush=True)
