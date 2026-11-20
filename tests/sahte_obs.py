"""Test için sahte obs-websocket v5 sunucusu (stdlib)."""
import base64, hashlib, json, os, socket, socketserver, struct, threading
import cv2
from yardimci import yuz_karesi

SIFRE = "test123"
SALT, CHALLENGE = "tuz123", "meydan456"


class Durum:
    def __init__(self, kare_fn):
        self.kare_fn = kare_fn  # () -> BGR görüntü
        self.inputs = [
            {"inputName": "Facecam", "inputKind": "dshow_input"},
            {"inputName": "Capture Card", "inputKind": "dshow_input"},
            {"inputName": "Mikrofon", "inputKind": "wasapi_input_capture"},
        ]
        self.sahne = "Yayın"
        self.ogeler = [{"sceneItemId": 1, "sourceName": "Capture Card", "sceneItemIndex": 0},
                       {"sceneItemId": 2, "sourceName": "Facecam", "sceneItemIndex": 1}]
        self.ayarlar = {}
        self.istekler = []
        self.projektorler = []
        self.ses = {}
        self.ses_gecmisi = []
        self.dugmeler = []  # (kaynak, düğme): tarayıcı kaynağını yenileme gibi


def handler_yap(durum):
    class H(socketserver.BaseRequestHandler):
        def oku(self, n):
            while len(self.buf) < n:
                p = self.request.recv(65536)
                if not p: raise ConnectionError
                self.buf += p
            v, self.buf = self.buf[:n], self.buf[n:]
            return v

        def gonder(self, obj):
            y = json.dumps(obj).encode()
            n = len(y)
            bas = bytearray([0x81])
            if n < 126: bas.append(n)
            elif n < 65536: bas.append(126); bas += struct.pack(">H", n)
            else: bas.append(127); bas += struct.pack(">Q", n)
            self.request.sendall(bytes(bas) + y)

        def al(self):
            b1, b2 = self.oku(2)
            n = b2 & 0x7F
            if n == 126: n = struct.unpack(">H", self.oku(2))[0]
            elif n == 127: n = struct.unpack(">Q", self.oku(8))[0]
            m = self.oku(4)
            y = bytes(c ^ m[i % 4] for i, c in enumerate(self.oku(n)))
            if b1 & 0x0F == 8: raise ConnectionError
            return json.loads(y)

        def handle(self):
            self.buf = b""
            while b"\r\n\r\n" not in self.buf:
                self.buf += self.request.recv(4096)
            bas, self.buf = self.buf.split(b"\r\n\r\n", 1)
            key = [l.split(b": ")[1] for l in bas.split(b"\r\n") if l.lower().startswith(b"sec-websocket-key")][0]
            acc = base64.b64encode(hashlib.sha1(key + b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11").digest())
            self.request.sendall(b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: " + acc + b"\r\nSec-WebSocket-Protocol: obswebsocket.json\r\n\r\n")
            self.gonder({"op": 0, "d": {"obsWebSocketVersion": "5.5.0", "rpcVersion": 1,
                                        "authentication": {"challenge": CHALLENGE, "salt": SALT}}})
            try:
                tanit = self.al()
                gizli = base64.b64encode(hashlib.sha256((SIFRE + SALT).encode()).digest()).decode()
                beklenen = base64.b64encode(hashlib.sha256((gizli + CHALLENGE).encode()).digest()).decode()
                if tanit["d"].get("authentication") != beklenen:
                    self.request.sendall(b"\x88\x02\x0f\xa8"); return
                self.gonder({"op": 2, "d": {"negotiatedRpcVersion": 1}})
                while True:
                    m = self.al()["d"]
                    tur, veri = m["requestType"], m.get("requestData", {})
                    durum.istekler.append(tur)
                    ok, cevap, yorum = True, {}, None
                    if tur == "GetInputList":
                        cevap = {"inputs": durum.inputs}
                    elif tur == "GetSourceScreenshot":
                        ad = veri["sourceName"]
                        if ad not in [i["inputName"] for i in durum.inputs]:
                            ok, yorum = False, "No source was found"
                        else:
                            img = durum.kare_fn() if ad == "Capture Card" else (
                                yuz_karesi() if ad == "Facecam" else None)
                            if img is None:
                                ok, yorum = False, "Source is not a video source"
                            else:
                                if veri.get("imageWidth"):
                                    w = veri["imageWidth"]; img = cv2.resize(img, (w, int(img.shape[0] * w / img.shape[1])))
                                _, j = cv2.imencode(".jpg", img)
                                cevap = {"imageData": "data:image/jpg;base64," + base64.b64encode(j.tobytes()).decode()}
                    elif tur == "GetCurrentProgramScene":
                        cevap = {"sceneName": durum.sahne, "currentProgramSceneName": durum.sahne}
                    elif tur == "CreateInput":
                        durum.inputs.append({"inputName": veri["inputName"], "inputKind": veri["inputKind"]})
                        durum.ayarlar[veri["inputName"]] = veri["inputSettings"]
                        yid = max(o["sceneItemId"] for o in durum.ogeler) + 1
                        durum.ogeler.insert(0, {"sceneItemId": yid, "sourceName": veri["inputName"]})
                        cevap = {"sceneItemId": yid}
                    elif tur == "SetInputSettings":
                        durum.ayarlar[veri["inputName"]] = veri["inputSettings"]
                    elif tur == "GetSceneItemId":
                        e = [o for o in durum.ogeler if o["sourceName"] == veri["sourceName"]]
                        if e: cevap = {"sceneItemId": e[0]["sceneItemId"]}
                        else: ok, yorum = False, "No scene items were found"
                    elif tur == "CreateSceneItem":
                        yid = max(o["sceneItemId"] for o in durum.ogeler) + 1
                        durum.ogeler.insert(0, {"sceneItemId": yid, "sourceName": veri["sourceName"]})
                        cevap = {"sceneItemId": yid}
                    elif tur == "GetSceneItemList":
                        cevap = {"sceneItems": [dict(o, sceneItemIndex=i) for i, o in enumerate(durum.ogeler)]}
                    elif tur == "SetSceneItemIndex":
                        o = [x for x in durum.ogeler if x["sceneItemId"] == veri["sceneItemId"]][0]
                        durum.ogeler.remove(o); durum.ogeler.insert(veri["sceneItemIndex"], o)
                    elif tur == "GetMonitorList":
                        cevap = {"monitors": [
                            {"monitorIndex": 0, "monitorName": "DELL U2419H(0)", "monitorWidth": 1920, "monitorHeight": 1080, "monitorPositionX": 0, "monitorPositionY": 0},
                            {"monitorIndex": 1, "monitorName": "LG ULTRAGEAR(1)", "monitorWidth": 2560, "monitorHeight": 1440, "monitorPositionX": 1920, "monitorPositionY": 0}]}
                    elif tur == "OpenVideoMixProjector":
                        durum.projektorler.append(veri)
                    elif tur == "GetInputVolume":
                        cevap = {"inputVolumeDb": durum.ses.get(veri["inputName"], 0.0), "inputVolumeMul": 1.0}
                    elif tur == "SetInputVolume":
                        durum.ses[veri["inputName"]] = veri["inputVolumeDb"]
                        durum.ses_gecmisi.append(veri["inputVolumeDb"])
                    elif tur == "PressInputPropertiesButton":
                        if veri["inputName"] in [i["inputName"] for i in durum.inputs]:
                            durum.dugmeler.append((veri["inputName"], veri["propertyName"]))
                        else:
                            ok, yorum = False, "No source was found"
                    else:
                        ok, yorum = False, "Unknown request"
                    self.gonder({"op": 7, "d": {"requestType": tur, "requestId": m["requestId"],
                                                "requestStatus": {"result": ok, "code": 100 if ok else 600, "comment": yorum},
                                                "responseData": cevap}})
            except (ConnectionError, OSError):
                pass
    return H


def baslat(kare_fn, port=4455):
    d = Durum(kare_fn)
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    s = socketserver.ThreadingTCPServer(("127.0.0.1", port), handler_yap(d))
    s.daemon_threads = True
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s, d
