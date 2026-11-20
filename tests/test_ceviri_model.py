"""Servis çeviri modelini kaldırınca (Groq, 16.08.2026: llama-3.3-70b-versatile -> 404) uygulama kendiliğinden
çalışan bir modele geçiyor mu; geçemezse çeviri yedek motorla sürüyor mu.

Sahte sunucu Groq'un gerçek cevaplarını taklit eder: 404 model_not_found (kullanıcının ekran görüntüsündeki gövde),
400 model_decommissioned, 400 "reasoning_effort is not supported", 401 invalid_api_key, 429 + Retry-After ve
/models listesi (Kasım 2026 belgelerindeki modeller; ses, denetim ve seslendirme modelleri dahil)."""
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import yardimci  # noqa: F401

import ceviri
import veri

ESKI = "llama-3.3-70b-versatile"
GROQ_LISTESI = [
    "openai/gpt-oss-20b", "whisper-large-v3", "whisper-large-v3-turbo", "canopylabs/orpheus-arabic-saudi",
    "canopylabs/orpheus-v1-english", "meta-llama/llama-prompt-guard-2-22m", "meta-llama/llama-prompt-guard-2-86m",
    "meta-models/muse-spark-open", "minimaxai/minimax-m2.7", "openai/gpt-oss-safeguard-20b", "qwen/qwen3.8-27b",
    "openai/gpt-oss-120b",
]
GEMINI_LISTESI = [
    "models/gemini-embedding-001", "models/gemini-3.8-flash", "models/gemini-3.6-flash", "models/gemini-3.1-flash-lite",
    "models/gemini-3.5-flash-lite", "models/gemini-3.8-live", "models/gemini-4-carbon", "models/imagen-4.0-generate-001",
    "models/gemini-2.5-flash-preview-tts", "models/gemini-2.5-flash-image", "models/gemini-2.5-flash-lite",
    "models/gemini-3-flash-preview", "models/veo-3.0-generate-001", "models/aqa",
]


class _Sunucu:
    """Sahte Groq. `var`: sohbet isteğini kabul eden modeller. `kapali`: 400 model_decommissioned verenler.
    `efor_yok`: reasoning_effort alanını reddedenler. `bos`: boş cevap verenler."""

    def __init__(self):
        self.var = {"openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b", "minimaxai/minimax-m2.7",
                    "meta-models/muse-spark-open"}
        self.liste = list(GROQ_LISTESI)
        self.kapali, self.efor_yok, self.bos = set(), set(), set()
        self.kota = False
        self.istekler = []  # (yol, model, gövde)
        dis = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _yaz(self, kod, govde, basliklar=None):
                veri_ = json.dumps(govde).encode("utf-8")
                self.send_response(kod)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(veri_)))
                for k, v in (basliklar or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(veri_)

            def _yetki(self):
                if self.headers.get("Authorization") == "Bearer dogru":
                    return True
                self._yaz(401, {"error": {"message": "Invalid API Key", "type": "invalid_request_error",
                                          "code": "invalid_api_key"}})
                return False

            def do_GET(self):
                dis.istekler.append((self.path, None, None))
                if not self._yetki():
                    return
                if self.path == "/openai/v1/models":
                    return self._yaz(200, {"object": "list", "data": [
                        {"id": k, "object": "model", "owned_by": "x", "active": True, "context_window": 131072}
                        for k in dis.liste]})
                self._yaz(404, {"error": {"message": "Unknown request URL", "type": "invalid_request_error"}})

            def do_POST(self):
                g = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
                model = g.get("model", "")
                dis.istekler.append((self.path, model, g))
                if not self._yetki():
                    return
                if dis.kota:
                    return self._yaz(429, {"error": {"message": "Rate limit reached", "type": "tokens",
                                                     "code": "rate_limit_exceeded"}}, {"retry-after": "240"})
                if model in dis.kapali:
                    return self._yaz(400, {"error": {
                        "message": f"The model `{model}` has been decommissioned and is no longer supported. Please "
                                   "refer to https://console.groq.com/docs/deprecations for a recommendation on "
                                   "which model to use instead.",
                        "type": "invalid_request_error", "code": "model_decommissioned"}})
                if model not in dis.var:  # kullanıcının ekran görüntüsündeki cevap
                    return self._yaz(404, {"error": {
                        "message": f"The model `{model}` does not exist or you do not have access to it.",
                        "type": "invalid_request_error", "code": "model_not_found"}})
                if "reasoning_effort" in g and model in dis.efor_yok:
                    return self._yaz(400, {"error": {"message": "`reasoning_effort` is not supported with this model",
                                                     "type": "invalid_request_error"}})
                if model in dis.bos:
                    return self._yaz(200, {"choices": [{"message": {"role": "assistant", "content": ""}}]})
                icerik = f"[{model}] Merhaba"
                mesaj = {"role": "assistant", "content": icerik}
                if "qwen" in model and g.get("reasoning_effort") != "none":  # Qwen düşünceyi cevabın içine yazar
                    mesaj["content"] = "<think>\nKullanıcı bir satır çeviri istiyor.\n</think>\n\n" + icerik
                if "gpt-oss" in model:  # gpt-oss düşünceyi ayrı alanda verir
                    mesaj["reasoning"] = "The user wants a translation."
                self._yaz(200, {"choices": [{"index": 0, "message": mesaj, "finish_reason": "stop"}]})

        self.http = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.http.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.http.server_address[1]}/openai/v1/chat/completions"

    def sayi(self, yol_sonu, model=None):
        return sum(1 for y, m, _ in self.istekler if y.endswith(yol_sonu) and (model is None or m == model))

    def kapat(self):
        self.http.shutdown()
        self.http.server_close()


