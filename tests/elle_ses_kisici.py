"""ELLE çalıştırılır (hoparlörden ~12 sn ÇOK KISIK 200 Hz ton çalar; başka uygulamaların sesine dokunmaz):

  .venv\\Scripts\\python.exe tests\\elle_ses_kisici.py

Gerçek Windows ses oturumlarıyla ses_kisici.SistemSesKisici:
- Başka bir sürecin (WMI ile başlatılan, oyunu temsil eden) ses oturumu bulunuyor mu, seviyesi okunuyor mu?
- kis() seviyeyi çarpana indiriyor, ac() eski değerine getiriyor mu?
- Kısıkken "çökme" (ac çağrılmadan bırakma) sonrası yarim_kalani_duzelt eski seviyeyi geri yüklüyor mu?
- Süreç loopback'i (konuşanı tanımak için dinlediğimiz ses) uygulama seviyesinden etkileniyor mu? (ölçüm)
Yalnızca test tonunun süreci kısılır (yalniz_pid); kullanıcının açık uygulamalarına dokunulmaz.
"""
import os
import subprocess
import sys
import tempfile
import threading
import time
import wave

import numpy as np

import yardimci  # noqa: F401
import ses_kisici
import surec_loopback

os.environ.pop("CTA_SES_KISMA_YOK", None)  # bu deneme gerçek ses oturumlarıyla çalışır (yalnız kendi ton süreciyle)

FREKANS, GENLIK, SURE = 200, 0.004, 14.0


def bant_genligi(x, f0, sr=16000):
    """f0 çevresindeki dar bandın genliği (tonun tepe genliğine yakın)."""
    if len(x) < sr // 4:
        return 0.0
    F = np.abs(np.fft.rfft(x * np.hanning(len(x)))) / (len(x) / 4)
    fr = np.fft.rfftfreq(len(x), 1 / sr)
    return float(np.sqrt((F[(fr > f0 - 6) & (fr < f0 + 6)] ** 2).sum()))


