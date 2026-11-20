"""Bilgisayar oyununda okurken oyunun sesini kısma (ses_kisici.py), sahte ses oturumlarıyla:
kimler kısılır / kısılmaz, eski seviyeye dönüş, yumuşak geçiş, çökme sonrası düzeltme, kullanıcı ayarına saygı.
Gerçek Windows ses oturumlarıyla deneme: tests/elle_ses_kisici.py (elle)."""
import os
import subprocess
import sys
import time

import yardimci  # noqa: F401

import ses_kisici


def _com_kipi_denemesi():
    """Gerçek ses oturumlarını OKUMA (hiçbir seviye değişmez), COM'u önceden iki kipte de açmış iş parçacığında.
    comtypes ilk kez böyle bir iş parçacığında içe aktarılınca düşüyordu (2.4.1 duman testinde yakalandı:
    Türkçe ses motoru WinRT ile COM'u çok iş parçacıklı kipte açtıktan sonra)."""
    if not sys.platform.startswith("win"):
        return
    kod = ("import ctypes, sys; sys.path.insert(0, sys.argv[1]); ctypes.windll.ole32.CoInitializeEx(None, int(sys.argv[2])); "
           "import ses_kisici; ses_kisici._com_ac(); print('OTURUM', len(ses_kisici.oturumlari_listele()))")
    for kip, ad in ((0, "çok iş parçacıklı"), (2, "tek iş parçacıklı")):
        r = subprocess.run([sys.executable, "-c", kod, yardimci.PROJE, str(kip)], capture_output=True, text=True,
                           timeout=60, encoding="utf-8", errors="replace")
        assert "OTURUM" in r.stdout, f"COM {ad} kipte açıkken ses oturumları okunamadı: {r.stdout} {r.stderr[-500:]}"
    print("  ✓ ses oturumları her iki COM kipinde de okunuyor")


class _Oturum:
    def __init__(self, uygulama, pid, seviye=1.0, sistem=False, kimlik=None, bozuk=False):
        self.uygulama, self.pid, self.sistem = uygulama, pid, sistem
        self.kimlik = kimlik or f"aygit|{uygulama}"
        self.ornek = f"{self.kimlik}|{pid}"
        self.v, self.bozuk, self.gecmis = seviye, bozuk, []

    def seviye(self):
        if self.bozuk:
            raise OSError("oturum kapandı")
        return self.v

    def ayarla(self, s):
        if self.bozuk:
            raise OSError("oturum kapandı")
        self.v = s
        self.gecmis.append(round(s, 4))


def _kayit_var():
    return os.path.exists(ses_kisici._kayit_yolu())


