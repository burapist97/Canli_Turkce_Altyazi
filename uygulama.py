"""Canlı Türkçe Altyazı — masaüstü uygulaması (bilgisayar oyunları için).

Kendi penceresinde (WebView2) tek sayfalık arayüzü (arayuz.html) gösterir; pencere kapatılınca bildirim alanına
(tepsi.py) iner ve çalışmaya devam eder. Arayüz HTML'dir; arkada yerel bir JSON API çalışır (rastgele port + belirteç).

  python uygulama.py             -> pencereli uygulama
  python uygulama.py --kucuk     -> pencere açmadan tepside başlat (Windows ile başlat)
  python uygulama.py --tarayici  -> pencere yerine varsayılan tarayıcıda aç (geliştirme)
"""
import argparse
import base64
import copy
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# --veri <klasör>: ayar klasörü (CTA_VERI ile aynı). Paket (MSIX) bağlamında başlatılan sürece ortam değişkeni
# aktarılamadığı için var: duman testi kullanıcının gerçek ayar klasörüne dokunmadan çalıştırılabilsin.
# veri.py klasörü içe aktarılırken belirlediğinden, öteki modüllerden ÖNCE okunmalı.
if "--veri" in sys.argv[1:-1]:
    os.environ["CTA_VERI"] = os.path.abspath(sys.argv[sys.argv.index("--veri") + 1])
# --kapilar <altyazı>,<ses>: aynı nedenle (paket bağlamındaki deneme, açık olan programın kapılarıyla çakışmasın)
if "--kapilar" in sys.argv[1:-1]:
    os.environ["CTA_ALTYAZI_KAPISI"], os.environ["CTA_SES_KAPISI"] = sys.argv[sys.argv.index("--kapilar") + 1].split(",")

import cv2

import ceviri
import dogal_ses
import konusmaci
import motor
import obs_yardim
import ocr
import oyun_sesi
import pc_katman
import ses_deneme
import ses_kisici
import seslendirme
import sunucu
import tepsi
import veri
from kaynak import bolge_kes
from obs_baglanti import OBS, OBSHatasi

ORNEK_CUMLE = "Get in the car. The cops are right behind us!"
ORNEK_CEVIRI = "Arabaya bin. Polisler hemen arkamızda!"
BASLANGIC_ANAHTARI = r"Software\Microsoft\Windows\CurrentVersion\Run"
BASLANGIC_ADI = "CanliTurkceAltyazi"
SES_TURLERI = ("wasapi", "coreaudio", "pulse", "alsa", "audio")
IZINLI_ADRESLER = tuple(ceviri.ANAHTAR_SAYFALARI.values()) + (
    "https://obsproject.com/", seslendirme.SES_AYARLARI_URL,
)


def jpg_data_url(img, genislik=None, kalite=85):
    if genislik and img.shape[1] > genislik:
        img = cv2.resize(img, (genislik, int(img.shape[0] * genislik / img.shape[1])), interpolation=cv2.INTER_AREA)
    _, j = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, kalite])
    return "data:image/jpeg;base64," + base64.b64encode(j.tobytes()).decode()


def renk_mi(deger):
    return isinstance(deger, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", deger) is not None


def windows_ile_baslat(ac):
    """Windows açılınca programı tepside başlatır (ya da bunu kaldırır). Yalnız kurulu programda anlamlıdır."""
    if os.environ.get("CTA_KAYIT_YOK"):  # testler kayıt defterine dokunmasın
        return
    if not sys.platform.startswith("win"):
        raise RuntimeError("Bu ayar yalnızca Windows'ta çalışır.")
    if ac and not getattr(sys, "frozen", False):
        raise RuntimeError("Bu ayar yalnızca kurulu programda çalışır.")
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, BASLANGIC_ANAHTARI, 0, winreg.KEY_SET_VALUE) as anahtar:
        if ac:
            winreg.SetValueEx(anahtar, BASLANGIC_ADI, 0, winreg.REG_SZ, f'"{sys.executable}" --kucuk')
        else:
            try:
                winreg.DeleteValue(anahtar, BASLANGIC_ADI)
            except FileNotFoundError:
                pass


def acik_kopyayi_one_getir(port):
    """Program zaten açıksa (altyazı kapısı dolu) onun penceresini öne getirir. Başardıysa True."""
    import urllib.request
    try:
        istek = urllib.request.Request(f"http://127.0.0.1:{port}/pencere_ac", data=b"", method="POST")
        with urllib.request.urlopen(istek, timeout=3) as yanit:
            return yanit.read() == b"canli-turkce-altyazi"
    except Exception:
        return False


