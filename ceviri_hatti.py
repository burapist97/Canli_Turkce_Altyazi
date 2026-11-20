"""Çeviri öncesi ve sonrası metin hattı: OCR hatalarını onarır, oyun dilini düzleştirir, Türkçeyi toparlar.

Sıra:
  1. ocr_onar        (her motor için; motor.py çağırır)
                     - harf/rakam/simge karışımı çöp parçalar atılır ya da kelimesi kurtarılır
                     - satır başına yapışan gösterge sayısı atılır ("23m JASON: ..." -> "JASON: ...")
                     - noktalamadan sonra okunmamış boşluk açılır ("move,brother.No" -> "move, brother. No")
                     - görünüşü karışan harfler düzeltilir ("heIIo" -> "hello", "c0ps" -> "cops")
  2. duzlestir       (çevrimdışı motor) BÜYÜK HARFLİ satır normal yazıma; deyim/argo -> düz İngilizce
  3. cumlelere_bol   her cümle ayrı çevrilir: model iki kısa cümleyi birlikte görünce birini düşürüyor
                     ("Police! Run!" -> yalnızca "Polis!")
  4. hazir_karsilik  modelin tek başına yanlış çevirdiği birkaç kısa ünlem tablodan ("Roger." -> "Anlaşıldı.")
  5. son_duzelt      kaynağın ! ? ?! … sonu korunur, noktalama boşlukları, baştaki tire

Listeler bu proje için, modelin (OPUS-MT tc-big en-tr) gerçek çıktıları ölçülerek hazırlandı: bir ifade ancak
ham çevirisi yanlışsa ve buradaki karşılığı doğru sonuç veriyorsa listededir (ölçüm: tests/test_ceviri_hatti.py).
Kelime denetimi için ayrı sözlük dosyası yok: modelin kaynak dağarcığındaki tam kelimeler kullanılır.
"""
import re

# ================================================================ kelime dağarcığı
_sozluk = None  # küçük harfli kelime -> sıra (küçük sıra = sık kelime); None: denetim yok
_ozel = set()   # dağarcıkta yalnız büyük harfle başlayan biçimi olan kelimeler (özel ad sayılır)


def sozluk_ayarla(kelimeler):
    """Bilinen kelimeler, sıklık sırasıyla. Büyük/küçük biçimler ayrı verilebilir ("Jason", "the")."""
    global _sozluk, _ozel
    _sozluk, kucuk = {}, set()
    for k in kelimeler:
        _sozluk.setdefault(k.lower(), len(_sozluk))
        if k[:1].islower():
            kucuk.add(k.lower())
    _ozel = {k for k in _sozluk if k not in kucuk}


def spm_yukle(yol):
    """SentencePiece modelini yükler. Kitaplığa dosyanın YOLU değil İÇERİĞİ verilir: sentencepiece Windows'ta Türkçe
    (ASCII dışı) karakter içeren yoldaki dosyayı açamıyor ("NOT_FOUND"). Kurulum programı uygulamayı kullanıcının
    klasörüne kurduğu için, kullanıcı adı "Şükrü" ya da "Çağrı" olan bilgisayarda yol böyledir; orada hazır çeviri
    hiç açılmazdı (2.5.0'da bulundu; Store paketinin klasörü ASCII olduğu için orada görülmez)."""
    import sentencepiece as spm
    with open(yol, "rb") as f:
        return spm.SentencePieceProcessor(model_proto=f.read())


def sozluk_yukle_modelden(spm_yolu):
    """OPUS-MT kaynak dağarcığındaki tam kelimeler (SentencePiece sırası kabaca sıklık sırasıdır)."""
    sp = spm_yukle(spm_yolu)
    parcalar = (sp.id_to_piece(i) for i in range(sp.get_piece_size()))
    sozluk_ayarla(p[1:] for p in parcalar if p.startswith("▁") and p[1:].replace("'", "").isalpha())


def _sira(k):
    return _sozluk.get(k.lower(), 10 ** 6) if _sozluk else 0


_EKLER = ("'s", "'re", "'ll", "'ve", "'d", "'m", "n't", "s", "es", "ed", "ing", "ly", "er", "est")


def _bilinen(k):
    """Kelime dağarcıkta mı (yaygın ekleriyle birlikte)? Dağarcık yüklü değilse her şey bilinir sayılır."""
    if _sozluk is None:
        return True
    k = k.lower().replace("’", "'")
    if k in _sozluk:
        return True
    return any(k.endswith(e) and len(k) > len(e) + 1 and k[:-len(e)] in _sozluk for e in _EKLER)


