"""Altyazının ne zaman değiştiğini/kaybolduğunu anlayan mantık.
OCR'ı sadece yeni ve sabitlenmiş bir altyazı geldiğinde çalıştırır."""
import difflib
import re
import time
from collections import deque

import cv2
import numpy as np

import konusmaci
import ocr


def maske_farki(a, b):
    if a is None or b is None or a.shape != b.shape:
        return 1.0
    return float(np.count_nonzero(cv2.absdiff(a, b))) / a.size


class AltyaziTakipcisi:
    ERKEN_GUVEN = 0.92  # erken okuma için okuyucunun en düşük satır güveni
    # Kelime kelime yazılan / yukarı kayan altyazılar (video altyazıları, daktilo efekti): okunan yazı cümle sonuyla
    # bitmiyorsa DURULMA_SN boyunca değişmemesi beklenir (yarım cümle çevrilmesin, kayarken okunup harfler
    # karışmasın); sürekli değişiyorsa en çok EN_COK_BEKLEME sn. ayar["tespit"]["durulma_sn"] ile değişir.
    DURULMA_SN = 0.35
    EN_COK_BEKLEME = 1.6
    # Hızlı okunan (yazı aranmadan, yalnız tanıma: ~30 ms) satır hemen çeviriye gider; görüntü durunca bir kez de
    # tam okuma (~120 ms) yapılır, fark varsa satır düzeltilir. Böylece hem hızlı hem tam okuma kadar doğru.
    DOGRULAMA_SN = 0.4  # çeviri bitsin diye beklenir: iki iş aynı anda çalışınca ikisi de yavaşlıyor
    # Gürültü koruması: altyazının ARKASINDA hareketli parlak görüntü varsa (film, video, hareketli sahne) yazı maskesi
    # her karede değişir. Eskiden bu her karede okuma başlatıyordu (saniyede 4-5 tam okuma: işlemci doluyor, çeviri
    # 1 sn'ye çıkıyordu). Artık böyle sahnelerde yalnız şu durumlarda okunur: yazı pikseli birden arttı (altyazı
    # belirdi), ekrandaki satırın yazısı kayboldu/değişti, ya da son okumadan beri ARA süresi geçti (okumalar yeni
    # bir şey getirmedikçe ARA_ILK'ten ARA_EN_COK'a uzar). Temiz sahnede (maske altyazı satırlarına benziyorsa) eskisi gibi.
    ARA_ILK = 0.3
    ARA_EN_COK = 1.0      # ekranda satır varken (satırın değiştiği yazı kaybından ayrıca anlaşılır)
    ARA_EN_COK_BOS = 0.3  # ekranda satır yokken (yeni altyazı en geç bu kadar sonra okunur; ~%30 çekirdek)
    # Yazı kaybı eşiği: kutudaki arka plan gürültüsü de "kaybolan piksel" sayılır (ölçüm: çok yoğun gürültüde 0,34'e
    # kadar); satır değişince en az 0,60, kalkınca 0,84.
    KAYIP_ESIGI = 0.5
    EN_SIK_OKUMA = 0.12  # gürültülü sahnede iki okuma arası en az süre

    def __init__(self, ayar, ocr_motoru):
        self.o = ayar["ocr"]
        self.t = ayar["tespit"]
        self.motor = ocr_motoru
        self.onceki_maske = None
        self.son_ocr_maskesi = None
        self.son_ocr_zamani = 0.0
        self.aktif_metin = ""
        self.aktif_id = 0
        self.bos_baslangic = None
        self.sayac = 0
        self.son_okunan = ""
        self.bekleme_baslangic = None
        self.son_satirlar = deque(maxlen=3)
        self.ocr_sureleri = deque(maxlen=50)  # ms — panel ve günlük için
        self.ocr_sayisi = 0  # toplam okuma sayısı (günlükte dakikadaki okuma: çok yüksekse bölgede altyazı dışı hareket var)
        self._erken_okunan = False  # etkin satır kararlılık beklenmeden okundu (düzeltme gelebilir)
        self.aktif_bas = 0.0  # son 'yeni' satırın ekranda belirdiği an (dublajda konuşanı dinlemek için)
        self.aktif_renk = None  # son 'yeni' satırın yazı rengi ('renk:120') ya da None (beyaz)
        self._son_okuma_bos = False  # son OCR'da anlamlı yazı çıkmadı
        self._ocr_dolu = 0  # son OCR anında yazı sayılan piksel sayısı
        self._aday = None  # durulması beklenen okuma: [metin, okunduğu an, ilk bekleme anı, belirdiği an, renk]
        self._ekran = ""  # ekranda en son okunan yazının tamamı
        self._akan_son = -1e9  # en son "öncekinin devamı" görülen an: akan/daktilo altyazı kipinde durulma beklenir
        self._simdi = 0.0
        self.durulma_sn = float(self.t.get("durulma_sn", self.DURULMA_SN))
        self.hizli = bool(self.o.get("hizli", True))  # yazıyı aramadan oku (ocr.RapidOCRMotoru.hizli_oku)
        self._son_hizli = False  # son okuma hızlı yoldan mı geldi
        self._dogrula = False  # etkin satır hızlı okundu: görüntü durunca tam okumayla doğrulanacak
        self._kutu = None  # ekrandaki satırın yazısının kesit içindeki yeri (y1, y2, x1, x2)
        self._dolu_gecmis = deque(maxlen=14)  # son karelerde yazı sayılan piksel sayısı (arka plan gürültüsünün düzeyi)
        self._ara = self.ARA_ILK
        self._gurultulu_okuma = False
        self.gurultu_korumasi = bool(self.t.get("gurultu_korumasi", True))

    def _oku(self, kesit, maske, hizli=True):
        t0 = time.perf_counter()
        onceki = list(getattr(self.motor, "hizli_sayac", (0, 0)))
        metin = ocr.oku(self.motor, kesit, maske, self.o.get("buyutme", 1.0), hizli=hizli and self.hizli)
        self._son_hizli = getattr(self.motor, "hizli_sayac", [0, 0])[0] > onceki[0]
        self.ocr_sayisi += 1
        k = getattr(self.motor, "son_kutu", None)
        if k and ocr.anlamli_mi(metin):  # yazının yeri (kenar payıyla, kesit sınırları içinde)
            h, w = maske.shape[:2]
            self._okunan_kutu = (max(0, k[0] - 3), min(h, k[1] + 3), max(0, k[2] - 6), min(w, k[3] + 6))
        else:
            self._okunan_kutu = None
        self.ocr_sureleri.append((time.perf_counter() - t0) * 1000)
        return metin

    def ayni_mi(self, a, b):
        if not a or not b:
            return False
        return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio() >= self.t["ayni_satir_benzerlik"]

    _okunan_kutu = None

    def isle(self, kesit, simdi):
        """Bir kareyi işler (olaylar için _isle'ye bakın). Gürültülü sahnede okuma aralığını burada ayarlar."""
        onceki = self.ocr_sayisi
        self._gurultulu_okuma = False
        olaylar = self._isle(kesit, simdi)
        if olaylar:
            self._ara = self.ARA_ILK
        elif self._gurultulu_okuma and self.ocr_sayisi > onceki:  # okundu ama yeni bir şey çıkmadı: seyrekleştir
            self._ara = min(self.ARA_EN_COK, self._ara * 1.5)
        return olaylar

    _bos_ust_uste = 0

    def _okunamadi(self, simdi, olaylar):
        """Okumada yazı çıkmadı. Arka planı oynayan sahnede tek boş okuma yanılgı olabilir (satır bir an kaybolup geri
        geliyordu): ekranda satır varken ikinci boş okuma beklenir."""
        self._bos_ust_uste += 1
        if self._gurultulu_okuma and self.aktif_metin and self._bos_ust_uste < 2:
            return
        self._son_okuma_bos = True
        self._bos(simdi, olaylar)

    def _yazi_kaybi(self, maske):
        """Son okumada yazı olan piksellerin (yalnız yazının olduğu kutuda) şimdi yazı olmayanlarının oranı."""
        if self._kutu is None or self.son_ocr_maskesi is None or self.son_ocr_maskesi.shape != maske.shape:
            return None
        y1, y2, x1, x2 = self._kutu
        once = self.son_ocr_maskesi[y1:y2, x1:x2]
        n = int(np.count_nonzero(once))
        if n < 20:
            return None
        return float(np.count_nonzero(cv2.bitwise_and(once, cv2.bitwise_not(maske[y1:y2, x1:x2])))) / n

    def _isle(self, kesit, simdi):
        """Bir kareyi işler. Olay listesi döner:
        ('geri', id, metin)  -> kaybolduğu bildirilen satır geri geldi: yeniden göster (yeniden seslendirme yok)
        ('yeni', id, metin)  -> çevirmeye gönder
        ('yeni', id, yeni_kisim, ekrandaki_tam_yazi) -> ekrandaki yazı öncekinin DEVAMI (uzayan cümle, yukarı kayan
                                satır): ekranda tam yazının çevirisi gösterilir, yalnız yeni kısım seslendirilir.
                                Önceki satır için 'temizle' gönderilmez; yeni çeviri gelince onun yerini alır.
        ('duzelt', id, metin) -> aynı satırın daha doğru okunmuş hali (yeniden çevir, yeniden seslendirme)
        ('temizle', id)      -> altyazı kayboldu"""
        olaylar = []
        self._simdi = simdi
        # Oyun altyazısı tek seferde belirir: iki karede aynıysa tamamdır, beklenmez. Durulma beklemesi yalnız yazı
        # kelime kelime geliyorsa (son 15 sn içinde "devam" görüldüyse) uygulanır.
        durulma = self.durulma_sn if simdi - self._akan_son < 15.0 else 0.0
        maske = ocr.yazi_maskesi(kesit, self.o["parlaklik_esigi"], self.o.get("kontur_gerekli", True))
        piksel_orani = np.count_nonzero(maske) / maske.size

        # 1) Bölgede yazıya benzer piksel yoksa: altyazı yok
        if piksel_orani < self.t["bos_piksel_orani"]:
            self._son_okuma_bos = False
            if self._aday:  # yazı kayboldu: bekleyen okuma varsa hemen işlenir (kısa replik kaçmasın)
                aday, self._aday = self._aday, None
                self._kesinlestir(aday[0], aday[3], aday[4], False, olaylar)
            self._bos(simdi, olaylar)
            self.onceki_maske = maske
            self.son_ocr_maskesi = None
            return olaylar

        # Yazı pikselleri birden çok azaldıysa altyazı kalkmıştır (ya da soluyor): okumayı beklemeden say.
        # (Eskiden görüntünün durulması beklenip yeniden okunuyordu; Türkçe yazı 0,6-1 sn geç kalkıyordu.)
        if self.aktif_metin and not self._aday and self._ocr_dolu \
                and np.count_nonzero(maske) < 0.35 * self._ocr_dolu:
            self._bos(simdi, olaylar)
            self.onceki_maske = maske
            if not self.aktif_metin:
                self.son_ocr_maskesi = None
            return olaylar
        sabit = maske_farki(maske, self.onceki_maske) < self.t["degisim_esigi"]
        fark = maske_farki(maske, self.son_ocr_maskesi)
        # yazıya göre de bak: uzun bir satıra tek kelime eklenince bölgenin küçük bir kısmı değişir (akan altyazı)
        # (yalnız yazı ARTTIYSA: hareketli parlak arka plan her karede okuma başlatmasın)
        dolu = np.count_nonzero(maske)
        yeni = fark >= self.t["degisim_esigi"] or (
            self._ocr_dolu and dolu >= self._ocr_dolu * 1.05 and fark * maske.size >= 0.04 * dolu)
        guvenlik = simdi - self.son_ocr_zamani > 2.0  # arada bir yeniden kontrol
        self.onceki_maske = maske
        gecmis = list(self._dolu_gecmis)
        self._dolu_gecmis.append(dolu)

        # 2) Yazı yeni geldiyse ama hâlâ beliriyorsa (fade-in) bir kare bekle.
        #    Arka plan sürekli oynuyorsa (parlak gökyüzü vb.) en fazla 0.4 sn bekle.
        if self._aday and not yeni:
            # okunan yazı değişmeden duruyor: süre dolunca kesinleşir
            if simdi - self._aday[1] >= durulma:
                aday, self._aday = self._aday, None
                self._kesinlestir(aday[0], aday[3], aday[4], False, olaylar)
            return olaylar
        if not (yeni or guvenlik):
            self.bekleme_baslangic = None
            # Son okumada yazı çıkmadıysa (bölgede altyazı değil, parlak bir nesne var) ve görüntü değişmediyse
            # altyazı hâlâ yok demektir: süre dolunca temizle. (Eskiden burada beklenirdi; kaybolan altyazının
            # Türkçesi 2-4 sn ekranda kalıyordu.)
            if self._son_okuma_bos:
                self._bos(simdi, olaylar)
            elif self._dogrula and self.aktif_metin and sabit and simdi - self.son_ocr_zamani >= self.DOGRULAMA_SN:
                # Hızlı okunan satır ekranda duruyor: bir kez tam okumayla doğrula. Fark küçükse 'duzelt'
                # (çeviri güncellenir, yeniden seslendirilmez); bambaşka çıktıysa yeni satır sayılır.
                self._dogrula = False
                tam = self._oku(kesit, maske, hizli=False)
                self.son_ocr_maskesi, self.son_ocr_zamani = maske, simdi
                self._ocr_dolu = int(np.count_nonzero(maske))
                if ocr.anlamli_mi(tam):
                    self._erken_okunan = True
                    self._kesinlestir(tam, self.aktif_bas, self.aktif_renk, False, olaylar)
            return olaylar
        # 2b) Gürültü koruması (sınıfın başındaki açıklama): maske altyazı satırlarına benzemiyorsa arkada başka
        #     parlak şeyler oynuyordur; her karede okumak yerine yalnız gerektiğinde oku.
        if yeni and not self._aday and self.gurultu_korumasi and ocr.satir_bantlari(maske) is None:
            if self.aktif_metin and self._son_okuma_bos:
                self._bos(simdi, olaylar)  # yazı az önce okunamadı (kalkmış): yeniden okumadan sürenin dolmasını bekle
                return olaylar
            gecen = simdi - self.son_ocr_zamani
            if self.aktif_metin:
                kayip = self._yazi_kaybi(maske)
                acil = kayip is not None and kayip > self.KAYIP_ESIGI  # ekrandaki satırın yazısı değişti ya da kalktı
                ara = self._ara
            else:
                # yazı birden belirdi: yazı pikseli, son karelerdeki düzeyin (gürültünün oynama payının) üstüne çıktı
                acil = len(gecmis) >= 4 and dolu - float(np.mean(gecmis)) > max(0.002 * maske.size,
                                                                                4.0 * float(np.std(gecmis)))
                ara = min(self._ara, self.ARA_EN_COK_BOS)
            if gecen < self.EN_SIK_OKUMA or not (acil or guvenlik or gecen >= ara):
                return olaylar
            self._gurultulu_okuma = True
        if self.bekleme_baslangic is None:
            self.bekleme_baslangic = simdi
            self._on_okuma_yapildi = False
        metin = None
        erken = False
        if not sabit and simdi - self.bekleme_baslangic < 0.4:
            # Hızlı yol: yazı yeni belirdi, kararlı olmasını beklemeden bir kez oku. Satır nokta/ünlem/soruyla
            # bitiyorsa tamamdır (daktilo efektinde cümle bitince noktalama gelir): hemen çeviriye gider.
            if getattr(self, "_on_okuma_yapildi", True):
                return olaylar
            self._on_okuma_yapildi = True
            on = self._oku(kesit, maske)
            # Yalnız okuyucu çok eminse (solma efektinin ortasında yarım okuma olmasın) ve satır cümle sonuyla bitiyorsa
            if not ocr.anlamli_mi(on):
                if self.aktif_metin:  # ekrandaki satır artık okunamıyor: kalkmıştır (süre dolunca temizlenir)
                    self._okunamadi(simdi, olaylar)
                self.son_ocr_maskesi, self.son_ocr_zamani = maske, simdi
                self.bekleme_baslangic = None  # bu belirme denemesi bitti: sonraki değişiklik yeniden hızlı okunur
                return olaylar
            # Oyun altyazısı tek seferde belirir: okuyucu eminse noktalama da aranmaz, satır hemen çeviriye gider
            # (yanlışsa görüntü durunca 'duzelt' ile düzelir). Yazı kelime kelime geliyorsa (durulma > 0) cümle sonu beklenir.
            if not ((durulma <= 0 or re.search(r"[.!?…][\"'”’)\]]*$", on.strip()))
                    and getattr(self.motor, "son_guven", 0.0) >= self.ERKEN_GUVEN):
                # Cümle sonu yok ya da okuyucu emin değil: bir sonraki karede yazı aynıysa bu okuma kullanılır
                # (yeniden okunmaz); değiştiyse durulunca yeniden okunur.
                try:
                    renk0 = konusmaci.yazi_rengi(kesit, maske)
                except Exception:
                    renk0 = None
                ilk0 = self._aday[2] if self._aday else simdi
                belirdi0 = self._aday[3] if self._aday else self.bekleme_baslangic
                self.son_ocr_maskesi = maske
                self.son_ocr_zamani = simdi
                self._ocr_dolu = int(np.count_nonzero(maske))
                self._kutu = self._okunan_kutu
                if simdi - ilk0 >= self.EN_COK_BEKLEME:  # yazı hiç durulmuyor: eldekini gönder (kayıp olmasın)
                    self._aday = None
                    self.bekleme_baslangic = None
                    self._kesinlestir(on, belirdi0, renk0, False, olaylar)
                else:
                    self._aday = [on, simdi, ilk0, belirdi0, renk0]
                return olaylar
            metin = on
            erken = True
            self._bos_ust_uste = 0
        belirdi = self.bekleme_baslangic
        self.bekleme_baslangic = None

        if metin is None:
            metin = self._oku(kesit, maske)
        self.son_ocr_maskesi = maske
        self.son_ocr_zamani = simdi
        self._ocr_dolu = int(np.count_nonzero(maske))
        self.son_okunan = metin
        self._kutu = self._okunan_kutu

        if not ocr.anlamli_mi(metin):
            self._okunamadi(simdi, olaylar)
            return olaylar

        self._son_okuma_bos = False
        self._bos_ust_uste = 0
        try:
            renk = konusmaci.yazi_rengi(kesit, maske)
        except Exception:
            renk = None
        ilk = self._aday[2] if self._aday else simdi
        cumle_sonu = re.search(r"[.!?…][\"'”’)\]]*$", metin.strip())
        # arka plan oynarken görüntü hiç "durulmaz": art arda iki okuma aynı yazıyı verdiyse yazı durmuştur
        ayni_okundu = durulma <= 0 and self._aday is not None and self.ayni_mi(metin, self._aday[0])
        if erken or (cumle_sonu and sabit) or (durulma <= 0 and sabit) or ayni_okundu \
                or simdi - ilk >= self.EN_COK_BEKLEME:
            self._aday = None
            self._kesinlestir(metin, belirdi, renk, erken, olaylar)
        else:
            # cümle bitmemiş görünüyor (ya da yazı hâlâ oynuyor): durulmasını bekle
            self._aday = [metin, simdi, ilk, self._aday[3] if self._aday else belirdi, renk]
        return olaylar

    @staticmethod
    def _kelimeler(metin):
        return metin.split()

    def _yeni_kisim(self, onceki, metin):
        """Ekrandaki yazı öncekinin devamıysa (kelime kelime uzayan satır, yukarı kayan iki satırlı altyazı: yeni yazı
        öncekinin sonuyla başlar) yalnızca YENİ gelen kısmı verir; devamı değilse metnin tamamını. Yeni bir şey
        yoksa "" döner. Böylece aynı sözler yeniden çevrilip yeniden okunmaz."""
        a, b = self._kelimeler(onceki), self._kelimeler(metin)
        if a and len(b) > len(a) and [k.lower() for k in b[:len(a)]] == [k.lower() for k in a]:
            return " ".join(b[len(a):])  # öncekinin birebir devamı (kısa satırlar dahil)
        if len(a) < 2 or len(b) < 2:
            return metin
        en_iyi = (0.0, 0)
        for k in range(min(len(a), len(b)), 1, -1):  # öncekinin son k kelimesi = yeninin ilk k kelimesi; en iyi uyan k
            x, y = " ".join(a[-k:]).lower(), " ".join(b[:k]).lower()
            if len(x) < 8:
                continue
            oran = difflib.SequenceMatcher(None, x, y).ratio()
            if oran > en_iyi[0] + 1e-9:
                en_iyi = (oran, k)
        if en_iyi[0] < 0.86:
            return metin
        kalan = " ".join(b[en_iyi[1]:])
        return kalan if len(re.findall(r"[A-Za-z]", kalan)) >= 2 else ""

    def _kesinlestir(self, metin, belirdi, renk, erken, olaylar):
        """Durulmuş okumayı işler: aynı satır mı, geri gelen satır mı, öncekinin devamı mı, yeni satır mı."""
        self.bos_baslangic = None
        gonderilecek = metin
        devam = False
        if self.aktif_metin:
            ekran = self._ekran or self.aktif_metin
            kalan = self._yeni_kisim(ekran, metin)
            ayni = kalan == "" or (kalan == metin and self.ayni_mi(metin, ekran))
            if ayni:
                # Aynı altyazı. Erken okunmuş satır kararlı karede biraz farklı okunduysa düzeltme gönderilir
                # (ekrandaki çeviri güncellenir, yeniden seslendirilmez).
                if self._erken_okunan and not erken:
                    if ekran == self.aktif_metin and metin.strip().lower() != self.aktif_metin.strip().lower():
                        self.aktif_metin = metin
                        self.son_satirlar.append((self.aktif_id, metin))
                        olaylar.append(("duzelt", self.aktif_id, metin))
                    self._erken_okunan = False
                self._ekran = metin
                return
            gonderilecek = kalan  # öncekinin devamıysa yalnız yeni kısım, değilse tamamı
            if kalan != metin:
                self._akan_son = self._simdi  # yazı kelime kelime geliyor: bundan sonra durulması beklenir
                devam = True
        if not self.aktif_metin and any(self.ayni_mi(metin, s) for _, s in self.son_satirlar):
            # Kısa süre kaybolup geri gelen aynı satır (patlama, parlama vb.)
            self.aktif_id, self.aktif_metin = next(
                (i, s) for i, s in reversed(self.son_satirlar) if self.ayni_mi(metin, s))
            self._ekran = metin
            # Bu satır için 'temizle' gönderilmişti (ekrandan kalktı); geri geldiğini de bildir, yoksa oyunda
            # altyazı dururken Türkçesi görünmez kalır.
            olaylar.append(("geri", self.aktif_id, self.aktif_metin))
            return

        if self.aktif_metin and not devam:
            olaylar.append(("temizle", self.aktif_id))
        self.sayac += 1
        self.aktif_id = self.sayac
        self.aktif_metin = gonderilecek  # çeviriye giden kısım
        self._ekran = metin              # ekrandaki yazının tamamı (devamını ayırmak için)
        self._erken_okunan = erken
        self.aktif_bas = belirdi
        self.aktif_renk = renk
        self.son_satirlar.append((self.aktif_id, gonderilecek))
        self._dogrula = self._son_hizli  # yalnız yeni satır doğrulanır; tam okumayla gelen satır doğrulanmaz
        # Devam: ekranda yazının TAMAMI duruyor; Türkçesi de tamamı gösterilmeli (eskiden yalnız yeni kısım
        # gösteriliyordu: "uzun cümlede yalnız sonunu gösteriyor"). Yeni kısım ayrıca verilir: seslendirme için.
        olaylar.append(("yeni", self.aktif_id, gonderilecek, metin) if devam else ("yeni", self.aktif_id, gonderilecek))

    def _bos(self, simdi, olaylar):
        if not self.aktif_metin:
            return
        if self.bos_baslangic is None:
            self.bos_baslangic = simdi
        elif simdi - self.bos_baslangic >= self.t["bos_temizle_sn"]:
            olaylar.append(("temizle", self.aktif_id))
            self.aktif_metin = self._ekran = ""
            self.bos_baslangic = None
