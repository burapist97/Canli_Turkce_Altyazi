"""ELLE çalıştırılır (hoparlörden iki kez ~3 sn 440 Hz ton çalar):

  .venv\\Scripts\\python.exe tests\\elle_surec_loopback.py

Süreç loopback'i (surec_loopback.py) bizim süreç ağacımızı hariç tutuyor mu?
- Ağaç DIŞINDAN (WMI ile başlatılan süreç) çalınan ton yakalanmalı (oyunu temsil eder).
- Kendi sürecimizden çalınan ton yakalanmamalı (Türkçe okumamızı temsil eder).
Not: subprocess ile başlatılan süreçler bizim ağacımızdadır, onlar da hariç tutulur; deneme bu yüzden WMI kullanır.
"""
import os
import subprocess
import sys
import tempfile
import threading
import time
import wave
import winsound

import numpy as np

import yardimci  # noqa: F401
import surec_loopback


def bant_payi(x, f0, sr=16000):
    F = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
    fr = np.fft.rfftfreq(len(x), 1 / sr)
    return F[(fr > f0 - 5) & (fr < f0 + 5)].sum() / max(F.sum(), 1e-12)


def main():
    if not surec_loopback.destekleniyor():
        print("Bu Windows'ta süreç loopback'i yok (2004 öncesi): atlandı")
        return
    ton = os.path.join(tempfile.mkdtemp(), "ton440.wav")
    t = np.arange(int(44100 * 2.5)) / 44100
    w = wave.open(ton, "wb")
    w.setnchannels(1), w.setsampwidth(2), w.setframerate(44100)
    w.writeframes((0.3 * np.sin(2 * np.pi * 440 * t) * 32767).astype(np.int16).tobytes())
    w.close()

    tampon, dur, hazir = [], threading.Event(), threading.Event()

    def dongu():
        k = surec_loopback.SurecLoopback()
        k.baslat()
        hazir.set()
        while not dur.is_set():
            tampon.append(k.oku())
        k.durdur()
    th = threading.Thread(target=dongu)
    th.start()
    assert hazir.wait(10), "süreç loopback'i başlamadı"
    time.sleep(0.3)

    def disaridan():
        komut = f"powershell -NoProfile -WindowStyle Hidden -Command (New-Object Media.SoundPlayer '{ton}').PlaySync()"
        subprocess.run(["powershell", "-NoProfile", "-Command",
                        f"Invoke-CimMethod -ClassName Win32_Process -MethodName Create "
                        f"-Arguments @{{CommandLine=\"{komut}\"}} | Out-Null"])
        time.sleep(3.5)

    sonuc = {}
    for ad, f in (("disari", disaridan), ("kendi", lambda: winsound.PlaySound(ton, winsound.SND_FILENAME))):
        tampon.clear()
        f()
        time.sleep(0.3)
        sonuc[ad] = bant_payi(np.concatenate(tampon), 440)
    dur.set()
    th.join()
    print(f"  440 Hz payı: ağaç dışı {sonuc['disari']:.3f} (yüksek olmalı) | kendi sürecimiz {sonuc['kendi']:.3f} (düşük olmalı)")
    assert sonuc["disari"] > 0.3, "başka uygulamanın sesi yakalanmadı"
    assert sonuc["kendi"] < 0.1, "kendi sesimiz yakalandı"
    print("  ✓ süreç loopback'i: oyunun sesi duyuluyor, bizim sesimiz duyulmuyor")


if __name__ == "__main__":
    sys.exit(main())
