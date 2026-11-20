"""Altyazı motoru: görüntü al → altyazıyı oku → çevir → overlay'e gönder.

Hem uygulama penceresi (uygulama.py) hem komut satırı (main.py) bunu kullanır.
"""
import difflib
import os
import threading
import time
from collections import deque

import cv2

import ceviri
import ceviri_hatti
import dogal_ses
import konusmaci
import ocr
import oyun_sesi
import ses_kisici
import seslendirme
import tam_ekran
import veri
from kaynak import bolge_kes, kaynak_olustur
from obs_baglanti import ALTYAZI_KAYNAK_ADI
from takip import AltyaziTakipcisi

_ocr_kilit = threading.Lock()
_ocr_onbellek = {}


def overlay_tazele(obs):
    """Program güncellendiyse OBS'teki Türkçe altyazı sayfasını bir kez yeniletir. OBS açıkken güncellenen programın
    eski sayfası OBS'te açık kalır ve yeni ayarları (görünüm, konum, ek alanlar) anlamaz. 2.4.1 ve sonrasının
    sayfaları sürüm farkını görünce kendini yeniler (overlay.html); bu, daha eski sayfalar için. Sürüm başına bir kez."""
    isaret = veri.veri_yolu("overlay_surumu.txt")
    try:
        with open(isaret, encoding="utf-8") as f:
            if f.read().strip() == veri.SURUM:
                return False
    except OSError:
        pass
    yenilendi = False
    try:
        obs.istek("PressInputPropertiesButton", {"inputName": ALTYAZI_KAYNAK_ADI, "propertyName": "refreshnocache"})
        yenilendi = True
    except Exception as e:  # kaynak henüz yok ya da OBS bu isteği bilmiyor: yapılacak bir şey yok
        print(f"[overlay] OBS'teki altyazı sayfası yenilenemedi: {e}", flush=True)
    try:
        with open(isaret, "w", encoding="utf-8") as f:
            f.write(veri.SURUM)
    except OSError:
        pass
    return yenilendi


def ocr_motoru_al(ayar):
    """OCR modeli yüklemesi birkaç saniye sürer; bir kere yükleyip tekrar kullan."""
    anahtar = (ayar["ocr"]["motor"], ayar["ocr"].get("min_guven"))
    with _ocr_kilit:
        if anahtar not in _ocr_onbellek:
            _ocr_onbellek[anahtar] = ocr.motor_olustur(ayar)
            if hasattr(_ocr_onbellek[anahtar], "hizli_oku"):
                ocr.isit(_ocr_onbellek[anahtar])
        return _ocr_onbellek[anahtar]


