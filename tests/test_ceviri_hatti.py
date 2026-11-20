"""Çeviri hattı (ceviri_hatti.py + cevrimdisi motor): OCR onarımı, deyimler, kısa ünlemler, noktalama,
bölünmüş cümle. Gerçek OPUS-MT modeliyle çalışır; Türkçenin kendisi değil, kurallar denetlenir."""
import glob
import os
import re
import shutil
import tempfile
import time

import yardimci  # noqa: F401
import ceviri
import ceviri_hatti as h


def test_ceviri_hatti():
    m = ceviri.CevrimdisiMotor(ceviri.sozluk_yukle())

    def tr(en):
        return m.cevir(h.ocr_onar(en), [])

    # --- OCR onarımı: çöp atılır, gerçek sayı/kod/ad korunur
    assert h.ocr_onar("Io make sure the cops do nol follow us.") == "To make sure the cops do not follow us."
    assert h.ocr_onar("We need to move,brother.No time.") == "We need to move, brother. No time."
    assert h.ocr_onar("23m JASON: Over here!") == "JASON: Over here!"
    assert h.ocr_onar("The waters2aljd are rising fast.") == "The waters are rising fast."
    assert h.ocr_onar("The c0ps are here, he1p me!") == "The cops are here, help me!"
    assert h.ocr_onar("heIIo, my friend. lt's over.") == "hello, my friend. It's over."
    for dokunulmaz in ("Press R2 to fire the 2nd gun, $500 for PS5.", "Kratos, the Leviathan is here.",
                       "The code is 4-7-2-1.", "Grab the AK-47 and the M4A1.", "Two MP5s and a B-52.",
                       "1987. That was the year.", "5 Minutes left.", "Al, get in the car.",
                       "He paid 3.5 million in 1998, 20% more.", "T-800 model, 4x4 truck, 2v2 match.",
                       "I saw Dr.Smith and Mr.Jones."):
        assert h.ocr_onar(dokunulmaz) == dokunulmaz, f"dokunulmamalıydı: {h.ocr_onar(dokunulmaz)}"

    # --- İngilizce altyazı olmayan yazı çevrilmez (Türkçe sayfa yazısı, oynatıcı düğmeleri); şüphede çevrilir
    for cop in ("Gerçek Hayatta Açlık Oyunları'nı Yaptık", "Türkçe dublaj için abone olmayı unutmayın",
                "Görüntüleme sayısı çok yüksek, üç gün önce yüklendi", "bayBeast Katil Malikaneye abone olun",
                "Ayarlar Oynatma hizi Kalite Altyazilar"):
        assert h.ingilizce_degil(cop), f"çevrilmemeliydi: {cop}"
    for altyazi in ("Lucia, get in the car. The cops are right behind us!", "Yo Trev, whatcha doin?", "JASON: Yeah.",
                    "Go go go!", "Señor Müller, the façade is ready.", "Kratos! Atreus! Mimir!", "Hmm.", "EPIC W X",
                    "Wıth thıs lıttle key we wın.", "Nah nah, fuhgeddaboudit, capisce?", "It's 15:44, hurry up!",
                    "RDR2 >> GTA5 lol gg wp", "Über cool, Björn. Really cool."):
        assert not h.ingilizce_degil(altyazi), f"altyazı atlanmamalıydı: {altyazi}"
    assert not h.ingilizce_degil("") and not h.ingilizce_degil(None)

    # --- düzleştirme ve bölme
    assert h.duzlestir("GET IN THE CAR, LUCIA!", ["Lucia"]) == "Get in the car, Lucia!"
    assert h.duzlestir("I've got your six.") == "I've got your back."
    assert h.cumlelere_bol("Police! Run!") == ["Police!", "Run!"]
    assert h.cumlelere_bol("Mr. Smith is here. Get the car.") == ["Mr. Smith is here.", "Get the car."]
    assert h.cumlelere_bol("I... I don't know.") == ["I...", "I don't know."]
    assert h.etiket_ayir("Note: this door is locked.")[0] is None
    h._gorulen_etiket.clear()
    assert h.etiket_ayir("Seriously: stop.")[0] is None, "sıradan kelime ilk görülüşte konuşmacı sayılmamalı"
    assert h.etiket_ayir("Kratos: Boy!")[0] == "Kratos" and h.etiket_ayir("SOAP: Moving.")[0] == "SOAP"
    assert h.etiket_ayir("Master Chief: Finish the fight.")[0] == "Master Chief"
    h._gorulen_etiket.clear()
    assert h.etiket_ayir("Snake: I'm here.")[0] is None and h.etiket_ayir("Snake: Kept you waiting.")[0] == "Snake"
    h._gorulen_etiket.clear()

    # --- çeviri: ölçülmüş beklenen sonuçlar (model + hat)
    beklenen = {
        "Police! Run!": "Polis! Kaçın!",                      # ham model ikinci cümleyi düşürüyordu
        "I've got your six.": "Arkanı kollarım.",             # ham: Altını aldım.
        "We're toast.": "Mahvolduk.",                         # ham: Kadeh kaldırıyoruz.
        "It's a piece of cake.": "Çok kolay.",                # ham: Bu bir parça kek.
        "Floor it!": "Bas gaza!",                             # ham: Yere yatın!
        "The coast is clear.": "Bölge temiz.",                # ham: Kıyı temiz.
        "Roger.": "Anlaşıldı.", "Who?": "Kim?", "Freeze!": "Kımıldama!", "Medic!": "Sıhhiye!",
        "Go! Go! Go!": "Yürü! Yürü! Yürü!", "Yes.": "Evet.",
        "The code is 4-7-2-1.": "Kod 4-7-2-1'dir.",
    }
    for en, bek in beklenen.items():
        assert tr(en) == bek, f"{en} -> {tr(en)} (beklenen {bek})"
    assert tr("What the hell is going on here?!").endswith("?!")
    assert tr("I can't believe you did that...").endswith("...")
    assert "Jason" in tr("Jason, get in the car!") and "Vice City" in tr("Meet me at Vice City beach tonight.")
    assert tr("LUCIA: WHERE ARE YOU GOING?").startswith("LUCIA: ")
    assert tr("Kratos: Boy!").startswith("Kratos: "), "karışık yazılı etiket de korunmalı"

    # --- ad koruma: iki kez konuşmacı etiketi olarak görülen ad cümle içinde de çevrilmez
    h._gorulen_etiket.clear()
    assert "Sabun" in tr("Soap, cover me!"), "henüz öğrenilmemiş ad (ham modelin davranışı)"
    tr("SOAP: I'm in position.")
    tr("SOAP: Moving up.")
    assert "Soap" in h.ogrenilen_adlar()
    for en, parca in (("Soap, cover me!", "Soap, "), ("Where is Soap?", "Soap nerede"), ("This is Soap's rifle.", "Soap'ın"),
                      ("Give the rifle to Soap.", "Soap'a")):
        assert parca in tr(en), f"{en} -> {tr(en)}"
    h._gorulen_etiket.clear()

    # --- bölünmüş cümle: ekranda cümlenin tamamı, seslendirme için yalnız yeni parça
    sonuc, tekler = [], []
    isci = ceviri.CeviriIscisi(m, lambda i, en, t, s: (sonuc.append(t), tekler.append(isci.son_tek)),
                               onbellek_yolu=None, motor_adi="cevrimdisi", birlestir=True)
    for i, p in enumerate(["You're the ones", "who are gonna need help", "when they come for you."]):
        isci.ekle(i, p)
        time.sleep(0.5)
    isci.ekle(9, "Hurry!")  # bitmiş cümleden sonra gelen satır birleşmemeli
    time.sleep(0.6)
    isci.durdur()
    assert len(sonuc) == 4 and len(sonuc[2]) > len(sonuc[0]) + 15, sonuc
    assert tekler[0] is None and tekler[1] and tekler[2] and len(tekler[2]) < len(sonuc[2]), tekler
    assert tekler[3] is None and sonuc[3], (sonuc, tekler)
    # internetli motorlarda (bağlam alırlar) birleştirme yapılmaz
    sonuc2 = []
    isci2 = ceviri.CeviriIscisi(m, lambda i, en, t, s: sonuc2.append((t, isci2.son_tek)), onbellek_yolu=None,
                                motor_adi="gemini", birlestir=False)
    isci2.ekle(1, "You're the ones")
    time.sleep(0.4)
    isci2.ekle(2, "who are gonna need help")
    time.sleep(0.5)
    isci2.durdur()
    assert all(t is None for _, t in sonuc2), sonuc2

    # --- önbellek anahtarı motor ve kural sürümünü içerir
    assert all(k.startswith(f"cevrimdisi#{ceviri.CeviriIscisi.KURAL_SURUMU}#") for k in isci.onbellek), list(isci.onbellek)[:2]
    print(f"  ✓ çeviri hattı: OCR onarımı, deyimler, ünlemler, noktalama, ad koruma, bölünmüş cümle ({sonuc[2]})")


