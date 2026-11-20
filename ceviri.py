"""İngilizce -> Türkçe çeviri motorları + önbellek + arka plan işçisi.

Anahtarsız, varsayılan:
  cevrimdisi : OPUS-MT (Helsinki-NLP, CC BY 4.0) bilgisayarda çalışır; internet ve anahtar gerekmez

Daha doğal çeviri için kullanıcı kendi (ücretsiz) anahtarını girebilir:
  gemini : Google AI Studio, kartsız ücretsiz kota (önerilen)
  groq   : Groq, kartsız ücretsiz kota
  deepl  : DeepL API Free, ayda 500 bin karakter (kayıtta kart doğrulaması ister)
  claude : Anthropic, ücretli
  llm    : OpenAI uyumlu herhangi bir uç nokta (Ollama, LM Studio...)
"""
import json
import os
import queue
import re
import threading
import time
from collections import deque

import requests

import ceviri_hatti
import veri

# OpenAI uyumlu uç noktası olan hazır motorlar.
# "model" ilk denenen modeldir. Servisler modelleri sık sık kaldırır (Groq llama-3.3-70b-versatile'ı 16.08.2026'da
# kapattı; uygulama o günden sonra 404 veriyordu). Model reddedilirse LLMMotoru servisin kendi model listesinden
# "tercih" sırasına göre (düzenli ifadeler, baştaki en iyi) başka bir model seçer; bkz. model_sirala.
HAZIR_MOTORLAR = {
    "gemini": {
        "ad": "Google Gemini",
        "url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "model": "gemini-flash-lite-latest",
        "tercih": (r"^gemini-flash-lite-latest$", r"^gemini-[\d.]+-flash-lite$", r"^gemini-flash-latest$",
                   r"^gemini-[\d.]+-flash$", r"^gemini-[\d.]+-flash-lite", r"^gemini-[\d.]+-flash"),
        "anahtar_sayfasi": "https://aistudio.google.com/apikey",
    },
    "groq": {
        "ad": "Groq",
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "model": "openai/gpt-oss-120b",
        "tercih": (r"^openai/gpt-oss-120b$", r"^qwen/qwen-?3[\d.]*-\d+b$", r"^openai/gpt-oss-20b$", r"gpt-oss-\d+b$",
                   r"llama-[\d.]+-\d+b-versatile$", r"qwen|kimi|llama|mistral|gemma"),
        "anahtar_sayfasi": "https://console.groq.com/keys",
    },
}
# Düşünen modellerde gecikmeyi azaltan ek istek alanları: motor -> [(model adı kalıbı, alanlar)].
# Yalnızca servisin belgelediği birleşimler (Groq, Kasım 2026): gpt-oss "low/medium/high" alır; Qwen 3.x "none" ile
# hiç düşünmez. Servis alanı reddederse (400 + alanın adı) alansız yeniden denenir.
HIZ_AYARLARI = {
    "groq": ((re.compile(r"gpt-oss", re.I), {"reasoning_effort": "low"}),
             (re.compile(r"qwen-?3", re.I), {"reasoning_effort": "none"})),
}
ANAHTAR_SAYFALARI = {
    **{k: v["anahtar_sayfasi"] for k, v in HAZIR_MOTORLAR.items()},
    "deepl": "https://www.deepl.com/pro-api",
    "claude": "https://console.anthropic.com/settings/keys",
}
MOTOR_ADLARI = {"cevrimdisi": "Ücretsiz (anahtarsız)", **{k: v["ad"] for k, v in HAZIR_MOTORLAR.items()},
                "deepl": "DeepL", "claude": "Claude", "llm": "Yerel model"}
ANAHTARSIZ = ("cevrimdisi", "llm")


class CeviriHatasi(Exception):
    """Kullanıcıya gösterilecek, ne yapılacağını söyleyen hata."""


class KotaHatasi(CeviriHatasi):
    """Ücretsiz kota / hız sınırı doldu. Yedek motora geçilebilir."""


class BaglantiHatasi(CeviriHatasi):
    """İnternet yok / servis cevap vermiyor. Yedek motora geçilebilir."""


class AnahtarHatasi(CeviriHatasi):
    """Anahtar geçersiz, silinmiş ya da süresi dolmuş. Kendiliğinden düzelmez; yedek motora geçilir."""


class ModelHatasi(CeviriHatasi):
    """Servis istenen modeli tanımıyor: kaldırılmış ya da bu anahtara kapalı. Kendiliğinden düzelmez. Hazır
    motorlarda (Gemini, Groq) LLMMotoru servisin listesinden başka bir model seçer; o da olmazsa yedek motora geçilir."""


class BosCevap(CeviriHatasi):
    """Servis bu satır için boş cevap verdi. Motor bozuk değil: yalnız bu satır yedek motorla çevrilir."""


_MODEL_YOK = ("model_not_found", "model_decommissioned", "does not exist", "decommissioned", "no longer supported",
              "no longer available", "has been deprecated", "is not found", "not found", "not_found")


