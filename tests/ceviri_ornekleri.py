"""Çevrimdışı çeviri hattının sınama satırları (oyun altyazılarında sık görülen sorunlar).

Her öğe: (OCR'dan gelen İngilizce, açıklama). Beklenen Türkçe kesin değil; kalite elle ve
`tests/test_ceviri_hatti.py`'deki kurallarla (ör. noktalama korunuyor mu, isim çevrildi mi) denetlenir.
"""
ORNEKLER = [
    ("GET IN THE CAR, WE HAVE TO GO!", "tamamı büyük harf"),
    ("LUCIA: WHERE ARE YOU GOING?", "büyük harfli konuşmacı + büyük harf"),
    ("I've got your six.", "oyun deyimi"),
    ("Heads up, we've got company!", "iki deyim"),
    ("Lock and load, people.", "deyim"),
    ("Took you long enough.", "deyim"),
    ("Well?", "kısa ünlem"),
    ("See?", "kısa ünlem"),
    ("Okay.", "kısa ünlem"),
    ("Hurry!", "kısa ünlem"),
    ("Brother?", "kısa hitap"),
    ("Morning!", "selam"),
    ("Io make sure the cops do nol follow us.", "OCR: t->l/I harf karışıklığı"),
    ("We need to move,brother.No time.", "OCR: noktadan sonra boşluk yok"),
    ("23m JASON: Over here!", "satır başına yapışan gösterge"),
    ("The waters2aljd are rising fast.", "OCR çöpü"),
    ("You're the ones", "bölünmüş cümle 1/3"),
    ("who are gonna need help", "bölünmüş cümle 2/3"),
    ("when they come for you.", "bölünmüş cümle 3/3"),
    ("Jason, get in the car!", "isim korunmalı"),
    ("Meet me at Vice City beach tonight.", "yer adı korunmalı"),
    ("Run!", "ünlem korunmalı"),
    ("What the hell is going on here?!", "?! korunmalı"),
    ("I told you. Wait here!", "sen/siz tutarlılığı"),
    ("Five-O! Five-O! Get down!", "argo"),
    ("Nice work, homie.", "argo"),
    ("We pulled off the heist.", "terim"),
    ("Don't do anything stupid.", "düz cümle"),
    ("If we don't leave now, we're dead.", "koşul"),
    ("I can't believe you did that...", "üç nokta korunmalı"),
]
