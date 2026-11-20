"""Hafif doğal ses motorunun seslerini ölçer ve hafif_ses\\sesler\\uyum.json dosyasına yazar.

  .venv\\Scripts\\python.exe paket\\hafif_ses\\uyum_hazirla.py     (projenin ANA ortamıyla; ses çalınmaz)

"Sesi konuşana uydur" her sesin ses izini (TitaNet) ve perdesini, birkaç kaydırma oranı için bilmek ister
(ses_uyum.Uyumlayici). Bunlar çalışırken ölçülürse açılışta her sesle bir örnek cümle üretmek gerekir (12 ses ~40 sn;
o sürede doğal ses kullanılamaz). Sesler pakette sabit olduğu için ölçüm bir kez burada yapılır; uygulama dosyayı
okur ve doğal ses açılır açılmaz kullanılır. Sesler ya da model değişince yeniden çalıştırılır
(tests/test_hafif_ses.py dosyanın bütün sesleri kapsadığını denetler).
"""
import json
import os
import socket
import sys
import tempfile
import time

PROJE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJE)
os.environ.setdefault("CTA_VERI", tempfile.mkdtemp(prefix="cta_uyum_"))
os.environ["CTA_UYUM_HAZIRLA"] = "1"  # dosya olsa da sesleri yeniden üretip ölç
os.environ.pop("CTA_DOGAL_SES_YOK", None)

import dogal_ses  # noqa: E402
import konusmaci  # noqa: E402
import ses_uyum  # noqa: E402


def main():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    d = dogal_ses.DogalSes(adres=f"http://127.0.0.1:{port}", motor="hafif")
    if not d.klasor:
        sys.exit("[X] Hafif ses ortamı yok. Önce: powershell -ExecutionPolicy Bypass -File paket\\hafif_ses\\ortam_hazirla.ps1")
    tanici = konusmaci.KonusmaciTanici()
    try:
        if not d.baslat(180):
            sys.exit(f"[X] Ses sunucusu başlamadı: {d.hata}")
        for _ in range(600):
            if d.isinma_bitti:
                break
            time.sleep(0.5)
        eksik = [x["id"] for x in d.sesler if x["id"] not in d.ornekler]
        if eksik:
            sys.exit(f"[X] Bu seslerin örneği üretilemedi: {eksik}")
        u = ses_uyum.Uyumlayici(tanici)
        sesler = {}
        for ses in d.sesler:
            u.ses_ekle(ses["id"], ses["cinsiyet"], d.ornekler[ses["id"]], d.ornek_hizi)
            olcum = u.disari_ver(ses["id"])
            if len(olcum) != len(ses_uyum.KAYDIRMALAR):
                sys.exit(f"[X] {ses['id']} ölçülemedi ({len(olcum)}/{len(ses_uyum.KAYDIRMALAR)} oran)")
            # cinsiyet modelimiz de aynı şeyi söylüyor mu (yanlış etiketli ses pakete girmesin)
            _, _, kadin = tanici.cozumle(d.ornekler[ses["id"]], d.ornek_hizi)
            beklenen = ses["cinsiyet"] == "kadin"
            if (kadin > konusmaci.KADIN_ESIGI) != beklenen:
                sys.exit(f"[X] {ses['id']} '{ses['cinsiyet']}' diye tanımlı ama modelimiz kadın olasılığını {kadin:.2f} buldu")
            sesler[ses["id"]] = olcum
            print(f"  {ses['id']:<14} {ses['ad']:<8} {ses['cinsiyet']:<6} perde {olcum['1']['perde']:6.1f} Hz "
                  f"(kaydırmayla {olcum['0.88']['perde']:.0f}-{olcum['1.12']['perde']:.0f}), kadın olasılığı {kadin:.2f}")
    finally:
        d.durdur()
    yol = os.path.join(d.klasor, "sesler", "uyum.json")
    with open(yol, "w", encoding="utf-8") as f:
        json.dump({"aciklama": "Seslerin önceden ölçülmüş ses izi (TitaNet) ve perdesi; paket/hafif_ses/uyum_hazirla.py üretir",
                   "ornek_cumle": dogal_ses.ORNEK_CUMLE, "kaydirmalar": list(ses_uyum.KAYDIRMALAR), "sesler": sesler},
                  f, ensure_ascii=False, separators=(",", ":"))
    print(f"[OK] {len(sesler)} ses ölçüldü: {yol} ({os.path.getsize(yol) // 1024} KB)")


if __name__ == "__main__":
    main()
