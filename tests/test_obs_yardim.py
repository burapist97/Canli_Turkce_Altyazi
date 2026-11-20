"""OBS ayar dosyasından WebSocket şifresini okuma (eski ve yeni OBS biçimleri) ve capture card tahmini."""
import json
import os
import tempfile

import yardimci  # noqa: F401

import obs_yardim


def test_obs_yardim():
    # OBS 31+ (obs-websocket 5.5+): user.ini, BOM'lu
    k = tempfile.mkdtemp()
    with open(os.path.join(k, "user.ini"), "w", encoding="utf-8-sig") as f:
        f.write("[General]\nName=Yayın\n\n[OBSWebSocket]\nFirstLoad=false\nServerEnabled=true\nServerPort=4456\n"
                "AlertsEnabled=false\nAuthRequired=true\nServerPassword=Ab%cD=12\n")
    a = obs_yardim.websocket_ayari(k)
    assert a == {"etkin": True, "port": 4456, "sifre": "Ab%cD=12", "sifre_gerekli": True}, a

    # OBS 28-30: plugin_config/obs-websocket/config.json
    k = tempfile.mkdtemp()
    os.makedirs(os.path.join(k, "plugin_config", "obs-websocket"))
    with open(os.path.join(k, "plugin_config", "obs-websocket", "config.json"), "w", encoding="utf-8") as f:
        json.dump({"alerts_enabled": False, "auth_required": False, "first_load": False,
                   "server_enabled": False, "server_password": "xyz", "server_port": 4455}, f)
    a = obs_yardim.websocket_ayari(k)
    assert a == {"etkin": False, "port": 4455, "sifre": "", "sifre_gerekli": False}, a

    assert obs_yardim.websocket_ayari(tempfile.mkdtemp()) is None

    p = obs_yardim.capture_card_puani
    assert p("Elgato HD60 X", "dshow_input") > p("Facecam", "dshow_input")
    assert p("Video Yakalama Aygıtı", "dshow_input") > 0
    assert p("Logitech C920", "dshow_input") < 0
    print("  ✓ test_obs_yardim")


if __name__ == "__main__":
    test_obs_yardim()
