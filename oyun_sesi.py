"""Oyunun sesini dinler (konuşanı tanımak için): son birkaç saniyeyi bellekte tutar.

Ses diske yazılmaz, hiçbir yere gönderilmez; yalnızca konuşmacının sesinden
"kim konuşuyor / kadın mı erkek mi" çıkarmak için kullanılır.

Nereden dinlenir (config.dublaj.ses_kaynagi = "otomatik"):
- Konsol + OBS: capture card'ın kendi ses girişi (Windows'ta mikrofon gibi görünür).
  OBS kaynağının ayarındaki aygıt adından ya da "capture/elgato/hdmi" gibi adlardan bulunur.
- Bilgisayar oyunu ya da capture card sesi bulunamazsa: hoparlöre giden ses (loopback).
  Windows 10 2004+ ise **süreç loopback'i** kullanılır (surec_loopback.py): bizim süreç ağacımız
  hariç bütün ses, yani Türkçe okumamız kayda hiç girmez. Daha eski Windows'ta normal loopback
  kullanılır; okuduğumuz anlar `kendi_sesimiz` ile işaretlenip çözümlemeden çıkarılır.
"""
import threading
import time
import warnings

import numpy as np

ORNEK_HIZI = 16000
TAMPON_SN = 12
_BLOK = 800  # 50 ms

CAPTURE_KELIMELER = ("capture", "elgato", "avermedia", "live gamer", "game capture", "cam link", "hdmi",
                     "usb3.0", "usb 3.0", "digital audio interface", "video", "ezcap", "razer ripsaw",
                     "4k60", "hd60")


def _sc():
    import soundcard
    return soundcard


def aygitlar():
    """Panel için: [{'id','ad','tur'}] — tur: 'giris' (capture card / mikrofon) ya da 'hoparlor' (loopback)."""
    try:
        sc = _sc()
        liste = [{"id": m.id, "ad": m.name, "tur": "hoparlor" if m.isloopback else "giris"}
                 for m in sc.all_microphones(include_loopback=True)]
        return liste
    except Exception:
        return []


def _obs_aygit_adi(obs, kaynak_adi):
    """OBS'teki video yakalama kaynağının ses/görüntü aygıt adı (ör. 'USB3.0 HD Video')."""
    try:
        ayar = obs.istek("GetInputSettings", {"inputName": kaynak_adi}).get("inputSettings", {})
    except Exception:
        return []
    adlar = []
    for anahtar in ("audio_device_id", "video_device_id"):
        deger = ayar.get(anahtar) or ""
        ad = deger.split(":")[0].strip()
        if ad:
            adlar.append(ad.lower())
    return adlar


def otomatik_sec(senaryo, obs=None, kaynak_adi=""):
    """(aygıt id, açıklama, loopback mu). Hiçbiri yoksa (None, '', False)."""
    sc = _sc()
    if senaryo != "pc":
        girisler = [m for m in sc.all_microphones() if not m.isloopback]
        obs_adlari = _obs_aygit_adi(obs, kaynak_adi) if obs and kaynak_adi else []
        for m in girisler:  # OBS'in kullandığı aygıtla aynı adı taşıyan ses girişi
            ad = m.name.lower()
            if any(o and (o in ad or ad.split("(")[-1].rstrip(")").strip() in o) for o in obs_adlari):
                return m.id, m.name, False
        for m in girisler:
            if any(k in m.name.lower() for k in CAPTURE_KELIMELER):
                return m.id, m.name, False
    try:
        h = sc.default_speaker()
        return sc.get_microphone(h.id, include_loopback=True).id, h.name, True
    except Exception:
        return None, "", False


