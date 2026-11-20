"""Microsoft Store görselleri: 8 tanıtım karesi (1920x1080), 16:9 hero, 9:16 poster, 1:1 kutu görseli.

  .venv\\Scripts\\python.exe magaza\\gorsel_uret.py      -> magaza\\gorseller\\*.png

Tasarım: her kare tek bir fikir (büyük başlık + kısa açıklama + tek görsel), koyu zemin, logonun camgöbeği-mor geçişi.
Sahneler soyuttur (odak dışı ışıklar, siluetler): marka, gerçek film/oyun görüntüsü ya da karakter adı YOK.
Altyazılar uygulamanın kendi koduyla (altyazi_stil.js + veri.HAZIR_GORUNUMLER) çizilir; Türkçeleri hazır çevirinin
(OPUS-MT) bu cümlelere verdiği gerçek çıktıdır (2026-11-21'de alındı).
Arayüz kareleri gerçek arayüzdür (Store sürümü görünümüyle): sahte ekranla, geçici ayar klasörüyle (gerçek ayarlara
dokunmaz); ham hâlleri magaza\\gorseller\\arayuz\\ klasörüne yazılır. Program açıksa: CTA_SES_KAPISI=38777.
"""
import base64
import html
import json
import os
import random
import sys
import tempfile
import time

KLASOR = os.path.dirname(os.path.abspath(__file__))
PROJE = os.path.dirname(KLASOR)
CIKTI = os.path.join(KLASOR, "gorseller")
ARAYUZ = os.path.join(CIKTI, "arayuz")
os.makedirs(ARAYUZ, exist_ok=True)
os.environ["CTA_VERI"] = tempfile.mkdtemp(prefix="cta_magaza_")
sys.path[:0] = [PROJE, os.path.join(PROJE, "tests")]

import veri  # noqa: E402  (CTA_VERI ayarlandıktan sonra)

HAZIR = {g["id"]: g["ayar"] for g in veri.HAZIR_GORUNUMLER}
STIL_JS = open(os.path.join(PROJE, "altyazi_stil.js"), encoding="utf-8").read()


def _veri_uri(yol):
    return "data:image/png;base64," + base64.b64encode(open(yol, "rb").read()).decode()


LOGO = _veri_uri(os.path.join(PROJE, "paket", "gorseller", "simge_1024.png"))

# İngilizce -> hazır çevirinin gerçek çıktısı
CUMLE = {
    "dun": ("Where were you last night?", "Dün gece neredeydin?"),
    "araba": ("Get in the car. They're right behind us!", "Arabaya bin. Tam arkamızdalar!"),
    "gunes": ("We have to leave before sunrise.", "Güneş doğmadan gitmeliyiz."),
    "kestirme": ("Trust me, I know a shortcut.", "Güven bana, kestirme bir yol biliyorum."),
    "kolay": ("I never said it would be easy.", "Kolay olacağını hiç söylemedim."),
    "sessiz": ("Stay close and don't make a sound.", "Yakın durun ve ses çıkarmayın."),
}

# ---------------------------------------------------------------- ortak görünüm
GREN = ("url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='260' height='260'>"
        "<filter id='n'><feTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='2' stitchTiles='stitch'/>"
        "<feColorMatrix values='0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 0 .55 0'/></filter>"
        "<rect width='100%' height='100%' filter='url(%23n)'/></svg>\")")