# İngilizcede (OCR hatasıyla bile) pek çıkmayan, Türkçe yazıyı ele veren harfler. "ı" ve "İ" bilerek yok:
# küçük yazıda "i"nin noktası okunmayabilir, İngilizce satırı Türkçe sanmayalım.
_TURKCE_HARF = set("çğöşüÇĞÖŞÜ")


def ingilizce_degil(metin):
    """Okunan yazı açıkça İngilizce altyazı DEĞİL mi? Altyazı alanına oyun yokken başka şeyler girer: Türkçe bir
    web sayfası, video oynatıcının düğmeleri, kanal adları. Bunlar çevrilince anlamsız Türkçe çıkar ve sesli okunur
    (kullanıcının ilk denemesinde oldu: YouTube sayfasındaki Türkçe başlıklar "çevrildi").
    TEMKİNLİDİR: emin olunmayan her şey İngilizce sayılır, çünkü gerçek bir altyazıyı atlamak çöpü çevirmekten
    kötüdür. Argo ve özel adlarla dolu kısa satırlar ("Yo Trev, whatcha doin?") bu yüzden atlanmaz.
    Yalnız iki durumda True döner:
      1. En az iki kelimede (ve kelimelerin dörtte birinde) Türkçeye özgü harf var VE bilinen İngilizce kelimeler
         azınlıkta ("Gerçek Hayatta Açlık Oyunları"). "Señor Müller, the façade is ready." atlanmaz.
      2. Üç ve daha çok harfli en az dört kelime var ve HİÇBİRİ İngilizce dağarcığında yok."""
    kelimeler = re.findall(r"[^\W\d_]{2,}", metin or "")
    if len(kelimeler) < 2:
        return False
    duz = [k for k in kelimeler if k.isascii() and len(k) >= 3]
    bilinen = sum(1 for k in duz if _bilinen(k)) if _sozluk is not None else 0
    turkce = sum(1 for k in kelimeler if _TURKCE_HARF & set(k))
    if turkce >= 2 and turkce * 4 >= len(kelimeler) and bilinen * 2 < max(1, len(duz)):
        return True
    return _sozluk is not None and len(duz) >= 4 and bilinen == 0


def ingilizce_kesin(metin):
    """Yazı büyük olasılıkla İngilizce mi? Tüm ekran kipi için SIKI denetim (ingilizce_degil temkinlidir: emin
    olamadığını İngilizce sayar; tüm ekranda bu, Türkçe menüleri ve programların arayüzünü de "çevirtirdi").
    Üç ve daha çok harfli kelimelerin en az %60'ı İngilizce dağarcığında olmalı ve Türkçeye özgü harf az olmalı."""
    kelimeler = re.findall(r"[^\W\d_]{2,}", metin or "")
    duz = [k for k in kelimeler if k.isascii() and len(k) >= 3]
    if not duz:
        return False
    if sum(1 for k in kelimeler if _TURKCE_HARF & set(k)) * 3 > len(kelimeler):
        return False
    if _sozluk is None:
        return not ingilizce_degil(metin)
    bilinen = sum(1 for k in duz if _bilinen(k))
    return bilinen >= 1 and bilinen * 10 >= 6 * len(duz)


# ================================================================ 1. OCR onarımı
# Kural: emin olunmayan hiçbir şey atılmaz. Sayılar, kodlar ve adlar ("4-7-2-1", "AK-47", "M4A1", "R2", "$500",
# "Kratos") olduğu gibi kalır. Yalnız küçük harfli bir kelimenin ORTASINA rakam karışmışsa ("waters2aljd",
# "c0ps") parça onarılır; onarılamazsa baştaki gerçek kelime kurtarılır; o da yoksa atılır.
_KENAR = "\"'\u201c\u201d\u2018\u2019\u00ab\u00bb()[]{}.,!?;:\u2026-\u2013\u2014"
_KELIME = re.compile(r"[A-Za-z\u00c0-\u024f]+(?:['\u2019\-][A-Za-z\u00c0-\u024f]+)*\Z")
_OLCULU_SAYI = re.compile(r"\d{1,4}(?:m|km|ft|yd|mi)\Z")   # altyazının yanındaki mesafe göstergesi: 23m, 150ft
_CIPLAK_SAYI = re.compile(r"\d{1,4}\Z")
_KISALTMA = {"mr", "mrs", "ms", "dr", "st", "jr", "sr", "vs", "etc", "no", "lt", "sgt", "col", "gen", "capt",
             "prof", "mt", "ft", "cmdr", "gov", "rev"}

