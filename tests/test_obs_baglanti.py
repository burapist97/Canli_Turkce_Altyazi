"""OBS WebSocket istemcisi: kimlik doğrulama, kaynak listesi, görüntü, altyazı katmanı ekleme."""
import yardimci  # noqa: F401
from yardimci import ornek_kare

import sahte_obs
from obs_baglanti import ALTYAZI_KAYNAK_ADI, OBS, OBSHatasi


def test_obs(port=4461):
    kare = ornek_kare()
    srv, d = sahte_obs.baslat(lambda: kare, port)
    for sifre, beklenen in (("", "şifre istiyor"), ("yanlis", "yanlış")):
        try:
            OBS(port=port, sifre=sifre)
            raise AssertionError("yanlış şifreyle bağlandı")
        except OBSHatasi as e:
            assert beklenen in str(e).lower(), e
    try:
        OBS(port=port + 50)
        raise AssertionError("kapalı porta bağlandı")
    except OBSHatasi:
        pass

    o = OBS(port=port, sifre=sahte_obs.SIFRE)
    assert [k["inputName"] for k in o.kaynaklar()] == ["Facecam", "Capture Card", "Mikrofon"]
    assert o.goruntu("Capture Card").shape == (1080, 1920, 3)
    assert o.goruntu("Facecam", 320).shape[1] == 320
    try:
        o.goruntu("Mikrofon", 320)
        raise AssertionError("ses kaynağından görüntü alındı")
    except OBSHatasi:
        pass
    assert o.altyazi_ekle("http://127.0.0.1:8765") == "Yayın"
    o.altyazi_ekle("http://127.0.0.1:8765")  # ikinci kez: kopya oluşturmamalı
    adlar = [x["sourceName"] for x in d.ogeler]
    assert adlar.count(ALTYAZI_KAYNAK_ADI) == 1 and adlar[-1] == ALTYAZI_KAYNAK_ADI, adlar
    # bağlantı koparsa (OBS yeniden başladı, bir an cevap vermedi): o istek hata verir, sonraki yeniden bağlanır
    o.sock.close()
    try:
        o.kaynaklar()
        raise AssertionError("kopuk bağlantıda hata bekleniyordu")
    except OBSHatasi:
        pass
    assert len(o.kaynaklar()) >= 3 and o.yeniden_baglanma == 1, o.yeniden_baglanma
    assert o.goruntu("Capture Card").shape[:2] == (1080, 1920)
    o.kapat()
    srv.shutdown()
    print("  ✓ test_obs (kopan bağlantı kendiliğinden yeniden kuruldu)")


if __name__ == "__main__":
    test_obs()