def _model_yok_mu(kod, govde):
    """Servis "bu model yok / kaldırıldı" mı diyor? Groq: 404 model_not_found ("The model `x` does not exist or you
    do not have access to it"), 400 model_decommissioned. Gemini: 404 "models/x is not found for API version".
    Claude: 404 not_found_error "model: x". Ollama: 404 'model "x" not found'.
    "x is not supported with this model" gibi alan retleri model hatası DEĞİLDİR (bkz. LLMMotoru._iste)."""
    return kod in (400, 404, 410) and "model" in govde and any(k in govde for k in _MODEL_YOK)


def _http_hatasi(motor_adi, r):
    govde = (r.text or "")[:600].lower()
    # 403 + "model ... blocked / permission": anahtar sağlam ama bu modele izni yok (Groq'ta proje ayarıyla model
    # kapatılabiliyor). Anahtar hatası değil model hatasıdır: listeden izinli bir modele geçilebilir.
    model_izni_yok = r.status_code == 403 and "model" in govde and any(
        k in govde for k in ("blocked", "permission", "not allowed", "do not have access"))
    # Gemini süresi dolan / geçersiz anahtar için 400 döndürür ("API key expired", "API key not valid")
    if model_izni_yok:
        h = ModelHatasi(f"{motor_adi} bu anahtarla seçili çeviri modelini kullandırmıyor. Başka bir çeviri seçin.")
    elif r.status_code in (401, 403) or (r.status_code == 400 and ("api key" in govde or "api_key" in govde)):
        h = AnahtarHatasi(f"{motor_adi} anahtarı geçersiz ya da süresi dolmuş. "
                          "Panel → Çeviri'den yeni bir anahtar girin.")
    elif r.status_code == 402 or "credit balance" in govde:
        h = KotaHatasi(f"{motor_adi} hesabındaki kredi bitti. Hesabınıza kredi ekleyin ya da ücretsiz bir motor seçin.")
    elif r.status_code in (429, 456):
        h = KotaHatasi(f"{motor_adi} ücretsiz kotası doldu ya da çok hızlı istek gitti. "
                       "Biraz bekleyin veya ikinci bir çeviri anahtarı ekleyin.")
        try:  # servis ne kadar beklenmesi gerektiğini söylüyorsa (sn) yedek motorda o kadar kalınır
            h.bekle = float((getattr(r, "headers", None) or {}).get("retry-after"))
        except (TypeError, ValueError):
            pass
    elif r.status_code >= 500:
        h = BaglantiHatasi(f"{motor_adi} şu an cevap vermiyor ({r.status_code}). Biraz sonra kendiliğinden düzelir.")
    elif _model_yok_mu(r.status_code, govde):
        h = ModelHatasi(f"{motor_adi} çeviri modeli artık kullanılamıyor. Programı güncelleyin ya da başka bir çeviri seçin.")
    else:
        h = CeviriHatasi(f"{motor_adi} hatası ({r.status_code}): {r.text[:150]}")
    h.kod, h.govde = r.status_code, govde  # çağıran ayrıntıya bakabilsin (ör. reddedilen istek alanı)
    return h


def _istek(motor_adi, yontem, url, **kw):
    try:
        r = requests.request(yontem, url, **kw)
    except requests.exceptions.Timeout:
        raise BaglantiHatasi(f"{motor_adi} zamanında cevap vermedi. İnternet bağlantınızı kontrol edin.")
    except requests.exceptions.RequestException:
        raise BaglantiHatasi(f"{motor_adi} sunucusuna ulaşılamadı. İnternet bağlantınızı kontrol edin.")
    if r.status_code != 200:
        raise _http_hatasi(motor_adi, r)
    try:
        return r.json()
    except ValueError:  # 200 ama JSON değil: araya giren bir giriş sayfası (otel/okul ağı) ya da yarım cevap
        raise BaglantiHatasi(f"{motor_adi} anlaşılmayan bir cevap verdi. İnternet bağlantınızı kontrol edin.")


# ---------- model seçimi: servis modeli kaldırırsa çalışan bir modele kendiliğinden geçiş ----------
_SOHBET_DEGIL_PARCA = ("whisper", "embed", "guard", "rerank", "moderat", "orpheus", "playai", "imagen", "compound")
_SOHBET_DEGIL_KELIME = {"tts", "speech", "audio", "image", "vision", "aqa", "live", "learnlm", "robotics", "computer",
                        "veo", "transcribe", "realtime"}


def _buyukluk(kimlik):
    """Model adındaki parametre sayısı (milyar): "gpt-oss-120b" -> 120, "qwen3.8-27b" -> 27, yoksa 0."""
    b = re.findall(r"(?<![\w.])(\d+(?:\.\d+)?)b(?![a-z0-9])", kimlik.lower())
    return max(map(float, b)) if b else 0.0


def _surum(kimlik):
    """Model adındaki ilk sürüm sayısı: "gemini-3.5-flash-lite" -> 3.5, "qwen3.8-27b" -> 3.8."""
    m = re.search(r"\d+(?:\.\d+)?", kimlik.rsplit("/", 1)[-1])
    return float(m.group()) if m else 0.0