class Uygulama:
    def __init__(self):
        self.ayar = veri.ayar_yukle()
        # Görüntü kaynağı: bu bilgisayarın ekranı ("pc") ya da konsol + capture card + OBS ("konsol_obs").
        # (2.7.0-2.7.1'de yalnız ekran vardı; 2.7.2'de OBS arayüze geri geldi: Ekran ve altyazı alanı sayfası.)
        if self.ayar.get("senaryo") != "konsol_obs":
            self.ayar["senaryo"] = "pc"
        self.ayar["kaynak"]["tip"] = "obs" if self.ayar["senaryo"] == "konsol_obs" else "ekran"
        if os.environ.get("CTA_ALTYAZI_KAPISI"):  # denemeler: açık olan programın kapısıyla çakışmasın (kaydedilmez)
            self.ayar["goruntu"]["port"] = int(os.environ["CTA_ALTYAZI_KAPISI"])
        self.tepsi = None  # tepsi.Tepsi — yalnızca pencereli modda (main() kurar)
        self.obs = None
        self.kare = None
        self.ocr_hatasi = None
        self.overlay_hatasi = ""
        self.motor = None
        self.katman = None  # pc_katman.Katman — yalnızca pencereli modda (main() kurar)
        self.ana_pencere = None
        self.katman_notu = ""
        self.kilit = threading.Lock()
        self.yayinci = sunucu.Yayinci(self.ayar["goruntu"], self.ayar["bolge"], self.ayar.get("ek_bolgeler"))
        try:
            sunucu.sunucu_baslat(self.yayinci, self.ayar["goruntu"]["port"])
        except OSError as e:
            self.overlay_hatasi = str(e)
        self.yayinci.pencere_ac = self.pencereyi_goster
        threading.Thread(target=self._ocr_yukle, daemon=True).start()
        ses_kisici.yarim_kalani_duzelt()  # önceki çalışma oyunun sesini kısık bıraktıysa (çökme) geri aç
        dogal_ses.tercih_ayarla(self.ayar.get("dublaj", {}).get("dogal_motor", "otomatik"))

    def pencereyi_goster(self):
        if self.tepsi:
            self.tepsi.pencereyi_goster()

    def _ocr_yukle(self):
        try:
            motor.ocr_motoru_al(self.ayar)
        except Exception as e:
            self.ocr_hatasi = str(e)

    def _ocr(self):
        for _ in range(150):
            if self.ocr_hatasi:
                raise RuntimeError("Yazı okuma motoru yüklenemedi: " + self.ocr_hatasi)
            try:
                return motor.ocr_motoru_al(self.ayar)
            except Exception:
                time.sleep(0.1)
        raise RuntimeError("Yazı okuma motoru yüklenemedi.")

    def kaydet(self, motoru_yenile=False):
        veri.ayar_kaydet(self.ayar)
        self.yayinci.ayar_guncelle(self.ayar["goruntu"], self.ayar["bolge"], self.ayar.get("ek_bolgeler"))
        if motoru_yenile and self.motor and self.motor.durum in ("basliyor", "calisiyor"):
            # Çalışan motor ayarların eski kopyasını kullanıyor: yenisiyle yeniden başlat
            threading.Thread(target=self._yeniden_baslat, daemon=True).start()

    def _yeniden_baslat(self):
        with self.kilit:
            if self.motor:
                self.motor.durdur()
            try:
                self._katman_hazirla()  # oyunun ekranı değişmiş olabilir
            except Exception as e:
                print(f"[katman] {e}", flush=True)
            self.motor = motor.AltyaziMotoru(copy.deepcopy(self.ayar), self.yayinci, yazdir=False)
            self.motor.baslat()

    # ---------- genel ----------
    def durum(self, _):
        a = self.ayar
        c = a["ceviri"]
        return {
            "uygulama": veri.UYGULAMA_ADI, "surum": veri.SURUM,
            "obs": {**{k: v for k, v in a.get("obs", {}).items() if k != "sifre"}, "baglandi": bool(self.obs)},
            "bolge": a["bolge"], "goruntu": a["goruntu"],
            "ek_bolgeler": a.get("ek_bolgeler", []),
            "kaynak_tip": a["kaynak"]["tip"], "senaryo": a.get("senaryo", "konsol_obs"),
            "ekran_no": a["kaynak"].get("ekran_no", 1), "katman_notu": self.katman_notu,
            "dublaj": a.get("dublaj", {}),
            "anahtar_sayfalari": ceviri.ANAHTAR_SAYFALARI,
            "ceviri": {"motor": c["motor"], "yedek_motor": c.get("yedek_motor", ""),
                       "llm_url": c.get("llm_url", ""), "llm_model": c.get("llm_model", ""),
                       "anahtar_var": {**{k: bool(v) for k, v in c.get("anahtarlar", {}).items()},
                                       "cevrimdisi": ceviri.model_var()}},
            "motor_adlari": ceviri.MOTOR_ADLARI,
            "kurulum_tamam": a.get("kurulum_tamam", False),
            "overlay_url": f"http://127.0.0.1:{a['goruntu']['port']}",
            "overlay_hatasi": self.overlay_hatasi,
            "veri_klasoru": veri.VERI_KLASORU,
            "magaza": veri.MAGAZA,
            "tam_ekran": a.get("tam_ekran", {}),
            "hazir_gorunumler": veri.HAZIR_GORUNUMLER,
            "uygulama_ayar": {**a.get("uygulama", {}), "tepsi_var": bool(self.tepsi and self.tepsi.ikon),
                              "kurulu": bool(getattr(sys, "frozen", False))},
            "ornek": {"en": ORNEK_CUMLE, "tr": ORNEK_CEVIRI},
        }

    def tam_ekran_ayar(self, v):
        """Ne çevrilsin: seçilen alanlar (acik=False) ya da ekranın tamamı (tam_ekran.py)."""
        import tam_ekran
        t = self.ayar.setdefault("tam_ekran", {})
        if "acik" in v:
            t["acik"] = bool(v["acik"])
        if v.get("yerlesim") in tam_ekran.YERLESIMLER:
            t["yerlesim"] = v["yerlesim"]
        if "aralik" in v:
            try:
                t["aralik"] = max(0.3, min(5.0, float(v["aralik"])))
            except (TypeError, ValueError):
                pass
        self.kaydet(motoru_yenile=True)
        return {"tam_ekran": t}

    def uygulama_ayar(self, v):
        """Pencere küçültülünce simgeye in / Windows açılınca başlat."""
        u = self.ayar.setdefault("uygulama", {})
        if "tepsiye_kucult" in v:
            u["tepsiye_kucult"] = bool(v["tepsiye_kucult"])
        if "windows_ile_baslat" in v and not veri.MAGAZA:  # Store paketinde: Windows'un Başlangıç sayfası
            windows_ile_baslat(bool(v["windows_ile_baslat"]))
            u["windows_ile_baslat"] = bool(v["windows_ile_baslat"])
        self.kaydet()
        return {"uygulama_ayar": u}

    def baslangic_ayarlari(self, _):
        """Store sürümü: Windows'un "Başlangıç uygulamaları" sayfasını açar (program orada açılıp kapatılır)."""
        if not os.environ.get("CTA_KAYIT_YOK"):  # testler pencere açmasın
            os.startfile("ms-settings:startupapps")
        return {}

    def yazi_tipleri(self, _):
        """Bilgisayarda yüklü yazı tipleri (Görünüm > Yazı tipi > Bilgisayarımdaki bir yazı tipi)."""
        return {"yazi_tipleri": pc_katman.yuklu_yazi_tipleri()}

    def disari_ac(self, v):
        url = str(v.get("url", ""))
        if not url.startswith(IZINLI_ADRESLER):
            raise ValueError("Bu adres açılamaz.")
        webbrowser.open(url)
        return {}

    def sorun_raporu(self, _):
        """Sorun bildirirken gönderilecek tek dosya: günlükler, ayarlar (anahtarlar ve şifre SİLİNMİŞ) ve o anki durum.
        Masaüstüne yazılır ve klasörü açılır. Altyazı metinleri günlükte geçer; ses ya da görüntü içermez."""
        import zipfile
        hedef_klasor = os.environ.get("CTA_RAPOR_KLASORU") or os.path.join(os.path.expanduser("~"), "Desktop")
        if not os.path.isdir(hedef_klasor):
            hedef_klasor = veri.VERI_KLASORU
        hedef = os.path.join(hedef_klasor, f"CanliTurkceAltyazi_sorun_raporu_{time.strftime('%Y%m%d_%H%M')}.zip")
        ayar = copy.deepcopy(self.ayar)
        for k in list(ayar.get("ceviri", {}).get("anahtarlar", {})):
            ayar["ceviri"]["anahtarlar"][k] = "(var)" if ayar["ceviri"]["anahtarlar"][k] else ""
        if ayar.get("obs", {}).get("sifre"):
            ayar["obs"]["sifre"] = "(var)"
        durum = {"surum": veri.SURUM, "zaman": time.strftime("%Y-%m-%d %H:%M:%S"), "windows": sys.getwindowsversion()[:3]
                 if hasattr(sys, "getwindowsversion") else None, "program_klasoru": veri.KLASOR,
                 "veri_klasoru": veri.VERI_KLASORU, "bos_bellek_gb": dogal_ses.bos_bellek_gb()}
        try:
            durum["motor"] = self.motor_ozet(None)
        except Exception as e:
            durum["motor"] = f"okunamadı: {e}"
        try:
            d = dogal_ses.paylasilan(baslat=False)
            durum["dogal_ses"] = d.ozet() if d else None
        except Exception as e:
            durum["dogal_ses"] = f"okunamadı: {e}"
        try:
            sys.stdout.flush()
        except Exception:
            pass
        with zipfile.ZipFile(hedef, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("ayarlar.json", json.dumps(ayar, ensure_ascii=False, indent=2))
            z.writestr("durum.json", json.dumps(durum, ensure_ascii=False, indent=2, default=str))
            for ad in ("gunluk.txt", "gunluk.txt.eski", "ses_sunucusu.log", "model_secimi.json"):
                yol = os.path.join(veri.VERI_KLASORU, ad)
                if os.path.exists(yol):
                    try:
                        with open(yol, "rb") as f:
                            z.writestr(ad, f.read()[-3_000_000:])
                    except OSError:
                        pass
        if sys.platform.startswith("win") and not os.environ.get("CTA_PENCERE_ACMA"):
            subprocess.Popen(["explorer", "/select,", hedef])
        return {"dosya": hedef}

    # ---------- OBS ----------
    def obs_baglan(self, v):
        if self.obs:
            self.obs.kapat()
            self.obs = None
        port = int(v.get("port") or 4455)
        sifre = (v.get("sifre") or "").strip()
        self.obs = OBS(port=port, sifre=sifre)
        self.ayar.setdefault("obs", {}).update({"port": port, "sifre": sifre})
        if self.ayar.get("kurulum_tamam"):
            self.kaydet()
        return {}

    def _obs(self):
        if not self.obs:
            raise OBSHatasi("Önce OBS'e bağlanın.")
        return self.obs

    def obs_kaynaklar(self, _):
        obs = self._obs()
        liste = []
        for k in obs.kaynaklar():
            if any(t in k["inputKind"] for t in SES_TURLERI) or k["inputName"] == "Türkçe Altyazı":
                continue
            try:
                resim = jpg_data_url(obs.goruntu(k["inputName"], 400), kalite=75)
            except OBSHatasi:
                continue  # görüntüsü olmayan kaynak
            liste.append({"ad": k["inputName"], "resim": resim,
                          "puan": obs_yardim.capture_card_puani(k["inputName"], k["inputKind"])})
        en_iyi = max(liste, key=lambda x: x["puan"], default=None)
        onerilen = en_iyi["ad"] if en_iyi and en_iyi["puan"] > 0 else ""
        return {"kaynaklar": liste, "secili": self.ayar.get("obs", {}).get("kaynak_adi", ""), "onerilen": onerilen}

    def obs_otomatik(self, _):
        """OBS kurulu mu / açık mı / WebSocket açık mı — ve mümkünse şifre sormadan bağlan."""
        sonuc = {"kurulu": obs_yardim.obs_kurulu_mu(), "acik": obs_yardim.obs_acik_mi(),
                 "websocket": None, "baglandi": bool(self.obs), "hata": ""}
        ws = obs_yardim.websocket_ayari()
        if ws:
            sonuc["websocket"] = {"etkin": ws["etkin"], "port": ws["port"]}
        if self.obs:
            return sonuc
        denenecek = []
        if ws and ws["etkin"]:
            denenecek.append((ws["port"], ws["sifre"]))
        o = self.ayar.get("obs", {})
        if o.get("sifre") or not denenecek:
            denenecek.append((o.get("port", 4455), o.get("sifre", "")))
        for port, sifre in denenecek:
            try:
                self.obs_baglan({"port": port, "sifre": sifre})
                sonuc["baglandi"] = True
                sonuc["acik"] = True
                break
            except OBSHatasi as e:
                sonuc["hata"] = str(e)
        return sonuc

    def obs_monitorler(self, _):
        liste = []
        for m in self._obs().monitorler():
            ad = str(m.get("monitorName", "")).rsplit("(", 1)[0].strip() or f"Ekran {m['monitorIndex'] + 1}"
            liste.append({"index": m["monitorIndex"], "ad": ad, "genislik": m.get("monitorWidth"),
                          "yukseklik": m.get("monitorHeight"), "x": m.get("monitorPositionX", 0),
                          "y": m.get("monitorPositionY", 0)})
        return {"monitorler": liste, "secili": self.ayar["obs"].get("projektor_monitor")}

    def obs_projektor_ac(self, v):
        idx = int(v["index"])
        self._obs().projektor_ac(idx)
        self.ayar["obs"]["projektor_monitor"] = idx
        if self.ayar.get("kurulum_tamam"):
            self.kaydet()
        return {}

    def senaryo_sec(self, v):
        if v.get("senaryo") not in ("konsol_obs", "pc"):
            raise ValueError("Bilinmeyen kurulum türü.")
        self.ayar["senaryo"] = v["senaryo"]
        self.ayar["kaynak"]["tip"] = "ekran" if v["senaryo"] == "pc" else "obs"
        self.kare = None
        if self.ayar.get("kurulum_tamam"):
            self.kaydet(motoru_yenile=True)
        return {}

    # ---------- bilgisayar oyunu: ekran ----------
    def _ekran_karesi(self, no):
        """Ekranı yakalar; bizim pencere oyunun önünde olsa bile arkasındaki oyunu görmek için
        yakalama süresince ana pencereyi yakalamaya görünmez yap."""
        hwnd = pc_katman.pencere_kolu(self.ana_pencere) if self.ana_pencere else 0
        gizlendi = pc_katman.yakalamadan_gizle(hwnd, True)
        try:
            if gizlendi:
                time.sleep(0.15)  # bir ekran yenilemesi beklensin
            return pc_katman.ekran_goruntusu(no)
        finally:
            if gizlendi and not self._pc_calisiyor():
                pc_katman.yakalamadan_gizle(hwnd, False)

    def _pc_calisiyor(self):
        return bool(self.motor and self.motor.durum in ("basliyor", "calisiyor")
                    and self.ayar["kaynak"]["tip"] == "ekran")

    def ekran_listesi(self, _):
        liste = []
        for e in pc_katman.ekranlar():
            try:
                resim = jpg_data_url(self._ekran_karesi(e["no"]), 400, 75)
            except Exception:
                resim = ""
            liste.append({**e, "resim": resim})
        # Birden çok ekranda yeni kurulumda tahmin etme; kullanıcı oyunun ekranını kendi seçsin
        secili = (self.ayar["kaynak"].get("ekran_no") if self.ayar["kaynak"]["tip"] == "ekran"
                  and self.ayar.get("kurulum_tamam") else None)
        if len(liste) == 1:
            secili = 1
        return {"ekranlar": liste, "secili": secili}

    def ekran_sec(self, v):
        no = int(v["no"])
        if not any(e["no"] == no for e in pc_katman.ekranlar()):
            raise ValueError("Bu ekran bulunamadı.")
        self.ayar["kaynak"].update({"tip": "ekran", "ekran_no": no})
        self.kare = None
        if self.ayar.get("kurulum_tamam"):
            self.kaydet(motoru_yenile=True)
        return {}

    # ---------- dublaj ----------
    def dublaj_durum(self, _):
        destek = seslendirme.destekleniyor()
        return {"destek": destek, "sesler": seslendirme.sesler() if destek else [],
                "turkce_var": bool(seslendirme.turkce_sesler()) if destek else False,
                "ayar": self.ayar.get("dublaj", {}),
                "profiller": [{"id": k, "ad": v[2]} for k, v in seslendirme.SES_PROFILLERI.items()],
                "karakter_destek": konusmaci.model_var(),
                "aygitlar": oyun_sesi.aygitlar() if destek else []}

    def dublaj_kisiler(self, _):
        """Tanınan konuşanlar ve verilen sesler (motor yeniden başlasa da korunur)."""
        t = konusmaci._paylasilan
        s = self.motor.seslendirici if self.motor else None
        kisiler = t.liste() if t else []
        d = dogal_ses._paylasilan
        # Kişiye elle verilebilecek sesler: doğal sesler kullanılıyorsa onların adlarıyla (her profil bir doğal sese
        # karşılık gelir), değilse Windows sesinden türetilen profiller
        secenekler = [{"id": k, "ad": v[2]} for k, v in seslendirme.SES_PROFILLERI.items()]
        if d and d.kullanilabilir() and self.ayar.get("dublaj", {}).get("dogal_ses", True):
            for k in kisiler:  # doğal ses açıksa kişinin hangi doğal sesle okunduğu da görünsün
                e = d.ses_esle(k.get("ses"))
                k["dogal_ad"] = e["ad"] if e else None
            profiller = t.profiller() if t else list(seslendirme.SES_PROFILLERI)
            secenekler = []
            for p in profiller:
                e = d.ses_esle(p)
                if e:
                    secenekler.append({"id": p, "ad": f"{e['ad']} · {'kadın' if e['cinsiyet'] == 'kadin' else 'erkek'}"})
        return {"kisiler": kisiler, "son": s.son_kisi if s else None, "sesler": secenekler}

    # ---------- doğal sesler (uygulamayla gelen hafif motor; isteğe bağlı güçlü motor ayrı pakettir) ----------
    def dogal_durum(self, _):
        d = dogal_ses.paylasilan(baslat=False)
        if not d:
            return {"kurulu": False, "durum": "kapali", "sesler": [], "klasorler": dogal_ses.kurulum_klasorleri(),
                    "hafif_var": False, "guclu_var": False, "motor": None}
        return d.ozet()

    def dogal_baslat(self, _):
        d = dogal_ses.paylasilan(baslat=False)
        if not d:
            raise RuntimeError("Doğal sesler bu kurulumda yok.")
        threading.Thread(target=d.baslat, daemon=True).start()
        return {}

    def dogal_dinle(self, v):
        """Bir doğal sesi dinletir. Ses sunucusu kapalıysa önce açar (hafif motor ~10 sn'de açılır); yanıt o zaman
        döner. Açılamazsa nedeni (ör. boş bellek yok) hata olarak gelir."""
        d = dogal_ses.paylasilan(baslat=False)
        if not d:
            raise RuntimeError("Doğal sesler bu kurulumda yok.")
        ses = next((s for s in d.sesler if s["id"] == v.get("id")), None)
        if not ses:
            raise ValueError("Bu ses bulunamadı.")
        if not d.kullanilabilir():
            if d.durum in ("kapali", "hata"):
                d.baslat(90)
            son = time.time() + 90
            while not d.kullanilabilir() and d.durum in ("basliyor", "hazir") and time.time() < son:
                time.sleep(0.25)
            if not d.kullanilabilir():
                raise RuntimeError(d.hata or "Doğal sesler henüz hazır değil. Biraz bekleyip tekrar deneyin.")
        metin = (v.get("metin") or "").strip() or "Arabaya bin, polisler hemen arkamızda! Bu sefer kaçamayız."
        seviye = float(self.ayar.get("dublaj", {}).get("seviye", 1.0))
        threading.Thread(target=lambda: self._dogal_cal(d, metin, ses, seviye), daemon=True).start()
        return {}

    @staticmethod
    def _dogal_cal(d, metin, ses, seviye):
        try:
            d.cal(metin, ses, seviye)
        except Exception as e:
            d.hata_oldu(e)

    # ---------- ses motorlarını karşılaştırma (deneme; ses_deneme.py) ----------
    def ses_deneme_durum(self, _):
        return ses_deneme.durum()

    def ses_deneme_indir(self, v):
        if veri.MAGAZA:
            raise ValueError("Ses motoru denemeleri Store sürümünde yok.")
        ses_deneme.indir(str(v.get("id", "")))
        return {}

    def ses_deneme_dinle(self, v):
        """Seçilen modelle cümleyi üretip çalar; yanıt çalma bitince döner (ölçümle birlikte)."""
        if self.motor and self.motor.durum in ("basliyor", "calisiyor"):
            raise RuntimeError("Altyazı çalışırken ses denemesi yapılamıyor: deneme modelleri ekran kartını yoğun kullanır; "
                               "oyunla ya da canlı seslendirmeyle aynı anda çalışınca ekran kartı sürücüsü "
                               "kilitlenebiliyor. Önce Ana sayfadan Durdur'a basın.")
        seviye = float(self.ayar.get("dublaj", {}).get("seviye", 1.0))
        olcum = ses_deneme.dinle(str(v.get("id", "")), v.get("metin"), v.get("ses"), seviye, v.get("abarti"))
        return {"olcum": olcum}

    def ses_deneme_kapat(self, _):
        ses_deneme.kapat()
        return {}

    def dublaj_kisi_ses(self, v):
        t = konusmaci._paylasilan
        if not t or (v.get("ses") != "otomatik" and v.get("ses") not in seslendirme.SES_PROFILLERI
                     and v.get("ses") not in t.profiller()):
            raise ValueError("Bu kişi ya da ses bulunamadı.")
        t.ses_degistir(int(v["no"]), v["ses"], v.get("oran"))
        return {}

    def dublaj_kisileri_sifirla(self, _):
        if konusmaci._paylasilan:
            konusmaci._paylasilan.sifirla()
        return {}

    def dublaj_ses_dene(self, v):
        """Oyunun sesi duyuluyor mu? 2 sn dinler (motor çalışıyorsa onun dinleyicisine bakar)."""
        s = self.motor.seslendirici if self.motor else None
        if s and s.oyun_sesi:
            o = s.oyun_sesi
            return {"ad": o.ad, "hoparlor": o.loopback, "seviye": o.seviye, "hata": o.hata}
        ayar = copy.deepcopy(self.ayar)
        if "ses_kaynagi" in v:
            ayar.setdefault("dublaj", {})["ses_kaynagi"] = v["ses_kaynagi"]
        dinleyici = oyun_sesi.olustur(ayar, self.obs)
        if not dinleyici:
            raise RuntimeError("Bu bilgisayarda dinlenecek ses aygıtı bulunamadı.")
        try:
            en_yuksek = 0.0
            for _ in range(20):
                time.sleep(0.1)
                en_yuksek = max(en_yuksek, dinleyici.seviye)
            return {"ad": dinleyici.ad, "hoparlor": dinleyici.loopback, "seviye": en_yuksek, "hata": dinleyici.hata}
        finally:
            dinleyici.kapat()

    def dublaj_kaydet(self, v):
        d = self.ayar.setdefault("dublaj", {})
        if "acik" in v:
            d["acik"] = bool(v["acik"])
        if "ses" in v:
            d["ses"] = str(v["ses"] or "")
        if "hiz" in v:
            d["hiz"] = max(0.8, min(2.0, float(v["hiz"])))
        if "seviye" in v:
            d["seviye"] = max(0.1, min(1.0, float(v["seviye"])))
        if "okurken_kis" in v:
            d["okurken_kis"] = bool(v["okurken_kis"])
        if "kisma_db" in v:
            d["kisma_db"] = max(-24.0, min(-3.0, float(v["kisma_db"])))
        if "karakter_sesleri" in v:
            d["karakter_sesleri"] = bool(v["karakter_sesleri"])
        if "ses_kaynagi" in v:
            d["ses_kaynagi"] = str(v["ses_kaynagi"] or "otomatik")
        if "dogal_ses" in v:
            d["dogal_ses"] = bool(v["dogal_ses"])
            if not d["dogal_ses"]:
                dogal_ses.kapat()  # kapatıldı: ses sunucusu belleği (hafif ~2 GB, güçlü ~5 GB) boşaltsın
        if v.get("dogal_motor") in ("otomatik", "hafif", "guclu"):
            d["dogal_motor"] = v["dogal_motor"]
            dogal_ses.gecici_hafifi_sifirla()  # kullanıcı modeli kendisi seçti: güçlü model yeniden denenir
            dogal_ses.tercih_ayarla(d["dogal_motor"])
        if "ses_uyarla" in v:
            d["ses_uyarla"] = bool(v["ses_uyarla"])
        if self.ayar.get("kurulum_tamam"):
            self.kaydet(motoru_yenile=True)
        return {}

    def dublaj_dinle(self, v):
        self.dublaj_kaydet({k: v[k] for k in ("ses", "hiz", "seviye") if k in v})
        d = dict(self.ayar.get("dublaj", {}))
        metin = (v.get("metin") or "").strip() or "Arabaya bin, polisler hemen arkamızda!"
        try:
            sentezci = seslendirme._Sentezci(d.get("ses", ""))
            profil = v.get("profil") if v.get("profil") in seslendirme.SES_PROFILLERI else None
            wav = sentezci.wav(metin, float(d.get("hiz", 1.15)), float(d.get("seviye", 1.0)), profil)
        except Exception as e:
            raise RuntimeError(str(e))
        threading.Thread(target=seslendirme.Seslendirici._winsound_cal, args=(wav,), daemon=True).start()
        return {}

    def kaynak_sec(self, v):
        self.ayar["obs"]["kaynak_adi"] = v["ad"]
        self.ayar["kaynak"]["tip"] = "obs"
        self.kare = None
        if self.ayar.get("kurulum_tamam"):
            self.kaydet(motoru_yenile=True)
        return {}

    def goruntu(self, _):
        if self.ayar["kaynak"]["tip"] == "ekran":
            self.kare = self._ekran_karesi(self.ayar["kaynak"].get("ekran_no", 1))
        else:
            obs = self._obs()
            ad = self.ayar["obs"].get("kaynak_adi")
            if not ad:
                raise OBSHatasi("Önce oyun görüntüsünü seçin.")
            self.kare = obs.goruntu(ad, self.ayar["obs"].get("goruntu_genislik"))
        h, w = self.kare.shape[:2]
        return {"resim": jpg_data_url(self.kare, 1280), "boyut": [w, h], "bolge": self.ayar["bolge"]}

    def altyazi_ekle(self, v):
        g = self.ayar["goruntu"]
        for k in ("orijinali_kapat", "ingilizce_goster"):
            if k in v:
                g[k] = bool(v[k])
        sahne = self._obs().altyazi_ekle(f"http://127.0.0.1:{g['port']}")
        return {"sahne": sahne}

    # ---------- bölge ----------
    def _bolge(self, v):
        return {k: round(min(1.0, max(0.0, float(v["bolge"][k]))), 4) for k in ("x", "y", "w", "h")}

    def okuma_testi(self, v):
        self.ayar["bolge"] = self._bolge(v)
        if self.kare is None:
            raise OBSHatasi("Önce görüntüyü yenileyin.")
        o = self.ayar["ocr"]
        kesit = bolge_kes(self.kare, self.ayar["bolge"])
        if kesit.size == 0:
            raise ValueError("Seçilen alan boş. Altyazının etrafına bir kutu çizin.")
        maske = ocr.yazi_maskesi(kesit, o["parlaklik_esigi"], o.get("kontur_gerekli", True))
        metin = ocr.oku(self._ocr(), kesit, maske, o.get("buyutme", 1.0))
        return {"metin": metin, "anlamli": ocr.anlamli_mi(metin),
                "kesit": jpg_data_url(kesit, 900), "maske": jpg_data_url(cv2.cvtColor(maske, cv2.COLOR_GRAY2BGR), 900)}

    def bolge_bul(self, _):
        if self.ayar["kaynak"]["tip"] == "ekran" or (self.obs and self.ayar["obs"].get("kaynak_adi")):
            self.goruntu(None)  # en güncel kare
        if self.kare is None:
            raise OBSHatasi("Önce görüntüyü yenileyin.")
        s = ocr.altyazi_bolgesi_bul(self._ocr(), self.kare)
        if not s:
            raise ValueError("Ekranda altyazı bulamadım. Oyunda bir İngilizce altyazı çıktığı anda oyunu durdurun ve tekrar deneyin.")
        self.ayar["bolge"], metin = s
        # Altyazının bulunduğu kareyi geri ver: yeniden çekilen karede altyazı çoktan kaybolmuş olabilir
        return {"bolge": s[0], "metin": metin, "resim": jpg_data_url(self.kare, 1280)}

    EN_FAZLA_EK_ALAN = 6

    def alanlar_kaydet(self, v):
        """Ek çeviri alanları: [{ad, x, y, w, h, seslendir}] (ana altyazı alanı ayrı: bolge)."""
        temiz = []
        for b in (v.get("ek_bolgeler") or [])[: self.EN_FAZLA_EK_ALAN]:
            k = self._bolge({"bolge": b})
            if k["w"] < 0.02 or k["h"] < 0.015:
                continue
            k["ad"] = str(b.get("ad") or f"Alan {len(temiz) + 2}")[:40]
            k["seslendir"] = bool(b.get("seslendir", False))
            if isinstance(b.get("gorunum"), dict):  # alanın kendi görünümü (alan_gorunum) korunur
                k["gorunum"] = self._gorunum_uygula({}, b["gorunum"])
                k["gorunum"].pop("altyazi_goster", None)
            temiz.append(k)
        self.ayar["ek_bolgeler"] = temiz
        self.kaydet(motoru_yenile=True)
        return {"ek_bolgeler": temiz}

    def alan_okuma_testi(self, v):
        """Çizilen alandaki yazıyı okuyup çevirir (panelde 'Dene')."""
        if self.kare is None:
            raise RuntimeError("Önce oyun görüntüsü alınmalı.")
        b = self._bolge(v)
        kesit = bolge_kes(self.kare, b)
        o = self.ayar["ocr"]
        maske = ocr.yazi_maskesi(kesit, o["parlaklik_esigi"], o.get("kontur_gerekli", True))
        import ceviri_hatti
        metin = ceviri_hatti.ocr_onar(ocr.oku(self._ocr(), kesit, maske, o.get("buyutme", 1.0)))
        return {"metin": metin}

    def bolge_kaydet(self, v):
        self.ayar["bolge"] = self._bolge(v)
        if self.ayar.get("kurulum_tamam"):
            self.kaydet(motoru_yenile=True)
        return {}

    # ---------- çeviri ----------
    def ceviri_ayarla(self, v):
        c = self.ayar["ceviri"]
        c.setdefault("anahtarlar", {})
        if v.get("motor"):
            if v["motor"] not in ceviri.MOTOR_ADLARI:
                raise ValueError("Bilinmeyen çeviri motoru.")
            c["motor"] = v["motor"]
        if "yedek_motor" in v:
            c["yedek_motor"] = v["yedek_motor"] or ""
        self._yerel_model_ayari(c, v)
        for ad, anahtar in (v.get("anahtarlar") or {}).items():
            if ad in ceviri.MOTOR_ADLARI and anahtar is not None:
                c["anahtarlar"][ad] = str(anahtar).strip()
        if self.ayar.get("kurulum_tamam"):
            self.kaydet(motoru_yenile=True)
        return {}

    @staticmethod
    def _yerel_model_ayari(c, v):
        """Bilgisayardaki yapay zekâ (Ollama vb.): model adı ve adresi. Adres yalnız bu bilgisayarı gösterebilir."""
        if v.get("llm_model"):
            c["llm_model"] = str(v["llm_model"]).strip()[:120]
        if v.get("llm_url"):
            adres = str(v["llm_url"]).strip()
            if not re.match(r"^https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?/", adres):
                raise ValueError("Adres bu bilgisayarı göstermeli (ör. http://localhost:11434/v1/chat/completions).")
            c["llm_url"] = adres[:300]

    def ceviri_testi(self, v):
        """Motoru (varsa yeni anahtarla) gerçek bir cümleyle dener. Seçili motor ve anahtar ancak deneme başarılı
        olursa değişir: başarısız bir deneme, çalışan çeviriyi bozuk bir motorla değiştirmemeli."""
        c = copy.deepcopy(self.ayar["ceviri"])
        c.setdefault("anahtarlar", {})
        for motor_adi, anahtar in (v.get("anahtarlar") or {}).items():
            if motor_adi in ceviri.MOTOR_ADLARI and anahtar is not None:
                c["anahtarlar"][motor_adi] = str(anahtar).strip()
        self._yerel_model_ayari(c, v)
        ad = v.get("test_motor") or v.get("motor") or c["motor"]
        if ad not in ceviri.MOTOR_ADLARI:
            raise ValueError("Bilinmeyen çeviri motoru.")
        try:
            m = ceviri.tek_motor(ad, c, ceviri.sozluk_yukle())
        except ceviri.CeviriHatasi as e:
            raise ValueError(str(e))
        metin = (v.get("metin") or "").strip() or ORNEK_CUMLE
        t0 = time.time()
        sonuc = m.cevir(metin, [])
        sure_ms = int((time.time() - t0) * 1000)
        self.ceviri_ayarla(v)
        return {"metin": metin, "ceviri": sonuc, "sure_ms": sure_ms, "model": getattr(m, "model", "")}

    # ---------- görünüm ----------
    def mod_sec(self, v):
        """Ana ekrandaki seçim: 'altyazi' (yalnızca Türkçe yazı), 'ikisi' (yazı + Türkçe ses), 'ses' (yalnızca ses)."""
        mod = v.get("mod")
        if mod not in ("altyazi", "ikisi", "ses"):
            raise ValueError("Bilinmeyen seçim.")
        if mod != "altyazi" and not (seslendirme.destekleniyor() and seslendirme.turkce_sesler()) \
                and not dogal_ses.var_mi():
            raise RuntimeError("Bu bilgisayarda Türkçe ses yok. Türkçe ses sayfasından ekleyebilirsiniz.")
        self.ayar.setdefault("dublaj", {})["acik"] = mod != "altyazi"
        self.ayar["goruntu"]["altyazi_goster"] = mod != "ses"
        self.kaydet(motoru_yenile=True)
        return {"mod": mod}

    def gorunum_kaydet(self, v):
        """Altyazının görünümü. Geçersiz değerler yok sayılır (eski değer kalır); sınırlar ve seçenekler veri.py'deki
        GORUNUM_* tanımlarıyla, onlar da altyazi_stil.js ile aynıdır."""
        g = self._gorunum_uygula(self.ayar["goruntu"], v)
        self.kaydet()
        # Ayar yapılırken sonuç oyunun üstünde de görünsün; ekranda gerçek bir altyazı varsa ona dokunulmaz
        if v.get("ornek") and g.get("altyazi_goster", True) and not self.yayinci.son_satirlar.get(0):
            self.ornek_goster(None)
        return {"goruntu": g}

    @staticmethod
    def _gorunum_uygula(g, v):
        """v'deki geçerli görünüm değerlerini g'ye yazar (ana altyazının ya da bir ek alanın görünümü)."""
        for k, (az, cok) in veri.GORUNUM_SINIRLARI.items():
            if k not in v:
                continue
            try:
                d = float(v[k])
            except (TypeError, ValueError):
                continue
            if d != d:  # NaN
                continue
            d = max(az, min(cok, d))
            g[k] = int(round(d)) if k == "yazi_boyutu" else int(round(d / 100.0) * 100) if k == "yazi_kalinligi" \
                else round(d, 4)
        for k, secenekler in veri.GORUNUM_SECENEKLERI.items():
            if v.get(k) in secenekler:
                g[k] = v[k]
        for k in veri.GORUNUM_ACKAPA:
            if k in v:
                g[k] = bool(v[k])
        for k in veri.GORUNUM_RENKLERI:
            if renk_mi(v.get(k)):
                g[k] = v[k].lower()
        if "etiket_rengi" in v:  # konuşmacı adının rengi; boş: yazıyla aynı
            g["etiket_rengi"] = v["etiket_rengi"].lower() if renk_mi(v["etiket_rengi"]) else ""
        if "yazi_tipi_ozel" in v:
            g["yazi_tipi_ozel"] = re.sub(r"[\"'\\;{}<>]", "", str(v["yazi_tipi_ozel"] or ""))[:80]
        if v.get("kutu") in veri.ESKI_KUTU:  # eski arayüzün "kutu" seçimi
            g["kutu_saydamlik"] = veri.ESKI_KUTU[v["kutu"]]
        if g.get("yazi_tipi") == "ozel" and not g.get("yazi_tipi_ozel"):
            g["yazi_tipi"] = "standart"
        return g

    def alan_gorunum(self, v):
        """Bir ek alanın (2., 3. ... çeviri alanı) kendi görünümü: yeri, boyutu, rengi, arka planı ana altyazıdan ayrı
        ayarlanabilir. no: 1'den başlar (ek_bolgeler sırası). gorunum yoksa (null) alan varsayılana döner: kendi
        yerinde, üstü kapalı, ana altyazının yazı tipi ve rengiyle."""
        ekler = self.ayar.get("ek_bolgeler") or []
        try:
            alan = ekler[int(v.get("no")) - 1]
            if int(v.get("no")) < 1:
                raise IndexError
        except (TypeError, ValueError, IndexError):
            raise ValueError("Bu alan bulunamadı.")
        if isinstance(v.get("gorunum"), dict):
            g = self._gorunum_uygula({}, v["gorunum"])
            g.pop("altyazi_goster", None)  # yazıyı göster / gizle bütün alanlar için ortaktır
            alan["gorunum"] = g
        else:
            alan.pop("gorunum", None)
        self.kaydet()
        if v.get("ornek") and self.ayar["goruntu"].get("altyazi_goster", True) \
                and not self.yayinci.son_satirlar.get(int(v["no"])):
            self.yayinci.gonder({"tip": "satir", "id": -2, "alan": int(v["no"]), "en": ORNEK_CUMLE, "tr": ORNEK_CEVIRI,
                                 "temizlendi": True})
        return {"ek_bolgeler": ekler}

    def ornek_goster(self, _):
        self.yayinci.gonder({"tip": "satir", "id": -2, "en": ORNEK_CUMLE, "tr": ORNEK_CEVIRI, "temizlendi": True})
        return {}

    # ---------- kurulum bitti ----------
    def bitir(self, _):
        self.ayar["kurulum_tamam"] = True
        self.kaydet(motoru_yenile=True)
        return {}

    # ---------- motor ----------
    def motor_baslat(self, _):
        with self.kilit:
            if self.motor and self.motor.durum in ("basliyor", "calisiyor"):
                return {}
            ses_deneme.kapat()  # deneme modeli ekran kartını ve belleği oyuna / canlı sese bıraksın
            if self.overlay_hatasi:
                raise RuntimeError(self.overlay_hatasi)
            self._katman_hazirla()
            self.motor = motor.AltyaziMotoru(copy.deepcopy(self.ayar), self.yayinci, yazdir=False)
            self.motor.baslat()
        return {}

    def _katman_hazirla(self):
        """Bilgisayar oyunu modunda Türkçe altyazı penceresini oyunun ekranında aç (diğer modlarda kapat)."""
        if self.ayar["kaynak"]["tip"] != "ekran":
            self._katman_kapat()
            return
        hwnd = pc_katman.pencere_kolu(self.ana_pencere) if self.ana_pencere else 0
        pc_katman.yakalamadan_gizle(hwnd, True)  # panel oyunun önündeyse onu okumayalım
        if not self.katman:
            return  # --tarayici (geliştirme): katman penceresi yok
        no = self.ayar["kaynak"].get("ekran_no", 1)
        ekran = next((e for e in pc_katman.ekranlar() if e["no"] == no), None)
        if not ekran:
            raise RuntimeError(f"{no} numaralı ekran bulunamadı. Kaynak ve alan bölümünden oyunun ekranını seçin.")
        if self.katman.ac(ekran) is False:
            # Eski Windows: katman yakalamadan gizlenemiyor. Orijinal altyazının üstünü kapatırsak
            # kendi Türkçemizi okuruz; Türkçeyi orijinalin üstüne yaz.
            self.katman_notu = ("Windows sürümünüz eski olduğu için Türkçe yazı, İngilizce altyazının üstüne "
                                "yazılıyor (kapatılamıyor). Windows'u güncellerseniz bu düzelir.")
            if self.ayar["goruntu"].get("orijinali_kapat"):
                self.ayar["goruntu"]["orijinali_kapat"] = False
                self.kaydet()

    def _katman_kapat(self):
        if self.katman:
            self.katman.kapat()
        if self.ana_pencere:
            pc_katman.yakalamadan_gizle(pc_katman.pencere_kolu(self.ana_pencere), False)

    def motor_durdur(self, _):
        with self.kilit:
            if self.motor:
                self.motor.durdur(bekle=False)
            self._katman_kapat()
        return {}

    def motor_ozet(self, _):
        if not self.motor:
            return {"durum": "durdu", "hata": "", "ceviri_hatasi": "", "gecmis": [], "sayac": {"okunan": 0, "cevrilen": 0},
                    "motor": self.ayar["ceviri"]["motor"]}
        return self.motor.ozet()

    def kapat(self):
        if self.motor:
            self.motor.durdur()
        if self.katman:
            self.katman.kapat()
        if self.obs:
            self.obs.kapat()
        dogal_ses.kapat()  # bizim başlattığımız ses sunucusu ekran kartını boşaltsın
        ses_deneme.kapat()


DOSYALAR = {"/altyazi_stil.js": "text/javascript; charset=utf-8", "/arayuz.js": "text/javascript; charset=utf-8",
            "/arayuz.css": "text/css; charset=utf-8"}


def api_sunucusu(uyg, belirtec):
    yollar = {
        "/api/durum": uyg.durum, "/api/disari_ac": uyg.disari_ac, "/api/sorun_raporu": uyg.sorun_raporu,
        "/api/obs/baglan": uyg.obs_baglan, "/api/obs/kaynaklar": uyg.obs_kaynaklar,
        "/api/obs/kaynak_sec": uyg.kaynak_sec, "/api/obs/altyazi_ekle": uyg.altyazi_ekle,
        "/api/obs/otomatik": uyg.obs_otomatik, "/api/obs/monitorler": uyg.obs_monitorler,
        "/api/obs/projektor_ac": uyg.obs_projektor_ac, "/api/senaryo": uyg.senaryo_sec,
        "/api/ekran/listesi": uyg.ekran_listesi, "/api/ekran/sec": uyg.ekran_sec,
        "/api/bolge_bul": uyg.bolge_bul, "/api/alanlar/kaydet": uyg.alanlar_kaydet,
        "/api/alanlar/dene": uyg.alan_okuma_testi, "/api/alan_gorunum": uyg.alan_gorunum,
        "/api/dublaj/durum": uyg.dublaj_durum, "/api/dublaj/kaydet": uyg.dublaj_kaydet,
        "/api/dublaj/dinle": uyg.dublaj_dinle, "/api/dublaj/kisiler": uyg.dublaj_kisiler,
        "/api/dublaj/kisi_ses": uyg.dublaj_kisi_ses, "/api/dublaj/kisileri_sifirla": uyg.dublaj_kisileri_sifirla,
        "/api/dublaj/ses_dene": uyg.dublaj_ses_dene, "/api/dogal/durum": uyg.dogal_durum,
        "/api/dogal/baslat": uyg.dogal_baslat, "/api/dogal/dinle": uyg.dogal_dinle,
        "/api/ses_deneme/durum": uyg.ses_deneme_durum, "/api/ses_deneme/indir": uyg.ses_deneme_indir,
        "/api/ses_deneme/dinle": uyg.ses_deneme_dinle, "/api/ses_deneme/kapat": uyg.ses_deneme_kapat,
        "/api/goruntu": uyg.goruntu, "/api/okuma_testi": uyg.okuma_testi, "/api/bolge_kaydet": uyg.bolge_kaydet,
        "/api/ceviri_ayarla": uyg.ceviri_ayarla, "/api/ceviri_testi": uyg.ceviri_testi,
        "/api/gorunum_kaydet": uyg.gorunum_kaydet, "/api/mod": uyg.mod_sec, "/api/ornek_goster": uyg.ornek_goster,
        "/api/bitir": uyg.bitir, "/api/tam_ekran": uyg.tam_ekran_ayar, "/api/uygulama_ayar": uyg.uygulama_ayar, "/api/yazi_tipleri": uyg.yazi_tipleri,
        "/api/baslangic_ayarlari": uyg.baslangic_ayarlari,
        "/api/motor/baslat": uyg.motor_baslat, "/api/motor/durdur": uyg.motor_durdur,
        "/api/motor/ozet": uyg.motor_ozet,
    }
    sayfalar = {"/": "arayuz.html"}

    class Isleyici(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _yanit(self, kod, govde, tur="application/json; charset=utf-8"):
            self.send_response(kod)
            self.send_header("Content-Type", tur)
            self.send_header("Content-Length", str(len(govde)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(govde)

        def do_GET(self):
            yol = self.path.split("?")[0]
            if yol in sayfalar:
                with open(veri.kaynak(sayfalar[yol]), "rb") as f:
                    self._yanit(200, f.read(), "text/html; charset=utf-8")
            elif yol in DOSYALAR:
                with open(veri.kaynak(yol[1:]), "rb") as f:
                    self._yanit(200, f.read(), DOSYALAR[yol])
            else:
                self._yanit(404, b"{}")

        def do_POST(self):
            # Belirteç: başka bir web sayfası bu yerel API'ye istek atamasın
            if not secrets.compare_digest(self.headers.get("X-Belirtec", ""), belirtec):
                return self._yanit(403, b'{"ok":false,"hata":"izin yok"}')
            n = int(self.headers.get("Content-Length") or 0)
            try:
                gelen = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                gelen = {}
            yol = self.path.split("?")[0]
            if yol not in yollar:
                return self._yanit(404, b"{}")
            try:
                sonuc = yollar[yol](gelen) or {}
                sonuc.setdefault("ok", True)
            except Exception as e:
                sonuc = {"ok": False, "hata": str(e)}
            self._yanit(200, json.dumps(sonuc, ensure_ascii=False).encode("utf-8"))

    s = ThreadingHTTPServer(("127.0.0.1", 0), Isleyici)
    s.daemon_threads = True
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s


def gunluk_ac():
    """Pencereli (konsolsuz) derlemede print/hata çıktısı kaybolmasın: gunluk.txt'ye yaz."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    yol = veri.veri_yolu("gunluk.txt")
    try:
        if os.path.exists(yol) and os.path.getsize(yol) > 1_000_000:
            os.replace(yol, yol + ".eski")
        f = open(yol, "a", encoding="utf-8", buffering=1)
        f.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')}  {veri.UYGULAMA_ADI} {veri.SURUM} =====\n")
        sys.stdout = sys.stderr = f
    except OSError:
        pass


_kopya_isareti = None


def kopya_isareti_koy():
    """Windows'a "program açık" işareti bırakır (adlandırılmış mutex). Kurulum/kaldırma programı (paket/kurulum.iss
    AppMutex) bu işareti görünce "önce programı kapatın" der: program tepside çalışırken dosyaları değiştirilemez."""
    global _kopya_isareti
    if sys.platform.startswith("win") and _kopya_isareti is None:
        import ctypes
        _kopya_isareti = ctypes.windll.kernel32.CreateMutexW(None, False, "CanliTurkceAltyaziCalisiyor")


def main():
    gunluk_ac()
    ap = argparse.ArgumentParser()
    ap.add_argument("--tarayici", action="store_true", help="Pencere yerine tarayıcıda aç")
    ap.add_argument("--kucuk", action="store_true", help="Pencereyi açmadan tepside başlat")
    ap.add_argument("--deneme", action="store_true", help="Pencereyi aç, yüklendiğini doğrula, kapat")
    ap.add_argument("--veri", metavar="KLASÖR", help="Ayar klasörü (denemelerde gerçek ayarlara dokunmamak için)")
    ap.add_argument("--kapilar", metavar="ALTYAZI,SES", help="Denemelerde kullanılacak kapılar (açık programla çakışmasın)")
    args = ap.parse_args()

    uyg = Uygulama()
    if uyg.overlay_hatasi and not args.tarayici and not args.deneme \
            and acik_kopyayi_one_getir(uyg.ayar["goruntu"]["port"]):
        sys.exit(0)  # program zaten açık (tepside): onun penceresi öne geldi
    belirtec = secrets.token_urlsafe(24)
    s = api_sunucusu(uyg, belirtec)
    url = f"http://127.0.0.1:{s.server_address[1]}/#{belirtec}"

    if args.tarayici:
        print("Arayüz:", url, flush=True)
        webbrowser.open(url)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    else:
        import webview
        if not args.deneme:
            kopya_isareti_koy()
        pencere = webview.create_window(veri.UYGULAMA_ADI, url, width=1240, height=860, min_size=(980, 660),
                                        background_color="#0b0d12", hidden=bool(args.kucuk and not args.deneme))
        pencere.events.shown += lambda: pc_katman.baslik_cubugu_temasi(pc_katman.pencere_kolu(pencere), True)
        uyg.ana_pencere = pencere
        uyg.katman = pc_katman.Katman(f"http://127.0.0.1:{uyg.ayar['goruntu']['port']}")
        uyg.tepsi = tepsi.Tepsi(uyg, pencere)
        pencere.events.closing += uyg.tepsi.kapatiliyor  # kapatınca (X) her şey durur ve program kapanır
        pencere.events.minimized += uyg.tepsi.kucultuldu  # küçültünce (–) simgeye iner, çalışmaya devam eder

        def kapandi():
            # Güvence: pencere kapandıktan sonra süreç bir nedenle (açık kalan bir pencere, takılan iş parçacığı)
            # bitmezse zorla bitir. Pencere yokken arkada çeviri sürmemeli.
            def bitir():
                time.sleep(8)
                os._exit(0)
            threading.Thread(target=bitir, daemon=True).start()

        pencere.events.closed += kapandi

        def acilis():
            # webview.start bu işlevi pencere daha kurulmadan çağırabiliyor (2.7.0'ın ilk derlemesinde tepsi simgesi
            # bu yüzden hiç kurulmadı: "'NoneType' object has no attribute 'Invoke'"). Pencere hazır olana kadar beklenir.
            pencere.events.shown.wait(20)
            for _ in range(100):
                if pencere.native is not None and uyg.tepsi.kur():
                    break
                time.sleep(0.2)
            else:
                print("[tepsi] simge kurulamadı: pencere hazır olmadı", flush=True)
            if args.kucuk and uyg.ayar.get("kurulum_tamam"):
                try:  # Windows ile başlatıldı: altyazı da kendiliğinden başlasın
                    uyg.motor_baslat(None)
                except Exception as e:
                    print(f"[açılış] altyazı başlatılamadı: {e}", flush=True)

        def deneme():
            # Derlenmiş paketin duman testi: sayfa yüklendi mi, sonra kendini kapat. Açılış adımları gerçek
            # kullanımdakiyle aynı çalışır (tepsi simgesi dahil).
            acilis()
            time.sleep(4)
            try:
                baslik = pencere.evaluate_js("document.title + ' | ' + (document.querySelector('.sayfa.aktif h1,.sayfa.aktif h3')||{}).textContent")
                tr_ses = [s["ad"] for s in seslendirme.turkce_sesler()]
                if tr_ses:  # Türkçe ses paketlenmiş uygulamada da üretilebiliyor mu?
                    wav = seslendirme._Sentezci().wav("Deneme")
                    tr_ses.append(f"{len(wav)} bayt")
                    wav = seslendirme._Sentezci().wav("Merhaba, nasılsın? Arabaya bin.", 1.0, 1.0, "kadin1")
                    # Karakter sesleri: konuşmacı modeli paketten yüklenip parmak izi çıkarabiliyor mu?
                    import io as _io, wave as _wave, numpy as _np
                    _w = _wave.open(_io.BytesIO(wav))
                    _x = _np.frombuffer(_w.readframes(_w.getnframes()), _np.int16).astype(_np.float32) / 32768
                    _t = konusmaci.paylasilan()
                    if not _t:
                        raise RuntimeError(f"Konuşmacı modeli yüklenemedi: {konusmaci._yukleme_hatasi}")
                    _e, _, _k = _t.cozumle(_x, _w.getframerate())
                    if _e is None:
                        raise RuntimeError("Konuşmacı parmak izi çıkarılamadı.")
                    tr_ses.append(f"kadın1→kadın olasılığı {_k:.2f} (ECAPA {'var' if _t.ecapa else 'yok'})")
                    tr_ses.append(f"oyun sesi aygıtı: {len(oyun_sesi.aygitlar())}")
                    # Sesi konuşana uydurma: sesin perdesi ölçülüp istenen perdede üretilebiliyor mu?
                    import ses_uyum as _su
                    _sz = seslendirme._Sentezci()
                    _taban, _ = _sz.kalibre()
                    _w2 = _wave.open(_io.BytesIO(_sz.wav("Sakin ol, kestirme bir yol biliyorum. Hemen çıkmamız lazım.",
                                                         1.0, 1.0, "erkek1", 1.0, 125)))
                    _x2 = _np.frombuffer(_w2.readframes(_w2.getnframes()), _np.int16).astype(_np.float32) / 32768
                    if _w2.getframerate() != 16000:
                        _x2 = _np.interp(_np.arange(0, len(_x2), _w2.getframerate() / 16000), _np.arange(len(_x2)), _x2)
                    _p = _su.perde_olc(_x2)
                    if not _p or abs(_p - 125) > 12:
                        raise RuntimeError(f"Ses hedef perdeye oturmadı: 125 Hz istendi, {_p} Hz çıktı")
                    tr_ses.append(f"perde: taban {_taban:.0f} Hz, 125 Hz istendi {_p:.0f} Hz çıktı")
                # Okurken oyunun sesini kısma: Windows ses oturumları okunabiliyor mu? (hiçbir seviye değiştirilmez)
                import ses_kisici
                ses_kisici._com_ac()
                oturum_bilgi = f"{len(ses_kisici.oturumlari_listele())} ses oturumu okundu"
                cevrimdisi = ceviri.CevrimdisiMotor().cevir("Get in the car, the cops are behind us!", [])
                # Yazı okuma (OCR) gerçekten yüklenip okuyabiliyor mu?
                import numpy as np, cv2
                kare = np.full((120, 900, 3), 255, np.uint8)
                cv2.putText(kare, "Get in the car", (20, 80), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 0), 4)
                okunan = ocr.RapidOCRMotoru().oku(kare)
                if "car" not in okunan.lower():
                    raise RuntimeError(f"OCR okuyamadı: {okunan!r}")
                ekran = pc_katman.ekran_goruntusu(1).shape  # bilgisayar oyunu modu: ekran yakalama paketlendi mi
                # Saydam katman penceresi (pythonnet/WinForms) paketlenmiş halde açılıyor mu
                katman_gizli = uyg.katman.ac(pc_katman.ekranlar()[0])
                time.sleep(1)
                uyg.katman.kapat()
                if katman_gizli is not True:
                    raise RuntimeError("Katman penceresi ekran yakalamadan gizlenemedi.")
                # Çeviri hattı: deyim, kısa ünlem, çok cümleli satır (ceviri_hatti.py)
                import ceviri_hatti
                hat = ceviri.CevrimdisiMotor(ceviri.sozluk_yukle())
                hat_sonuc = hat.cevir(ceviri_hatti.ocr_onar("Police! Run! We're toast."), [])
                if "Mahvolduk" not in hat_sonuc or hat_sonuc.count("!") < 2:
                    raise RuntimeError(f"Çeviri hattı beklenen sonucu vermedi: {hat_sonuc}")
                # Doğal sesler: ses sunucusu bu uygulamadan (paket içinden de) başlatılıp ses üretebiliyor mu? Ayarda
                # seçili motor denenir: uygulamayla gelen hafif motor (varsayılan) ya da kuruluysa güçlü motor.
                # Hafif motor uygulamanın parçasıdır: pakette varsa çalışmak ZORUNDA (çalışmıyorsa deneme başarısız);
                # ayrıca bütün seslerini hazırlayabildiğine bakılır (kopyalanan sesler ses dosyası okuma
                # kitaplıklarını ister; derlemede unutulursa yalnız onlar sessizce Windows sesine düşerdi).
                dogal_bilgi = "yok"
                _d = dogal_ses.paylasilan(baslat=False)
                if _d and _d.klasor:
                    class _Sessiz:
                        def cal(self, x):
                            pass

                        def bitir(self):
                            pass
                    _hafif_sorun = ""
                    try:
                        if _d.baslat(120):
                            _t = time.time()
                            _sure = _d.cal("Deneme tamam, sesler hazır.", _d.sesler[0], oynatici=_Sessiz())
                            dogal_bilgi = (f"{_d.motor} motor, {len(_d.sesler)} ses, {_sure:.1f} sn ses "
                                           f"{time.time() - _t:.1f} sn'de üretildi")
                            if _d.motor == "hafif":
                                for _ in range(120):  # arka plandaki ses hazırlığı (12 ses ~10 sn)
                                    _d.saglik(2)
                                    if _d.sunucu_hazir_ses == len(_d.sesler):
                                        break
                                    time.sleep(0.5)
                                dogal_bilgi += f", {_d.sunucu_hazir_ses}/{len(_d.sesler)} ses hazır"
                                if _d.sunucu_hazir_ses != len(_d.sesler):
                                    _hafif_sorun = f"seslerin hepsi hazırlanamadı ({dogal_bilgi}; ayrıntı: {_d._gunluk_yolu()})"
                                else:  # kopyalanan (referans kaydından) bir sesle de üret
                                    _kopya = next((s for s in _d.sesler if s["id"] == "sert_erkek"), _d.sesler[-1])
                                    _t = time.time()
                                    _sure = _d.cal("Ne yapıyorsun sen? Hemen silahını indir!", _kopya, oynatici=_Sessiz())
                                    dogal_bilgi += (f", {_kopya['ad']}: {_sure:.1f} sn ses {time.time() - _t:.1f} sn'de "
                                                    f"(ilk ses {_d.son_gecikme_ms} ms)")
                        else:
                            dogal_bilgi = f"{_d.motor} motor başlamadı: " + _d.hata
                            if _d.motor == "hafif":
                                _hafif_sorun = _d.hata
                    except Exception as _e:
                        dogal_bilgi = f"{_d.motor} motor, hata: {_e}"
                        if _d.motor == "hafif":
                            _hafif_sorun = str(_e)
                    finally:
                        _d.durdur()
                    if _hafif_sorun:
                        raise RuntimeError(f"Uygulamayla gelen doğal sesler çalışmadı: {_hafif_sorun}")
                # Arayüz paketlenmiş halde açılıyor mu: dosyalar eksiksiz mi (altyazi_stil.js dahil), sayfa hatasız
                # kuruluyor mu, Görünüm sayfasının hazır görünümleri ve yazı tipleri çiziliyor mu? Overlay sunucusu da stil
                # dosyasını verebiliyor mu?
                for _dosya in ("arayuz.html", "arayuz.js", "arayuz.css", "overlay.html", "altyazi_stil.js"):
                    if not os.path.exists(veri.kaynak(_dosya)):
                        raise RuntimeError(f"Pakette dosya eksik: {_dosya}")
                if not tepsi.simge_yolu():
                    raise RuntimeError("Pakette dosya eksik: uygulama.ico (tepsi simgesi)")
                panel = ""
                for _ in range(60):
                    time.sleep(0.25)
                    panel = pencere.evaluate_js(
                        "(typeof AltyaziStil) + '|' + document.querySelectorAll('#g-hazir .hazir').length + '|' + "
                        "document.querySelectorAll('#g-yazi-tipi option').length + '|' + "
                        "((document.getElementById('surum') || {}).textContent || '') + '|' + "
                        "((document.getElementById('u-hata') || {}).textContent || '') + '|' + "
                        "(document.body.dataset.hazir || '')") or ""
                    if panel.startswith(f"object|{len(veri.HAZIR_GORUNUMLER)}|{len(veri.GORUNUM_SECENEKLERI['yazi_tipi'])}|Sürüm") \
                            and panel.endswith("|1"):
                        break
                else:
                    raise RuntimeError(f"Arayüz açılmadı: {panel!r}")
                if panel.split("|")[4].strip():
                    raise RuntimeError(f"Arayüz hata gösterdi: {panel.split('|')[4]}")
                if len(pc_katman.yuklu_yazi_tipleri()) < 5:
                    raise RuntimeError("Yüklü yazı tipleri okunamadı.")
                # Tepsi simgesi: açılışta (acilis) kendiliğinden kuruldu mu, kapatma düğmesi pencereyi tepsiye
                # indiriyor mu, simgeden geri geliyor mu?
                if not uyg.tepsi.ikon:
                    raise RuntimeError("Tepsi simgesi açılışta kurulmadı.")
                uyg.ayar.setdefault("uygulama", {})["tepsi_bilgisi_gosterildi"] = True  # denemede bildirim balonu çıkmasın
                pencere.minimize()  # küçültünce simgeye inmeli (görev çubuğundan kalkar)
                time.sleep(1.2)
                _gorunur = bool(pencere.native.Visible)
                uyg.tepsi.pencereyi_goster()
                time.sleep(0.8)
                if _gorunur or not pencere.native.Visible:
                    raise RuntimeError(f"Küçültünce simgeye inme / geri gelme çalışmadı (inince görünür={_gorunur}, "
                                       f"dönünce görünür={bool(pencere.native.Visible)}).")
                _menu = [o.get("ad") for o in tepsi.menu_modeli(uyg) if not o.get("ayrac")]
                tepsi_bilgi = f"simge var, {len(_menu)} menü öğesi, küçültünce simgeye inip geri geldi"
                print("DENEME_OK", baslik, "| Türkçe ses:", tr_ses or "yok", "| Çevrimdışı:", cevrimdisi,
                      "| Hat:", hat_sonuc, "| OCR:", okunan, "| Ekran:", f"{ekran[1]}x{ekran[0]}", "| Katman: tamam",
                      "| Ses kısma:", oturum_bilgi, "| Doğal ses:", dogal_bilgi, "| Arayüz:", panel.split("|")[3],
                      "| Tepsi:", tepsi_bilgi, "| Store paketi:", "evet" if veri.MAGAZA else "hayır", flush=True)
            except Exception as e:
                print("DENEME_HATA", e, flush=True)
            pencere.destroy()

        webview.start(deneme if args.deneme else acilis, private_mode=False, storage_path=veri.veri_yolu("webview"))
        uyg.tepsi.kaldir()
    uyg.kapat()
    sys.exit(0)


if __name__ == "__main__":
    main()
