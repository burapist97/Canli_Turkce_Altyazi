"""OBS Tarayıcı Kaynağı için yerel overlay sunucusu (Server-Sent Events)."""
import json
import queue
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import veri


class Yayinci:
    """Olaylar: ayar, satir {id, alan, en, tr}, temizle {id, alan | hepsi}, bilgi. alan 0 ana altyazı,
    1.. ek çeviri alanları (config ek_bolgeler)."""

    def __init__(self, goruntu_ayar, bolge, ek_bolgeler=None):
        self.istemciler = []
        self.kilit = threading.Lock()
        self.ayar_olayi = self._ayar(goruntu_ayar, bolge, ek_bolgeler)
        self.son_satirlar = {}  # alan -> son gösterilen satır (yeni bağlanan overlay hemen görsün)
        self.son_tam = None  # tüm ekran kipinin son kutuları (yeni bağlanan overlay hemen görsün)
        self.pencere_ac = None  # program ikinci kez açılırsa çağrılır: açık olan kopyanın penceresini öne getirir

    @staticmethod
    def _ayar(goruntu_ayar, bolge, ek_bolgeler):
        # surum: OBS'te açık kalmış eski sürüm sayfası bunu kendi sürümüyle karşılaştırıp kendini yeniler
        return {"tip": "ayar", "surum": veri.SURUM, "bolge": bolge, "ek_bolgeler": ek_bolgeler or [], **goruntu_ayar}

    def ayar_guncelle(self, goruntu_ayar, bolge, ek_bolgeler=None):
        """Ayarlar değişince açık overlay'ler sayfa yenilemeden güncellensin."""
        self.ayar_olayi = self._ayar(goruntu_ayar, bolge, ek_bolgeler)
        self.gonder(self.ayar_olayi)

    @property
    def son_satir(self):
        return self.son_satirlar.get(0)

    def gonder(self, olay):
        alan = olay.get("alan", 0)
        if olay["tip"] == "temizle" and olay.get("hepsi"):
            self.son_satirlar = {}
            self.son_tam = None
        if olay["tip"] == "tam":
            self.son_tam = olay if olay.get("kutular") else None
        if olay["tip"] == "satir" and olay.get("id", 0) >= 0:  # örnek cümle (id < 0) "son satır" sayılmaz
            self.son_satirlar[alan] = olay
        elif olay["tip"] == "temizle" and self.son_satirlar.get(alan, {}).get("id") == olay.get("id"):
            self.son_satirlar.pop(alan, None)
        with self.kilit:
            for q in list(self.istemciler):
                q.put(olay)

    def abone_ol(self):
        q = queue.Queue()
        q.put(self.ayar_olayi)
        for satir in list(self.son_satirlar.values()):
            q.put(satir)
        if self.son_tam:
            q.put(self.son_tam)
        with self.kilit:
            self.istemciler.append(q)
        return q

    def ayril(self, q):
        with self.kilit:
            if q in self.istemciler:
                self.istemciler.remove(q)


def sunucu_baslat(yayinci, port):
    class Isleyici(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            yol = self.path.split("?")[0]
            if yol in ("/", "/overlay.html", "/altyazi_stil.js"):
                # altyazi_stil.js: yazının görünümü (panelin önizlemesiyle ortak kod)
                js = yol.endswith(".js")
                with open(veri.kaynak("altyazi_stil.js" if js else "overlay.html"), "rb") as f:
                    govde = f.read()
                if not js:  # sayfa kendi sürümünü bilsin: program güncellenince açık kalan eski sayfa kendini yeniler
                    govde = govde.replace(b"__SURUM__", veri.SURUM.encode("ascii"))
                self.send_response(200)
                self.send_header("Content-Type", "text/javascript; charset=utf-8" if js else "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(govde)))
                self.send_header("Cache-Control", "no-store")  # program güncellenince OBS eski dosyayı göstermesin
                self.end_headers()
                self.wfile.write(govde)
            elif yol == "/olaylar":
                try:  # olaylar bekletilmeden gitsin (art arda iki küçük paket Windows'ta 40-200 ms bekleyebiliyor)
                    self.connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                except OSError:
                    pass
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                q = yayinci.abone_ol()
                try:
                    while True:
                        try:
                            olay = q.get(timeout=15)
                            paket = "data: " + json.dumps(olay, ensure_ascii=False) + "\n\n"
                        except queue.Empty:
                            paket = ": canli\n\n"  # bağlantıyı açık tut
                        self.wfile.write(paket.encode("utf-8"))
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass
                finally:
                    yayinci.ayril(q)
            else:
                self.send_response(404)
                self.end_headers()

        def do_POST(self):
            # Program zaten açıkken yeniden başlatıldı: ikinci kopya bunu çağırıp kapanır, açık olan öne gelir
            if self.path.split("?")[0] == "/pencere_ac" and yayinci.pencere_ac:
                try:
                    yayinci.pencere_ac()
                except Exception:
                    pass
                govde = b"canli-turkce-altyazi"
                self.send_response(200)
                self.send_header("Content-Length", str(len(govde)))
                self.end_headers()
                self.wfile.write(govde)
            else:
                self.send_response(404)
                self.end_headers()

    try:
        sunucu = ThreadingHTTPServer(("127.0.0.1", port), Isleyici)
    except OSError:
        raise OSError(f"{port} numaralı port başka bir program tarafından kullanılıyor. "
                      "Programın başka bir kopyası açık olabilir; kapatıp tekrar deneyin.")
    sunucu.daemon_threads = True
    threading.Thread(target=sunucu.serve_forever, daemon=True).start()
    return sunucu