# Görünüşü neredeyse aynı olan harfler: çoğu yazı tipinde karışır
_AYNI_GORUNEN = [("I", "l"), ("l", "I"), ("rn", "m"), ("vv", "w")]
# Rakam olarak okunmuş harfler
_RAKAM_HARF = [("0", "o"), ("0", "O"), ("1", "l"), ("1", "I"), ("5", "s"), ("5", "S"), ("8", "B")]
# İnce yazı tiplerinde karışanlar: yalnız çok sık bir kelime çıkıyorsa kabul edilir
_INCE_YAZI = [("l", "t"), ("I", "T")]
_SIK_KELIME = 3000
_COK_SIK_KELIME = 500


def _kenar_ayir(parca):
    i, j = 0, len(parca)
    while i < j and parca[i] in _KENAR:
        i += 1
    while j > i and parca[j - 1] in _KENAR:
        j -= 1
    return parca[:i], parca[i:j], parca[j:]


def _degisimler(kelime, ciftler):
    """Her çift için tek tek ve topluca değiştirilmiş biçimler."""
    for eski, yeni in ciftler:
        if eski not in kelime:
            continue
        yield kelime.replace(eski, yeni)
        bas = kelime.find(eski)
        while bas >= 0:
            yield kelime[:bas] + yeni + kelime[bas + len(eski):]
            bas = kelime.find(eski, bas + 1)


def _en_iyi(adaylar, en_fazla_sira=10 ** 6):
    if _sozluk is None:
        return None
    gecerli = {a for a in adaylar if _bilinen(a) and _sira(a.split("'")[0]) < en_fazla_sira}
    # eşit sıklıkta, ortasında büyük harf olmayan biçim ("cops", "cOps" değil)
    return min(gecerli, key=lambda a: (_sira(a), sum(c.isupper() for c in a[1:]))) if gecerli else None


def _harf_onar(kelime, cumle_basi):
    """Dağarcıkta olmayan kelimede karışan harfleri düzelterek gerçek bir kelime arar; bulamazsa dokunmaz.
    Çok kısa parçalarda (iki harf) yalnız çok sık kelimeler kabul edilir ("lt" -> "It"; "Al" adı "AI" olmaz)."""
    if _sozluk is None or len(kelime) < 2:
        return kelime
    # Küçük harfle yazılmış ama dağarcıkta yalnız büyük harfli biçimi olan parça ("lt": "Lt." var, "lt" yok) bilinmez sayılır
    yalniz_buyuk = kelime[0].islower() and kelime.lower().split("'")[0] in _ozel
    if _bilinen(kelime) and not yalniz_buyuk:
        # Dağarcıkta olan ama çok nadir kısa parça ("lt", "ls"): benzeri çok sık bir kelimeyse odur ("It", "Is")
        kok = kelime.split("'")[0]
        if len(kok) <= 3 and _sira(kok) > 2500:
            return _en_iyi(_degisimler(kelime, _AYNI_GORUNEN), 200) or kelime
        return kelime
    sinir = _COK_SIK_KELIME if len(kelime) <= 2 else 10 ** 6
    aday = _en_iyi(_degisimler(kelime, _AYNI_GORUNEN), sinir)
    ozel_ad_olabilir = kelime[0].isupper() and not cumle_basi and not kelime.isupper()
    if aday is None and not ozel_ad_olabilir and len(kelime) > 1:
        aday = _en_iyi(_degisimler(kelime, _INCE_YAZI), min(sinir, _SIK_KELIME))
    return aday or kelime


def _cop_adayi(c):
    """Küçük harfli kelimenin ortasına rakam karışmış mı? Kodlar (M4A1, MP5s, AK-47, 4x4, 1980s) aday değildir."""
    if "-" in c or not (c[0].isalpha() and c[-1].isalpha()):
        return False
    ilk_rakam = next((i for i, ch in enumerate(c) if ch.isdigit()), -1)
    return ilk_rakam > 0 and any(ch.islower() for ch in c[:ilk_rakam])


def _karisik_onar(cekirdek):
    """Rakamı harfe çevirerek kelime ara ("c0ps" -> "cops"); olmazsa baştaki gerçek kelimeyi kurtar
    ("waters2aljd" -> "waters"); o da olmazsa None (parça atılır)."""
    aday = _en_iyi(_degisimler(cekirdek, _RAKAM_HARF))
    if aday and _KELIME.match(aday):
        return aday
    bas = re.match(r"[A-Za-z]+", cekirdek)
    if bas and len(bas.group()) >= 3 and _sozluk is not None and bas.group().lower() in _sozluk:
        return bas.group()
    return None