def model_sirala(kimlikler, tercih=()):
    """Servisin model listesinden altyazı çevirisine uygun olanları, en iyi aday başta olacak şekilde sıralar.
    Ses, görüntü, gömme ve denetim modelleri elenir. Önce `tercih` kalıplarına uyanlar (kalıp sırasıyla), sonra
    geri kalanlar; eşitlikte büyük ve yeni model önce gelir."""
    adaylar = set()
    for k in kimlikler:
        if not isinstance(k, str) or not k.strip():
            continue
        k = k.strip()
        k = k[len("models/"):] if k.startswith("models/") else k  # Gemini listesi "models/…" ön ekiyle verir
        kucuk = k.lower()
        if any(p in kucuk for p in _SOHBET_DEGIL_PARCA) or _SOHBET_DEGIL_KELIME & set(re.split(r"[^a-z0-9]+", kucuk)):
            continue
        adaylar.add(k)

    def sira(k):
        for i, kalip in enumerate(tercih):
            if re.search(kalip, k, re.I):
                return (0, i, -_buyukluk(k), -_surum(k), k)
        return (1, 0, -_buyukluk(k), -_surum(k), k)

    return sorted(adaylar, key=sira)


def hiz_ayari(motor_id, model):
    for kalip, alanlar in HIZ_AYARLARI.get(motor_id, ()):
        if kalip.search(model):
            return dict(alanlar)
    return {}


_secim_kilidi = threading.Lock()
_secim_bellek = {}  # (motor, istenen model) -> seçilen model; dosyaya yazılamasa da bu oturumda hatırlansın


def _secim_yolu():
    return veri.veri_yolu("model_secimi.json")


def model_secimi_oku(motor_id, istenen):
    """`istenen` model daha önce reddedildiği için yerine seçilmiş model; yoksa None. Programın yeni sürümü başka
    bir varsayılan modelle gelirse (istenen değişir) eski seçim kendiliğinden geçersiz olur."""
    if (motor_id, istenen) in _secim_bellek:
        return _secim_bellek[(motor_id, istenen)]
    try:
        with open(_secim_yolu(), encoding="utf-8") as f:
            kayit = json.load(f)[motor_id]
        return kayit["model"] if kayit["yerine"] == istenen and isinstance(kayit["model"], str) else None
    except (OSError, ValueError, KeyError, TypeError):
        return None


def model_secimi_yaz(motor_id, istenen, model):
    with _secim_kilidi:
        _secim_bellek[(motor_id, istenen)] = model
        try:
            yol = _secim_yolu()
            try:
                with open(yol, encoding="utf-8") as f:
                    hepsi = json.load(f)
            except (OSError, ValueError):
                hepsi = {}
            if not isinstance(hepsi, dict):
                hepsi = {}
            hepsi[motor_id] = {"model": model, "yerine": istenen, "zaman": int(time.time())}
            with open(yol + ".tmp", "w", encoding="utf-8") as f:
                json.dump(hepsi, f, ensure_ascii=False, indent=2)
            os.replace(yol + ".tmp", yol)
        except OSError as e:
            print(f"[çeviri] model seçimi kaydedilemedi: {e}", flush=True)


def sozluk_yukle(yol=None):
    yol = yol or veri.sozluk_yolu()
    if not os.path.exists(yol):
        return {"cevirme": [], "terimler": {}}
    with open(yol, encoding="utf-8") as f:
        return json.load(f)


class DeepLMotoru:
    def __init__(self, anahtar):
        if not anahtar:
            raise CeviriHatasi("DeepL için API anahtarı girin.")
        self.anahtar = anahtar
        self.url = (
            "https://api-free.deepl.com/v2/translate"
            if anahtar.endswith(":fx")
            else "https://api.deepl.com/v2/translate"
        )

    def cevir(self, metin, baglam):
        veri_ = {"text": metin, "source_lang": "EN", "target_lang": "TR"}
        if baglam:
            veri_["context"] = "Video game dialogue. Previous lines: " + " ".join(baglam)
        j = _istek("DeepL", "POST", self.url, data=veri_, timeout=6,
                   headers={"Authorization": f"DeepL-Auth-Key {self.anahtar}"})
        try:
            return j["translations"][0]["text"]
        except (KeyError, IndexError, TypeError):
            raise CeviriHatasi("DeepL beklenmeyen bir cevap verdi.")


