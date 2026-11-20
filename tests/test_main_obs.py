"""Ana program OBS kaynağıyla: sahte OBS'ten kare alıp altyazıyı okumalı."""
import json
import os
import subprocess
import sys
import threading
import time

import yardimci
from yardimci import ornek_kare

import sahte_obs


def test_main_obs(obs_port=4463):
    kare = ornek_kare()
    srv, d = sahte_obs.baslat(lambda: kare, obs_port)
    proje = yardimci.gecici_proje()
    p = os.path.join(proje, "config.json")
    with open(p, encoding="utf-8") as f:
        a = json.load(f)
    a["kaynak"]["tip"] = "obs"
    a["obs"].update({"port": obs_port, "sifre": sahte_obs.SIFRE, "kaynak_adi": "Capture Card"})
    a["goruntu"]["port"] = 8798
    # Anahtar gerektirmeyen motor; ulaşılamayan adres -> "çeviri hatası" basar, normal
    a["ceviri"].update({"motor": "llm", "llm_url": "http://127.0.0.1:9/v1/chat/completions"})
    with open(p, "w", encoding="utf-8") as f:
        json.dump(a, f)
    pr = subprocess.Popen([sys.executable, "-u", os.path.join(proje, "main.py"), "--config", p],
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                          env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    # Sabit süre yerine: altyazı okunana kadar (en çok 40 sn) bekle, sonra 4 sn daha çalıştır (kare sayısı için)
    satirlar = []
    threading.Thread(target=lambda: satirlar.extend(iter(pr.stdout.readline, "")), daemon=True).start()
    son = time.time() + 40
    while time.time() < son and not any("EN: Lucia" in x for x in satirlar):
        time.sleep(0.2)
    time.sleep(4)
    pr.terminate()
    pr.wait(timeout=10)
    time.sleep(0.3)
    cikti = "".join(satirlar)
    print("  " + "\n  ".join(cikti.strip().splitlines()[-6:]))
    istek = d.istekler.count("GetSourceScreenshot")
    assert "EN: Lucia" in cikti, "altyazı okunmadı"
    assert istek >= 30, f"OBS'ten çok az kare alındı: {istek}"
    srv.shutdown()
    print(f"  ✓ test_main_obs ({istek} kare alındı; ağ yoksa çeviri hatası normal)")


if __name__ == "__main__":
    test_main_obs()