def ocr_onar(metin):
    metin = re.sub(r"\s+", " ", metin or "").strip()
    # okunmamış boşluk: virgül/ünlem/sorudan sonra harf; noktadan sonra büyük harfle başlayan kelime
    metin = re.sub(r"(?<=[A-Za-z]{2})([,;!?])(?=[A-Za-z])", r"\1 ", metin)
    metin = re.sub(r"\b([A-Za-z]{2,})\.(?=[A-Z][a-z])",
                   lambda m: m.group(0) if m.group(1).lower() in _KISALTMA else m.group(1) + ". ", metin)
    if _sozluk is None:
        return metin  # dağarcık yüklü değil: kelime onarımı yapılamaz
    kalan = []
    for parca in metin.split(" "):
        on, cekirdek, son = _kenar_ayir(parca)
        if not cekirdek:
            kalan.append(parca)
            continue
        cumle_basi = not kalan or kalan[-1][-1:] in ".!?:\u2026"
        if _KELIME.match(cekirdek):
            cekirdek = _harf_onar(cekirdek, cumle_basi)
        elif _cop_adayi(cekirdek):
            cekirdek = _karisik_onar(cekirdek)
            if cekirdek is None:  # çöp: atılır; ardındaki noktalama cümleye aittir
                if son and kalan:
                    kalan[-1] += son
                continue
        kalan.append(on + cekirdek + son)
    # Altyazının yanındaki göstergenin sayısı satır başına yapışmış: "23m JASON: Over here!" (ölçülü sayı +
    # büyük harfle başlayan kelime) ya da "9 JASON: Over here!" (çıplak sayı + konuşmacı etiketi)
    if len(kalan) >= 3 and kalan[1][:1].isupper():
        if _OLCULU_SAYI.match(kalan[0]) or (_CIPLAK_SAYI.match(kalan[0]) and kalan[1].endswith(":")):
            kalan = kalan[1:]
    return " ".join(kalan)


# ================================================================ 2. düzleştirme
_ZAMIR = {"my": "me", "our": "us", "your": "you", "his": "him", "her": "her", "their": "them"}

# (desen, karşılık). Ölçülen ham çeviri -> karşılığın çevirisi yorumda. Sıra önemli: özel olan önce.
DEYIMLER = [
    (r"check (?:your|my|our) six", "check behind you"),              # Altınızı kontrol edin -> Arkanı kontrol et
    (r"(your|my|our|his|her) six", r"\1 back"),                      # Altını aldım -> Arkanı kollarım
    (r"lock and load", "get ready"),                                 # Kilitle ve yükle -> Hazır ol
    (r"took you long enough", "you finally came"),                   # Yeterince uzun sürdü -> Sonunda geldin
    (r"sitting ducks", "easy targets"),                              # ördek gibi oturuyoruz -> kolay hedefiz
    (r"five-?o", "police"),                                          # (düşüyor) -> Polis
    (r"(?:the )?po-?po", "the police"),                              # Po-po -> polis
    (r"pulled off the (heist|job|robbery|score)", r"completed the \1"),   # Soygundan kurtulduk -> Soygunu tamamladık
    (r"pull off the (heist|job|robbery|score)", r"complete the \1"),
    (r"(I'm|we're|you're|he's|she's|they're) toast", r"\1 doomed"),  # Kadeh kaldırıyoruz -> Mahvolduk
    (r"a piece of cake", "very easy"),                               # bir parça kek -> çok kolay
    (r"fire in the hole", "bomb incoming"),                          # Delikte ateş -> Bomba geliyor
    (r"tango down", "target down"),                                  # Tango düştü -> Hedef vuruldu
    (r"bite me", "screw you"),                                       # Isır beni -> Canın cehenneme
    (r"(he's|she's) a goner", r"\1 doomed"),                         # O bir goner -> Mahvoldu
    (r"stay frosty", "stay alert"),                                  # Donuk kal -> Tetikte olun
    (r"look alive", "stay alert"),                                   # Canlı görünün -> Tetikte olun
    (r"the coast is clear", "the area is clear"),                    # Kıyı temiz -> Bölge temiz
    (r"l(?:ay|ie) low", "stay hidden"),                              # eğilin -> saklan
    (r"let's bounce", "let's leave"),                                # Hadi zıplayalım -> Hadi gidelim
    (r"packing heat", "carrying a gun"),                             # Isı topluyor -> Silah taşıyor
    (r"(I'm|we're) all ears", r"\1 listening"),                      # Kulaklarım var -> Dinliyorum
    (r"spill the beans", "tell me everything"),                      # Fasulyeleri dökün -> Bana her şeyi anlat
    (r"a close call", "close"),                                      # yakın bir karardı -> Çok yakındı
    (r"(?:floor|gun|punch) it", "step on it"),                       # Yere yatın / Silahla / Yumruk -> Bas gaza
    (r"shake (them|him) off", r"get rid of \1"),                     # Sallayın onları -> Kurtul onlardan
    (r"lose (them|him)(?=!)", r"get rid of \1"),                     # Onları kaybedin -> Kurtul onlardan
    (r"on (my|our|your) tail", lambda m: "right behind " + _ZAMIR[m.group(1).lower()]),  # Kuyruğumda -> Tam arkamda
    (r"take point", "go first"),                                     # Sadede gel -> Önce sen
    (r"frag out", "grenade"),                                        # Lanet olsun -> El bombası
    (r"(?:waste|ice|whack|smoke) (him|her|them)", r"kill \1"),       # Buzla onu -> Öldürün onu
    (r"sounds like a plan", "good plan"),                            # Kulağa bir plan gibi geliyor -> İyi plan
    (r"hold the line", "hold your position"),                        # Sırayı koruyun -> Yerinizde kalın
    (r"hit the (?:deck|dirt)", "get down"),                          # Güverteye çık -> Yere yat
    (r"weapons hot", "weapons free"),                                # Silahlar ateşlendi -> Silahlar serbest
    (r"rally on me", "regroup"),                                     # Toplanın bana -> Toplanın
    (r"coming through", "make way"),                                 # Geliyorum -> Yol açın
    (r"not so fast", "hold on"),                                     # O kadar hızlı değil -> Bir dakika
    (r"dead ahead", "straight ahead"),                               # Çok ileride -> Dümdüz ileri
]
_DEYIM_RE = [(re.compile(r"\b" + d + r"\b", re.IGNORECASE), k) for d, k in DEYIMLER]


