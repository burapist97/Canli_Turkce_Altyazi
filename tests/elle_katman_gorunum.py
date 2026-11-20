"""ELLE çalıştırılır (birinci ekranın ÜST kısmında ~6 sn örnek Türkçe yazı görünür; başka hiçbir şeye dokunmaz):

  .venv\\Scripts\\python.exe tests\\elle_katman_gorunum.py

Altyazı özelleştirmesi GERÇEK katman penceresinde (bilgisayar oyunu modu: WebView2 + renk anahtarıyla saydamlık)
doğru çiziliyor mu? Otomatik test (test_gorunum) bunu Chromium'da dener; katman penceresinde saydamlık başka
çalıştığı için ayrıca ekran görüntüsünden ölçülür:
- sarı yazı + koyu kutu, ekranın üstünde: o şeritte sarı ve siyah pikseller belirir;
- beyaz yazı + kenar çizgisi, kutusuz: beyaz pikseller belirir, ama kutu kadar siyah alan OLUŞMAZ (arkası saydam);
- yazı istenen yükseklikte durur.
Oyun yerine sahte pencere açılmaz, alt taraftaki altyazı bölgesine bir şey çizilmez (o sırada çalışan gerçek
uygulama bunu altyazı sanıp okumasın diye). Ekran görüntüsü yalnız bellekte ölçülür, DOSYAYA KAYDEDİLMEZ: o an ekranda
açık olan her şey (özel bilgiler dahil) görüntüye girer (2026-11-20'de böyle oldu, dosyalar silindi).
Siyah piksel sayan denetimler arka plan koyuysa (koyu temalı pencere) anlamsızdır ve atlanır.
"""
import os
import socket
import sys
import tempfile
import time

KLASOR = os.path.dirname(os.path.abspath(__file__))
PROJE = os.path.dirname(KLASOR)
CIKTI = os.path.join(KLASOR, "cikti")
os.makedirs(CIKTI, exist_ok=True)
os.environ["CTA_VERI"] = tempfile.mkdtemp(prefix="cta_katman_")
os.environ["CTA_DOGAL_SES_YOK"] = "1"
sys.path.insert(0, PROJE)


