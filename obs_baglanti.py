"""OBS WebSocket (v5, OBS 28+) ile konuşan küçük, bağımlılıksız istemci.

OBS'te: Araçlar -> WebSocket Sunucu Ayarları -> "WebSocket sunucusunu etkinleştir".
Varsayılan port 4455.
"""
import base64
import hashlib
import json
import os
import socket
import struct
import threading
import uuid

import cv2
import numpy as np

ALTYAZI_KAYNAK_ADI = "Türkçe Altyazı"


class OBSHatasi(Exception):
    pass


class OBS:
    def __init__(self, host="127.0.0.1", port=4455, sifre="", zaman_asimi=5):
        self.kilit = threading.Lock()
        self._adres = (host, port, sifre, zaman_asimi)
        self._bozuk = False  # bağlantı koptu ya da akış bozuldu: bir sonraki istekte yeniden bağlanılır
        self.yeniden_baglanma = 0
        self._baglan()

    def _baglan(self):
        host, port, sifre, zaman_asimi = self._adres
        try:
            self.sock = socket.create_connection((host, int(port)), timeout=zaman_asimi)
        except OSError:
            raise OBSHatasi(
                "OBS'e bağlanılamadı. OBS açık mı? Araçlar → WebSocket Sunucu Ayarları'nda "
                "'WebSocket sunucusunu etkinleştir' işaretli mi?"
            )
        self.sock.settimeout(zaman_asimi)
        self._tampon = b""
        self._el_sikis(host, port)
        merhaba = self._json_al()
        if merhaba.get("op") != 0:
            raise OBSHatasi("OBS beklenmeyen bir cevap verdi.")
        tanit = {"rpcVersion": 1, "eventSubscriptions": 0}
        dogrulama = merhaba["d"].get("authentication")
        if dogrulama:
            if not sifre:
                raise OBSHatasi("OBS şifre istiyor. 'Bağlantı Bilgilerini Göster'deki şifreyi girin.")
            gizli = base64.b64encode(hashlib.sha256((sifre + dogrulama["salt"]).encode()).digest()).decode()
            tanit["authentication"] = base64.b64encode(
                hashlib.sha256((gizli + dogrulama["challenge"]).encode()).digest()).decode()
        self._json_gonder({"op": 1, "d": tanit})
        try:
            cevap = self._json_al()
        except OBSHatasi:
            raise OBSHatasi("Şifre yanlış. OBS'teki 'Bağlantı Bilgilerini Göster'den tekrar kopyalayın.")
        if cevap.get("op") != 2:
            raise OBSHatasi("Şifre yanlış.")

    # ---------- WebSocket katmanı ----------
    def _el_sikis(self, host, port):
        anahtar = base64.b64encode(os.urandom(16)).decode()
        istek = (
            f"GET / HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {anahtar}\r\nSec-WebSocket-Version: 13\r\n"
            f"Sec-WebSocket-Protocol: obswebsocket.json\r\n\r\n"
        )
        self.sock.sendall(istek.encode())
        while b"\r\n\r\n" not in self._tampon:
            parca = self.sock.recv(4096)
            if not parca:
                raise OBSHatasi("OBS bağlantıyı kapattı.")
            self._tampon += parca
        baslik, self._tampon = self._tampon.split(b"\r\n\r\n", 1)
        if b" 101 " not in baslik.split(b"\r\n")[0]:
            raise OBSHatasi("Bu port OBS WebSocket değil gibi görünüyor.")

    def _oku(self, n):
        while len(self._tampon) < n:
            try:
                parca = self.sock.recv(max(65536, n - len(self._tampon)))
            except socket.timeout:
                raise OBSHatasi("OBS cevap vermedi (zaman aşımı).")
            if not parca:
                raise OBSHatasi("OBS bağlantısı koptu.")
            self._tampon += parca
        veri, self._tampon = self._tampon[:n], self._tampon[n:]
        return veri

    def _cerceve_gonder(self, opcode, yuk):
        bas = bytearray([0x80 | opcode])
        n = len(yuk)
        if n < 126:
            bas.append(0x80 | n)
        elif n < 65536:
            bas.append(0x80 | 126)
            bas += struct.pack(">H", n)
        else:
            bas.append(0x80 | 127)
            bas += struct.pack(">Q", n)
        maske = os.urandom(4)
        bas += maske
        dizi = np.frombuffer(yuk, dtype=np.uint8)
        m = np.frombuffer((maske * (n // 4 + 1))[:n], dtype=np.uint8)
        self.sock.sendall(bytes(bas) + (dizi ^ m).tobytes())

    def _mesaj_al(self):
        parcalar = []
        while True:
            b1, b2 = self._oku(2)
            fin, opcode = b1 & 0x80, b1 & 0x0F
            n = b2 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._oku(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._oku(8))[0]
            maske = self._oku(4) if b2 & 0x80 else None
            yuk = self._oku(n)
            if maske:
                m = np.frombuffer((maske * (n // 4 + 1))[:n], dtype=np.uint8)
                yuk = (np.frombuffer(yuk, dtype=np.uint8) ^ m).tobytes()
            if opcode == 0x8:
                raise OBSHatasi("OBS bağlantıyı kapattı.")
            if opcode == 0x9:
                self._cerceve_gonder(0xA, yuk)
                continue
            if opcode == 0xA:
                continue
            parcalar.append(yuk)
            if fin:
                return b"".join(parcalar)

    def _json_gonder(self, nesne):
        self._cerceve_gonder(0x1, json.dumps(nesne).encode("utf-8"))

    def _json_al(self):
        return json.loads(self._mesaj_al().decode("utf-8"))

    # ---------- OBS istekleri ----------
    def istek(self, tur, veri=None):
        """Bir istek gönderir, cevabını bekler. Bağlantı koparsa ya da OBS bir kez geç cevap verirse (zaman aşımı)
        akışın neresinde kaldığımız belli olmaz; eskiden o andan sonra HER istek başarısız oluyor, yani altyazı
        program yeniden başlatılana kadar tamamen kesiliyordu. Artık bağlantı kapatılır ve bir sonraki istekte
        baştan kurulur (görüntü döngüsü saniyede bir yeniden dener)."""
        with self.kilit:
            if self._bozuk:
                try:
                    self.sock.close()
                except OSError:
                    pass
                self._tampon = b""
                self._baglan()  # olmazsa OBSHatasi: çağıran yeniden dener
                self._bozuk = False
                self.yeniden_baglanma += 1
            iid = uuid.uuid4().hex
            try:
                self._json_gonder({"op": 6, "d": {"requestType": tur, "requestId": iid, "requestData": veri or {}}})
                while True:
                    m = self._json_al()
                    if m.get("op") == 7 and m["d"].get("requestId") == iid:
                        break
            except OBSHatasi:
                self._bozuk = True
                raise
            except (OSError, ValueError, KeyError, TypeError) as e:
                self._bozuk = True
                raise OBSHatasi(f"OBS bağlantısı koptu ({type(e).__name__}).")
            durum = m["d"]["requestStatus"]
            if not durum.get("result"):
                raise OBSHatasi(f"{tur}: {durum.get('comment') or durum.get('code')}")
            return m["d"].get("responseData") or {}

    def kaynaklar(self):
        return self.istek("GetInputList")["inputs"]

    def goruntu(self, kaynak, genislik=None, kalite=90):
        veri = {"sourceName": kaynak, "imageFormat": "jpg", "imageCompressionQuality": kalite}
        if genislik:
            veri["imageWidth"] = int(genislik)
        d = self.istek("GetSourceScreenshot", veri)["imageData"]
        ham = base64.b64decode(d.split(",", 1)[1])
        return cv2.imdecode(np.frombuffer(ham, np.uint8), cv2.IMREAD_COLOR)

    def aktif_sahne(self):
        d = self.istek("GetCurrentProgramScene")
        return d.get("sceneName") or d.get("currentProgramSceneName")

    def altyazi_ekle(self, url, sahne=None, genislik=1920, yukseklik=1080):
        """Türkçe altyazı tarayıcı kaynağını sahneye ekler ve en üste taşır."""
        sahne = sahne or self.aktif_sahne()
        ayar = {"url": url, "width": genislik, "height": yukseklik, "reroute_audio": False}
        adlar = {k["inputName"] for k in self.kaynaklar()}
        if ALTYAZI_KAYNAK_ADI in adlar:
            self.istek("SetInputSettings", {"inputName": ALTYAZI_KAYNAK_ADI, "inputSettings": ayar})
            try:
                oge_id = self.istek("GetSceneItemId", {"sceneName": sahne, "sourceName": ALTYAZI_KAYNAK_ADI})["sceneItemId"]
            except OBSHatasi:
                oge_id = self.istek("CreateSceneItem", {"sceneName": sahne, "sourceName": ALTYAZI_KAYNAK_ADI})["sceneItemId"]
        else:
            oge_id = self.istek("CreateInput", {
                "sceneName": sahne, "inputName": ALTYAZI_KAYNAK_ADI, "inputKind": "browser_source",
                "inputSettings": ayar, "sceneItemEnabled": True,
            })["sceneItemId"]
        ogeler = self.istek("GetSceneItemList", {"sceneName": sahne})["sceneItems"]
        self.istek("SetSceneItemIndex", {"sceneName": sahne, "sceneItemId": oge_id, "sceneItemIndex": len(ogeler) - 1})
        return sahne

    # ---------- ekranlar ve projektör ----------
    def monitorler(self):
        return self.istek("GetMonitorList").get("monitors", [])

    def projektor_ac(self, monitor_index):
        """Program görüntüsünü (oyun + Türkçe altyazı) verilen monitörde tam ekran açar."""
        self.istek("OpenVideoMixProjector", {"videoMixType": "OBS_WEBSOCKET_VIDEO_MIX_TYPE_PROGRAM",
                                             "monitorIndex": int(monitor_index)})

    # ---------- ses (dublaj sırasında oyun sesini kısmak için) ----------
    def ses_al(self, kaynak):
        return float(self.istek("GetInputVolume", {"inputName": kaynak}).get("inputVolumeDb", 0.0))

    def ses_ayarla(self, kaynak, db):
        self.istek("SetInputVolume", {"inputName": kaynak, "inputVolumeDb": max(-100.0, min(26.0, float(db)))})

    def kapat(self):
        try:
            self._cerceve_gonder(0x8, b"")
            self.sock.close()
        except OSError:
            pass