def _buyuk_koru(eslesme, karsilik):
    yeni = karsilik(eslesme) if callable(karsilik) else eslesme.expand(karsilik)
    return yeni[:1].upper() + yeni[1:] if eslesme.group(0)[:1].isupper() else yeni


def _normal_yazim(metin, adlar):
    """Tamamı büyük harfle yazılmış satırı cümle düzenine getirir; özel adlar büyük harfle kalır."""
    ad_kume = {a.lower() for ad in adlar for a in ad.split()}
    cikti, bas = [], True
    for parca in metin.split(" "):
        on, c, son = _kenar_ayir(parca)
        k = c.lower()
        ozel = k in ad_kume or k in _ozel or (_sozluk is not None and len(k) > 2 and not _bilinen(k))
        if k == "i" or k.startswith("i'") or ozel or (bas and c):
            k = k[:1].upper() + k[1:]
        cikti.append(on + k + son)
        if c:
            bas = (son[:1] in ".!?:…") if son else False
    return " ".join(cikti)


def duzlestir(metin, adlar=()):
    harfler = [c for c in metin if c.isalpha()]
    if len(harfler) >= 6 and sum(c.isupper() for c in harfler) / len(harfler) > 0.85:
        metin = _normal_yazim(metin, adlar)
    for desen, karsilik in _DEYIM_RE:
        metin = desen.sub(lambda m, k=karsilik: _buyuk_koru(m, k), metin)
    return metin


# ================================================================ 3. cümlelere bölme
_BOLME = re.compile(r"(?:(?<=[.!?…])|(?<=[.!?…][\"”’)]))\s+(?=[\"“‘(\[]?[A-ZÀ-Þ0-9])")


def cumlelere_bol(metin):
    """Satırı cümlelerine ayırır. Kısaltmadan ("Mr.", "Dr.") ve tek harfli baş harften ("J.") sonra bölmez."""
    parcalar, bekleyen = [], ""
    for p in _BOLME.split(metin.strip()):
        p = (bekleyen + " " + p).strip() if bekleyen else p
        son_kelime = re.search(r"([A-Za-z]+)\.$", p)
        if son_kelime and (son_kelime.group(1).lower() in _KISALTMA or len(son_kelime.group(1)) == 1) \
                and not p.endswith("..."):
            bekleyen = p
            continue
        bekleyen = ""
        if p:
            parcalar.append(p)
    if bekleyen:
        parcalar.append(bekleyen)
    return parcalar or [metin]


