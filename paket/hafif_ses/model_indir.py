"""Pocket TTS Turkish modelini modeller\\pocket-tts-turkish klasörüne indirir ve doğrular.

  .venv-ses\\Scripts\\python.exe paket\\hafif_ses\\model_indir.py

Model: wite-tech/pocket-tts-turkish (Hugging Face), ağırlıklar CC-BY-4.0, Kyutai Pocket TTS'ten (CC-BY-4.0) türetilmiş.
Belirli bir sürüme (commit) sabitlenir ve her dosyanın SHA-256 özeti denetlenir: sonradan değişen bir dosya
pakete girmez. Dosyalar zaten yerindeyse ve özetleri tutuyorsa hiçbir şey indirilmez.
"""
import hashlib
import json
import os
import shutil
import sys

DEPO = "wite-tech/pocket-tts-turkish"
SURUM = "fcbd37c74dc127be846face0ff36062e9a939f7b"
DOSYALAR = {
    "config.yaml": "fa60a7799ac09778360ce1aa5c2216fa2ce6f1be06aabb2e0dd4f6ea63a6d3d7",
    "model.safetensors": "c43b72ed336b64c66adceba8fbbb059e869f753b60de086e3f32bf1b118d5a77",
    "tokenizer.model": "a6c3a7ca48ecf3c9254bf72dff58e3f09f2798f49effcbd7debcf6f7a87f3568",
    "voices/female_1.wav": "82be41762735f5004cec992badc67813a02206fe53888ba7342a589197850225",
    "voices/female_2.wav": "98cd697c9dd6f77f253bd1233675496b6d4882cd9c0ef72434b6a12e06564aa7",
    "voices/female_3.wav": "555eab5c0640649c1323e6e51c2fae10a334ac3988e6ba0052822147fd9bc40c",
    "voices/male_1.wav": "e6538a1f0ce60d08994c3a733946589d327cf9256b35b77e4155c0baefadc81a",
    "voices/male_2.wav": "d5585323c634900b054ea20d1c8c9e39d35516b89dba693eaabf8587143dd6d8",
    "voices/male_3.wav": "b5bbbca120837cca1b93c3b8d740e70bcc3f32f53c557af04b207fc69a31545e",
}
PROJE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HEDEF = os.path.join(PROJE, "modeller", "pocket-tts-turkish")


def ozet(yol):
    h = hashlib.sha256()
    with open(yol, "rb") as f:
        for parca in iter(lambda: f.read(1 << 20), b""):
            h.update(parca)
    return h.hexdigest()


def eksikler(klasor):
    return [ad for ad, beklenen in DOSYALAR.items()
            if not os.path.isfile(os.path.join(klasor, ad)) or ozet(os.path.join(klasor, ad)) != beklenen]


def main():
    kaynak = sys.argv[1] if len(sys.argv) > 1 else None  # isteğe bağlı: daha önce indirilmiş klasör (kopyalanır)
    os.makedirs(os.path.join(HEDEF, "voices"), exist_ok=True)
    if kaynak:
        for ad in DOSYALAR:
            if os.path.isfile(os.path.join(kaynak, ad)):
                shutil.copyfile(os.path.join(kaynak, ad), os.path.join(HEDEF, ad))
    if eksikler(HEDEF):
        from huggingface_hub import hf_hub_download
        os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
        for ad in eksikler(HEDEF):
            print("indiriliyor:", ad, flush=True)
            yol = hf_hub_download(repo_id=DEPO, filename=ad, revision=SURUM)
            shutil.copyfile(yol, os.path.join(HEDEF, ad))
    kalan = eksikler(HEDEF)
    if kalan:
        sys.exit(f"[X] Bu dosyalar eksik ya da özeti tutmuyor (pakete alınmaz): {', '.join(kalan)}")
    with open(os.path.join(HEDEF, "kaynak.json"), "w", encoding="utf-8") as f:
        json.dump({"depo": DEPO, "surum": SURUM, "lisans": "CC-BY-4.0",
                   "atif": "Pocket TTS Turkish (Wite Tech), Kyutai Pocket TTS üzerine kurulu",
                   "adres": f"https://huggingface.co/{DEPO}", "dosyalar": DOSYALAR}, f, ensure_ascii=False, indent=1)
    boyut = sum(os.path.getsize(os.path.join(HEDEF, ad)) for ad in DOSYALAR) / 2 ** 20
    print(f"[OK] model hazır: {HEDEF} ({boyut:.0f} MB, sürüm {SURUM[:12]})")


if __name__ == "__main__":
    main()