def test_turkce_yol():
    """Hazır çeviri, Türkçe karakterli bir klasörden de açılmalı. Kurulum programı uygulamayı kullanıcının klasörüne
    kurar; kullanıcı adı "Şükrü" olan bilgisayarda model yolu böyledir. sentencepiece böyle bir yoldaki dosyayı
    açamadığı için hazır çeviri orada hiç çalışmıyordu (2.5.0'da bulundu): dosya artık içeriğiyle yükleniyor."""
    gecici = tempfile.mkdtemp(prefix="cta_yol_")
    kopya = os.path.join(gecici, "Şükrü Öğün ığİ çÇ", "modeller", "en-tr")
    shutil.copytree(ceviri.model_klasoru(), kopya)
    asil_klasor, asil_model = ceviri.model_klasoru, ceviri.CevrimdisiMotor._paylasilan
    try:
        ceviri.model_klasoru = lambda: kopya
        ceviri.CevrimdisiMotor._paylasilan = None  # model bu klasörden yeniden yüklensin
        sonuc = ceviri.CevrimdisiMotor().cevir("Get in the car, the cops are behind us!", [])
        assert "araba" in sonuc.lower() and "polis" in sonuc.lower(), sonuc
        assert h.spm_yukle(os.path.join(kopya, "source.spm")).get_piece_size() > 1000
    finally:
        ceviri.model_klasoru, ceviri.CevrimdisiMotor._paylasilan = asil_klasor, asil_model
        shutil.rmtree(gecici, ignore_errors=True)
    # kimse yeniden yoluyla yüklemesin (yalnız ceviri_hatti.spm_yukle kullanılır)
    for dosya in glob.glob(os.path.join(yardimci.PROJE, "*.py")):
        with open(dosya, encoding="utf-8") as f:
            assert not re.search(r"SentencePieceProcessor\((?!\s*model_proto\s*=)", f.read()), \
                f"{os.path.basename(dosya)}: SentencePiece dosyası yoluyla yükleniyor; ceviri_hatti.spm_yukle kullanılmalı"
    print(f"  ✓ hazır çeviri Türkçe karakterli klasörden de açılıyor ({sonuc})")


if __name__ == "__main__":
    test_ceviri_hatti()
    test_turkce_yol()