class OyunSesi:
    """Arka planda kaydeder; `parca(bas, bit)` istenen zaman aralığının sesini (16 kHz mono) verir."""

    def __init__(self, aygit_id, loopback=False, ad=""):
        self.aygit_id, self.loopback, self.ad = aygit_id, loopback, ad
        self.tampon = np.zeros(ORNEK_HIZI * TAMPON_SN, np.float32)
        self.yazilan = 0  # toplam örnek sayısı
        self.son_zaman = 0.0  # tampondaki son örneğin duvar saati
        self.kilit = threading.Lock()
        self.hata = ""
        self.seviye = 0.0  # son yarım saniyenin ses seviyesi (panelde "ses geliyor mu")
        self._kendi = []  # [(bas, bit)] bizim Türkçe okuduğumuz anlar (loopback'te çıkarılır)
        self.kendini_haric = False  # süreç loopback'i açıldıysa True: bizim sesimiz zaten kayıtta yok
        self._telafi = 1.0  # okurken oyunun sesi kısılıyorsa hoparlörden dinlenen ses de kısık gelir: geri çarpılır
        self._calisiyor = True
        self._thread = threading.Thread(target=self._dongu, daemon=True)
        self._thread.start()

    def _dongu(self):
        if self.loopback:
            try:
                import surec_loopback
                if surec_loopback.destekleniyor():
                    return self._surec_dongusu(surec_loopback)
            except Exception as e:
                print(f"[oyun sesi] süreç loopback'i açılamadı, normal loopback kullanılıyor: {e}", flush=True)
        try:
            sc = _sc()
            mik = sc.get_microphone(self.aygit_id, include_loopback=True)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")  # soundcard "data discontinuity" uyarıları
                with mik.recorder(samplerate=ORNEK_HIZI, channels=1, blocksize=_BLOK) as kayit:
                    while self._calisiyor:
                        d = kayit.record(numframes=_BLOK)
                        simdi = time.time()
                        d = np.asarray(d, np.float32).reshape(-1)
                        self._ekle(d, simdi)
        except Exception as e:
            self.hata = f"Oyun sesi dinlenemedi: {e}"
            print(f"[oyun sesi] {self.hata}", flush=True)

    def _surec_dongusu(self, surec_loopback):
        k = surec_loopback.SurecLoopback(ORNEK_HIZI)
        k.baslat()  # hata fırlatırsa _dongu normal loopback'e döner
        self.kendini_haric = True
        print("[oyun sesi] süreç loopback'i: kendi sesimiz hariç dinleniyor", flush=True)
        try:
            while self._calisiyor:
                d = k.oku(100)
                if len(d):
                    self._ekle(d, time.time())
        except Exception as e:
            self.hata = f"Oyun sesi dinlenemedi: {e}"
            print(f"[oyun sesi] {self.hata}", flush=True)
        finally:
            k.durdur()

    def kisik_carpan(self, carpan):
        """Ses kısıcı bildirir: oyunun sesi şu an `carpan` ile çarpılmış çalıyor (1.0 = kısık değil).
        Hoparlörden dinlenen ses uygulama seviyesinden SONRA alındığı için (ölçüldü) o da aynı oranda kısık gelir;
        konuşanı tanıma kısık sesle şaşmasın diye geri yükseltilir. Capture card girişi kısmadan etkilenmez."""
        self._telafi = 1.0 / max(0.05, min(1.0, float(carpan))) if self.loopback else 1.0

    def _ekle(self, d, simdi):
        n = len(d)
        if not n:
            return
        if self._telafi != 1.0:
            d = d * self._telafi
        with self.kilit:
            T = len(self.tampon)
            i = self.yazilan % T
            if i + n <= T:
                self.tampon[i:i + n] = d
            else:
                k = T - i
                self.tampon[i:] = d[:k]
                self.tampon[:n - k] = d[k:]
            self.yazilan += n
            self.son_zaman = simdi
            self.seviye = 0.8 * self.seviye + 0.2 * float(np.sqrt((d ** 2).mean()))

    def kendi_sesimiz(self, bas, bit):
        """Bu aralıkta biz konuştuk (yalnızca loopback'te önemli)."""
        if self.loopback and not self.kendini_haric:
            self._kendi = [a for a in self._kendi if a[1] > time.time() - TAMPON_SN] + [(bas, bit)]

    def parca(self, bas, bit):
        """[bas, bit] duvar saati aralığındaki ses; bizim konuştuğumuz anlar sıfırlanır."""
        with self.kilit:
            if not self.yazilan:
                return np.zeros(0, np.float32)
            T = len(self.tampon)
            eldeki = min(self.yazilan, T)
            ilk_zaman = self.son_zaman - eldeki / ORNEK_HIZI
            bas, bit = max(bas, ilk_zaman), min(bit, self.son_zaman)
            if bit <= bas:
                return np.zeros(0, np.float32)
            n = int((bit - bas) * ORNEK_HIZI)
            son = self.yazilan - int((self.son_zaman - bit) * ORNEK_HIZI)
            idx = (np.arange(son - n, son)) % T
            x = self.tampon[idx].copy()
        for kb, kbit in self._kendi:  # bizim sesimizi çıkar (+0,3 sn yankı payı)
            a = int((kb - bas) * ORNEK_HIZI)
            b = int((kbit + 0.3 - bas) * ORNEK_HIZI)
            if b > 0 and a < n:
                x[max(a, 0):min(b, n)] = 0
        return x

    def kapat(self):
        self._calisiyor = False
        self._thread.join(timeout=2)


def olustur(ayar, obs=None):
    """config'e göre OyunSesi; dinlenemiyorsa None (dublaj yine çalışır, tek sesle)."""
    d = ayar.get("dublaj", {})
    try:
        secim = d.get("ses_kaynagi", "otomatik")
        if secim and secim != "otomatik":
            sc = _sc()
            m = sc.get_microphone(secim, include_loopback=True)
            return OyunSesi(m.id, m.isloopback, m.name)
        aygit, ad, loopback = otomatik_sec(ayar.get("senaryo", ""), obs, ayar.get("obs", {}).get("kaynak_adi", ""))
        if not aygit:
            return None
        print(f"[oyun sesi] dinlenen: {ad}{' (hoparlör)' if loopback else ''}", flush=True)
        return OyunSesi(aygit, loopback, ad)
    except Exception as e:
        print(f"[oyun sesi] kullanılamıyor: {e}", flush=True)
        return None