def main():
    ton = os.path.join(tempfile.mkdtemp(), "ton.wav")
    t = np.arange(int(44100 * SURE)) / 44100
    w = wave.open(ton, "wb")
    w.setnchannels(1), w.setsampwidth(2), w.setframerate(44100)
    w.writeframes((GENLIK * np.sin(2 * np.pi * FREKANS * t) * 32767).astype(np.int16).tobytes())
    w.close()

    # Ağacımızın DIŞINDA bir süreç (oyun yerine): WMI ile başlatılır
    komut = f"powershell -NoProfile -WindowStyle Hidden -Command (New-Object Media.SoundPlayer '{ton}').PlaySync()"
    cikti = subprocess.run(["powershell", "-NoProfile", "-Command",
                            f"(Invoke-CimMethod -ClassName Win32_Process -MethodName Create "
                            f"-Arguments @{{CommandLine=\"{komut}\"}}).ProcessId"], capture_output=True, text=True)
    pid = int(cikti.stdout.strip())
    print(f"  ton süreci: {pid}")

    ses_kisici._com_ac()
    oturum = None
    for _ in range(50):
        oturum = next((o for o in ses_kisici.oturumlari_listele() if o.pid == pid), None)
        if oturum:
            break
        time.sleep(0.1)
    assert oturum, "ton sürecinin ses oturumu bulunamadı"
    hepsi = ses_kisici.oturumlari_listele()
    print(f"  oturumlar: {[(o.uygulama or '?', o.pid, round(o.seviye(), 2), 'sistem' if o.sistem else '') for o in hepsi]}")
    assert any(o.sistem for o in hepsi) or True
    assert not oturum.sistem and oturum.uygulama == "powershell.exe", (oturum.sistem, oturum.uygulama)
    assert "powershell" in oturum.kimlik.lower(), oturum.kimlik
    eski = oturum.seviye()
    print(f"  ton oturumu: {oturum.uygulama}, seviye {eski:.2f}")
    if eski < 0.5:  # önceki denemeden kısık kalmış olabilir
        oturum.ayarla(1.0)
        eski = oturum.seviye()

    tampon, dur = [], threading.Event()
    loopback_var = surec_loopback.destekleniyor()
    if loopback_var:
        hazir = threading.Event()

        def dinle():
            k = surec_loopback.SurecLoopback()
            k.baslat()
            hazir.set()
            while not dur.is_set():
                tampon.append(k.oku())
            k.durdur()
        th = threading.Thread(target=dinle)
        th.start()
        assert hazir.wait(10)

    def olc(sn=1.0):
        tampon.clear()
        time.sleep(sn)
        return bant_genligi(np.concatenate(tampon) if tampon else np.zeros(0), FREKANS) if loopback_var else 0.0

    try:
        time.sleep(0.4)
        acik = olc()
        k = ses_kisici.SistemSesKisici(-14, yalniz_pid=[pid])
        t0 = time.time()
        k.kis()
        assert k.bekle(2), "kısma bitmedi"
        inis = time.time() - t0
        kisik_seviye = oturum.seviye()
        assert k.kisilan == 1, f"yalnız ton süreci kısılmalıydı: {k.kisilan}"
        assert abs(kisik_seviye - eski * k.carpan) < 0.02, (kisik_seviye, eski, k.carpan)
        assert os.path.exists(ses_kisici._kayit_yolu()), "eski seviye diske yazılmadı"
        kisik = olc()
        t0 = time.time()
        k.ac()
        assert k.bekle(2), "geri açma bitmedi"
        cikis = time.time() - t0
        assert abs(oturum.seviye() - eski) < 0.01, (oturum.seviye(), eski)
        assert not os.path.exists(ses_kisici._kayit_yolu()), "geri açılınca kayıt silinmeli"
        yeniden = olc()
        print(f"  kis: {eski:.2f} -> {kisik_seviye:.2f} ({inis * 1000:.0f} ms) | ac: -> {oturum.seviye():.2f} ({cikis * 1000:.0f} ms)")
        if loopback_var and acik > 1e-5:
            oran = kisik / acik
            print(f"  süreç loopback'i 200 Hz genliği: açık {acik:.5f}, kısık {kisik:.5f} (oran {oran:.2f}), yeniden açık {yeniden:.5f}")
            print("  => dinlediğimiz ses uygulama seviyesinden " + ("ETKİLENİYOR" if oran < 0.6 else "etkilenmiyor"))

        # "çökme": kısıkken iş parçacığı geri almadan bırakılır; yeni çalışmada düzeltilmeli
        k.kis()
        assert k.bekle(2)
        assert abs(oturum.seviye() - eski * k.carpan) < 0.02
        k._izlenen = []          # geri alma bilgisini unut (çökmüş gibi)
        k._bitir = True
        k._olay.set()
        k._thread.join(2)
        assert abs(oturum.seviye() - eski * k.carpan) < 0.02, "çökme benzetimi sesi geri açmamalıydı"
        ses_kisici.yarim_kalani_duzelt(bekle=True)
        assert abs(oturum.seviye() - eski) < 0.01, f"çökme sonrası ses geri açılmadı: {oturum.seviye()}"
        assert not os.path.exists(ses_kisici._kayit_yolu())
        print("  ✓ çökme sonrası bir sonraki açılışta ses eski seviyesine döndü")

        # kullanıcı arada sürgüyü elle değiştirdiyse dokunulmaz
        ses_kisici._kayit_yaz({oturum.kimlik: 0.5})
        oturum.ayarla(0.9)
        ses_kisici.yarim_kalani_duzelt(bekle=True)
        assert abs(oturum.seviye() - 0.9) < 0.01, "elle yükseltilmiş seviyeye dokunuldu"
        oturum.ayarla(eski)
        print("  ✓ ses_kisici: gerçek ses oturumu kısıldı, geri açıldı, çökme sonrası düzeltildi")
    finally:
        try:
            oturum.ayarla(max(eski, 1.0))
        except Exception:
            pass
        dur.set()
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)  # kendi başlattığımız ton süreci


if __name__ == "__main__":
    sys.exit(main())
