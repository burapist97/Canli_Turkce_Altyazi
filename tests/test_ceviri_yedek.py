"""Anahtarlı çeviri motoru bozulunca (süresi dolan anahtar, kota, internet) yedeğe geçiş ve uyarı."""
import yardimci  # noqa: F401

import ceviri


class _Yanit:
    def __init__(self, kod, metin=""):
        self.status_code, self.text = kod, metin


class _Bozuk:
    def __init__(self, hata):
        self.hata, self.cagri = hata, 0

    def cevir(self, metin, baglam):
        self.cagri += 1
        if self.hata:
            raise self.hata
        return "asıl:" + metin


class _Yedek:
    def cevir(self, metin, baglam):
        return "yedek:" + metin


def test_ceviri_yedek():
    # HTTP yanıtları doğru hata türüne çevriliyor mu
    h = ceviri._http_hatasi
    assert isinstance(h("Gemini", _Yanit(400, '{"error":{"message":"API key expired. Please renew the API key."}}')),
                      ceviri.AnahtarHatasi)
    assert isinstance(h("Groq", _Yanit(401, "invalid_api_key")), ceviri.AnahtarHatasi)
    assert isinstance(h("Gemini", _Yanit(429, "RESOURCE_EXHAUSTED")), ceviri.KotaHatasi)
    assert isinstance(h("Claude", _Yanit(400, "Your credit balance is too low")), ceviri.KotaHatasi)
    assert isinstance(h("Groq", _Yanit(503)), ceviri.BaglantiHatasi)
    assert type(h("Groq", _Yanit(400, "bad request"))) is ceviri.CeviriHatasi

    # Süresi dolmuş anahtar: yedeğe geç, uyarı ver, 10 dk asıl motoru deneme
    asil = _Bozuk(ceviri.AnahtarHatasi("Gemini anahtarı geçersiz ya da süresi dolmuş."))
    y = ceviri.YedekliMotor([("gemini", asil), ("cevrimdisi", _Yedek())])
    assert y.uyari() is None
    assert y.cevir("hi", []) == "yedek:hi"
    u = y.uyari()
    assert u and u["asil"] == ceviri.MOTOR_ADLARI["gemini"] and u["aktif"] == ceviri.MOTOR_ADLARI["cevrimdisi"], u
    assert "süresi dolmuş" in u["neden"]
    y.cevir("hi2", [])
    assert asil.cagri == 1, "bozuk anahtar her satırda tekrar denenmemeli"
    assert y.ceza["gemini"] - ceviri.time.time() > 500

    # Asıl motor düzelince uyarı kalkar
    asil.hata = None
    y.ceza.clear()
    assert y.cevir("hi3", []) == "asıl:hi3"
    assert y.uyari() is None

    # Kota: kısa bekleme
    asil.hata = ceviri.KotaHatasi("kota")
    y.cevir("hi4", [])
    assert 0 < y.ceza["gemini"] - ceviri.time.time() <= 61
    print("  ✓ test_ceviri_yedek")