TEMEL_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
html,body{overflow:hidden}
body{position:relative;background:#07070b;color:#f4f3fa;font-family:'Segoe UI',sans-serif;-webkit-font-smoothing:antialiased}
.ortam{position:absolute;inset:0;background:
  radial-gradient(1000px 680px at 92% 4%,rgba(192,77,255,.17),transparent 70%),
  radial-gradient(1000px 700px at 2% 104%,rgba(46,240,255,.11),transparent 70%)}
.gren{position:absolute;inset:0;background-image:__GREN__;opacity:.06;mix-blend-mode:overlay;pointer-events:none;z-index:50}
.ust{font-size:21px;font-weight:600;letter-spacing:.26em;margin-bottom:30px;
  background:linear-gradient(90deg,#2ef0ff,#c04dff);-webkit-background-clip:text;background-clip:text;color:transparent;display:inline-block}
.baslik{font-size:86px;font-weight:700;letter-spacing:-.032em;line-height:1.03}
.renkli{background:linear-gradient(90deg,#2ef0ff 0%,#8f7bff 55%,#c04dff 100%);-webkit-background-clip:text;background-clip:text;color:transparent}
.aciklama{font-size:29px;line-height:1.5;color:#a3a0bb;margin-top:32px}
.aciklama b{color:#e6e4f2;font-weight:600}
.marka{position:absolute;left:120px;bottom:60px;display:flex;align-items:center;gap:14px;font-size:21px;font-weight:600;color:#cfcde0;z-index:40}
.marka img{width:38px;height:38px;border-radius:9px}
.cip{display:inline-flex;align-items:center;gap:10px;padding:11px 22px;border-radius:999px;border:1px solid rgba(255,255,255,.12);
  background:rgba(255,255,255,.04);font-size:22px;color:#d4d2e4;white-space:nowrap}
.cip i{width:8px;height:8px;border-radius:50%;background:linear-gradient(135deg,#2ef0ff,#c04dff)}
/* sahne: kapsayıcı genişliğine göre ölçeklenir (cqw) */
.sahne{position:absolute;overflow:hidden;container-type:inline-size;border-radius:22px;background:#000;
  box-shadow:0 60px 140px -30px rgba(0,0,0,.85),0 0 0 1px rgba(255,255,255,.07)}
.sahne.tam{inset:0;border-radius:0;box-shadow:none}
.sahne>.k{position:absolute;inset:0}
.bokeh{position:absolute;border-radius:50%;transform:translate(-50%,-50%);mix-blend-mode:screen}
.figur{position:absolute;display:block}
.hud{position:absolute;border:.14cqw solid rgba(255,255,255,.55)}
.altyazi{position:absolute;left:5%;right:5%;bottom:7%;text-align:center;z-index:5}
.kose{position:absolute;z-index:6;border-style:solid;border-width:0}
.etiket{position:absolute;left:3.4cqw;top:3.4cqw;z-index:7;padding:.8cqw 2.2cqw;border-radius:99px;font-size:3.6cqw;font-weight:600;
  color:#fff;background:rgba(10,10,16,.62);border:1px solid rgba(255,255,255,.14);backdrop-filter:blur(6px)}
.pencere{position:absolute;border-radius:14px;overflow:hidden;background:#0b0b10;
  box-shadow:0 60px 140px -30px rgba(0,0,0,.9),0 0 0 1px rgba(255,255,255,.09)}
.pencere .cubuk{height:40px;background:#16161d;display:flex;align-items:center;gap:10px;padding:0 0 0 16px;font-size:14px;color:#c9c7d6}
.pencere .cubuk img{width:18px;height:18px;border-radius:4px}
.pencere .cubuk span.d{margin-left:auto;display:flex}
.pencere .cubuk span.d b{width:46px;text-align:center;font-weight:400;color:#9a98a8;font-size:15px}
.pencere > img{display:block;width:100%}
"""

SAYFA_JS = r"""
(function () {
  function olcek(el) { var s = el.closest('.sahne'); return s.clientWidth / 1920; }
  var alanlar = document.querySelectorAll('.altyazi');
  for (var i = 0; i < alanlar.length; i++) {
    var a = alanlar[i], k = olcek(a), ayar = JSON.parse(a.dataset.stil);
    var u = function (px) { return (px * k).toFixed(2) + 'px'; };
    var el = AltyaziStil.kur(a);
    AltyaziStil.uygula(el, ayar, u, +a.dataset.boyut);
    AltyaziStil.yaz(el, a.dataset.tr, a.dataset.en || '', ayar);
    if (!a.dataset.en) el.en.style.display = 'none';
    if (a.classList.contains('tara')) {
      // logodaki köşe çizgileri: program bu alanı okuyor
      var s = a.closest('.sahne'), sr = s.getBoundingClientRect(), r = el.govde.getBoundingClientRect(), W = s.clientWidth;
      var p = 0.022 * W, b = 0.034 * W, t = Math.max(2, 0.0034 * W);
      var konum = [['left', 'top', '#2ef0ff'], ['right', 'top', '#c04dff'], ['left', 'bottom', '#2ef0ff'], ['right', 'bottom', '#c04dff']];
      for (var j = 0; j < 4; j++) {
        var d = document.createElement('div'), y = konum[j];
        d.className = 'kose';
        d.style.width = b + 'px'; d.style.height = b + 'px';
        d.style.borderColor = y[2];
        d.style.filter = 'drop-shadow(0 0 ' + (0.006 * W) + 'px ' + y[2] + ')';
        d.style['border' + (y[0] === 'left' ? 'Left' : 'Right') + 'Width'] = t + 'px';
        d.style['border' + (y[1] === 'top' ? 'Top' : 'Bottom') + 'Width'] = t + 'px';
        d.style['border' + (y[1] === 'top' ? 'Top' : 'Bottom') + (y[0] === 'left' ? 'Left' : 'Right') + 'Radius'] = (t * 2.2) + 'px';
        if (y[0] === 'left') d.style.left = (r.left - sr.left - p) + 'px'; else d.style.left = (r.right - sr.left + p - b) + 'px';
        if (y[1] === 'top') d.style.top = (r.top - sr.top - p) + 'px'; else d.style.top = (r.bottom - sr.top + p - b) + 'px';
        s.appendChild(d);
      }
    }
  }
  document.fonts.ready.then(function () { document.body.dataset.hazir = '1'; });
})();
"""


def sayfa(govde, gen=1920, yuk=1080, marka=True, ortam=True):
    return ("<!doctype html><html lang='tr'><head><meta charset='utf-8'><style>" + TEMEL_CSS.replace("__GREN__", GREN)
            + f"</style></head><body style='width:{gen}px;height:{yuk}px'>"
            + ("<div class='ortam'></div>" if ortam else "")
            + govde
            + (f"<div class='marka'><img src='{LOGO}'>Canlı Türkçe Altyazı</div>" if marka else "")
            + "<div class='gren'></div>"
            + f"<script>{STIL_JS}</script><script>{SAYFA_JS}</script></body></html>")


# ---------------------------------------------------------------- soyut sahne
PALET = {
    "gece": {"ust": "#0c1824", "alt": "#100a12", "isik": ["#ffb347", "#ff7a45", "#59d2ff", "#ffd98a", "#ff5e7a"]},
    "gunbatimi": {"ust": "#3a1522", "alt": "#100810", "isik": ["#ff8a3d", "#ff4d6d", "#ffc46b", "#ffdca8"]},
    "soguk": {"ust": "#08202b", "alt": "#06090f", "isik": ["#3dd6ff", "#6a7dff", "#a6f0ff", "#7fffd4"]},
    "neon": {"ust": "#1b0b30", "alt": "#07060f", "isik": ["#c04dff", "#2ef0ff", "#ff3d9a", "#7a5cff"]},
}

_FIGUR = ("<svg class='figur' viewBox='0 0 400 520' style='{stil}'><g fill='{renk}'>"
          "<ellipse cx='200' cy='150' rx='70' ry='88'/><path d='M166 220 L234 220 L244 305 L156 305 Z'/>"
          "<path d='M8 520 C 22 365 108 292 200 292 C 292 292 378 365 392 520 Z'/></g></svg>")


def sahne(palet, tohum=1, figur=2, oyun=False, canli=False):
    """Odak dışı bir film karesi: ışık lekeleri, siluetler, alt gölge, köşe kararması."""
    p, r = PALET[palet], random.Random(tohum)
    k = [f"<div class='k' style='background:linear-gradient(180deg,{p['ust']},{p['alt']})'></div>",
         f"<div class='k' style='background:radial-gradient(ellipse 75% 45% at {r.randint(35, 65)}% 60%,"
         f"{p['isik'][0]}50,transparent 70%)'></div>"]
    for _ in range(30):
        boy = r.uniform(1.2, 10.5)
        renk = r.choice(p["isik"])
        k.append(f"<i class='bokeh' style='left:{r.uniform(-4, 104):.1f}%;top:{r.uniform(10, 74):.1f}%;"
                 f"width:{boy:.2f}cqw;height:{boy:.2f}cqw;background:radial-gradient(circle,{renk} 0,{renk}bb 42%,transparent 70%);"
                 f"opacity:{r.uniform(.22, .8):.2f};filter:blur({r.uniform(0, .3) * boy:.2f}cqw)'></i>")
    if figur >= 2:  # orta plandaki kişi (keskin, kenarından ışık alıyor)
        k.append(_FIGUR.format(renk="#06060a", stil=f"right:15%;bottom:-3%;width:17%;"
                               f"filter:drop-shadow(-.25cqw -.15cqw .5cqw {p['isik'][1]}66)"))
    if figur >= 1:  # ön plandaki kişi (odak dışı)
        k.append(_FIGUR.format(renk="#030305", stil=f"left:-4%;bottom:-17%;width:35%;"
                               f"filter:blur(.55cqw) drop-shadow(.4cqw -.2cqw .9cqw {p['isik'][0]}40)"))
    k.append("<div class='k' style='background:linear-gradient(180deg,transparent 52%,rgba(0,0,0,.7))'></div>")
    k.append("<div class='k' style='background:radial-gradient(ellipse at 50% 42%,transparent 52%,rgba(0,0,0,.6))'></div>")
    if oyun:  # oyun arayüzünü andıran çizgiler: can çubuğu, harita, nişangâh
        k.append("<div class='hud' style='left:3%;top:5%;width:17%;height:1.1cqw;border-radius:.6cqw;padding:.18cqw'>"
                 "<div style='width:72%;height:100%;border-radius:.4cqw;background:linear-gradient(90deg,#2ef0ff,#c04dff)'></div></div>"
                 "<div class='hud' style='left:3%;top:calc(5% + 1.9cqw);width:11%;height:.7cqw;border-radius:.4cqw;opacity:.7'></div>"
                 "<div class='hud' style='right:3%;top:5%;width:9cqw;height:9cqw;border-radius:50%;background:rgba(0,0,0,.35)'>"
                 "<div style='position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);width:0;height:0;"
                 "border-left:.7cqw solid transparent;border-right:.7cqw solid transparent;border-bottom:1.3cqw solid #2ef0ff'></div></div>"
                 "<div style='position:absolute;left:50%;top:44%;width:2cqw;height:2cqw;transform:translate(-50%,-50%);"
                 "background:linear-gradient(#fff9,#fff9) center/100% .14cqw no-repeat,linear-gradient(#fff9,#fff9) center/.14cqw 100% no-repeat'></div>")
    if canli:  # yayın (OBS) işareti
        k.append("<div style='position:absolute;right:3%;top:5%;display:flex;align-items:center;gap:.8cqw;padding:.6cqw 1.4cqw;"
                 "border-radius:.6cqw;background:rgba(0,0,0,.5);font:700 1.8cqw Segoe UI;color:#fff;letter-spacing:.08em'>"
                 "<i style='width:1.2cqw;height:1.2cqw;border-radius:50%;background:#ff3b4a;box-shadow:0 0 1cqw #ff3b4a'></i>CANLI</div>")
    return "".join(k)


def altyazi(anahtar, stil="klasik", boyut=54, en=False, tara=False, ek=None, yer=""):
    e, t = CUMLE[anahtar]
    ayar = dict(HAZIR[stil])
    ayar.update(ek or {})
    return (f"<div class='altyazi{' tara' if tara else ''}' style='{yer}' data-stil='{html.escape(json.dumps(ayar))}' data-boyut='{boyut}' "
            f"data-tr='{html.escape(t)}' data-en='{html.escape(e) if en else ''}'></div>")


def metin(ust, baslik, aciklama="", stil=""):
    return (f"<div style='position:absolute;{stil}'><div class='ust'>{ust}</div><div class='baslik'>{baslik}</div>"
            + (f"<div class='aciklama'>{aciklama}</div>" if aciklama else "") + "</div>")


def pencere(resim_uri, stil):
    return (f"<div class='pencere' style='{stil}'><div class='cubuk'><img src='{LOGO}'>Canlı Türkçe Altyazı"
            "<span class='d'><b>&#x2013;</b><b>&#x25A1;</b><b>&#x2715;</b></span></div><img src='" + resim_uri + "'></div>")


# ---------------------------------------------------------------- kareler
def kare_giris(metinli=True):
    """01 ve hero: tam ekran film karesi, altyazıyı okuyan köşe çizgileri."""
    g = (f"<div class='sahne tam'>{sahne('gece', 3)}"
         + altyazi("dun", "klasik", 58, en=True, tara=True, ek={"ingilizce_rengi": "#c9c9d4", "ingilizce_oran": 0.5}) + "</div>")
    if metinli:
        g += ("<div style='position:absolute;inset:0;background:linear-gradient(100deg,rgba(5,5,9,.86) 0,rgba(5,5,9,.55) 38%,transparent 62%)'></div>"
              + metin("CANLI TÜRKÇE ALTYAZI", "İngilizce altyazı,<br><span class='renkli'>anında Türkçe.</span>",
                      "Film, dizi, video ya da oyun:<br>ekranda ne oynuyorsa.", "left:120px;top:150px"))
    return sayfa(g, ortam=False, marka=metinli)


def kare_hiz():
    x0, ps = 150, 208.6  # zaman ekseni: 0 sn -> 150 px, saniyede 208,6 px

    def zx(t):
        return x0 + t * ps
    en0, en1, tr0, tr1 = zx(.4), zx(3.0), zx(.6), zx(3.1)
    kilavuz = "".join(f"<div style='position:absolute;left:{x}px;top:70px;height:236px;border-left:2px dashed rgba(255,255,255,.18)'></div>"
                      for x in (en0, tr0, en1, tr1))
    eksen = "".join(f"<div style='position:absolute;left:{zx(t) - 40}px;width:80px;top:452px;text-align:center;font-size:19px;color:#6f6c86'>"
                    f"{'0' if t == 0 else str(t) + ' sn'}</div><div style='position:absolute;left:{zx(t)}px;top:430px;height:12px;"
                    f"border-left:2px solid rgba(255,255,255,.22)'></div>" for t in (0, 1, 2, 3))
    kart = (f"<div style='position:absolute;left:860px;top:236px;width:960px;height:600px;border-radius:30px;"
            f"background:rgba(255,255,255,.028);border:1px solid rgba(255,255,255,.07)'>"
            f"{kilavuz}"
            f"<div style='position:absolute;left:40px;top:118px;font-size:20px;color:#8c89a3'>EN</div>"
            f"<div style='position:absolute;left:{en0}px;top:96px;width:{en1 - en0}px;height:70px;border-radius:16px;"
            f"background:rgba(255,255,255,.07);display:flex;align-items:center;padding:0 26px;font-size:25px;color:#b9b7c9'>{CUMLE['dun'][0]}</div>"
            f"<div style='position:absolute;left:40px;top:238px;font-size:20px;font-weight:700' class='renkli'>TR</div>"
            f"<div style='position:absolute;left:{tr0}px;top:216px;width:{tr1 - tr0}px;height:70px;border-radius:16px;padding:2px;"
            f"background:linear-gradient(90deg,#2ef0ff,#c04dff)'><div style='height:100%;border-radius:14px;background:#14121f;"
            f"display:flex;align-items:center;padding:0 24px;font-size:27px;font-weight:600'>{CUMLE['dun'][1]}</div></div>"
            f"<div style='position:absolute;left:{(en0 + tr0) / 2 - 70}px;width:140px;top:318px;text-align:center;font-size:22px;font-weight:700;color:#2ef0ff'>≈ 0,2 sn</div>"
            f"<div style='position:absolute;left:{(en1 + tr1) / 2 - 70}px;width:140px;top:318px;text-align:center;font-size:22px;font-weight:700;color:#c04dff'>≈ 0,1 sn</div>"
            f"<div style='position:absolute;left:{x0}px;width:{zx(3.5) - x0}px;top:430px;border-top:2px solid rgba(255,255,255,.22)'></div>{eksen}"
            f"<div style='position:absolute;left:40px;right:40px;bottom:34px;font-size:17px;color:#6f6c86'>"
            f"Ortanca ölçüm: Ryzen 5 5600X işlemci, hazır çeviri. Bilgisayara ve seçilen çeviri servisine göre değişir.</div></div>")
    return sayfa(metin("HIZ", "Aynı anda gelir.<br><span class='renkli'>Aynı anda gider.</span>",
                       "İngilizce belirdikten yaklaşık<br><b>0,2 saniye</b> sonra Türkçesi ekranda.<br>İngilizce kalkınca o da kalkar.",
                       "left:120px;top:250px;width:700px") + kart)


def kare_her_yerde():
    kutular = [("Film ve dizi", "Tarayıcıda ya da oynatıcıda,<br>tam ekranda da.", sahne("gunbatimi", 11), altyazi("gunes", "klasik", 84)),
               ("Bilgisayar oyunları", "Oyunun üstünde durur;<br>tıklamalar oyuna geçer.", sahne("neon", 5, figur=1, oyun=True),
                altyazi("kestirme", "oyun", 80)),
               ("Konsol + OBS", "Capture card ile; yayında<br>ve kayıtta da görünür.", sahne("soguk", 8, figur=2, canli=True),
                altyazi("sessiz", "serit", 80))]
    g = ""
    for i, (ad, alt, sh, ay) in enumerate(kutular):
        x = 150 + i * 560
        g += (f"<div class='sahne' style='left:{x}px;top:420px;width:500px;height:281px;border-radius:18px'>{sh}{ay}</div>"
              f"<div style='position:absolute;left:{x}px;top:735px;width:500px'><div style='font-size:32px;font-weight:700;letter-spacing:-.01em'>{ad}</div>"
              f"<div style='font-size:22px;line-height:1.45;color:#9a97b1;margin-top:8px'>{alt}</div></div>")
    return sayfa(metin("FİLM · DİZİ · VİDEO · OYUN", "Ekranda ne oynuyorsa,<br><span class='renkli'>Türkçesi üstünde.</span>", "",
                       "left:150px;top:118px") + g)


def _simge(ic, no):
    return (f"<svg viewBox='0 0 48 48' width='86' height='86' fill='none' stroke='url(#g{no})' stroke-width='2.6' stroke-linecap='round' "
            f"stroke-linejoin='round'><defs><linearGradient id='g{no}' x1='0' y1='0' x2='1' y2='1'><stop offset='0' stop-color='#2ef0ff'/>"
            f"<stop offset='1' stop-color='#c04dff'/></linearGradient></defs>{ic}<path d='M7 7 L41 41'/></svg>")


def kare_internetsiz():
    simgeler = [
        ("İnternet yok.", _simge("<path d='M7 19a25 25 0 0 1 34 0'/><path d='M13 26a16 16 0 0 1 22 0'/><path d='M19 33a7 7 0 0 1 10 0'/>"
                                 "<circle cx='24' cy='39' r='1.4'/>", 1)),
        ("Anahtar yok.", _simge("<circle cx='15' cy='24' r='8'/><path d='M23 24h19M36 24v6M41 24v5'/>", 2)),
        ("Ücret yok.", _simge("<circle cx='24' cy='24' r='16'/><text x='24' y='31' text-anchor='middle' font-size='20' "
                              "font-weight='700' font-family='Segoe UI' fill='url(#g3)' stroke='none'>₺</text>", 3)),
    ]
    sutun = "".join(f"<div style='width:440px;text-align:center'>{s}<div style='font-size:64px;font-weight:700;letter-spacing:-.03em;"
                    f"margin-top:26px'>{ad}</div></div>" for ad, s in simgeler)
    cipler = "".join(f"<span class='cip'><i></i>{c}</span>" for c in ("Gemini", "Groq", "DeepL", "Claude", "Yerel model"))
    return sayfa("<div style='position:absolute;left:0;right:0;top:210px;text-align:center'><div class='ust'>HAZIR ÇEVİRİ</div></div>"
                 f"<div style='position:absolute;left:0;right:0;top:310px;display:flex;justify-content:center;gap:40px'>{sutun}</div>"
                 "<div class='aciklama' style='position:absolute;left:0;right:0;top:630px;text-align:center;margin:0'>"
                 "Çeviri modeli uygulamayla gelir ve bilgisayarınızda çalışır.<br>"
                 "İsterseniz kendi anahtarınızla bir çeviri servisini de bağlayabilirsiniz:</div>"
                 f"<div style='position:absolute;left:0;right:0;top:770px;display:flex;justify-content:center;gap:16px'>{cipler}</div>")


def kare_gorunum():
    secim = [("sinema", "Sinema"), ("cam", "Buzlu cam"), ("gece", "Gece mavisi"), ("yumusak", "Yumuşak")]
    g = ""
    for i, (stil, ad) in enumerate(secim):
        x, y = 830 + (i % 2) * 496, 236 + (i // 2) * 300
        g += (f"<div class='sahne' style='left:{x}px;top:{y}px;width:470px;height:264px;border-radius:18px'>{sahne('gece', 21, figur=2)}"
              f"<div class='etiket'>{ad}</div>{altyazi('kolay', stil, 96)}</div>")
    return sayfa(metin("GÖRÜNÜM", "Altyazınız,<br><span class='renkli'>sizin tarzınız.</span>",
                       "Yazı tipi, renk, kenar çizgisi, gölge,<br>saydamlığı ayarlanan arka plan.<br>"
                       "Yerini de siz seçin: <b>sürükleyip bırakın</b>.", "left:120px;top:270px;width:660px") + g)


def kare_arayuz(resim, ust, baslik, aciklama):
    return sayfa(metin(ust, f"<span style='font-size:70px'>{baslik}</span>", aciklama, "left:120px;top:330px;width:600px")
                 + pencere(_veri_uri(os.path.join(ARAYUZ, resim)), "left:760px;top:200px;width:1060px"))


def kare_gizlilik():
    cipler = "".join(f"<span class='cip'><i></i>{c}</span>" for c in
                     ("Ekran görüntüsü kaydedilmez", "İnternetsiz çalışır", "Açık kaynak · AGPL-3.0"))
    return sayfa("<div style='position:absolute;left:0;right:0;top:250px;text-align:center'><div class='ust'>GİZLİLİK</div>"
                 "<div class='baslik'>Hesap yok. Reklam yok.<br><span class='renkli'>Takip yok.</span></div>"
                 "<div class='aciklama'>Altyazıyı okumak için alınan görüntü yalnızca bilgisayarınızın belleğinde işlenir;<br>"
                 "kaydedilmez, hiçbir yere gönderilmez.</div></div>"
                 f"<div style='position:absolute;left:0;right:0;top:770px;display:flex;justify-content:center;gap:16px'>{cipler}</div>")


def poster(gen, yuk):
    """9:16 poster: üstte film karesi, altta ad."""
    sh = (f"<div class='sahne' style='left:0;top:0;width:{gen}px;height:{int(yuk * .6)}px;border-radius:0;box-shadow:none'>"
          f"{sahne('gece', 3)}{altyazi('dun', 'klasik', 62, en=True, tara=True, ek={'ingilizce_rengi': '#c9c9d4', 'ingilizce_oran': .5}, yer='bottom:26%')}</div>"
          f"<div style='position:absolute;left:0;right:0;top:{int(yuk * .42)}px;height:{int(yuk * .2)}px;"
          "background:linear-gradient(180deg,transparent,#07070b)'></div>")
    a = gen / 1440
    yazi = (f"<div style='position:absolute;left:0;right:0;top:{int(yuk * .6)}px;text-align:center'>"
            f"<img src='{LOGO}' style='width:{int(220 * a)}px;border-radius:{int(48 * a)}px;margin-top:{int(-60 * a)}px'>"
            f"<div class='baslik' style='font-size:{int(150 * a)}px;margin-top:{int(40 * a)}px'>Canlı Türkçe<br><span class='renkli'>Altyazı</span></div>"
            f"<div class='aciklama' style='font-size:{int(46 * a)}px;margin-top:{int(36 * a)}px'>Ekrandaki İngilizce altyazı,<br>anında Türkçe.</div></div>")
    return sayfa(sh + yazi, gen, yuk, marka=False)


def kutu(boy):
    a = boy / 2160
    return sayfa(f"<div style='position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center'>"
                 f"<div style='position:absolute;left:50%;top:38%;width:{int(1500 * a)}px;height:{int(1500 * a)}px;"
                 "transform:translate(-50%,-50%);background:radial-gradient(circle,rgba(143,123,255,.22),transparent 60%)'></div>"
                 f"<img src='{LOGO}' style='position:relative;width:{int(720 * a)}px'>"
                 f"<div class='baslik' style='font-size:{int(190 * a)}px;margin-top:{int(110 * a)}px'>Canlı Türkçe <span class='renkli'>Altyazı</span></div>"
                 f"<div class='aciklama' style='font-size:{int(60 * a)}px;margin-top:{int(40 * a)}px'>Ekrandaki İngilizce altyazı, anında Türkçe.</div></div>",
                 boy, boy, marka=False)


# ---------------------------------------------------------------- gerçek arayüz
def ekran_goruntuleri(p):
    """Yeni arayüzün (2.7) gerçek ekranları, Store sürümü gibi (seslendirme "geliştiriliyor" işaretli). Ekran yakalama
    sahtedir: soyut film karesi + düz beyaz İngilizce altyazı "bu bilgisayarın ekranı" olarak verilir."""
    import cv2

    import kaynak
    import pc_katman
    import uygulama

    veri.MAGAZA = True
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1920, "height": 1080})
    en_css = ("position:absolute;left:0;right:0;bottom:8%;text-align:center;font:600 50px 'Segoe UI';color:#fff;z-index:9;"
              "text-shadow:0 0 4px #000,2px 2px 3px #000,-2px -2px 3px #000,2px -2px 3px #000,-2px 2px 3px #000")
    pg.set_content(sayfa(f"<div class='sahne tam'>{sahne('gece', 3)}<div style=\"{en_css}\">{CUMLE['dun'][0]}</div></div>",
                         ortam=False, marka=False))
    pg.wait_for_function("document.body.dataset.hazir === '1'")
    pg.wait_for_timeout(300)
    oyun_yolu = os.path.join(tempfile.gettempdir(), "cta_magaza_sahne.png")
    pg.screenshot(path=oyun_yolu)
    pg.close()
    kare = cv2.imread(oyun_yolu)
    pc_katman.ekranlar = lambda: [{"no": 1, "x": 0, "y": 0, "genislik": 1920, "yukseklik": 1080, "ana": True}]
    pc_katman.ekran_goruntusu = lambda no: kare.copy()

    class SahteEkran:
        def __init__(self, no):
            self.son_kare_ms = 1

        def kare_al(self):
            time.sleep(0.03)
            return kare.copy()

        def kapat(self):
            pass

    kaynak.EkranKaynagi = SahteEkran

    a = veri.ayar_yukle()
    a["goruntu"]["port"] = 8795
    veri.ayar_kaydet(a)
    uyg = uygulama.Uygulama()
    satirlar = [CUMLE["araba"] + (112,), CUMLE["kestirme"] + (96,), CUMLE["gunes"] + (121,), CUMLE["dun"] + (108,)]
    ozet = [{"durum": "durdu", "hata": "", "ceviri_hatasi": "", "gecmis": [], "sayac": {"okunan": 0, "cevrilen": 0},
             "motor": "cevrimdisi"}]
    uyg.motor_ozet = lambda _: ozet[0]
    uyg.motor_baslat = lambda _: {}
    ws = uygulama.api_sunucusu(uyg, "m")
    adres = f"http://127.0.0.1:{ws.server_address[1]}"

    pg = b.new_page(viewport={"width": 1600, "height": 900}, device_scale_factor=1.2)  # -> 1920x1080
    pg.goto(f"{adres}/#m")
    pg.wait_for_function("document.body.dataset.hazir === '1'")

    def foto(ad, basa_don=True):
        pg.wait_for_timeout(700)
        if basa_don:
            pg.evaluate("document.querySelector('main').scrollTop = 0; window.scrollTo(0, 0)")
            pg.wait_for_timeout(200)
        pg.screenshot(path=os.path.join(ARAYUZ, ad))
        print("  [OK] arayuz/" + ad, flush=True)

    def bekle(kosul, sn=30):
        for _ in range(sn * 10):
            if kosul():
                return
            pg.wait_for_timeout(100)
        raise RuntimeError("bekleme süresi doldu")

    def ac(sayfa_adi):
        pg.click(f'#nav button[data-sayfa="{sayfa_adi}"]')
        pg.wait_for_selector(f"#s-{sayfa_adi}.aktif")
        pg.evaluate("document.querySelector('main').scrollTop = 0")

    # ilk kurulum: ekran seçilir, altyazının yeri bulunur
    bekle(lambda: pg.locator("#ekranlar .ekran-oge").count() >= 1)
    pg.locator("#ekranlar .ekran-oge").nth(0).click()
    bekle(lambda: (pg.get_attribute("#cizim-resim", "src") or "").startswith("data:image"))
    pg.click("#al-bul")
    bekle(lambda: "Altyazı bulundu" in (pg.text_content("#al-sonuc") or ""), 60)
    pg.evaluate("document.querySelector('#cizim').scrollIntoView({block: 'center'})")
    foto("altyazi_alani.png", basa_don=False)
    pg.click("#al-kaydet")
    bekle(lambda: uyg.ayar.get("kurulum_tamam") and pg.is_visible("#s-ana"))
    # çalışırken ana sayfa
    ozet[0] = {"durum": "calisiyor", "hata": "", "ceviri_hatasi": "", "ceviri_uyari": None, "motor": "cevrimdisi",
               "gecmis": [{"id": i, "en": e, "tr": t, "ms": ms} for i, (e, t, ms) in enumerate(satirlar)],
               "sayac": {"okunan": 128, "cevrilen": 126}, "dublaj": {"acik": False},
               "hiz": {"ocr_ms": 31, "ceviri_ms": 108, "kare_ms": 25, "atlanan": 0}}
    bekle(lambda: "neredeydin" in (pg.text_content("#satirlar") or ""))
    pg.wait_for_timeout(6000)  # "Kurulum tamam" bildirimi kalksın
    foto("ana_sayfa.png")
    ac("gorunum")
    pg.click('#g-hazir .hazir[data-v="sinema"]')
    foto("gorunum.png")
    ac("ceviri")
    bekle(lambda: pg.locator("#motorlar > *").count() >= 3)
    foto("ceviri.png")
    ac("ses")
    bekle(lambda: pg.text_content("#d-dogal-rozet") != "–")
    foto("seslendirme.png")
    b.close()
    ws.shutdown()
    uyg.kapat()


def main():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        if "--arayuz-yok" not in sys.argv:
            ekran_goruntuleri(p)
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1920, "height": 1080})

        def ciz(ad, icerik, gen=1920, yuk=1080):
            pg.set_viewport_size({"width": gen, "height": yuk})
            pg.set_content(icerik)
            pg.wait_for_function("document.body.dataset.hazir === '1'")
            pg.wait_for_timeout(250)
            pg.screenshot(path=os.path.join(CIKTI, ad))
            print("  [OK]", ad, flush=True)

        ciz("01_giris.png", kare_giris())
        ciz("02_hiz.png", kare_hiz())
        ciz("03_her_yerde.png", kare_her_yerde())
        ciz("04_internetsiz.png", kare_internetsiz())
        ciz("05_gorunum.png", kare_gorunum())
        ciz("06_kurulum.png", kare_arayuz("altyazi_alani.png", "KURULUM",
                                          "Altyazının yerini<br><span class='renkli'>bir kez gösterin.</span>",
                                          "<b>Altyazıyı bul</b>'a basın ya da fareyle bir kutu çizin. Gerisini program yapar."))
        ciz("07_baslat.png", kare_arayuz("ana_sayfa.png", "KULLANIM",
                                         "Başlat'a basın,<br><span class='renkli'>izlemeye dönün.</span>",
                                         "Pencereyi küçültünce saatin yanındaki simgeye iner; başlatmak, durdurmak ve görünüm oradan."))
        ciz("08_gizlilik.png", kare_gizlilik())
        ciz("hero_16x9.png", kare_giris(metinli=False))  # Store kuralı: hero görselinde ürün adı/yazı olmaz
        ciz("poster_9x16.png", poster(1440, 2160), 1440, 2160)
        ciz("kutu_1x1.png", kutu(2160), 2160, 2160)
        b.close()
    print("Görseller:", CIKTI)


if __name__ == "__main__":
    main()
