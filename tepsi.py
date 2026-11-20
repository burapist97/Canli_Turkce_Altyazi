"""Bildirim alanı (saatin yanındaki) simge: pencere KÜÇÜLTÜLÜNCE buraya iner (program çalışmaya devam eder), sağ
tıkla hızlı ayarlar. Pencere kapatılınca (X) program tamamen kapanır.

Simge ve menü Windows'un kendi bileşenleridir (WinForms NotifyIcon; pywebview zaten WinForms penceresi kullanır,
ek kitaplık gerekmez). Menünün içeriği menu_modeli() ile düz Python verisi olarak üretilir (testlerde pencere
açmadan denenebilsin); Tepsi sınıfı onu Windows menüsüne çevirir.
"""
import os
import sys
import threading

import veri

BOYUTLAR = (("Küçük", 32), ("Orta", 44), ("Büyük", 56), ("Çok büyük", 72))
ARKA_PLANLAR = (("Yok", 0.0), ("Yarı saydam", 0.5), ("Koyu", 0.85))
KONUMLAR = (("Altyazının yerinde", {"konum": "orijinal"}),
            ("Üstte", {"konum": "serbest", "konum_x": 0.5, "konum_y": 0.1}),
            ("Ortada", {"konum": "serbest", "konum_x": 0.5, "konum_y": 0.5}),
            ("Altta", {"konum": "serbest", "konum_x": 0.5, "konum_y": 0.9}))


def simge_yolu():
    for yol in (veri.kaynak("uygulama.ico"), os.path.join(veri.KLASOR, "paket", "gorseller", "uygulama.ico")):
        if os.path.exists(yol):
            return yol
    return ""


def calisiyor_mu(uyg):
    return bool(uyg.motor and uyg.motor.durum in ("basliyor", "calisiyor"))


def menu_modeli(uyg):
    """[{ad, eylem, isaretli, kalin, alt:[...]} | {ayrac: True}] — eylem: parametresiz çağrılır (arka planda)."""
    g = uyg.ayar["goruntu"]
    d = uyg.ayar.get("dublaj", {})
    calisiyor = calisiyor_mu(uyg)

    def gorunum(**v):
        return lambda: uyg.gorunum_kaydet({**v, "ornek": True})

    def mod(yazi, ses):
        # ikisi de kapatılamaz: en az biri açık kalır
        return lambda: uyg.mod_sec({"mod": "ikisi" if (yazi and ses) else "ses" if ses else "altyazi"})

    yazi_acik, ses_acik = g.get("altyazi_goster", True), bool(d.get("acik"))
    konum_simdi = g.get("konum", "orijinal"), round(float(g.get("konum_y", 0.85)), 2)
    return [
        {"ad": "Paneli aç", "eylem": "pencere", "kalin": True},
        {"ad": "Altyazıyı durdur" if calisiyor else "Altyazıyı başlat",
         "eylem": (lambda: uyg.motor_durdur(None)) if calisiyor else (lambda: uyg.motor_baslat(None))},
        {"ayrac": True},
        {"ad": "Türkçe yazı", "isaretli": yazi_acik, "eylem": mod(not yazi_acik, ses_acik or yazi_acik)},
        {"ad": "Türkçe seslendirme" + (" (geliştiriliyor)" if veri.MAGAZA else ""), "isaretli": ses_acik, "eylem": mod(yazi_acik or ses_acik, not ses_acik)},
        {"ad": "İngilizcesini de göster", "isaretli": bool(g.get("ingilizce_goster")),
         "eylem": gorunum(ingilizce_goster=not g.get("ingilizce_goster"))},
        {"ayrac": True},
        {"ad": "Yazı boyutu", "alt": [{"ad": ad, "isaretli": int(g.get("yazi_boyutu", 44)) == px,
                                       "eylem": gorunum(yazi_boyutu=px)} for ad, px in BOYUTLAR]},
        {"ad": "Görünüm", "alt": [{"ad": h["ad"], "isaretli": all(g.get(k) == v for k, v in h["ayar"].items()),
                                   "eylem": gorunum(**h["ayar"])} for h in veri.HAZIR_GORUNUMLER]},
        {"ad": "Arka plan", "alt": [{"ad": ad, "isaretli": abs(float(g.get("kutu_saydamlik", 0)) - s) < 0.03,
                                     "eylem": gorunum(kutu_saydamlik=s)} for ad, s in ARKA_PLANLAR]},
        {"ad": "Konum", "alt": [{"ad": ad, "isaretli": (a["konum"], a.get("konum_y", konum_simdi[1])) == konum_simdi
                                 if a["konum"] == "serbest" else konum_simdi[0] == "orijinal",
                                 "eylem": gorunum(**a)} for ad, a in KONUMLAR]},
        {"ayrac": True},
        {"ad": "Çıkış", "eylem": "cikis"},
    ]