def _llm_talimati(sozluk):
    terimler = ", ".join(f'"{k}" -> "{v}"' for k, v in sozluk.get("terimler", {}).items())
    isimler = ", ".join(sozluk.get("cevirme", []))
    return (
        "Sen bir oyun altyazı çevirmenisin. Video oyunlarındaki İngilizce diyalog altyazılarını "
        "Türkçeye BİREBİR çevir: altyazıda ne yazıyorsa onu aktar. Yerelleştirme, uyarlama, yorum ya da süsleme yapma; "
        "espriyi ya da deyimi başka bir Türk deyimiyle değiştirme, anlamını düz ve doğru biçimde ver. Cümle "
        "Türkçe dilbilgisine uygun olsun. Küfürleri yumuşatma, abartma. "
        "Karakterler birbirine 'sen' diye hitap eder; satır açıkça resmî değilse 'siz' kullanma. "
        "Anlamı ve tonu koru: bir şey ekleme, bir şey atlama. Küçük harfle ya da 'and' ile başlayan satır "
        "önceki altyazının devamıdır; cümleyi ona göre tamamla. "
        "Altyazı kısa ve okunur olsun. Sadece çeviriyi yaz; açıklama, tırnak veya not ekleme. "
        "Satırın başında 'JASON:' gibi bir konuşmacı adı varsa adı aynen koru. "
        "Altyazı OCR ile okunduğu için küçük yazım hataları olabilir; anlamdan düzelt.\n"
        f"Çevrilmeyecek isimler: {isimler}\n"
        f"Terim sözlüğü: {terimler}"
    )


def _llm_mesaji(metin, baglam):
    if baglam:
        return "Önceki satırlar (sadece bağlam için, çevirme):\n" + "\n".join(baglam) + \
            f"\n\nÇevrilecek satır:\n{metin}"
    return f"Çevrilecek satır:\n{metin}"


_DUSUNCE = re.compile(r"<think(?:ing)?>.*?</think(?:ing)?>", re.S | re.I)


def _llm_cikti_temizle(s):
    """Düşünen modeller (Qwen, DeepSeek...) cevabın başına <think>…</think> koyabilir; çeviri ondan sonradır."""
    s = _DUSUNCE.sub("", s if isinstance(s, str) else "")
    kapanis = None
    for kapanis in re.finditer(r"</think(?:ing)?>", s, re.I):
        pass
    if kapanis:  # açılışı olmayan kapanış: sonrası cevaptır
        s = s[kapanis.end():]
    if re.search(r"<think(?:ing)?>", s, re.I):  # kapanmamış düşünce: cevaba sıra gelmeden kesilmiş
        return ""
    return s.strip().strip('"“”').strip()