class AltyaziMotoru:
    EK_ALAN_ARALIGI = 3  # ek çeviri alanlarına kaç karede bir bakılır

    def __init__(self, ayar, yayinci, debug=False, yazdir=True):
        self.ayar = ayar
        self.yayinci = yayinci
        self.debug = debug
        self.yazdir = yazdir
        self.durum = "durdu"  # durdu | basliyor | calisiyor | hata
        self.hata = ""
        self.ceviri_hatasi = ""
        self.ceviri_hata_zamani = 0
        self.gecmis = deque(maxlen=30)  # {"id","en","tr","ms"}
        self.sayac = {"okunan": 0, "cevrilen": 0}
        self._calisiyor = False
        self._thread = None
        self.seslendirici = None
        self.ceviri_motoru = None
        self._son_uyari = None
        self.takipci = None
        self.kare_sureleri = deque(maxlen=50)  # görüntü alma, ms
        self.atlanan = 0  # çeviri kuyruğu dolunca atlanan satır
        self._son_gonderilen = {}  # satır kimliği -> çeviriye gönderilen metin (düzeltme aynıysa yeniden çevrilmez)
        self.tarayici = None  # tam_ekran.TamEkranTarayici — yalnız tüm ekran kipinde

    def hiz(self):
        """Ortalama süreler (ms): yavaşlık şikâyetinde nerede takıldığını gösterir."""
        ort = lambda d: int(sum(d) / len(d)) if d else None  # noqa: E731
        return {"kare_ms": ort(self.kare_sureleri),
                "ocr_ms": ort(self.takipci.ocr_sureleri) if self.takipci else None,
                "ceviri_ms": ort([g["ms"] for g in self.gecmis]), "atlanan": self.atlanan}

    def _kendi_yazimiz_mi(self, metin):
        """Okunan yazı az önce bizim ekrana yazdığımız Türkçe satırlardan biri mi?"""
        a = metin.lower()
        for g in list(self.gecmis)[-6:]:
            if difflib.SequenceMatcher(None, a, g["tr"].lower()).ratio() >= 0.75:
                if not getattr(self, "_kendi_uyarisi", False):
                    self._kendi_uyarisi = True
                    print("[uyarı] Kendi Türkçe yazımızı okuduk; yok sayıldı.", flush=True)
                return True
        return False

    def ceviri_uyari(self):
        f = getattr(self.ceviri_motoru, "uyari", None)
        return f() if f else None

    def _log(self, *a):
        if self.yazdir:
            print(*a, flush=True)

    # ---------- dışarıdan ----------
    def baslat(self):
        if self._calisiyor:
            return
        self._calisiyor = True
        self.durum, self.hata = "basliyor", ""
        self._thread = threading.Thread(target=self._calis, daemon=True)
        self._thread.start()

    def durdur(self, bekle=True):
        self._calisiyor = False
        if bekle and self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=5)

    def ozet(self):
        return {
            "durum": self.durum, "hata": self.hata,
            "ceviri_hatasi": self.ceviri_hatasi if time.time() - self.ceviri_hata_zamani < 20 else "",
            "ceviri_uyari": self.ceviri_uyari(), "hiz": self.hiz(),
            "gecmis": list(self.gecmis)[-8:], "sayac": dict(self.sayac),
            "motor": self.ayar["ceviri"]["motor"],
            "dublaj": self._dublaj_ozet(),
            "tam_ekran": {"tarama": self.tarayici.tarama_sayisi, "tarama_ms": self.tarayici.tarama_ms,
                          "kutu": len(self.tarayici.kutular)} if getattr(self, "tarayici", None) else None,
        }

    def _dublaj_ozet(self):
        s = self.seslendirici
        if not s:
            return {"acik": False, "okunan": 0, "hata": ""}
        o = s.oyun_sesi
        return {"acik": True, "okunan": s.okunan, "hata": s.hata, "karakter": s.karakter_sesleri(),
                "son_kisi": s.son_kisi, "dogal": s.dogal.ozet() if s.dogal else None, "son_okuyan": s.son_okuyan,
                "oyun_sesi": {"ad": o.ad, "hoparlor": o.loopback, "seviye": round(o.seviye, 4), "hata": o.hata,
                              "kendini_haric": o.kendini_haric}
                if o else None}

    # ---------- iç ----------
    def _hata(self, mesaj):
        self.durum, self.hata = "hata", mesaj
        self._calisiyor = False
        self._log(f"\n[!] {mesaj}")

    def _calis(self):
        ayar = self.ayar
        kaynak = isci = self.seslendirici = None
        try:
            try:
                ocr_motoru = ocr_motoru_al(ayar)
            except Exception as e:
                return self._hata(f"Yazı okuma motoru yüklenemedi: {e}")
            try:
                ceviri_motoru = self.ceviri_motoru = ceviri.motor_olustur(ayar, ceviri.sozluk_yukle())
            except ceviri.CeviriHatasi as e:
                return self._hata(str(e))
            if ceviri_hatti._sozluk is None and ceviri.model_var():  # OCR harf onarımı için kelime dağarcığı
                try:
                    ceviri_hatti.sozluk_yukle_modelden(os.path.join(ceviri.model_klasoru(), "source.spm"))
                except Exception as e:
                    self._log(f"[çeviri] kelime dağarcığı okunamadı: {e}")
            isit = getattr(ceviri_motoru, "isit", None)
            if isit:
                isit()  # ilk satır geç kalmasın
            try:
                kaynak = kaynak_olustur(ayar)
            except Exception as e:
                return self._hata(f"Oyun görüntüsü alınamadı: {e}")

            obs = getattr(kaynak, "obs", None)
            if obs:
                seslendirme.ObsSesKisici.yarim_kalani_duzelt(obs)
                overlay_tazele(obs)
            d = ayar.get("dublaj", {})
            # Tüm ekran kipi (tam_ekran.py): ekranın tamamı taranır; seslendirme yoktur
            tum_ekran = bool(ayar.get("tam_ekran", {}).get("acik")) and hasattr(ocr_motoru, "kutular") \
                and ayar["kaynak"]["tip"] == "ekran"
            if d.get("acik") and not tum_ekran:
                # Okurken oyunun sesini kıs (varsayılan açık). Konsol + OBS'te oyunun sesi OBS'ten geçer, orada kısılır;
                # bilgisayar oyununda öteki uygulamaların Windows ses seviyesi kısılır (ses_kisici.py).
                kisici = None
                if d.get("okurken_kis", True):
                    try:
                        if obs:
                            kisici = seslendirme.ObsSesKisici(obs, ayar["obs"]["kaynak_adi"], d.get("kisma_db", -14))
                        elif ses_kisici.destekleniyor():
                            ses_kisici.yarim_kalani_duzelt()
                            kisici = ses_kisici.SistemSesKisici(d.get("kisma_db", -14))
                    except Exception as e:
                        self._log(f"[ses kısma] kullanılamıyor: {e}")
                tanici = dinleyici = None
                if d.get("karakter_sesleri", True):
                    tanici = konusmaci.paylasilan()
                    if tanici:
                        dinleyici = oyun_sesi.olustur(ayar, obs)
                if kisici and dinleyici:
                    kisici.carpan_degisti = dinleyici.kisik_carpan
                dogal_ses.tercih_ayarla(d.get("dogal_motor", "otomatik"))  # hafif (varsayılan) ya da güçlü motor
                dogal = dogal_ses.paylasilan() if d.get("dogal_ses", True) else None
                self.seslendirici = seslendirme.Seslendirici(d, kisici, tanici=tanici, oyun_sesi=dinleyici, dogal=dogal)

            temizlenenler = set()
            kilit = threading.Lock()
            satir_bilgi = {}  # id -> (belirdiği an, yazı rengi): dublajda konuşanı tanımak için
            seslendirilen = deque(maxlen=200)  # sesli okunan satır kimlikleri (düzeltme gelince yeniden okunmaz)

            # alanlar: 0 ana altyazı (config bolge), 1.. ek çeviri alanları (config ek_bolgeler)
            alanlar = [(0, ayar["bolge"], True)] + [
                (i + 1, b, bool(b.get("seslendir", False))) for i, b in enumerate(ayar.get("ek_bolgeler") or [])
                if b.get("w", 0) > 0.01 and b.get("h", 0) > 0.01]
            sesli_alan = {no for no, _, ses in alanlar if ses}
            ALAN_CARPAN = 1_000_000  # satır kimliği = alan x ALAN_CARPAN + takipçinin sırası

            def ceviri_geldi(satir_id, en, tr, sure):
                alan = satir_id // ALAN_CARPAN
                with kilit:
                    gec = satir_id in temizlenenler
                self.sayac["cevrilen"] += 1
                self.ceviri_hatasi = ""
                self.gecmis.append({"id": satir_id, "en": en, "tr": tr, "ms": int(sure * 1000), "alan": alan})
                self._log(f"  TR ({sure * 1000:.0f} ms): {tr}")
                if not self.yazdir:  # pencereli program: günlüğe (gunluk.txt) kısa kayıt; şikâyette neyin nasıl
                    print(f"[satır] {en} => {tr} ({sure * 1000:.0f} ms)", flush=True)  # okunup çevrildiği görülsün
                # Çeviri geldiğinde satır ekrandan kalkmış olsa da (kısa replik, yavaş çeviri) okunur; eskiden böyle
                # satırlar hiç seslendirilmiyordu ("dublaj ara ara okuyor"). Çok eskimiş satırı Seslendirici atlar.
                if self.seslendirici and alan in sesli_alan and satir_id not in seslendirilen:
                    seslendirilen.append(satir_id)
                    with kilit:
                        bas, renk = satir_bilgi.pop(satir_id, (None, None))
                    # bölünmüş cümlede ekranda tamamı görünür, sesli yalnız bu parça okunur
                    self.seslendirici.soyle((isci.son_tek if isci else None) or tr, bas=bas, en=en, renk=renk)
                self.yayinci.gonder({"tip": "satir", "id": satir_id, "alan": alan, "en": en, "tr": tr, "temizlendi": gec})
                # Yedek motora geçildiyse oyunu oynayan da görsün (panel o sırada açık değil)
                u = self.ceviri_uyari()
                anahtar = u and (u["asil"], u["aktif"])
                if anahtar != self._son_uyari:
                    self._son_uyari = anahtar
                    if u:
                        self._log(f"[çeviri yedeğe geçti] {u['neden']}")
                        self.yayinci.gonder({"tip": "bilgi", "metin": f"{u['asil']} çalışmıyor, çeviri "
                                             f"{u['aktif']} ile devam ediyor. Ayrıntı panelde."})

            def ceviri_hatasi(mesaj):
                self.ceviri_hatasi, self.ceviri_hata_zamani = mesaj, time.time()
                self._log(f"[çeviri hatası] {mesaj}")

            isci = ceviri.CeviriIscisi(ceviri_motoru, ceviri_geldi, ayar["ceviri"].get("baglam_satir", 4),
                                       hata_cagir=ceviri_hatasi, motor_adi=ayar["ceviri"]["motor"],
                                       # Bölünmüş cümleyi önceki altyazıyla birleştirip çevirme: KAPALI (2.7.4).
                                       # Kullanıcı: "ekranda ne varsa o gösterilsin, ne eksik ne fazla"; birleştirince
                                       # ekranda o an yazandan fazlası görünüyordu. ceviri.cumle_birlestir açar.
                                       birlestir=bool(ayar["ceviri"].get("cumle_birlestir", False))
                                       and ayar["ceviri"]["motor"] == "cevrimdisi")
            isci.tek_gerekli = self.seslendirici is not None
            takipciler = [(no, b, AltyaziTakipcisi(ayar, ocr_motoru)) for no, b, _ in alanlar]
            self.takipci = takipciler[0][2]
            self.durum = "calisiyor"
            son_rapor = time.time()
            son_okuma = 0
            self._log(f"Hazır. Overlay: http://127.0.0.1:{ayar['goruntu']['port']}  |  Çeviri: {ayar['ceviri']['motor']}")

            aralik = 1.0 / ayar["tespit"]["fps"]
            kare_yok_basi = None
            kare_no = 0
            bolgesel = hasattr(kaynak, "kesitler_al")
            tarayici = None
            if tum_ekran:
                def tam_kayit(en, tr):
                    self.sayac["okunan"] += 1
                    self.sayac["cevrilen"] += 1
                    self.gecmis.append({"id": -len(self.gecmis) - 10, "en": en, "tr": tr, "ms": 0, "alan": 0})

                tarayici = self.tarayici = tam_ekran.TamEkranTarayici(
                    ayar, ocr_motoru, lambda metin: isci._cevir(metin, []), self.yayinci.gonder, tam_kayit)
                aralik = 0.12
            while self._calisiyor:
                t0 = time.time()
                if t0 - son_rapor > 60:  # dakikada bir günlüğe hız özeti (konsolsuz derlemede gunluk.txt)
                    son_rapor = t0
                    okuma = sum(t.ocr_sayisi for _, _, t in takipciler)
                    print(f"[hız] {self.hiz()} okunan={self.sayac['okunan']} cevrilen={self.sayac['cevrilen']} "
                          f"okuma/dk={okuma - son_okuma}", flush=True)
                    son_okuma = okuma
                if tarayici:  # tüm ekran kipi
                    kare = kaynak.kare_al()
                    if kare is not None:
                        tarayici.adim(kare, t0)
                    bekle = aralik - (time.time() - t0)
                    time.sleep(max(0.01, bekle))
                    continue
                kare_no += 1
                # Ek alanlar (görev yazısı, mesaj) yavaş değişir: üç karede bir, sırayla bakılır ki
                # ana altyazının okunması gecikmesin
                bakilacak = [x for x in takipciler if not (x[0] and (kare_no + x[0]) % self.EK_ALAN_ARALIGI)]
                if bolgesel:  # ekran: yalnız bakılacak bölgeler yakalanır
                    kesitler = kare = kaynak.kesitler_al([b for _, b, _ in bakilacak])
                else:
                    kare = kaynak.kare_al()
                    kesitler = None if kare is None else [bolge_kes(kare, b) for _, b, _ in bakilacak]
                self.kare_sureleri.append(getattr(kaynak, "son_kare_ms", 0))
                if kare is None:
                    kare_yok_basi = kare_yok_basi or t0
                    if t0 - kare_yok_basi > 10 and getattr(kaynak, "hata", None):
                        self.hata = f"Görüntü gelmiyor: {kaynak.hata}"
                    time.sleep(0.05)
                    continue
                kare_yok_basi = None
                if self.hata and not getattr(kaynak, "hata", None):
                    self.hata = ""
                for (alan, bolge, takipci), kesit in zip(bakilacak, kesitler):
                    self._alan_isle(alan, takipci, kesit, t0, isci, kilit, satir_bilgi, temizlenenler, ALAN_CARPAN)

                if self.debug:
                    self._debug_goster(kesitler[0])

                bekle = aralik - (time.time() - t0)
                if bekle > 0:
                    time.sleep(bekle)
            if self.durum != "hata":
                self.durum = "durdu"
        except Exception as e:  # beklenmeyen hata pencereyi çökertmesin
            self._hata(f"Beklenmeyen hata: {e}")
        finally:
            if getattr(self, "tarayici", None):
                self.tarayici.kapat()
                self.tarayici = None
            if isci:
                isci.durdur()
            if self.seslendirici:
                self.seslendirici.durdur()
            if kaynak:
                try:
                    kaynak.kapat()
                except Exception:
                    pass
            self.yayinci.gonder({"tip": "temizle", "id": -1, "hepsi": True})

    EN_GENIS_KESIT = 1600  # px — daha geniş altyazı bölgesi (1440p / 4K ekran) bu genişliğe küçültülerek işlenir

    def _alan_isle(self, alan, takipci, kesit, t0, isci, kilit, satir_bilgi, temizlenenler, carpan):
        """Bir alanın karesini takipçiye verir; yeni satırı çeviriye, kaybolanı overlay'e iletir."""
        # Yazı maskesi ve okuma 1080p ölçüsüne göre ayarlı (kenar çekirdeği, satır boyları). 4K'da aynı bölge 4 kat
        # piksel demek: her karede maske ~18 ms sürer ve kalın harflerin içi "kontrastsız" sayılıp maskeden düşer.
        # Bölge 1080p eşdeğerine küçültülür; yazı o boyutta da rahat okunur.
        if kesit.shape[1] > self.EN_GENIS_KESIT:
            oran = 1460.0 / kesit.shape[1]
            kesit = cv2.resize(kesit, (1460, max(1, int(round(kesit.shape[0] * oran)))), interpolation=cv2.INTER_AREA)
        for olay in takipci.isle(kesit, t0):
            if olay[0] == "geri":  # kısa süre kaybolup (parlama, patlama) geri gelen satır: yeniden göster
                sid = alan * carpan + olay[1]
                with kilit:
                    temizlenenler.discard(sid)
                eski = next((g for g in reversed(self.gecmis) if g["id"] == sid), None)
                if eski:
                    self.yayinci.gonder({"tip": "satir", "id": sid, "alan": alan, "en": eski["en"], "tr": eski["tr"],
                                         "temizlendi": False})
                continue
            if olay[0] in ("yeni", "duzelt"):
                sid, metin = olay[1], olay[2]
                sid = alan * carpan + sid
                metin = ceviri_hatti.ocr_onar(metin)  # çöp, gösterge sayısı, boşluk, karışan harfler
                # ekrandaki yazı öncekinin devamıysa: ekranda duran yazının tamamı (çevirisi gösterilecek olan)
                tam = ceviri_hatti.ocr_onar(olay[3]) if len(olay) > 3 else None
                if tam and tam.strip().lower() == metin.strip().lower():
                    tam = None
                if not ocr.anlamli_mi(metin):
                    continue
                if self._kendi_yazimiz_mi(metin):
                    continue  # kendi Türkçe katmanımızı okuduk (yanlış OBS sahnesi / eski Windows)
                if ceviri_hatti.ingilizce_degil(metin):
                    # alana altyazı dışında bir şey girmiş (Türkçe sayfa yazısı, oynatıcı düğmeleri): çevrilmez, okunmaz
                    self.sayac["ingilizce_degil"] = self.sayac.get("ingilizce_degil", 0) + 1
                    if self.sayac["ingilizce_degil"] <= 3:
                        self._log(f"[atlandı: İngilizce altyazı değil] {metin[:80]}")
                    continue
                if olay[0] == "duzelt":
                    if metin.lower() != self._son_gonderilen.get(sid, "").lower():
                        self._son_gonderilen[sid] = metin
                        self._log(f"EN (düzeltme): {metin}")
                        self.atlanan += isci.ekle(sid, metin, alan)
                    continue
                self._son_gonderilen = {sid: metin} if len(self._son_gonderilen) > 40 else {**self._son_gonderilen, sid: metin}
                self.sayac["okunan"] += 1
                self._log(f"EN{'' if not alan else f' [alan {alan}]'}: {metin}")
                with kilit:
                    satir_bilgi[sid] = (takipci.aktif_bas or t0, takipci.aktif_renk)
                    if len(satir_bilgi) > 50:
                        satir_bilgi.pop(next(iter(satir_bilgi)))
                self.atlanan += isci.ekle(sid, metin, alan, tam)
            else:
                _, sid = olay
                sid = alan * carpan + sid
                with kilit:
                    temizlenenler.add(sid)
                self.yayinci.gonder({"tip": "temizle", "id": sid, "alan": alan})

    def _debug_goster(self, kesit):
        o = self.ayar["ocr"]
        maske = ocr.yazi_maskesi(kesit, o["parlaklik_esigi"], o.get("kontur_gerekli", True))
        cv2.imshow("Altyazi bolgesi", kesit)
        cv2.imshow("Maske (beyaz = yazi sanilan)", maske)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            self._calisiyor = False
