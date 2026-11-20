"""OBS'i kullanıcıya hiçbir şey sormadan bulmak için yardımcılar.

- OBS kurulu mu, açık mı?
- WebSocket sunucusu açık mı, şifresi ne? (OBS'in kendi ayar dosyasından okunur;
  kullanıcı şifre kopyalayıp yapıştırmak zorunda kalmaz)
- Hangi kaynak capture card?

Yalnızca OKUR, OBS'in dosyalarına yazmaz.
"""
import configparser
import json
import os
import subprocess
import sys

OBS_INDIRME = "https://obsproject.com/download"


def _appdata():
    return os.environ.get("APPDATA") or os.path.expanduser("~/.config")


def obs_kurulu_mu():
    if not sys.platform.startswith("win"):
        return True
    try:
        import winreg
        for kok in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(kok, r"SOFTWARE\OBS Studio") as k:
                    if winreg.QueryValue(k, None):
                        return True
            except OSError:
                pass
    except ImportError:
        pass
    adaylar = [os.path.join(os.environ.get(v, ""), "obs-studio", "bin", "64bit", "obs64.exe")
               for v in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)")]
    return any(os.path.exists(a) for a in adaylar) or os.path.isdir(os.path.join(_appdata(), "obs-studio"))


def obs_acik_mi():
    if not sys.platform.startswith("win"):
        return None  # bilinmiyor
    try:
        cikti = subprocess.run(["tasklist", "/FI", "IMAGENAME eq obs64.exe", "/NH", "/FO", "CSV"],
                               capture_output=True, text=True, timeout=5,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
        return "obs64.exe" in cikti.lower()
    except Exception:
        return None


def websocket_ayari(obs_klasoru=None):
    """{'etkin': bool|None, 'port': int, 'sifre': str, 'sifre_gerekli': bool} ya da None (bulunamadı).
    obs-websocket 5.0-5.4: plugin_config/obs-websocket/config.json
    obs-websocket 5.5+ (OBS 31+): user.ini / global.ini içindeki [OBSWebSocket] bölümü"""
    kok = obs_klasoru or os.path.join(_appdata(), "obs-studio")
    bulunan = None
    for ini in ("user.ini", "global.ini"):
        yol = os.path.join(kok, ini)
        if not os.path.exists(yol):
            continue
        c = configparser.ConfigParser(interpolation=None, strict=False)
        c.optionxform = str
        try:
            c.read(yol, encoding="utf-8-sig")
        except (configparser.Error, OSError, UnicodeDecodeError):
            continue
        if c.has_section("OBSWebSocket"):
            s = c["OBSWebSocket"]
            bulunan = {
                "etkin": s.get("ServerEnabled", "false").lower() == "true",
                "port": int(s.get("ServerPort", "4455") or 4455),
                "sifre": s.get("ServerPassword", ""),
                "sifre_gerekli": s.get("AuthRequired", "true").lower() == "true",
            }
            break
    if bulunan is None:
        yol = os.path.join(kok, "plugin_config", "obs-websocket", "config.json")
        if os.path.exists(yol):
            try:
                with open(yol, encoding="utf-8-sig") as f:
                    j = json.load(f)
                bulunan = {
                    "etkin": bool(j.get("server_enabled")),
                    "port": int(j.get("server_port") or 4455),
                    "sifre": j.get("server_password", ""),
                    "sifre_gerekli": bool(j.get("auth_required", True)),
                }
            except (ValueError, OSError):
                pass
    if bulunan and not bulunan["sifre_gerekli"]:
        bulunan["sifre"] = ""
    return bulunan


# Kaynak adı / türüne göre capture card tahmini
_OLUMLU = ("capture", "yakalama", "elgato", "avermedia", "hdmi", "game", "oyun", "cam link 4k", "usb video",
           "ugreen", "razer ripsaw", "magewell", "konsol", "ps5", "xbox", "switch")
_OLUMSUZ = ("facecam", "webcam", "kamera", "camera", "face", "yüz", "c920", "c922", "brio", "logitech")


def capture_card_puani(ad, tur):
    a = ad.lower()
    puan = 0
    if tur in ("dshow_input", "av_capture_input", "v4l2_input"):
        puan += 2
    if tur in ("game_capture", "window_capture", "monitor_capture"):
        puan += 1
    if any(k in a for k in _OLUMLU):
        puan += 3
    if any(k in a for k in _OLUMSUZ):
        puan -= 4
    return puan