def bos_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def main():
    import cv2
    import numpy as np
    import webview

    import pc_katman
    import uygulama
    import veri

    a = veri.ayar_yukle()
    a.update({"kurulum_tamam": True, "senaryo": "pc"})
    a["kaynak"].update({"tip": "ekran", "ekran_no": 1})
    a["goruntu"]["port"] = bos_port()  # 38765 o sırada açık olan gerçek uygulamada olabilir
    a["goruntu"]["orijinali_kapat"] = False  # alttaki altyazı bölgesine koyu şerit çizilmesin
    veri.ayar_kaydet(a)
    uyg = uygulama.Uygulama()
    assert not uyg.overlay_hatasi, uyg.overlay_hatasi
    s = uygulama.api_sunucusu(uyg, "x")
    pencere = webview.create_window("Katman denemesi", f"http://127.0.0.1:{s.server_address[1]}/#x", width=420, height=260,
                                    hidden=True)
    katman = pc_katman.Katman(f"http://127.0.0.1:{uyg.ayar['goruntu']['port']}")
    hatalar = []

    def kontrol(kosul, mesaj):
        print(("  [OK] " if kosul else "  [X] ") + mesaj, flush=True)
        if not kosul:
            hatalar.append(mesaj)

    def serit(img, y_orta, yari=0.07):
        h, w = img.shape[:2]
        return img[int(h * (y_orta - yari)):int(h * (y_orta + yari)), int(w * 0.15):int(w * 0.85)].astype(np.int16)

    def say(once, sonra, kosul):
        """Önceki görüntüde koşulu sağlamayıp sonrakinde sağlayan piksel sayısı (arka plandaki benzer renkler sayılmaz)."""
        return int((kosul(sonra) & ~kosul(once)).sum())

    def sari(p):  # BGR
        return (p[:, :, 2] > 215) & (p[:, :, 1] > 185) & (p[:, :, 0] < 130)

    def beyaz(p):
        return p.min(axis=2) > 235

    def siyah(p):
        return p.max(axis=2) < 10

    def is_():
        try:
            time.sleep(1.5)
            ekran = pc_katman.ekranlar()[0]
            katman.ac(ekran)
            pc_katman.yakalamadan_gizle(katman.hwnd, False)  # ekran görüntüsünde görünsün (normalde gizlidir)
            time.sleep(2.0)  # sayfa yüklensin, DWM yeni hali çizsin
            bos = pc_katman.ekran_goruntusu(1)

            # 1) sarı yazı + koyu kutu, kenar çizgisi yok, ekranın üstünde (y = 0,20)
            uyg.gorunum_kaydet({"yazi_rengi": "#ffe04a", "kutu": "koyu", "kenar": 0, "yazi_boyutu": 56, "yazi_tipi": "oyun",
                                "yazi_kalinligi": 800, "konum": "serbest", "konum_x": 0.5, "konum_y": 0.2})
            uyg.yayinci.gonder({"tip": "satir", "id": 1, "en": "", "tr": "Arabaya bin, polisler hemen arkamızda!"})
            time.sleep(1.8)
            g1 = pc_katman.ekran_goruntusu(1)
            s1, k1 = say(serit(bos, 0.2), serit(g1, 0.2), sari), say(serit(bos, 0.2), serit(g1, 0.2), siyah)
            koyu_zemin = float(serit(bos, 0.27, 0.14).mean()) < 60  # arkası zaten siyaha yakın: siyah sayımı işe yaramaz
            kontrol(s1 > 2500 and (k1 > 15000 or koyu_zemin), f"sarı yazı ve koyu kutu üstte çizildi (sarı {s1}, siyah {k1} piksel)")
            asagida = say(serit(bos, 0.45), serit(g1, 0.45), sari)
            kontrol(asagida < 50, f"yazı yalnız istenen yerde (ekranın ortasında sarı {asagida} piksel)")

            # 2) beyaz yazı + kalın kenar çizgisi, kutusuz, biraz daha aşağıda (y = 0,34): arkası saydam kalmalı
            uyg.gorunum_kaydet({"yazi_rengi": "#ffffff", "kutu": "yok", "kenar": 3, "konum_y": 0.34})
            time.sleep(1.8)
            g2 = pc_katman.ekran_goruntusu(1)
            b2, k2 = say(serit(bos, 0.34), serit(g2, 0.34), beyaz), say(serit(bos, 0.34), serit(g2, 0.34), siyah)
            kontrol(b2 > 2500, f"beyaz yazı yeni yerinde çizildi ({b2} piksel)")
            kontrol(koyu_zemin or 500 < k2 < k1 * 0.75, f"kenar çizgisi var ama kutu yok: arkası saydam (siyah {k2} piksel; kutuluyken {k1})")
            eski_yer = say(serit(bos, 0.2, 0.05), serit(g2, 0.2, 0.05), sari)
            kontrol(eski_yer < 50, f"eski yerde yazı kalmadı ({eski_yer} sarı piksel)")

            # 3) yarı saydam kutu: arkası kararır ama görünmeye devam eder (tam siyah olmaz). İlk ölçümde böyle çıktı;
            #    "renk anahtarlı pencere yarı saydam gösteremez" varsayımı YANLIŞTI, panelden o seçeneği gizlemek hataydı.
            uyg.gorunum_kaydet({"kutu": "yari", "kenar": 0})
            time.sleep(1.5)
            g3 = pc_katman.ekran_goruntusu(1)
            k3 = say(serit(bos, 0.34), serit(g3, 0.34), siyah)
            h, w = bos.shape[:2]
            ic = (slice(int(h * 0.325), int(h * 0.355)), slice(int(w * 0.32), int(w * 0.68)))  # kutunun içi
            once, sonra = float(bos[ic].mean()), float(g3[ic][g3[ic].min(axis=2) < 200].mean())  # yazının beyazı hariç
            kontrol(koyu_zemin or k3 < k1 * 0.3, f"yarı saydam kutu tam siyah değil (siyah {k3} piksel; koyu kutuda {k1})")
            kontrol(sonra < once * 0.8 or once < 40, f"yarı saydam kutunun arkası karardı (parlaklık {once:.0f} -> {sonra:.0f})")

            # 4) (2.7) istenen RENKTE yarı saydam arka plan, boydan boya şerit: kırmızı %60 -> şeridin içi kızarır,
            #    arkası yine görünür (tam kırmızı olmaz)
            uyg.gorunum_kaydet({"kutu_rengi": "#c81e1e", "kutu_saydamlik": 0.6, "kutu_bicimi": "serit", "kutu_kose": 0})
            time.sleep(1.5)
            g4 = pc_katman.ekran_goruntusu(1)
            kenar = (slice(int(h * 0.33), int(h * 0.35)), slice(int(w * 0.13), int(w * 0.2)))  # yazının solunda, şeridin içi
            o, s4 = bos[kenar].reshape(-1, 3).mean(axis=0), g4[kenar].reshape(-1, 3).mean(axis=0)  # BGR
            beklenen = o * 0.4 + np.array([30, 30, 200]) * 0.6
            kontrol(float(np.abs(s4 - beklenen).max()) < 28,
                    f"kırmızı %60 şerit doğru karıştı (önce BGR {o.round()}, sonra {s4.round()}, beklenen {beklenen.round()})")
        except Exception:
            import traceback
            traceback.print_exc()
            hatalar.append("istisna")
        finally:
            try:
                katman.kapat()
            except Exception:
                pass
            uyg.kapat()
            pencere.destroy()

    webview.start(is_)
    print("✓ elle_katman_gorunum geçti" if not hatalar else f"✗ {len(hatalar)} kontrol başarısız")
    sys.exit(1 if hatalar else 0)


if __name__ == "__main__":
    main()