# ================================================================ 4. hazır karşılıklar
# Tek başına cümle olduğunda modelin yanlış çevirdiği kısa ifadeler: (düz/ünlem karşılığı, soru karşılığı).
# None: o biçimde model doğru çeviriyor. Ölçülen ham çeviri yorumda.
HAZIR = {
    "roger": ("Anlaşıldı", "Anlaşıldı mı?"),          # Roger.
    "who": ("Kim", "Kim?"),                            # Kime?
    "huh": ("Ha", "Ha?"),                              # Huh?
    "hey": ("Hey", "Hey?"),                            # Merhaba!
    "what": ("Ne", "Ne?"),                             # Ne var?
    "why": (None, "Neden?"),                           # Neden mi?
    "yes": ("Evet", None),                             # Tamam. / İşte bu!
    "go": ("Yürü", None),                              # Git!
    "freeze": ("Kımıldama", None),                     # Dur!
    "on me": ("Beni takip edin", None),                # Üzerime!
    "contact": ("Düşman görüldü", None),               # Temas!
    "bingo": ("İşte bu", None),                        # Tombala!
    "medic": ("Sıhhiye", None),                        # Doktor!
    "officer down": ("Polis vuruldu", None),           # Memur yaralandı!
    "up there": ("Yukarıda", "Yukarıda mı?"),          # Yukarı!
    "down here": ("Aşağıda", "Aşağıda mı?"),           # Aşağıya!
    "in here": ("Buraya", "Burada mı?"),               # Buradayım!
    "covering fire": ("Koruma ateşi", None),           # Ateşi kapatın!
    "suppressing fire": ("Baskı ateşi", None),         # Ateşi bastırın!
    "fall in": ("Sıraya girin", None),                 # Yere yatın!
    "double time": ("Daha hızlı", None),               # Çifte zaman!
    "keep up": ("Geride kalma", None),                 # Devam edin!
    "jesus christ": ("Aman Tanrım", None),             # Yüce İsa.
    "hello": ("Merhaba", "Alo?"),                      # Merhabalar. / Alo? Alo?
}
_SON = re.compile(r"([.!?…]+)[\"'”’)\]]*$")


def _sonu(c):
    m = _SON.search(c.strip())
    return m.group(1) if m else ""


def hazir_karsilik(cumle):
    """Tek cümlenin hazır Türkçesi; tabloda yoksa (ya da o biçimi yoksa) None."""
    govde = re.sub(r"[.!?…\"'“”‘’,]+", " ", cumle).strip().lower()
    govde = re.sub(r"\s+", " ", govde)
    kayit = HAZIR.get(govde)
    if not kayit:
        return None
    son = _sonu(cumle)
    if "?" in son:
        return kayit[1]
    return kayit[0] + (son or "") if kayit[0] else None


# ================================================================ konuşmacı etiketi ve ad koruma
# "JASON: ..." ya da "Jason: ..." — satır başındaki konuşmacı adı çevrilmez, olduğu gibi başa konur.
_ETIKET = re.compile(r"^\s*([A-Z][A-Za-z0-9.'\-]{0,20}(?: [A-Z][A-Za-z0-9.'\-]{0,20}){0,2})\s*:\s+(?=\S)")
# İki nokta ile başlayan ama konuşmacı olmayan satır başları ("Note: ...")
_ETIKET_DEGIL = {"note", "warning", "tip", "hint", "objective", "mission", "update", "reminder", "attention",
                 "caution", "remember", "listen", "look", "ok", "okay", "well", "so", "now", "and", "but", "wait",
                 "ps", "answer", "question", "rule", "step", "example", "result", "error", "status", "location",
                 "time", "date", "score", "level", "target", "goal", "task", "quest", "reward", "new", "next",
                 "day", "chapter", "act", "part", "episode", "also", "first", "second", "third", "finally",
                 "plan", "problem", "solution", "fact", "truth", "point", "translation", "meaning", "summary"}
_gorulen_etiket = {}  # ad (küçük harf) -> (yazılışı, kaç kez etiket olarak görüldü)
AD_OGRENME_ESIGI = 2
_YAYGIN_KELIME = 12000  # dağarcıkta bu sıradan önce gelen kelime "yaygın" sayılır


