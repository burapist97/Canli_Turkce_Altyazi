"""Hafif doğal ses motoru (Pocket TTS Turkish), GERÇEK modelle uçtan uca. Ses çalınmaz (sessiz oynatıcı).

dogal_ses.DogalSes sunucuyu kendisi başlatır (kaynaktan: hafif_ses/sunucu.py, .venv-ses ortamında; CTA_HAFIF_SES
derlenmiş bir klasörü gösteriyorsa oradaki cta_ses.exe). Test şunlara bakar: sunucu açılıyor mu, örnek hızı
öğreniliyor mu, açılışta ısınma beklemeden kullanılabiliyor mu (seslerin ölçümleri sesler/uyum.json'da hazır),
ölçümler bütün sesleri kapsıyor ve gerçek seslerle tutuyor mu, kadın/erkek sesleri gerçekten farklı mı, üretim
canlıya yetişiyor mu, sunucu bütün sesleri hazırlayabiliyor mu, bilinmeyen ses ve boş metin doğru reddediliyor mu,
kapatınca süreç bitiyor mu.

turkce_yol_denemesi: model ve sesler Türkçe karakterli bir klasördeyken (kurulum klasöründe kullanıcı adı geçer:
"C:/Users/Şükrü/...") sunucu açılıp bütün sesleri hazırlayabiliyor mu. Gerçekten bozuktu: sentencepiece böyle bir
yoldaki dosyayı açamıyor, derlenmiş sunucu model ayarını yanlış kodlamayla okuyordu. Derlenmiş sunucu için
paket/derle.ps1 aynı denemeyi çağırır:  python tests/test_hafif_ses.py --turkce-yol <cta_ses.exe>

Ortam yoksa (paket/hafif_ses/ortam_hazirla.ps1 çalıştırılmamışsa) atlanır.
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

import numpy as np

import yardimci  # noqa: F401

import dogal_ses
import ses_uyum


class _Sessiz:
    def __init__(self):
        self.parcalar = []

    def cal(self, x):
        self.parcalar.append(np.asarray(x, np.float32).copy())

    def bitir(self):
        pass


def _bos_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def turkce_yol_denemesi(komut, model, sesler):
    """Sunucuyu (komut: [python, sunucu.py] ya da [cta_ses.exe]) Türkçe karakterli bir klasördeki model ve seslerle
    başlatır; bütün seslerin hazırlanmasını bekler ve kopyalanan bir sesle üretir. Dönüş: (açılış sn, ses sn)."""
    gecici = tempfile.mkdtemp(prefix="cta_yol_")
    kok = os.path.join(gecici, "Şükrü Öğün ığİ çÇ")
    shutil.copytree(model, os.path.join(kok, "model"))
    shutil.copytree(sesler, os.path.join(kok, "sesler"))
    n = len([a for a in os.listdir(sesler) if os.path.exists(os.path.join(sesler, a, "ses.json"))])
    adres = f"http://127.0.0.1:{_bos_port()}"
    gunluk_yolu = os.path.join(gecici, "sunucu.log")
    gunluk = open(gunluk_yolu, "w", encoding="utf-8")
    surec = subprocess.Popen(komut + ["--model", os.path.join(kok, "model"), "--sesler", os.path.join(kok, "sesler"),
                                      "--port", adres.rsplit(":", 1)[-1]], stdout=gunluk, stderr=subprocess.STDOUT,
                             env=dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8"),
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def gunlugu_oku():
        gunluk.flush()
        with open(gunluk_yolu, encoding="utf-8", errors="replace") as f:
            return f.read()[-1500:]

    try:
        t0, saglik = time.time(), {}
        while time.time() - t0 < 180:
            assert surec.poll() is None, f"ses sunucusu kapandı (kod {surec.returncode}):\n{gunlugu_oku()}"
            try:
                with urllib.request.urlopen(adres + "/health", timeout=2) as r:
                    saglik = json.loads(r.read().decode("utf-8"))
            except OSError:
                saglik = {}
            assert saglik.get("status") != "error", f"model Türkçe karakterli klasörden yüklenemedi: {saglik.get('hata')}"
            if saglik.get("status") == "ok" and saglik.get("hazir_ses") == n:
                break
            time.sleep(0.5)
        assert saglik.get("status") == "ok" and saglik.get("hazir_ses") == n, \
            f"sesler hazırlanamadı ({saglik.get('hazir_ses')}/{n}):\n{gunlugu_oku()}"
        acilis = time.time() - t0
        istek = urllib.request.Request(adres + "/v1/audio/speech", headers={"Content-Type": "application/json"},
                                       data=json.dumps({"input": "Türkçe karakterli klasörden okuyorum.",
                                                        "voice": "sert_erkek", "seed": 3}).encode("utf-8"))
        with urllib.request.urlopen(istek, timeout=60) as r:
            pcm = r.read()
        sure = len(pcm) / 2 / saglik["sample_rate"]
        assert sure > 1.0, f"kopyalanan sesle üretim çok kısa: {sure:.2f} sn"
        return acilis, sure
    finally:
        surec.terminate()
        try:
            surec.wait(10)
        except Exception:
            surec.kill()
        gunluk.close()
        shutil.rmtree(gecici, ignore_errors=True)


def test_hafif_ses():
    onceki = os.environ.pop("CTA_DOGAL_SES_YOK", None)  # bu test gerçek motoru kullanır
    try:
        kurulum = dogal_ses.hafif_kurulumu()
        if not kurulum:
            print("  - atlandı (hafif ses ortamı yok: paket\\hafif_ses\\ortam_hazirla.ps1)")
            return
        assert dogal_ses.motor_sec("otomatik") == "hafif", "hafif motor varken varsayılan o olmalı"
        d = dogal_ses.DogalSes(adres=f"http://127.0.0.1:{_bos_port()}", motor="hafif")
        assert d.motor == "hafif" and len(d.sesler) == 12, [s["id"] for s in d.sesler]
        erkekler = [s for s in d.sesler if s["cinsiyet"] == "erkek"]
        kadinlar = [s for s in d.sesler if s["cinsiyet"] == "kadin"]
        assert len(erkekler) == 7 and len(kadinlar) == 5
        assert (erkekler[0]["ad"], kadinlar[0]["ad"]) == ("Tarık", "Elif"), "ilk sesler modelin hazır sesleri olmalı"
        assert d.ses_esle("erkek1")["id"] == "tarik" and d.ses_esle("kadin2")["id"] == "zeynep"
        try:
            t0 = time.time()
            assert d.baslat(120), d.hata
            acilis = time.time() - t0
            assert d.ornek_hizi == 24000, d.ornek_hizi
            assert d.surec is not None and d.surec.poll() is None
            with urllib.request.urlopen(d.adres + "/health", timeout=3) as r:
                saglik = json.loads(r.read().decode("utf-8"))
            assert saglik["motor"] == "pocket-tts-turkish" and len(saglik["voices"]) == 12, saglik

            # ısınma YOK: seslerin ölçümleri pakette hazır (sesler/uyum.json), model yüklenir yüklenmez okunur
            for _ in range(40):
                if d.isinma_bitti:
                    break
                time.sleep(0.1)
            assert d.isinma_bitti and d.kullanilabilir(), (d.durum, d.hata)
            assert not d.ornekler, "ölçümler pakette hazırken açılışta örnek cümle üretilmemeli"
            uyum = d.uyum_verisi()
            oranlar = {f"{o:g}" for o in ses_uyum.KAYDIRMALAR}
            eksik = [s["id"] for s in d.sesler if set(uyum.get(s["id"], {})) != oranlar]
            assert not eksik, f"uyum.json bu sesleri tam kapsamıyor: {eksik} (paket/hafif_ses/uyum_hazirla.py çalıştırılmalı)"
            assert all(len(o["iz"]) == 192 and 60 < o["perde"] < 420 for ses in uyum.values() for o in ses.values())
            # hazır ölçümlerle ses seçimi: kalın erkek konuşmacıya erkek, ince kadın konuşmacıya kadın sesi
            u = ses_uyum.Uyumlayici(None)
            for s in d.sesler:
                u.hazir_ekle(s["id"], s["cinsiyet"], uyum[s["id"]])
            assert len(u.adaylar) == 12 * len(ses_uyum.KAYDIRMALAR), len(u.adaylar)
            kalin, ince = u.sec(None, 95.0, "erkek"), u.sec(None, 240.0, "kadin")
            assert kalin[0] in {s["id"] for s in erkekler} and abs(u.perde(kalin[0], kalin[1]) - 95) < 12, kalin
            assert ince[0] in {s["id"] for s in kadinlar} and abs(u.perde(ince[0], ince[1]) - 240) < 25, ince

            # sunucu "hazır" der demez okunabilmeli: her cinsiyetin ilk sesi çoktan hazır (ilk tanınan kişiler onları
            # alır); kalan sesler o sırada arka planda hazırlanır ve okuma isteğine yol verir
            ilk = {}
            for ses, metin in ((erkekler[0], "Dur, kıpırdama! Ellerini kaldır."), (kadinlar[0], "Hemen geliyorum, bekle.")):
                d.cal(metin, ses, 1.0, _Sessiz())
                ilk[ses["id"]] = d.son_gecikme_ms
                assert d.son_gecikme_ms < 2000, f"açılışta ilk satır geç başladı: {ses['id']} {d.son_gecikme_ms} ms"

            # sunucu arka planda bütün sesleri hazırlar (kopyalanan 6 ses dahil); hepsi hazırlanabiliyor mu
            hazir = 0
            for _ in range(180):
                with urllib.request.urlopen(d.adres + "/health", timeout=3) as r:
                    hazir = json.loads(r.read().decode("utf-8"))["hazir_ses"]
                if hazir == 12:
                    break
                time.sleep(0.5)
            assert hazir == 12, f"sunucu {hazir}/12 sesi hazırlayabildi (ayrıntı: {d._gunluk_yolu()})"
            hazirlik = time.time() - t0

            # üretim: erkek ve kadın sesi, akışla; canlıya yetişmeli
            sonuc = {}
            for ses, metin in ((erkekler[0], "Arabaya bin, polisler hemen arkamızda!"),
                               (kadinlar[0], "Sakin ol. Kestirme bir yol biliyorum, bana güven."),
                               (next(s for s in d.sesler if s["id"] == "sert_erkek"), "Ne yapıyorsun sen? Hemen silahını indir!")):
                o = _Sessiz()
                t = time.time()
                sure = d.cal(metin, ses, 1.0, o)
                gecen = time.time() - t
                x = np.concatenate(o.parcalar)
                x16 = np.interp(np.arange(0, len(x), d.ornek_hizi / 16000), np.arange(len(x)), x).astype(np.float32)
                sonuc[ses["id"]] = (sure, gecen, ses_uyum.perde_olc(x16), d.son_gecikme_ms)
                assert abs(sure - len(x) / d.ornek_hizi) < 0.05 and 1.2 < sure < 8, (ses["id"], sure)
                assert gecen < sure * 0.9 + 0.5, f"{ses['id']}: üretim canlıya yetişmiyor ({sure:.1f} sn ses {gecen:.1f} sn'de)"
                assert d.son_gecikme_ms < 800, f"{ses['id']}: ilk ses geç geldi ({d.son_gecikme_ms} ms)"
                assert float(np.abs(x).max()) > 0.05, "ses boş geldi"
            perde = {k: v[2] for k, v in sonuc.items()}
            assert perde["elif"] > perde["tarik"] * 1.4, f"kadın sesi erkek sesinden belirgin ince olmalı: {perde}"
            assert perde["sert_erkek"] < 115, f"kalın erkek sesi (Kaan) kalın çıkmalı: {perde}"

            # pakette gelen ölçümler bu seslerin gerçek perdesiyle tutuyor mu (ses ya da model değişti de dosya eski
            # kalmasın; cümleden cümleye tonlama %5-10 oynar)
            for k, olculen in perde.items():
                kayitli = uyum[k]["1"]["perde"]
                assert 0.8 < olculen / kayitli < 1.25, f"{k}: uyum.json {kayitli:.0f} Hz diyor, ses {olculen:.0f} Hz çıktı"

            # bilinmeyen ses ve boş metin: anlaşılır ret (uygulama o satırı Windows sesiyle okur)
            for govde in ({"input": "Merhaba.", "voice": "olmayan_ses"}, {"input": "  ", "voice": "tarik"}):
                try:
                    urllib.request.urlopen(urllib.request.Request(d.adres + "/v1/audio/speech", data=json.dumps(govde).encode(),
                                                                  headers={"Content-Type": "application/json"}), timeout=10)
                    raise AssertionError(f"reddedilmeliydi: {govde}")
                except urllib.error.HTTPError as e:
                    assert e.code == 400, e.code
            surec = d.surec
        finally:
            d.durdur()
        assert surec.poll() is not None, "kapatınca ses sunucusu süreci bitmeli"
        yol_acilis, yol_sure = turkce_yol_denemesi(kurulum["komut"], kurulum["model"], kurulum["sesler"])
        print(f"  ✓ hafif doğal ses: açılış {acilis:.1f} sn, hemen okundu (ilk ses {ilk['tarik']} / {ilk['elif']} ms), "
              f"12 sesin hazırlığı {hazirlik:.0f} sn'de bitti | "
              + " | ".join(f"{k}: {v[0]:.1f} sn ses {v[1]:.1f} sn'de, ilk ses {v[3]} ms, {v[2]:.0f} Hz" for k, v in sonuc.items()))
        print(f"  ✓ hafif doğal ses: Türkçe karakterli klasörden de açıldı ({yol_acilis:.0f} sn'de 12 ses hazır, "
              f"kopyalanan sesle {yol_sure:.1f} sn ses)")
    finally:
        if onceki is not None:
            os.environ["CTA_DOGAL_SES_YOK"] = onceki


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--turkce-yol":  # derle.ps1: derlenmiş sunucu (cta_ses.exe) için
        try:
            _acilis, _sure = turkce_yol_denemesi([os.path.abspath(sys.argv[2])],
                                                 os.path.join(yardimci.PROJE, "modeller", "pocket-tts-turkish"),
                                                 os.path.join(yardimci.PROJE, "hafif_ses", "sesler"))
        except AssertionError as e:
            print(f"[X] {e}")
            sys.exit(1)
        print(f"[OK] Ses sunucusu Turkce karakterli klasordeki modeli acti ({_acilis:.0f} sn'de sesler hazir, "
              f"{_sure:.1f} sn ses uretildi)")
    else:
        test_hafif_ses()
