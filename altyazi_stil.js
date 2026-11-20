// Türkçe altyazının görünümü. Oyunun üstündeki yazı (overlay.html) ve arayüzdeki önizleme (arayuz.html) AYNI kodu
// kullanır: önizlemede görülen ile oyunda görülen aynı olsun. Ayarlar config.goruntu altında durur;
// uygulama.gorunum_kaydet doğrular (buradaki sınırlarla aynı değerler: veri.py GORUNUM_SECENEKLERI;
// tests/test_arayuz.py ikisini karşılaştırır).
var AltyaziStil = (function () {
  var YAZI_TIPLERI = {
    standart: { ad: "Standart", aile: '"Segoe UI Variable Display", "Segoe UI", Arial, sans-serif' },
    oyun: { ad: "Oyun", aile: 'Bahnschrift, "Segoe UI", Arial, sans-serif' },
    sade: { ad: "Sade", aile: "Arial, Helvetica, sans-serif" },
    genis: { ad: "Geniş", aile: 'Verdana, Tahoma, "Segoe UI", sans-serif' },
    sinema: { ad: "Sinema", aile: '"Trebuchet MS", "Segoe UI", sans-serif' },
    kitap: { ad: "Kitap", aile: 'Georgia, "Times New Roman", serif' },
    daktilo: { ad: "Daktilo", aile: 'Consolas, "Courier New", monospace' },
    eglenceli: { ad: "Eğlenceli", aile: '"Comic Sans MS", "Segoe Print", cursive' },
    darbe: { ad: "Afiş", aile: 'Impact, "Arial Black", sans-serif' },
    ozel: { ad: "Bilgisayarımdaki bir yazı tipi", aile: "" }  // goruntu.yazi_tipi_ozel: yüklü yazı tipinin adı
  };
  var RENKLER = [["#ffffff", "Beyaz"], ["#ffe04a", "Sarı"], ["#9fd8ff", "Açık mavi"], ["#a8f0a0", "Açık yeşil"],
                 ["#ffb86b", "Turuncu"], ["#ffb3d9", "Pembe"], ["#f6ecd6", "Krem"], ["#101014", "Siyah"]];
  var KUTU_RENKLERI = [["#000000", "Siyah"], ["#14213d", "Lacivert"], ["#3a0d0d", "Bordo"], ["#0f2e1c", "Koyu yeşil"],
                       ["#2b2b33", "Gri"], ["#ffffff", "Beyaz"], ["#ffe04a", "Sarı"]];
  // Sayısal ayarların sınırları [en az, en çok] — veri.py GORUNUM_SECENEKLERI ile aynı
  var SINIR = {
    yazi_boyutu: [16, 120], yazi_kalinligi: [300, 900], kenar: [0, 4], golge: [0, 3],
    kutu_saydamlik: [0, 1], kutu_kose: [0, 1], kutu_bosluk: [0, 1], harf_araligi: [-0.03, 0.2],
    satir_araligi: [1, 1.8], genislik: [0.3, 0.96], ingilizce_oran: [0.4, 1], konum_x: [0.2, 0.8], konum_y: [0.06, 0.94],
    kapak_saydamlik: [0, 1]
  };
  var SECENEK = {
    kutu_bicimi: ["sar", "serit"],        // sar: yazıyı saran kutu; serit: satır boyunca uzanan şerit
    hizalama: ["orta", "sol", "sag"],
    konum: ["orijinal", "serbest"],       // orijinal: oyunun altyazısının yeri; serbest: (konum_x, konum_y) yazının ortası
    gecis: ["yok", "yumusak"]             // yumusak: 90 ms'de belirir (anında görünmesi için "yok")
  };
  var VARSAYILAN = {
    yazi_boyutu: 44, yazi_tipi: "standart", yazi_tipi_ozel: "", yazi_kalinligi: 700, italik: false, buyuk_harf: false,
    yazi_rengi: "#ffffff", kenar: 2, kenar_rengi: "#000000", golge: 1,
    kutu_rengi: "#000000", kutu_saydamlik: 0, kutu_bicimi: "sar", kutu_kose: 0.25, kutu_bosluk: 0.35,
    harf_araligi: 0, satir_araligi: 1.2, hizalama: "orta", genislik: 0.88,
    ingilizce_rengi: "#d9d9d9", ingilizce_oran: 0.6, ingilizce_ustte: false, etiket_rengi: "",
    kapak_rengi: "#08080a", kapak_saydamlik: 1, gecis: "yok", konum: "orijinal", konum_x: 0.5, konum_y: 0.85
  };
  var RENK_ALANLARI = ["yazi_rengi", "kenar_rengi", "kutu_rengi", "ingilizce_rengi", "kapak_rengi"];
  var HAZIR_KONUMLAR = [
    { id: "orijinal", ad: "Altyazının yerinde", ayar: { konum: "orijinal" } },
    { id: "ust", ad: "Üstte", ayar: { konum: "serbest", konum_x: 0.5, konum_y: 0.1 } },
    { id: "orta", ad: "Ortada", ayar: { konum: "serbest", konum_x: 0.5, konum_y: 0.5 } },
    { id: "alt", ad: "Altta", ayar: { konum: "serbest", konum_x: 0.5, konum_y: 0.9 } }
  ];
  var ESKI_KUTU = { yok: 0, yari: 0.55, koyu: 0.88 };  // 2.6 ve öncesinin "kutu" ayarı

  function renkMi(r) { return typeof r === "string" && /^#[0-9a-fA-F]{6}$/.test(r); }

  function sinirla(deger, aralik, yoksa) {
    var d = +deger;
    if (deger === null || deger === undefined || deger === "" || !isFinite(d)) d = yoksa;
    return Math.max(aralik[0], Math.min(aralik[1], d));
  }

  function tamamla(ayar) {
    var a = {}, k, kaynak = ayar || {};
    for (k in VARSAYILAN) a[k] = VARSAYILAN[k];
    for (k in kaynak) if (kaynak[k] !== undefined && kaynak[k] !== null) a[k] = kaynak[k];
    // eski sürümün ayar dosyası: kutu "yok/yari/koyu" -> saydamlık
    if ((kaynak.kutu_saydamlik === undefined || kaynak.kutu_saydamlik === null) && ESKI_KUTU[kaynak.kutu] !== undefined) {
      a.kutu_saydamlik = ESKI_KUTU[kaynak.kutu];
    }
    if (!YAZI_TIPLERI[a.yazi_tipi]) a.yazi_tipi = "standart";
    a.yazi_tipi_ozel = String(a.yazi_tipi_ozel || "").replace(/["'\\;{}<>]/g, "").slice(0, 80);
    if (a.yazi_tipi === "ozel" && !a.yazi_tipi_ozel) a.yazi_tipi = "standart";
    for (k = 0; k < RENK_ALANLARI.length; k++) {
      if (!renkMi(a[RENK_ALANLARI[k]])) a[RENK_ALANLARI[k]] = VARSAYILAN[RENK_ALANLARI[k]];
    }
    if (!renkMi(a.etiket_rengi)) a.etiket_rengi = "";
    for (k in SINIR) a[k] = sinirla(a[k], SINIR[k], VARSAYILAN[k]);
    a.yazi_kalinligi = Math.round(a.yazi_kalinligi / 100) * 100;
    for (k in SECENEK) if (SECENEK[k].indexOf(a[k]) < 0) a[k] = VARSAYILAN[k];
    a.italik = !!a.italik; a.buyuk_harf = !!a.buyuk_harf; a.ingilizce_ustte = !!a.ingilizce_ustte;
    return a;
  }

  function aile(a) {
    if (a.yazi_tipi === "ozel") return '"' + a.yazi_tipi_ozel + '", ' + YAZI_TIPLERI.standart.aile;
    return YAZI_TIPLERI[a.yazi_tipi].aile;
  }

  function rgba(renk, saydamlik) {
    var n = parseInt(renk.slice(1), 16);
    return "rgba(" + (n >> 16) + ", " + ((n >> 8) & 255) + ", " + (n & 255) + ", " + (+saydamlik).toFixed(3) + ")";
  }

  function yuzde(oran) { return (oran * 100).toFixed(3) + "%"; }

  /** Ana altyazının ekrandaki yeri (yüzdeler ekrana göredir). b: oyunun kendi altyazısının alanı {x, y, w, h} (0-1).
   *  Dönüş: { kapak: stil ya da null, kutu: stil, goster: kutunun görünürkenki "display" değeri }.
   *  kapak: "İngilizce altyazının üstünü kapat" açıksa İngilizcenin üstüne çekilen şerit. */
  function yerlesim(ayar, b) {
    var a = tamamla(ayar), kapat = !!(ayar && ayar.orijinali_kapat);
    // kapak_saydamlik: 1 = İngilizce tamamen kapanır; azaldıkça şerit saydamlaşır (0: Türkçe doğrudan İngilizcenin üstünde)
    var kapak = kapat ? { left: yuzde(b.x), top: yuzde(b.y), width: yuzde(b.w), height: yuzde(b.h),
                          background: rgba(a.kapak_rengi, a.kapak_saydamlik) } : null;
    var hiza = a.hizalama === "sol" ? "left" : a.hizalama === "sag" ? "right" : "center";
    var kutu, goster = "block";
    if (a.konum === "serbest") {
      // (konum_x, konum_y) yazının ortası; genişlik ekran kenarına taşmayacak kadar
      var w = Math.min(a.genislik, 2 * Math.min(a.konum_x, 1 - a.konum_x) - 0.04);
      kutu = { left: yuzde(a.konum_x), top: yuzde(a.konum_y), right: "auto", bottom: "auto", width: yuzde(w), height: "auto",
               padding: "0", transform: "translate(-50%, -50%)", textAlign: hiza };
    } else if (kapat) {
      // İngilizcenin üstü kapalı, Türkçe tam oraya yazılır
      kutu = { left: yuzde(b.x), top: yuzde(b.y), right: "auto", bottom: "auto", width: yuzde(b.w), height: yuzde(b.h),
               padding: "0 2%", transform: "none", flexDirection: "column", justifyContent: "center", textAlign: hiza };
      goster = "flex";
    } else {
      // Kapatmadan: İngilizce altyazının hemen üstüne
      kutu = { left: "0", right: "0", top: "auto", bottom: yuzde(1 - b.y + 0.01), width: "auto", height: "auto",
               padding: "0 6%", transform: "none", textAlign: hiza };
    }
    return { kapak: kapak, kutu: kutu, goster: goster };
  }

  // Yazının çevresine çizgi: çember üzerinde gölgeler (her tarayıcıda aynı görünür) + istenirse düşen gölge
  function yaziGolgesi(kenarPx, kenarRengi, golge, boyutPx, uzunluk) {
    var g = [], n, i, aci;
    if (kenarPx > 0) {
      n = kenarPx > 1.5 ? 16 : 8;
      for (i = 0; i < n; i++) {
        aci = 2 * Math.PI * i / n;
        g.push(uzunluk(Math.cos(aci) * kenarPx) + " " + uzunluk(Math.sin(aci) * kenarPx) + " 0 " + kenarRengi);
      }
      g.push("0 0 " + uzunluk(kenarPx * 1.6) + " " + kenarRengi);
    }
    if (golge > 0) {
      var k = boyutPx / 44;
      g.push(uzunluk(1.2 * golge * k) + " " + uzunluk(1.6 * golge * k) + " " + uzunluk(2.2 * golge * k) + " rgba(0, 0, 0, " + Math.min(0.95, 0.45 + 0.2 * golge).toFixed(2) + ")");
    }
    return g.length ? g.join(", ") : "none";
  }

  /** Türkçe yazı, İngilizcenin üstünü kapatan şeridin içinde mi duruyor? (üstünü kapat açık + yazı altyazının yerinde) */
  function seritIcinde(ayar) {
    return !!(ayar && ayar.orijinali_kapat) && tamamla(ayar).konum === "orijinal";
  }

  /** Bir altyazı kutusunun içini kurar: govde (arka plan kutusu) > tr (Türkçe) + en (İngilizce). */
  function kur(kutu) {
    var govde = document.createElement("div"), tr = document.createElement("div"), en = document.createElement("div");
    govde.className = "govde"; tr.className = "tr"; en.className = "en";
    govde.appendChild(tr); govde.appendChild(en); kutu.appendChild(govde);
    return { kutu: kutu, govde: govde, tr: tr, en: en };
  }

  /** Görünümü uygular. el: kur()'un döndürdüğü. uzunluk(px): 1080p'deki piksel değerini bu sayfanın birimine çevirir
   *  (overlay: ölçekli px, önizleme: cqw). boyut: yazı boyutu (1080p pikseli); verilmezse ayar.yazi_boyutu. */
  function uygula(el, ayar, uzunluk, boyut) {
    var a = tamamla(ayar), g = el.govde.style, s = el.tr.style, e = el.en.style;
    boyut = boyut || a.yazi_boyutu;
    // Türkçe, İngilizcenin üstünü kapatan şeridin içine yazılıyorsa arka planı o şerittir: ayrıca kutu çizilmez
    var kutulu = a.kutu_saydamlik > 0.001 && !seritIcinde(ayar);
    g.display = a.kutu_bicimi === "serit" && kutulu ? "block" : "inline-block";
    g.maxWidth = "100%"; g.boxSizing = "border-box"; g.alignSelf = a.kutu_bicimi === "serit" && kutulu ? "stretch" :
      (a.hizalama === "sol" ? "flex-start" : a.hizalama === "sag" ? "flex-end" : "center");
    g.background = kutulu ? rgba(a.kutu_rengi, a.kutu_saydamlik) : "transparent";
    g.padding = kutulu ? uzunluk(boyut * a.kutu_bosluk * 0.45) + " " + uzunluk(boyut * a.kutu_bosluk * 1.3) : "0";
    g.borderRadius = kutulu ? uzunluk(boyut * a.kutu_kose) : "0";
    g.textAlign = a.hizalama === "sol" ? "left" : a.hizalama === "sag" ? "right" : "center";
    g.transition = "none";
    s.fontFamily = aile(a);
    s.fontWeight = String(a.yazi_kalinligi);
    s.fontStyle = a.italik ? "italic" : "normal";
    s.textTransform = a.buyuk_harf ? "uppercase" : "none";
    s.fontSize = uzunluk(boyut);
    s.color = a.yazi_rengi;
    s.letterSpacing = a.harf_araligi ? a.harf_araligi.toFixed(3) + "em" : "normal";
    s.lineHeight = String(a.satir_araligi);
    s.textShadow = yaziGolgesi(a.kenar * 1.1 * Math.sqrt(boyut / 44), a.kenar_rengi, a.golge, boyut, uzunluk);
    e.fontFamily = aile(a);
    e.fontStyle = s.fontStyle;
    e.fontWeight = String(Math.max(400, a.yazi_kalinligi - 200));
    e.fontSize = uzunluk(boyut * a.ingilizce_oran);
    e.color = a.ingilizce_rengi;
    e.lineHeight = String(a.satir_araligi);
    e.textShadow = yaziGolgesi(Math.min(a.kenar, 2) * 0.8 * Math.sqrt(boyut * a.ingilizce_oran / 44), a.kenar_rengi, Math.min(a.golge, 1), boyut * a.ingilizce_oran, uzunluk);
    if (a.ingilizce_ustte && el.en.nextSibling !== el.tr) el.govde.insertBefore(el.en, el.tr);
    if (!a.ingilizce_ustte && el.tr.nextSibling !== el.en) el.govde.insertBefore(el.tr, el.en);
    return a;
  }

  /** Yazıyı koyar. Konuşmacı adı ("JASON: ...") ayrı renkte istenmişse adı boyar. */
  function yaz(el, tr, en, ayar) {
    var a = tamamla(ayar), m = a.etiket_rengi ? /^([^\s:][^:]{0,23}):\s+(\S[\s\S]*)$/.exec(tr || "") : null;
    el.tr.textContent = "";
    if (m) {
      var ad = document.createElement("span");
      ad.style.color = a.etiket_rengi; ad.textContent = m[1] + ": ";
      el.tr.appendChild(ad); el.tr.appendChild(document.createTextNode(m[2]));
    } else {
      el.tr.textContent = tr || "";
    }
    el.en.textContent = en || "";
  }

  return { YAZI_TIPLERI: YAZI_TIPLERI, RENKLER: RENKLER, KUTU_RENKLERI: KUTU_RENKLERI, SINIR: SINIR, SECENEK: SECENEK,
           VARSAYILAN: VARSAYILAN, RENK_ALANLARI: RENK_ALANLARI, HAZIR_KONUMLAR: HAZIR_KONUMLAR,
           tamamla: tamamla, uygula: uygula, yerlesim: yerlesim, kur: kur, yaz: yaz, rgba: rgba, seritIcinde: seritIcinde, aile: aile };
})();