def etiket_ayir(metin):
    """(konuşmacı adı ya da None, kalan metin). Ad her görülüşte sayılır: sık görülen ad cümle içinde de korunur."""
    m = _ETIKET.match(metin or "")
    if not m:
        return None, metin
    ad = m.group(1).strip()
    if ad.split(" ")[0].lower().rstrip(".") in _ETIKET_DEGIL or not any(c.isalpha() for c in ad):
        return None, metin
    anahtar = ad.lower()
    yazilis = ad.title() if ad.isupper() and len(ad) > 2 else ad
    kac = _gorulen_etiket.get(anahtar, (yazilis, 0))[1] + 1
    _gorulen_etiket[anahtar] = (yazilis, kac)
    # Küçük harfle de yaygın olan tek kelime ("Seriously: stop.", "Soap: ...") ilk görülüşte konuşmacı sayılmaz;
    # gerçek konuşmacı etiketi tekrar eder ve ikinci görülüşten itibaren ad olarak işlenir. BÜYÜK HARFLİ etiketler,
    # çok kelimeli adlar ve dağarcıkta sıradan kelime olmayan adlar ("Kratos", "Jason") hemen kabul edilir.
    tek_kelime = " " not in ad and not ad.isupper()
    if tek_kelime and _sozluk is not None and anahtar in _sozluk and anahtar not in _ozel \
            and _sira(anahtar) < _YAYGIN_KELIME and kac < AD_OGRENME_ESIGI:
        return None, metin
    return ad, metin[m.end():]


def ogrenilen_adlar():
    """Bu oturumda en az iki kez konuşmacı etiketi olarak görülen adlar."""
    return [y for y, n in _gorulen_etiket.values() if n >= AD_OGRENME_ESIGI]


# Yer tutucular: modelin olduğu gibi bıraktığı ve doğru Türkçe eki getirdiği uydurma adlar (ölçüldü: 27 addan
# 27'si 12 cümle kalıbının hepsinde korundu). Gerçek adın son ünlüsüne ve son harfine uyan seçilir ki ek doğru gelsin:
# (ünlü sınıfı, bitiş) -> a: a/ı, e: e/i/ö/ü, o: o/u  |  y: yumuşak ünsüz, s: sert ünsüz, u: ünlü
_YER_TUTUCU = {
    ("a", "y"): ("Zorvan", "Tarvan", "Halvar"), ("a", "s"): ("Zorvak", "Tarvak", "Varnak"), ("a", "u"): ("Zorva", "Tarva"),
    ("e", "y"): ("Kelmin", "Belmir", "Selvin"), ("e", "s"): ("Kelmit", "Belmit", "Senvik"), ("e", "u"): ("Kelmi", "Belmi"),
    ("o", "y"): ("Dorgun", "Morlun", "Bordun"), ("o", "s"): ("Dorguk", "Morluk", "Korduk"), ("o", "u"): ("Dorgu", "Morlu"),
}
_TUM_YER_TUTUCULAR = {a for grup in _YER_TUTUCU.values() for a in grup}
_UNLU = "aeıioöuü"
_SERT = "pçtkfhsşx"


def _ad_sinifi(ad):
    k = ad.lower().split(" ")[-1]
    if len(k) > 2 and k.endswith("e") and k[-2] not in _UNLU:  # okunmayan son "e": Hope, Price, Mike
        k = k[:-1]
    son = k[-1:]
    unlu_biten = son in _UNLU or son == "y"
    unlu = next((c for c in reversed(k) if c in _UNLU), "i" if "y" in k else "a")
    sinif = "a" if unlu in "aı" else "o" if unlu in "ou" else "e"
    return sinif, ("u" if unlu_biten else "s" if son in _SERT else "y")


def adlari_koru(cumle, adlar):
    """Bilinen adları yer tutucularla değiştirir. Dönüş: (yeni cümle, {yer tutucu: ad})."""
    harita = {}
    for ad in sorted({a for a in adlar if a and len(a) > 1}, key=len, reverse=True):
        desen = re.compile(r"\b" + re.escape(ad) + r"\b")
        if not desen.search(cumle):
            continue
        secenek = [y for y in _YER_TUTUCU[_ad_sinifi(ad)] if y not in harita and y.lower() not in cumle.lower()]
        if not secenek:
            continue
        harita[secenek[0]] = ad
        cumle = desen.sub(secenek[0], cumle)
    return cumle, harita


def adlari_geri_koy(tr, harita):
    """Yer tutucuların yerine gerçek adları koyar. Bir yer tutucu çeviride yoksa ya da fazladan biri kaldıysa None
    (çağıran korumasız çeviriye döner)."""
    for yer, ad in harita.items():
        if yer not in tr:
            return None
        tr = tr.replace(yer, ad)
    return None if any(y in tr for y in _TUM_YER_TUTUCULAR) else tr