class Tepsi:
    def __init__(self, uyg, pencere):
        self.uyg = uyg
        self.pencere = pencere
        self.ikon = None
        self.cikiliyor = False
        self._bilgi_gosterildi = False

    # ---------- kurulum (pencere gösterildikten sonra çağrılır) ----------
    def kur(self):
        if not sys.platform.startswith("win") or not simge_yolu():
            return False
        try:
            from System import Action
            self.pencere.native.Invoke(Action(self._kur))
            return True
        except Exception as e:
            print(f"[tepsi] simge kurulamadı: {e}", flush=True)
            return False

    def _kur(self):
        from System.Drawing import Icon
        from System.Windows.Forms import ContextMenuStrip, MouseButtons, NotifyIcon

        self.ikon = NotifyIcon()
        self.ikon.Icon = Icon(simge_yolu())
        self.ikon.Text = veri.UYGULAMA_ADI
        menu = ContextMenuStrip()
        menu.Opening += lambda s, e: self._menuyu_doldur(menu)
        self._menuyu_doldur(menu)
        self.ikon.ContextMenuStrip = menu

        def tiklandi(s, e):
            if e.Button == MouseButtons.Left:
                self.pencereyi_goster()

        self.ikon.MouseClick += tiklandi
        self.ikon.Visible = True

    def _menuyu_doldur(self, menu):
        from System.Drawing import FontStyle, Font
        from System.Windows.Forms import ToolStripMenuItem, ToolStripSeparator

        def ekle(hedef, ogeler):
            for o in ogeler:
                if o.get("ayrac"):
                    hedef.Add(ToolStripSeparator())
                    continue
                m = ToolStripMenuItem(o["ad"])
                m.Checked = bool(o.get("isaretli"))
                if o.get("kalin"):
                    m.Font = Font(m.Font, FontStyle.Bold)
                if o.get("alt"):
                    ekle(m.DropDownItems, o["alt"])
                else:
                    m.Click += (lambda eylem: lambda s, e: self._calistir(eylem))(o["eylem"])
                hedef.Add(m)

        menu.Items.Clear()
        try:
            ekle(menu.Items, menu_modeli(self.uyg))
        except Exception as e:
            print(f"[tepsi] menü kurulamadı: {e}", flush=True)
        self.ikon.Text = veri.UYGULAMA_ADI + (" — çalışıyor" if calisiyor_mu(self.uyg) else "")

    def _calistir(self, eylem):
        if eylem == "pencere":
            return self.pencereyi_goster()
        if eylem == "cikis":
            return self.cik()

        def is_parcasi():  # arayüz iş parçacığını tutmasın (motoru başlatmak pencere açar, saniyeler sürebilir)
            try:
                eylem()
            except Exception as e:
                self.bilgi(str(e))

        threading.Thread(target=is_parcasi, daemon=True).start()

    # ---------- pencere ----------
    def pencereyi_goster(self):
        def goster():
            try:
                self.pencere.show()
                self.pencere.restore()
                from System import Action
                self.pencere.native.Invoke(Action(self.pencere.native.Activate))
            except Exception as e:
                print(f"[tepsi] pencere gösterilemedi: {e}", flush=True)

        threading.Thread(target=goster, daemon=True).start()

    def kucultuldu(self):
        """Pencere küçültüldü (–): ayar açıksa görev çubuğundan kalkıp simgeye iner; program çalışmaya devam eder."""
        if self.cikiliyor or not self.ikon or not self.uyg.ayar.get("uygulama", {}).get("tepsiye_kucult", True):
            return
        threading.Thread(target=self.pencere.hide, daemon=True).start()
        if not self._bilgi_gosterildi and not self.uyg.ayar.get("uygulama", {}).get("tepsi_bilgisi_gosterildi"):
            self._bilgi_gosterildi = True
            self.bilgi("Arka planda çalışmaya devam ediyor. Açmak için bu simgeye tıklayın; hızlı ayarlar için sağ tıklayın.")
            self.uyg.ayar.setdefault("uygulama", {})["tepsi_bilgisi_gosterildi"] = True
            try:
                veri.ayar_kaydet(self.uyg.ayar)
            except OSError:
                pass

    def kapatiliyor(self):
        """Pencerenin kapatma düğmesi (X): program TAMAMEN kapanır — altyazı durur, oyun üstü pencere ve ses
        sunucuları kapanır, simge kalkar. (2.7.0-2.7.1'de pencere kapanınca çeviri arkada sürüyordu: kullanıcı
        "kapalı ama hâlâ çeviriyor" dedi.) Arka planda çalışsın isteyen pencereyi küçültür."""
        self.cikiliyor = True
        try:
            self.uyg.kapat()
        except Exception as e:
            print(f"[kapanış] {e}", flush=True)
        self.kaldir()
        return True

    def bilgi(self, metin):
        try:
            from System.Windows.Forms import ToolTipIcon
            self.ikon.ShowBalloonTip(5000, veri.UYGULAMA_ADI, metin, ToolTipIcon.Info)
        except Exception:
            pass

    def kaldir(self):
        try:
            if self.ikon:
                self.ikon.Visible = False
                self.ikon.Dispose()
        except Exception:
            pass
        self.ikon = None

    def cik(self):
        self.cikiliyor = True
        threading.Thread(target=self.pencere.destroy, daemon=True).start()