class LLMMotoru:
    """OpenAI uyumlu her uç nokta: Gemini, Groq, Ollama, LM Studio, OpenRouter...

    motor_id verilirse (hazır motorlar: "gemini", "groq") model adını kullanıcı değil biz seçmişizdir. Servis o
    modeli reddederse (kaldırılmış ya da anahtara kapalı) servisin model listesinden (/models) çeviriye uygun
    adaylar sırayla gerçek istekle denenir; ilk çalışan benimsenir ve model_secimi.json'a yazılır. Kullanıcı bir
    şey yapmak zorunda kalmaz; yalnızca o ilk satır biraz geç gelir."""

    EN_FAZLA_ADAY = 4
    SECIM_ARALIGI = 600  # sn — listedeki hiçbir model çalışmadıysa en erken bu kadar sonra yeniden bakılır

    def __init__(self, url, model, anahtar, sozluk, ad="Yerel model", anahtar_gerekli=False, motor_id=None):
        if anahtar_gerekli and not anahtar:
            raise CeviriHatasi(f"{ad} için API anahtarı girin.")
        self.url, self.anahtar, self.ad, self.motor_id = url, anahtar, ad, motor_id
        self.istenen = model
        self.model = (model_secimi_oku(motor_id, model) if motor_id else None) or model
        self.talimat = _llm_talimati(sozluk)
        self._eksiz = set()  # ek hız alanını kabul etmeyen modeller
        self._secim_yasak = 0.0

    def _basliklar(self):
        basliklar = {"Content-Type": "application/json"}
        if self.anahtar:
            basliklar["Authorization"] = f"Bearer {self.anahtar}"
        return basliklar

    def _iste(self, model, metin, baglam):
        govde = {
            "model": model,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": self.talimat},
                {"role": "user", "content": _llm_mesaji(metin, baglam)},
            ],
        }
        ek = {} if model in self._eksiz else hiz_ayari(self.motor_id, model)
        try:
            j = _istek(self.ad, "POST", self.url, headers=self._basliklar(), timeout=15, json={**govde, **ek})
        except CeviriHatasi as e:
            # Ek alanı tanımayan model (400 + alanın adı): alansız yeniden dene, bu modele bir daha gönderme
            if not ek or getattr(e, "kod", 0) not in (400, 422) or not any(k in getattr(e, "govde", "") for k in ek):
                raise
            self._eksiz.add(model)
            j = _istek(self.ad, "POST", self.url, headers=self._basliklar(), timeout=15, json=govde)
        try:
            cevap = j["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise CeviriHatasi(f"{self.ad} beklenmeyen bir cevap verdi.")
        tr = _llm_cikti_temizle(cevap)
        if not tr:
            raise BosCevap(f"{self.ad} bu satır için boş cevap verdi.")
        return tr

    def cevir(self, metin, baglam):
        try:
            return self._iste(self.model, metin, baglam)
        except ModelHatasi:
            if not self.motor_id:  # modeli kullanıcı yazmış (yerel model): onun yerine seçim yapılmaz
                raise ModelHatasi(f"{self.ad}: \"{self.model}\" adlı model bulunamadı. "
                                  "Ayarlardaki model adını kontrol edin.")
            return self._baska_modelle(metin, baglam)

    def _baska_modelle(self, metin, baglam):
        """self.model reddedildi: servisin listesindeki uygun modelleri sırayla dener, ilk çalışanı benimser."""
        olmadi = ModelHatasi(f"{self.ad} şu an bu anahtarla kullanılabilecek bir çeviri modeli vermiyor. "
                             "Programı güncelleyin ya da başka bir çeviri seçin.")
        if time.time() < self._secim_yasak:
            raise olmadi
        eski = self.model
        liste = _istek(self.ad, "GET", re.sub(r"/chat/completions/?$", "", self.url) + "/models",
                       headers=self._basliklar(), timeout=8)
        veriler = liste.get("data") if isinstance(liste, dict) else liste
        kimlikler = [m.get("id") for m in (veriler if isinstance(veriler, list) else [])
                     if isinstance(m, dict) and m.get("active", True) is not False]
        adaylar = [k for k in model_sirala(kimlikler, HAZIR_MOTORLAR.get(self.motor_id, {}).get("tercih", ()))
                   if k not in (eski, self.istenen)][:self.EN_FAZLA_ADAY]
        for aday in adaylar:
            try:
                tr = self._iste(aday, metin, baglam)
            except (KotaHatasi, BaglantiHatasi, AnahtarHatasi):
                raise  # modelle ilgisi yok: yedek motor devralır, seçim sonra yeniden denenir
            except CeviriHatasi as e:  # bu aday da olmadı (yok ya da isteği kabul etmiyor): sıradaki
                print(f"[çeviri] {self.ad}: \"{aday}\" denendi, olmadı: {e}", flush=True)
                continue
            self.model = aday
            model_secimi_yaz(self.motor_id, self.istenen, aday)
            print(f"[çeviri] {self.ad}: \"{eski}\" modeli artık kullanılamıyor; \"{aday}\" modeline geçildi.", flush=True)
            return tr
        self._secim_yasak = time.time() + self.SECIM_ARALIGI
        raise olmadi


class ClaudeMotoru:
    def __init__(self, anahtar, model, sozluk):
        if not anahtar:
            raise CeviriHatasi("Claude için API anahtarı girin.")
        self.anahtar, self.model = anahtar, model
        self.talimat = _llm_talimati(sozluk)

    def cevir(self, metin, baglam):
        j = _istek(
            "Claude", "POST", "https://api.anthropic.com/v1/messages", timeout=15,
            headers={
                "x-api-key": self.anahtar,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": self.model,
                "max_tokens": 300,
                "system": self.talimat,
                "messages": [{"role": "user", "content": _llm_mesaji(metin, baglam)}],
            },
        )
        try:
            return "".join(b["text"] for b in j["content"] if b["type"] == "text").strip()
        except (KeyError, TypeError):
            raise CeviriHatasi("Claude beklenmeyen bir cevap verdi.")


def model_klasoru():
    return veri.kaynak(os.path.join("modeller", "en-tr"))


def model_var():
    return os.path.exists(os.path.join(model_klasoru(), "model.bin"))


# "JASON:" / "Lucia -" gibi konuşmacı adı: çeviriye sokma, başa geri ekle
_KONUSMACI = re.compile(r"^\s*([A-Z][A-Za-z0-9 .'\-]{0,24}?)\s*:\s+(?=\S)")


class CevrimdisiMotor:
    """Bilgisayarda çalışan İngilizce->Türkçe model (OPUS-MT, CTranslate2 int8).
    İnternet ve anahtar gerekmez, sınırsızdır. Satır başına ~0,1-0,2 sn (CPU)."""

    _paylasilan = None  # model yüklemesi pahalı: süreç başına bir kere
    _kilit = threading.Lock()

    def __init__(self, sozluk=None):
        if not model_var():
            raise CeviriHatasi("Ücretsiz çeviri modeli bulunamadı. Programı yeniden kurun ya da başka bir çeviri seçin.")
        with CevrimdisiMotor._kilit:
            if CevrimdisiMotor._paylasilan is None:
                import ctranslate2
                d = model_klasoru()
                CevrimdisiMotor._paylasilan = (
                    ctranslate2.Translator(d, device="cpu", compute_type="int8", inter_threads=1,
                                           intra_threads=max(1, min(6, (os.cpu_count() or 2) // 2))),
                    # yol değil içerik: Türkçe karakterli kurulum klasöründe de açılsın (ceviri_hatti.spm_yukle)
                    ceviri_hatti.spm_yukle(os.path.join(d, "source.spm")),
                    ceviri_hatti.spm_yukle(os.path.join(d, "target.spm")),
                )
        self.cevirici, self.kaynak_sp, self.hedef_sp = CevrimdisiMotor._paylasilan
        if ceviri_hatti._sozluk is None:
            try:
                ceviri_hatti.sozluk_yukle_modelden(os.path.join(model_klasoru(), "source.spm"))
            except Exception as e:
                print(f"[çeviri] kelime dağarcığı okunamadı: {e}", flush=True)
        self.adlar = list(sozluk.get("cevirme", [])) if isinstance(sozluk, dict) else []

    def _model(self, cumleler):
        parcalar = [self.kaynak_sp.encode(c, out_type=str) + ["</s>"] for c in cumleler]
        with CevrimdisiMotor._kilit:  # aynı modeli iki iş parçacığı aynı anda kullanmasın
            sonuc = self.cevirici.translate_batch(parcalar, beam_size=3, max_decoding_length=200)
        return [self.hedef_sp.decode(s.hypotheses[0]).strip() for s in sonuc]

    def isit(self):
        """Modeli bir kez çalıştırır: ilk altyazının çevirisi 2-3 kat geç gelmesin."""
        try:
            self._model(["Hold on, I will be right back with the keys."])
        except Exception:
            pass

    def cevir(self, metin, baglam):
        """Hat: konuşmacı etiketi ayrılır -> düzleştirme -> her cümle ayrı (hazır karşılık ya da model; bilinen
        adlar ve rakam dizileri korunarak) -> son düzeltme."""
        etiket, metin = ceviri_hatti.etiket_ayir(metin)
        on_ek = etiket + ": " if etiket else ""
        adlar = self.adlar + ceviri_hatti.ogrenilen_adlar()
        cumleler = ceviri_hatti.cumlelere_bol(ceviri_hatti.duzlestir(metin, adlar))
        sonuc = [ceviri_hatti.hazir_karsilik(c) for c in cumleler]
        modele = [i for i, h in enumerate(sonuc) if h is None]
        if modele:
            korunan = []
            for i in modele:
                c, ad_haritasi = ceviri_hatti.adlari_koru(cumleler[i], adlar)
                c, rakam_haritasi = ceviri_hatti.rakam_dizisi_koru(c)
                korunan.append((c, ad_haritasi, rakam_haritasi))
            tekrar = []
            for i, (c, ad_h, rakam_h), tr in zip(modele, korunan, self._model([k[0] for k in korunan])):
                tr = ceviri_hatti.rakam_dizisi_geri_koy(tr, rakam_h)
                tr = ceviri_hatti.adlari_geri_koy(tr, ad_h) if ad_h else tr
                if tr is None:  # yer tutucu çeviride kayboldu: bu cümle korumasız çevrilir
                    tekrar.append(i)
                else:
                    sonuc[i] = ceviri_hatti.son_duzelt(cumleler[i], tr)
            if tekrar:
                for i, tr in zip(tekrar, self._model([cumleler[i] for i in tekrar])):
                    sonuc[i] = ceviri_hatti.son_duzelt(cumleler[i], tr)
        return on_ek + " ".join(x for x in sonuc if x)


def tek_motor(ad, c, sozluk):
    """c: config['ceviri']. Anahtarlar c['anahtarlar'][motor] içinde durur."""
    if ad == "cevrimdisi":
        return CevrimdisiMotor(sozluk)
    anahtarlar = c.get("anahtarlar", {})
    if ad in HAZIR_MOTORLAR:
        h = HAZIR_MOTORLAR[ad]
        return LLMMotoru(h["url"], c.get("modeller", {}).get(ad) or h["model"],
                         anahtarlar.get(ad, ""), sozluk, h["ad"], anahtar_gerekli=True, motor_id=ad)
    if ad == "deepl":
        return DeepLMotoru(anahtarlar.get("deepl", ""))
    if ad == "claude":
        return ClaudeMotoru(anahtarlar.get("claude", ""), c.get("modeller", {}).get("claude") or "claude-haiku-5-5", sozluk)
    if ad == "llm":
        return LLMMotoru(c["llm_url"], c["llm_model"], anahtarlar.get("llm", ""), sozluk)
    raise CeviriHatasi(f"Bilinmeyen çeviri motoru: {ad}. Ayarlar → Çeviri'den bir motor seçin.")


class YedekliMotor:
    """Asıl motor çalışmazsa bir süre yedek motora geçer: canlı altyazıda çeviri hiç durmamalı. Kota (429), internet,
    bozuk anahtar ve kaldırılmış modelin yanında beklenmeyen her hata da yedeğe geçirir; eskiden yalnız ilk üçü
    geçiriyordu ve Groq modeli kaldırınca (404) yedek hazır olduğu halde hiç çeviri çıkmıyordu."""

    BEKLEME = 60  # sn — kota / bağlantı / beklenmeyen hata: kısa süre sonra tekrar denenir
    ANAHTAR_BEKLEME = 600  # sn — bozuk anahtar ve kaldırılmış model kendiliğinden düzelmez, seyrek dene
    EN_UZUN_BEKLEME = 900  # sn — servis daha uzun bekleme istese de (günlük kota) en geç bu kadar sonra yoklanır

    def __init__(self, motorlar):
        self.motorlar = motorlar  # [(ad, motor), ...]
        self.ceza = {}  # ad -> şu zamana kadar kullanma
        self.neden = {}  # ad -> son hata mesajı
        self.son_kullanilan = motorlar[0][0]

    def cevir(self, metin, baglam):
        son_hata = None
        simdi = time.time()
        sirali = [m for m in self.motorlar if self.ceza.get(m[0], 0) <= simdi] or self.motorlar
        for ad, motor in sirali:
            try:
                sonuc = motor.cevir(metin, baglam)
            except BosCevap as e:  # yalnız bu satır sıradaki motora gider: motor bozuk değil, ceza ve uyarı yok
                son_hata = e
                continue
            except Exception as e:
                if not isinstance(e, CeviriHatasi):
                    print(f"[çeviri] {ad}: beklenmeyen hata: {type(e).__name__}: {e}", flush=True)
                    e = CeviriHatasi(f"{MOTOR_ADLARI.get(ad, ad)} beklenmeyen bir hata verdi ({type(e).__name__}).")
                if isinstance(e, (AnahtarHatasi, ModelHatasi)):
                    bekleme = self.ANAHTAR_BEKLEME
                else:  # servis Retry-After verdiyse ona uyulur (BEKLEME ile EN_UZUN_BEKLEME arasında)
                    bekleme = min(max(getattr(e, "bekle", 0) or 0, self.BEKLEME), self.EN_UZUN_BEKLEME)
                self.ceza[ad] = time.time() + bekleme
                self.neden[ad] = str(e)
                son_hata = e
                continue
            self.son_kullanilan = ad
            if ad == self.motorlar[0][0]:
                self.neden.pop(ad, None)  # asıl motor düzeldi, uyarı kalksın
            return sonuc
        raise son_hata

    def yedekten_mi(self):
        """Son çeviri asıl motordan değil de yedekten mi geldi?"""
        return self.son_kullanilan != self.motorlar[0][0]

    def uyari(self):
        """Asıl motor çalışmıyor ve yedekle devam ediliyorsa kullanıcıya gösterilecek bilgi."""
        asil = self.motorlar[0][0]
        if self.son_kullanilan == asil or asil not in self.neden:
            return None
        return {"neden": self.neden[asil], "asil": MOTOR_ADLARI.get(asil, asil),
                "aktif": MOTOR_ADLARI.get(self.son_kullanilan, self.son_kullanilan)}


def motor_olustur(ayar, sozluk):
    c = ayar["ceviri"]
    asil = tek_motor(c["motor"], c, sozluk)
    yedek_ad = c.get("yedek_motor")
    # Varsayılan yedek "cevrimdisi" (config.json); "" = kullanıcı yedeği kapattı
    if yedek_ad and yedek_ad != c["motor"]:
        try:
            return YedekliMotor([(c["motor"], asil), (yedek_ad, tek_motor(yedek_ad, c, sozluk))])
        except CeviriHatasi:
            pass  # yedeğin anahtarı yoksa yedeksiz devam
    return asil


class CeviriIscisi:
    """Satırları sırayla, arka planda çevirir; sonucu geri çağırır.
    Aynı cümle ikinci kez gelirse önbellekten anında döner."""

    # Çeviri öncesi/sonrası kurallar (ceviri_hatti.py) değişince artırılır: eski kurallarla çevrilmiş satırlar
    # önbellekten gelmesin. Önbellek anahtarı: "<motor>#<sürüm>#<küçük harfli kaynak>".
    KURAL_SURUMU = 3
    ONBELLEK_SINIRI = 20000

    def __init__(self, motor, geri_cagir, baglam_satir=4, onbellek_yolu="varsayilan", hata_cagir=None,
                 motor_adi="", birlestir=False):
        """birlestir: bölünmüş cümleleri birleştirerek çevir. Bağlam bilgisi kullanmayan çevrimdışı motor için;
        internetli motorlar önceki satırları zaten bağlam olarak alır."""
        self.motor = motor
        self.motor_adi = motor_adi
        self.birlestir = birlestir
        self.tek_gerekli = True  # False: satırın tek başına çevirisi (son_tek) hesaplanmaz — dublaj kapalıyken
        self.son_tek = None  # son geri çağrıda: satırın tek başına çevirisi (birleşik çevrildiyse), yoksa None
        self.geri_cagir = geri_cagir
        self.hata_cagir = hata_cagir or (lambda mesaj: print(f"[çeviri hatası] {mesaj}"))
        self.kuyruk = queue.Queue()
        self.baglam = deque(maxlen=baglam_satir)
        self.onbellek_yolu = veri.onbellek_yolu() if onbellek_yolu == "varsayilan" else onbellek_yolu
        self.onbellek = {}
        if self.onbellek_yolu and os.path.exists(self.onbellek_yolu):
            try:
                with open(self.onbellek_yolu, encoding="utf-8") as f:
                    eski = json.load(f)
                # eski biçimli (sürümsüz) ve eski kural sürümlü kayıtlar bırakılır
                gecerli = f"#{self.KURAL_SURUMU}#"
                self.onbellek = {k: v for k, v in eski.items() if gecerli in k[:40]}
            except Exception:
                self.onbellek = {}
        self._son_kayit = time.time()
        self._degisti = False
        self._yarim = {}  # alan -> (bitmemiş cümlenin o ana kadarki İngilizcesi, zamanı): bölünmüş altyazı için
        self._thread = threading.Thread(target=self._dongu, daemon=True)
        self._thread.start()

    def ekle(self, satir_id, metin, alan=0, tam=None):
        """Atlanan (çevrilmeden atılan) satır sayısını döner. alan: 0 ana altyazı, 1.. ek alanlar.
        tam: ekrandaki yazı öncekinin devamıysa ekranda duran yazının tamamı. O zaman ekranda `tam`ın çevirisi
        gösterilir (ekranda ne varsa o: ne eksik ne fazla); `metin` (yalnız yeni gelen kısım) seslendirme içindir."""
        # Çok birikirse en eskileri at (oyun hızlı akıyorsa geride kalmamak için)
        atlanan = 0
        while self.kuyruk.qsize() > 2:
            try:
                self.kuyruk.get_nowait()
                atlanan += 1
            except queue.Empty:
                break
        self.kuyruk.put((satir_id, metin, alan, tam))
        return atlanan

    DEVAM_SN = 6.0  # bölünmüş cümlenin parçaları en çok bu kadar arayla gelir
    DEVAM_UZUNLUK = 170  # birleşen cümle bundan uzunsa yeni satır tek başına çevrilir (kutuya sığsın)

    def _kaynak(self, metin, alan=0):
        """Oyunlar uzun cümleyi art arda altyazılara böler ("You're the ones" / "who are going to need help" /
        "when they come for you."). Parçalar tek tek çevrilince anlam dağılır; devam eden satır önceki parçayla
        birlikte çevrilir ve cümlenin o ana kadarki tamamının Türkçesi gösterilir."""
        simdi = time.time()
        kaynak = metin
        y = self._yarim.get(alan) if self.birlestir else None
        if y and simdi - y[1] <= self.DEVAM_SN and ceviri_hatti.devam_mi(metin) \
                and len(y[0]) + len(metin) < self.DEVAM_UZUNLUK:
            kaynak = y[0] + " " + metin.strip().lstrip("-–—… ")
        self._yarim[alan] = (kaynak, simdi) if ceviri_hatti.bitmemis_mi(metin) else None
        return kaynak

    def _dongu(self):
        while True:
            satir_id, metin, alan, tam = self.kuyruk.get()
            if satir_id is None:
                break
            if tam:  # ekrandaki yazının tamamı belli: bölünmüş cümle birleştirmesine gerek yok
                kaynak = tam
                self._yarim[alan] = (tam, time.time()) if ceviri_hatti.bitmemis_mi(tam) else None
            else:
                kaynak = self._kaynak(metin, alan)
            t0 = time.time()
            baglam = list(self.baglam) if alan == 0 else []
            tr = self._cevir(kaynak, baglam)
            # Ekranda cümlenin tamamı gösterilir; seslendirme için yalnız bu parçanın çevirisi (tekrar okunmasın).
            # Yalnız dublaj açıkken hesaplanır: altyazı ikinci bir çeviriyi beklemesin.
            self.son_tek = self._cevir(metin, baglam) if (tr and kaynak != metin and self.tek_gerekli) else None
            if alan == 0:
                self.baglam.append(metin)
            if tr:
                self.geri_cagir(satir_id, tam or metin, tr, time.time() - t0)
            if time.time() - self._son_kayit > 30:
                self.kaydet()

    def _cevir(self, kaynak, baglam):
        anahtar = f"{self.motor_adi}#{self.KURAL_SURUMU}#{kaynak.lower()}"
        if anahtar in self.onbellek:
            return self.onbellek[anahtar]
        try:
            tr = self.motor.cevir(kaynak, baglam)
        except Exception as e:
            self.hata_cagir(str(e))
            return None
        yedekten = getattr(self.motor, "yedekten_mi", None)
        if tr and not (yedekten and yedekten()):  # yedek motorun çevirisi asıl motorun adına saklanmaz
            self.onbellek[anahtar] = tr
            self._degisti = True
        return tr

    def kaydet(self):
        self._son_kayit = time.time()
        if not self.onbellek_yolu or not self._degisti:
            return
        try:
            if len(self.onbellek) > self.ONBELLEK_SINIRI:  # en eskiler atılır (sözlük ekleme sırasını korur)
                fazla = len(self.onbellek) - self.ONBELLEK_SINIRI
                for k in list(self.onbellek)[:fazla]:
                    del self.onbellek[k]
            gecici = self.onbellek_yolu + ".tmp"
            with open(gecici, "w", encoding="utf-8") as f:
                json.dump(self.onbellek, f, ensure_ascii=False)
            os.replace(gecici, self.onbellek_yolu)
            self._degisti = False
        except Exception as e:
            print(f"[önbellek kaydedilemedi] {e}")

    def durdur(self):
        self.kuyruk.put((None, None, 0, None))
        self._thread.join(timeout=2)
        self.kaydet()
