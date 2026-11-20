r"""ELLE çalıştırılır: Doğal ses sunucusu MSIX paket bağlamından başlatılabiliyor mu?

Store'dan kurulan uygulama "paket kabı" içinde çalışır (AppData yazmaları sanallaştırılır). Bu betik aynı kodu
(dogal_ses.py) paket bağlamında çalıştırır: sunucuyu başlatır, bir cümle üretir (hoparlörden ses çıkmaz) ve sonucu
tests\cikti\paket_dogal.txt dosyasına yazar.

  $p = Get-AppxPackage *CanlTrkeAltyaz*
  Invoke-CommandInDesktopPackage -PackageFamilyName $p.PackageFamilyName -AppId CanliTurkceAltyazi `
      -Command "<proje>\.venv\Scripts\python.exe" -Args "<proje>\tests\elle_paket_dogal.py [boş bellek sınırı GB] [birak]"

"birak" verilirse sunucu kapatılmadan süreçten çıkılır: uygulama çökerse sunucunun da kapanıp kapanmadığı
(iş nesnesi) dışarıdan `Get-Process audiocpp_server` ile denetlenir.
"""
import os
import sys
import time
import traceback

KLASOR = os.path.dirname(os.path.abspath(__file__))
PROJE = os.path.dirname(KLASOR)
sys.path.insert(0, PROJE)
CIKTI = os.path.join(KLASOR, "cikti", "paket_dogal.txt")


class Sessiz:
    def cal(self, x):
        pass

    def bitir(self):
        pass


def main():
    satirlar = []
    birak = "birak" in sys.argv[1:]
    try:
        import dogal_ses
        sayilar = [a for a in sys.argv[1:] if a.replace(".", "").isdigit()]
        if sayilar:
            dogal_ses.GEREKEN_BOS_BELLEK_GB = float(sayilar[0])
        satirlar.append(f"boş bellek: {dogal_ses.bos_bellek_gb():.1f} GB (sınır {dogal_ses.GEREKEN_BOS_BELLEK_GB})")
        d = dogal_ses.DogalSes()
        satirlar.append(f"paket klasörü: {d.klasor} | ses sayısı: {len(d.sesler)}")
        t = time.time()
        if not d.baslat(180):
            satirlar.append(f"BAŞLAMADI: {d.hata}")
        else:
            satirlar.append(f"sunucu {time.time() - t:.1f} sn'de açıldı, pid {d.surec.pid if d.surec else '-'}")
            t = time.time()
            sure = d.cal("Deneme tamam, sesler hazır.", d.sesler[0], oynatici=Sessiz())
            satirlar.append(f"TAMAM: {sure:.1f} sn ses {time.time() - t:.1f} sn'de üretildi")
            if birak:
                satirlar.append("sunucu kapatılmadan çıkılıyor (iş nesnesi denemesi)")
                with open(CIKTI, "w", encoding="utf-8") as f:
                    f.write("\n".join(satirlar) + "\n")
                os._exit(0)
            d.durdur()
    except Exception:
        satirlar.append("HATA:\n" + traceback.format_exc())
    os.makedirs(os.path.dirname(CIKTI), exist_ok=True)
    with open(CIKTI, "w", encoding="utf-8") as f:
        f.write("\n".join(satirlar) + "\n")


if __name__ == "__main__":
    main()