def test_ses_kisici():
    _com_kipi_denemesi()
    assert abs(ses_kisici.carpan_db(-14) - 0.1995) < 0.001 and ses_kisici.carpan_db(0) == 1.0
    assert ses_kisici.carpan_db(-60) == ses_kisici.EN_DUSUK_CARPAN, "ses tamamen kapatılmamalı"
    if _kayit_var():
        os.remove(ses_kisici._kayit_yolu())

    oyun = _Oturum("oyun.exe", 100, 0.8)
    tarayici = _Oturum("tarayici.exe", 101, 1.0)
    sohbet = _Oturum("discord.exe", 102, 1.0)
    biz = _Oturum("canliturkcealtyazi.exe", 7, 1.0)
    sistem = _Oturum("", 0, 1.0, sistem=True)
    sessiz = _Oturum("sessiz.exe", 103, 0.0)
    hepsi = [oyun, tarayici, sohbet, biz, sistem, sessiz]

    k = ses_kisici.SistemSesKisici(-14, listele=lambda: hepsi, kendi_pid=7)
    try:
        # --- kıs: oyun ve tarayıcı kısılır; sohbet, kendi sesimiz, sistem sesleri ve zaten kapalı olan kısılmaz
        t0 = time.time()
        k.kis()
        assert k.bekle(2), "kısma bitmedi"
        inis = time.time() - t0
        assert abs(oyun.v - 0.8 * k.carpan) < 0.005 and abs(tarayici.v - k.carpan) < 0.005, (oyun.v, tarayici.v)
        assert sohbet.v == 1.0 and biz.v == 1.0 and sistem.v == 1.0 and sessiz.v == 0.0
        assert k.kisilan == 2
        assert inis < 0.4, f"iniş yavaş: {inis:.2f} sn"
        assert len(oyun.gecmis) >= 3 and oyun.gecmis == sorted(oyun.gecmis, reverse=True), \
            f"iniş kademeli olmalı: {oyun.gecmis}"
        # eski seviyeler kısmadan önce diske yazıldı
        kayit, _ = ses_kisici._kayit_oku()
        assert kayit == {"aygit|oyun.exe": 0.8, "aygit|tarayici.exe": 1.0}, kayit

        # --- aç: tam eski seviye, yumuşak çıkış, kayıt silinir
        oyun.gecmis.clear()
        t0 = time.time()
        k.ac()
        assert k.bekle(2), "geri açma bitmedi"
        cikis = time.time() - t0
        assert oyun.v == 0.8 and tarayici.v == 1.0, (oyun.v, tarayici.v)
        assert 0.2 < cikis < 0.9, f"çıkış süresi: {cikis:.2f} sn"
        assert len(oyun.gecmis) >= 5 and oyun.gecmis == sorted(oyun.gecmis), f"çıkış kademeli olmalı: {oyun.gecmis}"
        assert not _kayit_var(), "geri açılınca kayıt silinmeli"

        # --- art arda satırlar: çıkış yarıdayken yeniden kıs -> seviye sıçramadan yine iner, sonunda tam açılır
        k.kis(); k.bekle(2)
        k.ac(); time.sleep(0.12)
        ara = oyun.v
        assert 0.8 * k.carpan < ara < 0.8, f"çıkışın ortasında olmalıydı: {ara}"
        k.kis()
        assert k.bekle(2) and abs(oyun.v - 0.8 * k.carpan) < 0.005
        k.ac()
        assert k.bekle(2) and oyun.v == 0.8 and not _kayit_var()

        # --- kısıkken uygulama kapanırsa: hata yok, kayıt kalır; uygulama yeniden açılınca düzelir
        k.kis(); k.bekle(2)
        tarayici.bozuk = True
        k.ac()
        assert k.bekle(2) and oyun.v == 0.8
        kayit, _ = ses_kisici._kayit_oku()
        assert kayit == {"aygit|tarayici.exe": 1.0}, kayit
        tarayici.bozuk = False
        tarayici.v = k.carpan  # Windows kısık seviyeyi hatırladı
        k.kis()
        assert k.bekle(2) and abs(tarayici.v - k.carpan) < 0.005
        k.ac()
        assert k.bekle(2) and tarayici.v == 1.0 and not _kayit_var(), (tarayici.v, _kayit_var())
    finally:
        k.kapat()

    # --- kapat(): kısıkken program kapanırsa ses hemen eski seviyesine döner
    k = ses_kisici.SistemSesKisici(-14, listele=lambda: hepsi, kendi_pid=7)
    k.kis(); k.bekle(2)
    assert abs(oyun.v - 0.8 * k.carpan) < 0.005
    k.kapat()
    assert oyun.v == 0.8 and tarayici.v == 1.0 and not _kayit_var()
    k.kapat()  # ikinci kez çağrılabilir

    # --- çökme: kısıkken süreç ölür (geri alma çalışmaz) -> sonraki açılışta düzeltilir
    k = ses_kisici.SistemSesKisici(-14, listele=lambda: hepsi, kendi_pid=7)
    k.kis(); k.bekle(2)
    k._izlenen = []
    k.kapat()
    assert abs(oyun.v - 0.8 * k.carpan) < 0.005 and _kayit_var(), "çökme benzetimi"
    assert ses_kisici._bekleyenleri_duzelt(lambda: hepsi) == 2
    assert oyun.v == 0.8 and tarayici.v == 1.0 and not _kayit_var()

    # --- kullanıcı arada sürgüyü elle değiştirdiyse dokunulmaz; kayıt yine temizlenir
    for elle in (0.95, 0.02):
        ses_kisici._kayit_yaz({"aygit|oyun.exe": 0.8})
        oyun.v = elle
        assert ses_kisici._bekleyenleri_duzelt(lambda: hepsi) == 0
        assert oyun.v == elle and not _kayit_var()
    oyun.v = 0.8
    # uygulama kapalıysa kayıt bekler; çok eski kayıt uygulanmaz
    ses_kisici._kayit_yaz({"aygit|baska.exe": 1.0})
    assert ses_kisici._bekleyenleri_duzelt(lambda: hepsi) == 0 and _kayit_var()
    ses_kisici._kayit_yaz({"aygit|oyun.exe": 0.8}, zaman=time.time() - ses_kisici.KAYIT_OMRU - 10)
    oyun.v = 0.16
    assert ses_kisici._bekleyenleri_duzelt(lambda: hepsi) == 0 and oyun.v == 0.16 and not _kayit_var()
    oyun.v = 0.8

    # --- aynı uygulamanın iki oturumu (iki sekme/süreç): ikisi de kısılır, ikisi de geri gelir
    a, b = _Oturum("oyun.exe", 100, 1.0), _Oturum("oyun.exe", 110, 0.5)
    k = ses_kisici.SistemSesKisici(-8, listele=lambda: [a, b], kendi_pid=7)
    try:
        k.kis(); k.bekle(2)
        assert abs(a.v - k.carpan) < 0.005 and abs(b.v - 0.5 * k.carpan) < 0.005
        k.ac()
        assert k.bekle(2) and a.v == 1.0 and b.v == 0.5 and not _kayit_var()

        # --- kısılacak ses yoksa hiçbir şey olmaz; liste hata verirse dublaj durmaz
        k.listele = lambda: [biz, sistem]
        k.kis()
        assert k.bekle(2) and k.kisilan == 0 and not _kayit_var()
        k.ac(); k.bekle(2)
        k.listele = lambda: (_ for _ in ()).throw(OSError("ses sistemi yok"))
        k.kis()
        assert k.bekle(2) and "ses sistemi yok" in k.hata
        k.ac(); k.bekle(2)
    finally:
        k.kapat()

    # --- yalnız belirli süreçler (elle denemede kullanılır)
    k = ses_kisici.SistemSesKisici(-14, listele=lambda: hepsi, kendi_pid=7, yalniz_pid=[101])
    try:
        k.kis(); k.bekle(2)
        assert oyun.v == 0.8 and abs(tarayici.v - k.carpan) < 0.005 and k.kisilan == 1
    finally:
        k.kapat()
    assert tarayici.v == 1.0 and not _kayit_var()

    # --- okurken dinlenen ses de kısık gelir: kısıcı çarpanı bildirir, dinleyici geri çarpar
    bildirilen = []
    k = ses_kisici.SistemSesKisici(-14, listele=lambda: hepsi, kendi_pid=7)
    k.carpan_degisti = bildirilen.append
    try:
        k.kis(); k.bekle(2)
        assert bildirilen and abs(bildirilen[-1] - k.carpan) < 0.001, bildirilen
        k.ac(); k.bekle(2)
        assert bildirilen[-1] == 1.0, bildirilen
    finally:
        k.kapat()
    print("  ✓ ses kısma: oyun kısılıp geri açılıyor; sohbet, sistem ve kendi sesimiz kısılmıyor; çökme sonrası düzeliyor")


if __name__ == "__main__":
    test_ses_kisici()