# Tek tek okunan rakamlar ("4-7-2-1"): model bunları düşürüyor ("Kod öyle."); çeviride tek sayı olarak taşınır.
_RAKAM_DIZISI = re.compile(r"\b\d(?:[-\u2013]\d){2,}\b")


def rakam_dizisi_koru(cumle):
    harita = {}

    def degis(m):
        duz = re.sub(r"\D", "", m.group(0))
        harita[duz] = m.group(0)
        return duz
    return _RAKAM_DIZISI.sub(degis, cumle), harita


def rakam_dizisi_geri_koy(tr, harita):
    for duz, asil in harita.items():
        tr = tr.replace(duz, asil)
    return tr


# ================================================================ 5. son düzeltme
# Model emirleri çoğu zaman "siz" ile çevirir ("Arabaya binin!"); oyunda karakterler birbirine "sen" der.
# Satırda açıkça "siz"li bir hitap yoksa cümle sonundaki emir kibar halinden yalın haline çevrilir.
# (Yöntem CouchSubs'ın TurkishPostEdit'inden; liste kendi listemiz. Belirsiz olanlar alınmadı: "kaçın" = sakın.)
_SIZ = re.compile(r"(?<![^\W\d_])(siz|sizi|size|sizin|sizde|sizden|sizinle|efendim|bayım|hanımefendi|beyefendi)(?![^\W\d_])", re.I)
_EMIRLER = {"bekleyin": "bekle", "durun": "dur", "gelin": "gel", "gidin": "git", "koşun": "koş", "bakın": "bak",
            "dinleyin": "dinle", "söyleyin": "söyle", "verin": "ver", "yapın": "yap", "bırakın": "bırak",
            "çıkın": "çık", "girin": "gir", "binin": "bin", "inin": "in", "susun": "sus", "açın": "aç",
            "kapatın": "kapat", "tutun": "tut", "edin": "et", "olun": "ol", "hazırlanın": "hazırlan",
            "atlayın": "atla", "izleyin": "izle", "getirin": "getir", "götürün": "götür", "anlatın": "anlat",
            "unutun": "unut", "deneyin": "dene", "başlayın": "başla"}
_EMIR = re.compile(r"(?<![^\W\d_])(" + "|".join(sorted(_EMIRLER, key=len, reverse=True)) + r")(?=\s*[!.,?…]|\s*$)", re.I)


def sen_diye_hitap(tr):
    if not tr or _SIZ.search(tr):
        return tr

    def cevir(m):
        yeni = _EMIRLER.get(m.group(1).lower())
        if not yeni:
            return m.group(1)
        return yeni[:1].upper() + yeni[1:] if m.group(1)[:1].isupper() else yeni
    return _EMIR.sub(cevir, tr)


def son_duzelt(kaynak, tr):
    tr = re.sub(r"\s+([.,!?;:…])", r"\1", (tr or "").strip())
    tr = sen_diye_hitap(tr)
    tr = re.sub(r"^[-–]\s*", "", tr)
    ks, ts = _sonu(kaynak), _sonu(tr)
    if ks and ks != ts and (set(ks) & set("!?…") or ks == "..."):
        govde = tr[:len(tr) - len(ts)].rstrip() if ts and tr.endswith(ts) else tr
        # soru eki olan çeviriye ("... mi?") ünlem dayatılmaz; soru kaynağın sorusuysa korunur
        if not ("?" in ts and "?" not in ks):
            tr = govde + ks
    # kaynak normal yazılmışken çıktı tamamen BÜYÜK HARF ise normal yazım
    kh = [c for c in kaynak if c.isalpha()]
    th = [c for c in tr if c.isalpha()]
    if len(th) >= 6 and all(c.isupper() for c in th) and kh and not all(c.isupper() for c in kh):
        tr = tr[:1] + tr[1:].replace("I", "ı").replace("İ", "i").lower()
    return tr


# ================================================================ bölünmüş cümle
def bitmemis_mi(metin):
    """Cümle ortasında kesilmiş satır mı (bölünmüş altyazının parçası)? Cümle sonu noktalaması yok, en az iki kelime."""
    m = metin.strip().rstrip("\"'”’)")
    if not m or _sonu(m):
        return False
    return len(re.findall(r"[A-Za-z]+", m)) >= 2


def devam_mi(metin):
    """Önceki bitmemiş satırın devamı olabilir mi: küçük harfle başlıyor."""
    m = metin.strip().lstrip("-–—…. ")
    return bool(m) and m[0].islower()
