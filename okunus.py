"""Seslendirmeden önce Türkçe metni okunuşa hazırlar: sayılar yazıyla, simgeler sözcükle.

Ses modelleri rakamları ve simgeleri tutarsız okuyor ("3" -> "three", "%20" -> "yüzde yirmi" ya da hiç).
  "3 kişi" -> "üç kişi"   "1250" -> "bin iki yüz elli"   "3,5" -> "üç virgül beş"   "%20" -> "yüzde yirmi"
  "$500" -> "beş yüz dolar"   "12:30" -> "on iki otuz"   "2." (sıra) -> "ikinci"   "+" -> "artı"
"""
import re

_BIR = ["", "bir", "iki", "üç", "dört", "beş", "altı", "yedi", "sekiz", "dokuz"]
_ON = ["", "on", "yirmi", "otuz", "kırk", "elli", "altmış", "yetmiş", "seksen", "doksan"]
_BUYUK = [(10 ** 12, "trilyon"), (10 ** 9, "milyar"), (10 ** 6, "milyon"), (1000, "bin")]


def sayi_yazi(n):
    if n == 0:
        return "sıfır"
    if n < 0:
        return "eksi " + sayi_yazi(-n)
    parcalar = []
    for deger, ad in _BUYUK:
        if n >= deger:
            kac, n = divmod(n, deger)
            parcalar.append(ad if (deger == 1000 and kac == 1) else f"{sayi_yazi(kac)} {ad}")
    if n >= 100:
        yuz, n = divmod(n, 100)
        parcalar.append("yüz" if yuz == 1 else f"{_BIR[yuz]} yüz")
    if n >= 10:
        parcalar.append(_ON[n // 10])
        n %= 10
    if n:
        parcalar.append(_BIR[n])
    return " ".join(parcalar)


def _sira_eki(yazi):
    """"iki" -> "ikinci", "dört" -> "dördüncü" (ünlü uyumu)."""
    son = yazi.split(" ")[-1]
    ozel = {"bir": "birinci", "iki": "ikinci", "üç": "üçüncü", "dört": "dördüncü", "beş": "beşinci", "altı": "altıncı",
            "yedi": "yedinci", "sekiz": "sekizinci", "dokuz": "dokuzuncu", "on": "onuncu", "yirmi": "yirminci",
            "otuz": "otuzuncu", "kırk": "kırkıncı", "elli": "ellinci", "altmış": "altmışıncı", "yetmiş": "yetmişinci",
            "seksen": "sekseninci", "doksan": "doksanıncı", "yüz": "yüzüncü", "bin": "bininci", "milyon": "milyonuncu"}
    return yazi[: len(yazi) - len(son)] + ozel.get(son, son + "inci")


def _tam(s):
    return sayi_yazi(int(s.replace(".", "").replace(" ", "")))


def okunus(metin):
    m = metin
    m = re.sub(r"(\d{1,2}):(\d{2})\b", lambda x: f"{_tam(x.group(1))} {_tam(x.group(2)) if int(x.group(2)) else ''}".strip(), m)
    m = re.sub(r"%\s?(\d+(?:[.,]\d+)?)", lambda x: "yüzde " + _ondalik(x.group(1)), m)
    m = re.sub(r"(\d+(?:[.,]\d+)?)\s?%", lambda x: "yüzde " + _ondalik(x.group(1)), m)
    for simge, ad in (("$", "dolar"), ("€", "avro"), ("£", "sterlin"), ("₺", "lira")):
        m = re.sub(re.escape(simge) + r"\s?(\d+(?:[.,]\d+)*)", lambda x, ad=ad: _ondalik(x.group(1)) + " " + ad, m)
        m = re.sub(r"(\d+(?:[.,]\d+)*)\s?" + re.escape(simge), lambda x, ad=ad: _ondalik(x.group(1)) + " " + ad, m)
    m = re.sub(r"\b(\d+)\.(?=\s+[a-zçğıöşü])", lambda x: _sira_eki(_tam(x.group(1))), m)  # "2. kat" -> ikinci kat
    m = re.sub(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?", lambda x: _ondalik(x.group(0)), m)
    m = m.replace(" + ", " artı ").replace("&", " ve ")
    return re.sub(r"\s+", " ", m).strip()


def _ondalik(s):
    s = s.strip()
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?", s):  # 1.250 / 1.250,5 (Türkçe binlik)
        s = s.replace(".", "")
    if "," in s:
        a, b = s.split(",", 1)
        return f"{_tam(a or '0')} virgül {_tam(b) if b.lstrip('0') else ' '.join('sıfır' for _ in b)}"
    if "." in s and re.fullmatch(r"\d+\.\d+", s):  # 3.5 (İngilizce ondalık çeviriden kalmış)
        a, b = s.split(".", 1)
        return f"{_tam(a)} nokta {_tam(b)}"
    return _tam(s) if s else s
