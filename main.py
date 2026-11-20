"""Komut satırı sürümü (geliştirme ve testler için). Normal kullanım: uygulama.py

  python main.py [--config yol] [--debug]
"""
import argparse
import time

import motor
import sunucu
import veri


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=None, help="Ayar dosyası (varsayılan: kullanıcı veri klasörü)")
    ap.add_argument("--debug", action="store_true", help="Kesit ve maskeyi pencerede göster")
    args = ap.parse_args()

    ayar = veri.ayar_yukle(args.config)
    yayinci = sunucu.Yayinci(ayar["goruntu"], ayar["bolge"])
    sunucu.sunucu_baslat(yayinci, ayar["goruntu"]["port"])
    print("OCR motoru yükleniyor...", flush=True)
    m = motor.AltyaziMotoru(ayar, yayinci, debug=args.debug or ayar.get("hata_ayiklama", False))
    m.baslat()
    try:
        while m.durum in ("basliyor", "calisiyor"):
            time.sleep(0.2)
    except KeyboardInterrupt:
        pass
    finally:
        print("\nKapatılıyor...")
        m.durdur()


if __name__ == "__main__":
    main()