class _Yanit:
    def __init__(self, kod, metin="", basliklar=None):
        self.status_code, self.text, self.headers = kod, metin, basliklar or {}


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


def _secimi_sil():
    ceviri._secim_bellek.clear()
    if os.path.exists(ceviri._secim_yolu()):
        os.remove(ceviri._secim_yolu())


def _motor(s, model=ESKI, anahtar="dogru"):
    return ceviri.LLMMotoru(s.url, model, anahtar, {}, "Groq", anahtar_gerekli=True, motor_id="groq")


def test_ceviri_model():
    h = ceviri._http_hatasi

    # --- hata türleri: kullanıcının aldığı cevap artık "model hatası"
    ekrandaki = ('{"error":{"message":"The model `llama-3.3-70b-versatile` does not exist or you do not have access '
                 'to it.","type":"invalid_request_error","code":"model_not_found"}}')
    e = h("Groq", _Yanit(404, ekrandaki))
    assert isinstance(e, ceviri.ModelHatasi), type(e)
    assert "llama" not in str(e) and "{" not in str(e), "kullanıcıya ham servis cevabı gösterilmemeli: " + str(e)
    assert isinstance(h("Groq", _Yanit(400, '{"error":{"message":"The model `x` has been decommissioned and is no '
                                            'longer supported.","code":"model_decommissioned"}}')), ceviri.ModelHatasi)
    assert isinstance(h("Gemini", _Yanit(404, '{"error":{"code":404,"message":"models/gemini-9 is not found for API '
                                              'version v1main, or is not supported for generateContent.",'
                                              '"status":"NOT_FOUND"}}')), ceviri.ModelHatasi)
    assert isinstance(h("Claude", _Yanit(404, '{"type":"error","error":{"type":"not_found_error","message":"model: '
                                              'claude-x"}}')), ceviri.ModelHatasi)
    # alan reddi ve başka 400/404'ler model hatası sayılmamalı (yoksa sağlam model boşuna değiştirilir)
    assert type(h("Groq", _Yanit(400, "`reasoning_effort` is not supported with this model"))) is ceviri.CeviriHatasi
    assert type(h("Groq", _Yanit(404, "Unknown request URL"))) is ceviri.CeviriHatasi
    assert type(h("Groq", _Yanit(400, "bad request"))) is ceviri.CeviriHatasi
    # anahtar hatası model hatasından önce gelir
    assert isinstance(h("Gemini", _Yanit(400, "API key not valid. Please pass a valid API key for the model.")),
                      ceviri.AnahtarHatasi)
    assert isinstance(h("Groq", _Yanit(403, "Forbidden")), ceviri.AnahtarHatasi)
    # anahtar sağlam ama modele izni yok (Groq'ta proje ayarı): model hatasıdır, izinli modele geçilebilir
    assert isinstance(h("Groq", _Yanit(403, '{"error":{"message":"The model `x` is blocked at the project level.",'
                                            '"type":"permissions_error","code":"model_permission_blocked_project"}}')),
                      ceviri.ModelHatasi)
    k = h("Groq", _Yanit(429, "rate_limit_exceeded", {"retry-after": "120"}))
    assert isinstance(k, ceviri.KotaHatasi) and k.bekle == 120.0
    assert not hasattr(h("Groq", _Yanit(429, "rate_limit_exceeded")), "bekle")

    # --- sıralama: Groq'un Kasım 2026 listesi
    sira = ceviri.model_sirala(GROQ_LISTESI, ceviri.HAZIR_MOTORLAR["groq"]["tercih"])
    assert sira[:3] == ["openai/gpt-oss-120b", "qwen/qwen3.8-27b", "openai/gpt-oss-20b"], sira
    assert set(sira) == {"openai/gpt-oss-120b", "qwen/qwen3.8-27b", "openai/gpt-oss-20b", "minimaxai/minimax-m2.7",
                         "meta-models/muse-spark-open"}, "ses/denetim/seslendirme modelleri elenmeli: %s" % sira
    # tanımadığımız bir gelecekte de mantıklı seçim: büyük sohbet modeli önce, ses modeli hiç
    gelecek = ceviri.model_sirala(["whisper-large-v4", "acme/nova-9b", "acme/nova-200b", "acme/nova-tts"],
                                  ceviri.HAZIR_MOTORLAR["groq"]["tercih"])
    assert gelecek == ["acme/nova-200b", "acme/nova-9b"], gelecek
    # Gemini: önce "latest" takma adı; yoksa en yeni flash-lite, sonra flash
    g_tercih = ceviri.HAZIR_MOTORLAR["gemini"]["tercih"]
    sira = ceviri.model_sirala(GEMINI_LISTESI, g_tercih)
    assert sira[:5] == ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-2.5-flash-lite", "gemini-3.8-flash",
                        "gemini-3.6-flash"], sira
    assert not [m for m in sira if any(x in m for x in ("embedding", "live", "imagen", "tts", "image", "veo", "aqa"))], sira
    assert ceviri.model_sirala(GEMINI_LISTESI + ["models/gemini-flash-lite-latest"], g_tercih)[0] == "gemini-flash-lite-latest"
    assert ceviri.model_sirala([None, "", 5, "  "], g_tercih) == []

    # --- düşünce etiketleri
    t = ceviri._llm_cikti_temizle
    assert t("<think>\nhmm\n</think>\n\nMerhaba") == "Merhaba"
    assert t('"Merhaba"') == "Merhaba" and t(None) == "" and t("düşünce sonu</think> Selam") == "Selam"
    assert t("<think>yarıda kesildi") == ""

    # --- varsayılanlar
    assert ceviri.HAZIR_MOTORLAR["groq"]["model"] != ESKI
    m = ceviri.tek_motor("groq", {"anahtarlar": {"groq": "x"}}, {})
    assert m.model == ceviri.HAZIR_MOTORLAR["groq"]["model"] and m.motor_id == "groq"
    assert ceviri.tek_motor("groq", {"anahtarlar": {"groq": "x"}, "modeller": {"groq": "elle/model"}}, {}).model == "elle/model"
    assert ceviri.hiz_ayari("groq", "openai/gpt-oss-120b") == {"reasoning_effort": "low"}
    assert ceviri.hiz_ayari("groq", "qwen/qwen3.8-27b") == {"reasoning_effort": "none"}
    assert ceviri.hiz_ayari("groq", "acme/nova-200b") == {} and ceviri.hiz_ayari("gemini", "gemini-3.5-flash-lite") == {}
    assert ceviri.hiz_ayari(None, "gpt-oss-20b") == {}, "yerel modele bilmediğimiz alan gönderilmemeli"

    s = _Sunucu()
    try:
        _secimi_sil()
        # --- asıl olay: eski model 404 -> listeden en iyi model seçilir, aynı istekte çeviri gelir
        m = _motor(s)
        assert m.model == ESKI
        assert m.cevir("Hello", []) == "[openai/gpt-oss-120b] Merhaba"
        assert m.model == "openai/gpt-oss-120b"
        assert s.sayi("/chat/completions", ESKI) == 1 and s.sayi("/models") == 1
        govde = [g for _, mm, g in s.istekler if mm == "openai/gpt-oss-120b"][-1]
        assert govde.get("reasoning_effort") == "low", "gpt-oss hızlı ayarla çağrılmalı"
        # sonraki satırlar doğrudan yeni modele gider
        m.cevir("Hi", [])
        assert s.sayi("/chat/completions", ESKI) == 1 and s.sayi("/models") == 1
        # seçim diske yazıldı: yeni motor (program yeniden açıldı) eski modeli hiç denemez
        with open(ceviri._secim_yolu(), encoding="utf-8") as f:
            kayit = json.load(f)["groq"]
        assert kayit["model"] == "openai/gpt-oss-120b" and kayit["yerine"] == ESKI, kayit
        ceviri._secim_bellek.clear()
        m2 = _motor(s)
        assert m2.model == "openai/gpt-oss-120b" and m2.cevir("Hey", []).endswith("Merhaba")
        assert s.sayi("/chat/completions", ESKI) == 1 and s.sayi("/models") == 1
        # programın yeni sürümü başka varsayılanla gelirse eski seçim uygulanmaz
        assert _motor(s, "openai/gpt-oss-20b").model == "openai/gpt-oss-20b"

        # --- seçilen model de kaldırılırsa (400 decommissioned) sıradakine geçilir; Qwen düşünmeden çağrılır
        s.var.discard("openai/gpt-oss-120b")
        s.kapali.add("openai/gpt-oss-120b")
        s.liste.remove("openai/gpt-oss-120b")
        assert m2.cevir("Hello", []) == "[qwen/qwen3.8-27b] Merhaba"
        assert m2.model == "qwen/qwen3.8-27b"
        govde = [g for _, mm, g in s.istekler if mm == "qwen/qwen3.8-27b"][-1]
        assert govde.get("reasoning_effort") == "none"
        ceviri._secim_bellek.clear()
        assert _motor(s).model == "qwen/qwen3.8-27b", "yeni seçim eskisinin üzerine yazılmalı"

        # --- model ek alanı reddederse alansız yeniden denenir (düşünce etiketi temizlenir), bir daha gönderilmez
        s.efor_yok.add("qwen/qwen3.8-27b")
        m3 = _motor(s)
        once = s.sayi("/chat/completions", "qwen/qwen3.8-27b")
        assert m3.cevir("Hello", []) == "[qwen/qwen3.8-27b] Merhaba"
        assert s.sayi("/chat/completions", "qwen/qwen3.8-27b") == once + 2
        assert m3.cevir("Hello again", []) == "[qwen/qwen3.8-27b] Merhaba"
        assert s.sayi("/chat/completions", "qwen/qwen3.8-27b") == once + 3
        assert "reasoning_effort" not in s.istekler[-1][2]
        s.efor_yok.clear()

        # --- liste modeli verse de sohbet ucu reddediyorsa (anahtara kapalı) sıradaki aday denenir
        _secimi_sil()
        s.var.discard("qwen/qwen3.8-27b")
        m4 = _motor(s)
        assert m4.cevir("Hello", []) == "[openai/gpt-oss-20b] Merhaba" and m4.model == "openai/gpt-oss-20b"

        # --- hiçbir model çalışmıyorsa anlaşılır hata; liste her satırda yeniden istenmez
        _secimi_sil()
        s.var.clear()
        m5 = _motor(s)
        once = s.sayi("/models")
        for _ in range(3):
            try:
                m5.cevir("Hello", [])
                raise AssertionError("model yokken çeviri döndü")
            except ceviri.ModelHatasi as e:
                assert "Groq" in str(e) and "{" not in str(e), str(e)
        assert s.sayi("/models") == once + 1, "liste yalnız bir kez istenmeli"
        assert not os.path.exists(ceviri._secim_yolu()), "çalışmayan model kaydedilmemeli"
        # ...ve yedek motor devralır, 10 dakika asıl motor yoklanmaz
        y = ceviri.YedekliMotor([("groq", m5), ("cevrimdisi", _Yedek())])
        assert y.cevir("hi", []) == "yedek:hi" and y.yedekten_mi()
        u = y.uyari()
        assert u and u["asil"] == "Groq" and "model" in u["neden"], u
        assert y.ceza["groq"] - ceviri.time.time() > 500

        # --- yanlış anahtar model hatası gibi görünmemeli
        s.var.update({"openai/gpt-oss-120b"})
        try:
            _motor(s, anahtar="yanlis").cevir("Hello", [])
            raise AssertionError("yanlış anahtar kabul edildi")
        except ceviri.AnahtarHatasi:
            pass

        # --- model seçimi sırasında kota dolarsa: seçim yapılmaz, kota hatası çıkar (yedek 240 sn devralır)
        _secimi_sil()
        s.liste = list(GROQ_LISTESI)
        s.var = {"openai/gpt-oss-120b"}
        s.kapali.clear()
        m6 = _motor(s)
        s.kota = True
        try:
            m6.cevir("Hello", [])
            raise AssertionError("kota doluyken çeviri döndü")
        except ceviri.KotaHatasi as e:
            assert e.bekle == 240.0
        s.kota = False
        assert m6.cevir("Hello", []) == "[openai/gpt-oss-120b] Merhaba", "kota açılınca seçim yeniden denenmeli"

        # --- boş cevap: yalnız o satır yedekten, ceza ve uyarı yok
        s.bos.add("openai/gpt-oss-120b")
        y = ceviri.YedekliMotor([("groq", m6), ("cevrimdisi", _Yedek())])
        assert y.cevir("hi", []) == "yedek:hi" and y.yedekten_mi()
        assert y.uyari() is None and not y.ceza, (y.uyari(), y.ceza)
        s.bos.clear()
        assert y.cevir("hi", []) == "[openai/gpt-oss-120b] Merhaba" and not y.yedekten_mi()

        # --- yerel model (kullanıcının yazdığı ad): yerine seçim yapılmaz, ne yapılacağı söylenir
        yerel = ceviri.LLMMotoru(s.url, "olmayan-model", "dogru", {})
        once = s.sayi("/models")
        try:
            yerel.cevir("Hello", [])
            raise AssertionError("olmayan yerel model çevirdi")
        except ceviri.ModelHatasi as e:
            assert "olmayan-model" in str(e), str(e)
        assert s.sayi("/models") == once
    finally:
        s.kapat()
        _secimi_sil()

    # --- yedeğe geçiş: eskiden yalnız kota/internet/anahtar geçiriyordu; 404 gibi hatalarda çeviri duruyordu
    for hata, en_az, en_cok in ((ceviri.ModelHatasi("model yok"), 500, 601), (ceviri.CeviriHatasi("400"), 1, 61),
                                (KeyError("choices"), 1, 61)):
        asil = _Bozuk(hata)
        y = ceviri.YedekliMotor([("groq", asil), ("cevrimdisi", _Yedek())])
        assert y.cevir("hi", []) == "yedek:hi", hata
        assert en_az < y.ceza["groq"] - ceviri.time.time() <= en_cok, (hata, y.ceza)
        assert y.uyari() and y.uyari()["aktif"] == ceviri.MOTOR_ADLARI["cevrimdisi"]
        y.cevir("hi2", [])
        assert asil.cagri == 1, "bozuk motor her satırda yeniden denenmemeli"
    # servis "şu kadar bekle" derse ona uyulur, ama en çok 15 dakika
    for bekle, alt, ust in ((300, 295, 301), (99999, 895, 901), (5, 55, 61)):
        k = ceviri.KotaHatasi("kota")
        k.bekle = bekle
        y = ceviri.YedekliMotor([("groq", _Bozuk(k)), ("cevrimdisi", _Yedek())])
        y.cevir("hi", [])
        assert alt < y.ceza["groq"] - ceviri.time.time() <= ust, (bekle, y.ceza)
    # yedek de bozuksa hata dışarı çıkar (çökme yok)
    y = ceviri.YedekliMotor([("groq", _Bozuk(ceviri.ModelHatasi("a"))), ("gemini", _Bozuk(ceviri.KotaHatasi("b")))])
    try:
        y.cevir("hi", [])
        raise AssertionError("iki motor da bozukken çeviri döndü")
    except ceviri.KotaHatasi:
        pass

    # --- önbellek: yedeğin çevirisi asıl motor adına saklanmaz (boş cevapta da)
    class _BirBos:
        def __init__(self):
            self.n = 0

        def cevir(self, metin, baglam):
            self.n += 1
            if self.n == 1:
                raise ceviri.BosCevap("boş")
            return "asıl:" + metin

    gelen = []
    olay = threading.Event()
    y = ceviri.YedekliMotor([("groq", _BirBos()), ("cevrimdisi", _Yedek())])
    isci = ceviri.CeviriIscisi(y, lambda i, en, tr, sure: (gelen.append(tr), olay.set()), onbellek_yolu=None,
                               motor_adi="groq")
    try:
        for beklenen in ("yedek:Hello there", "asıl:Hello there"):
            olay.clear()
            isci.ekle(len(gelen) + 1, "Hello there")
            assert olay.wait(5), "çeviri gelmedi"
            assert gelen[-1] == beklenen, gelen
    finally:
        isci.durdur()
    assert veri.VERI_KLASORU == os.environ["CTA_VERI"], "test kullanıcının gerçek ayar klasörüne yazmamalı"
    print("  ✓ test_ceviri_model")


if __name__ == "__main__":
    test_ceviri_model()
