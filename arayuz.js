/* Canlı Türkçe Altyazı — arayüz (2.7). Sayfalar: ana, alan, gorunum, ceviri, ses, ayarlar. */
"use strict";
const $ = (id) => document.getElementById(id);
const hepsi = (secici, kok) => Array.from((kok || document).querySelectorAll(secici));

// ---------- yerel API belirteci (adres çubuğundaki #... kısmı) ----------
const BELIRTEC = (() => {
  let b = location.hash.slice(1);
  try {
    if (b) sessionStorage.setItem("belirtec", b);
    else b = sessionStorage.getItem("belirtec") || "";
  } catch (e) {}
  if (location.hash) history.replaceState(null, "", location.pathname + location.search);
  return b;
})();

async function api(yol, veri) {
  let r;
  try {
    r = await fetch(yol, { method: "POST", headers: { "Content-Type": "application/json", "X-Belirtec": BELIRTEC }, body: JSON.stringify(veri || {}) });
  } catch (e) { throw new Error("Programın arka planına ulaşılamadı. Programı kapatıp yeniden açın."); }
  if (r.status === 403) throw new Error("Oturum süresi doldu. Programı kapatıp yeniden açın.");
  const j = await r.json();
  if (!j.ok) throw new Error(j.hata || "Bilinmeyen hata");
  return j;
}

let bildirimZ = null;
function bildir(metin, hata) {
  const e = $("bildirim");
  e.textContent = metin; e.className = "acik" + (hata ? " hata" : "");
  clearTimeout(bildirimZ);
  bildirimZ = setTimeout(() => { e.className = ""; }, hata ? 6000 : 2600);
}
const hataGoster = (e) => bildir(e.message || String(e), true);
function uyari(id, metin) { const e = $(id); e.textContent = metin || ""; e.classList.toggle("acik", !!metin); }
async function mesgul(dugme, is) {
  dugme.classList.add("bekliyor");
  try { return await is(); } catch (e) { hataGoster(e); } finally { dugme.classList.remove("bekliyor"); }
}
function secimIsaretle(kutu, deger) { hepsi("button", kutu).forEach((b) => b.classList.toggle("secili", b.dataset.v === String(deger))); }
function el(etiket, sinif, metin) { const e = document.createElement(etiket); if (sinif) e.className = sinif; if (metin !== undefined) e.textContent = metin; return e; }

let durum = null;      // /api/durum
let G = null;          // görünüm ayarları (durum.goruntu'nun kopyası)
let kurulumModu = false;

// ================= gezinme =================
function sayfaAc(ad) {
  hepsi("#nav button").forEach((b) => b.classList.toggle("aktif", b.dataset.sayfa === ad));
  hepsi(".sayfa").forEach((s) => s.classList.toggle("aktif", s.id === "s-" + ad));
  document.querySelector("main").scrollTop = 0;
  try { sessionStorage.setItem("sayfa", ad); } catch (e) {}
  if (ad === "alan") { alanAcildi(); if (alanYuklendi && durum && obsModu() && !(durum.obs || {}).baglandi) obsKontrol(); }
  if (ad === "ses") sesAcildi();
  if (ad === "gorunum" && durum) { hedefleriCiz(); G = hedefAyari(); gorunumDoldur(); onizle(); }
}
hepsi("#nav button").forEach((b) => (b.onclick = () => { if (!b.disabled) sayfaAc(b.dataset.sayfa); }));

// ================= ana sayfa =================
const DURUMLAR = {
  durdu: ["", "Kapalı", "Başlamaya hazır", "Filmi, diziyi ya da oyunu açın, sonra Başlat'a basın. İngilizce altyazı çıktığı anda Türkçesi üstünde belirir.",
          "Konsolu ve OBS'i açın, sonra Başlat'a basın. Türkçe yazı OBS'teki görüntünün üstünde görünür."],
  basliyor: ["sari", "Başlıyor", "Hazırlanıyor…", "Yazı okuma ve çeviri modelleri yükleniyor."],
  calisiyor: ["yesil", "Çalışıyor", "Altyazılar çevriliyor", "Ekrandaki İngilizce altyazılar Türkçe olarak üstünde görünüyor."],
  hata: ["kirmizi", "Durdu", "Bir sorun var", "Aşağıdaki açıklamaya bakın, sonra yeniden başlatın."],
};
let motorDurum = "durdu", sonSatirImza = "";

function modGoster() {
  const yazi = G.altyazi_goster !== false, ses = !!(durum.dublaj || {}).acik;
  secimIsaretle($("mod"), ses ? (yazi ? "ikisi" : "ses") : "altyazi");
  if ($("d-acik")) $("d-acik").checked = ses;
}

async function ozetYenile() {
  let m;
  try { m = await api("/api/motor/ozet"); } catch (e) { return; }
  motorDurum = m.durum;
  const d = DURUMLAR[m.durum] || DURUMLAR.durdu;
  $("ana-nokta").className = $("menu-nokta").className = "nokta " + d[0];
  $("ana-durum").textContent = $("menu-durum-yazi").textContent = d[1];
  $("ana-baslik").textContent = d[2];
  $("ana-aciklama").textContent = (durum.senaryo === "konsol_obs" && d[4]) || d[3];
  const acik = m.durum === "calisiyor" || m.durum === "basliyor";
  const dugme = $("ana-dugme");
  dugme.textContent = acik ? "Durdur" : "Başlat";
  dugme.className = "dugme buyuk " + (acik ? "kirmizi" : "ana");
  uyari("u-hata", m.hata || durum.overlay_hatasi || "");
  const u = m.ceviri_uyari;
  uyari("u-ceviri", m.ceviri_hatasi || (u ? u.asil + " çalışmıyor; çeviri " + u.aktif + " ile devam ediyor. Neden: " + u.neden : ""));
  const h = m.hiz || {};
  $("o-okuma").textContent = h.ocr_ms != null ? h.ocr_ms : "–";
  $("o-ceviri").textContent = h.ceviri_ms != null ? h.ceviri_ms : "–";
  $("o-okunan").textContent = (m.sayac || {}).okunan || 0;
  $("o-motor").textContent = ({ cevrimdisi: "Hazır çeviri" })[m.motor] || (durum.motor_adlari || {})[m.motor] || m.motor || "–";
  // Seslendirmeyi şu an hangi ses okuyor? (Windows sesi yalnız yedektir: doğal ses hazır değilken okur)
  const db = m.dublaj || {}, okuyan = { "dogal:hafif": "Doğal ses (hafif model)", "dogal:guclu": "Doğal ses (güçlü model)", windows: "Windows sesi (yedek; doğal ses hazır değil)" };
  $("ana-ses-bilgi").textContent = db.acik && db.son_okuyan ? "Okuyan ses: " + (okuyan[db.son_okuyan] || db.son_okuyan) : "";
  const gecisNotu = db.acik && db.dogal && db.dogal.not ? db.dogal.not : "";
  if (gecisNotu || !durum.katman_notu) uyari("u-not", gecisNotu);
  if ($("d-gecis-not")) uyari("d-gecis-not", gecisNotu);
  const gecmis = (m.gecmis || []).slice().reverse();
  const imza = gecmis.map((g) => g.id + g.tr).join("|");
  if (imza !== sonSatirImza) {
    sonSatirImza = imza;
    const kutu = $("satirlar");
    kutu.textContent = "";
    if (!gecmis.length) kutu.appendChild(el("div", "bos-not", "Henüz altyazı yok. Başlattıktan sonra çevrilen satırlar burada görünür."));
    gecmis.forEach((g) => {
      const o = el("div", "satir-oge sec-yazi");
      o.appendChild(el("span", "ms", g.ms + " ms"));
      o.appendChild(el("div", "tr", g.tr));
      o.appendChild(el("div", "en", g.en));
      kutu.appendChild(o);
    });
  }
}

$("ana-dugme").onclick = () => mesgul($("ana-dugme"), async () => {
  const acik = motorDurum === "calisiyor" || motorDurum === "basliyor";
  await api(acik ? "/api/motor/durdur" : "/api/motor/baslat");
  await ozetYenile();
});
hepsi("#mod button").forEach((b) => (b.onclick = () => modSec(b.dataset.v)));
async function modSec(mod) {
  try {
    await api("/api/mod", { mod });
    durum.dublaj = Object.assign({}, durum.dublaj, { acik: mod !== "altyazi" });
    G.altyazi_goster = mod !== "ses";
    modGoster();
  } catch (e) { hataGoster(e); modGoster(); }
}

// ================= görüntü kaynağı: bu bilgisayarın ekranı / konsol + OBS =================
let obsZ = null, obsKatmanEklendi = false;
const obsModu = () => durum.senaryo === "konsol_obs";

function kaynakTuruGoster() {
  const obs = obsModu();
  secimIsaretle($("kt-tur"), obs ? "konsol_obs" : "pc");
  $("obs-kartlari").style.display = obs ? "" : "none";
  $("ekran-karti").style.display = obs ? "none" : "";
  $("te-kart").style.display = obs ? "none" : "";  // tüm ekran kipi yalnız bu bilgisayarın ekranında
  $("kt-aciklama").textContent = obs
    ? "Konsol → capture card → OBS. Görüntü OBS'ten alınır; Türkçe yazı OBS'teki görüntünün üstünde (yayında ve tam ekran projektörde) görünür."
    : "Film, dizi, video ya da bilgisayar oyunu: bu bilgisayarın ekranı okunur, Türkçe yazı ekranın üstüne yazılır.";
  if (obs) obsKontrol(); else clearTimeout(obsZ);
}
hepsi("#kt-tur button").forEach((b) => (b.onclick = async () => {
  if (b.dataset.v === durum.senaryo) return;
  try {
    await api("/api/senaryo", { senaryo: b.dataset.v });
    durum.senaryo = b.dataset.v; durum.kaynak_tip = b.dataset.v === "pc" ? "ekran" : "obs";
    if (durum.tam_ekran && b.dataset.v !== "pc") durum.tam_ekran.acik = false;
    $("cizim-resim").removeAttribute("src");
    kaynakTuruGoster(); tamEkranGoster();
    if (b.dataset.v === "pc") { await ekranlariYukle(); await goruntuAl(); }
  } catch (e) { hataGoster(e); }
}));

async function obsKontrol() {
  clearTimeout(obsZ);
  if (!obsModu() || !$("s-alan").classList.contains("aktif")) return;
  let j;
  try { j = await api("/api/obs/otomatik"); } catch (e) { $("obs-durum").textContent = e.message; return; }
  const ws = j.websocket && j.websocket.etkin, acik = j.acik === true || j.baglandi;
  const rozet = $("obs-rozet");
  rozet.className = "rozet " + (j.baglandi ? "yesil" : "sari");
  rozet.textContent = j.baglandi ? "Bağlandı" : !j.kurulu ? "OBS yok" : !acik ? "OBS kapalı" : !ws ? "WebSocket kapalı" : "Bağlanamadı";
  $("obs-yok-yardim").classList.toggle("acik", !j.kurulu && !j.baglandi);
  $("obs-ws-yardim").classList.toggle("acik", !!j.kurulu && acik && !ws && !j.baglandi);
  $("obs-durum").textContent = j.baglandi ? "OBS'e bağlandım. Aşağıdan konsolun görüntüsünü seçin."
    : !j.kurulu ? "" : !acik ? "OBS'i açın (masaüstündeki OBS Studio simgesi); açılınca kendiliğinden bağlanırım."
    : !ws ? "" : (j.hata || "OBS'e bağlanılamadı; kapı ve şifreyi elle girmeyi deneyin.");
  const onceBagli = durum.obs && durum.obs.baglandi;
  durum.obs = Object.assign({}, durum.obs, { baglandi: !!j.baglandi });
  if (j.baglandi && !onceBagli) { await obsKaynaklar(); obsMonitorler(); }
  if (!j.baglandi) obsZ = setTimeout(obsKontrol, 2500);  // kullanıcı OBS'i açınca / kutuyu işaretleyince kendiliğinden
}
$("obs-yenile").onclick = () => { durum.obs = Object.assign({}, durum.obs, { baglandi: false }); obsKontrol(); };
$("obs-indir").onclick = () => api("/api/disari_ac", { url: "https://obsproject.com/" }).catch(hataGoster);
$("obs-baglan").onclick = () => mesgul($("obs-baglan"), async () => {
  await api("/api/obs/baglan", { port: $("obs-port").value.trim() || 4455, sifre: $("obs-sifre").value });
  durum.obs = Object.assign({}, durum.obs, { baglandi: false });
  await obsKontrol();
  bildir("OBS'e bağlandı.");
});

async function obsKaynaklar() {
  const kutu = $("obs-kaynaklar");
  let j;
  try { j = await api("/api/obs/kaynaklar"); } catch (e) { kutu.textContent = ""; kutu.appendChild(el("div", "bos-not", e.message)); return; }
  kutu.textContent = "";
  if (!j.kaynaklar.length) {
    kutu.appendChild(el("div", "bos-not", "OBS'te görüntü kaynağı yok. OBS'te Kaynaklar → + → Video Yakalama Aygıtı ile capture card'ı ekleyip Yenile'ye basın."));
    return;
  }
  let secili = j.secili;
  if (!secili && j.onerilen) { secili = j.onerilen; await obsKaynakSec(j.onerilen, false); }
  j.kaynaklar.forEach((k) => {
    const b = el("button", "ekran-oge" + (k.ad === secili ? " secili" : "")); b.dataset.ad = k.ad;
    const r = el("img"); r.src = k.resim; b.appendChild(r);
    b.appendChild(el("span", "", k.ad + (k.ad === j.onerilen ? " · oyun bu gibi" : "")));
    b.onclick = () => obsKaynakSec(k.ad, true);
    kutu.appendChild(b);
  });
  if (secili) await goruntuAl();
}
$("obs-kaynak-yenile").onclick = () => mesgul($("obs-kaynak-yenile"), obsKaynaklar);

async function obsKaynakSec(ad, goruntu) {
  try {
    await api("/api/obs/kaynak_sec", { ad });
    durum.obs = Object.assign({}, durum.obs, { kaynak_adi: ad });
    hepsi("#obs-kaynaklar .ekran-oge").forEach((x) => x.classList.toggle("secili", x.dataset.ad === ad));
    if (goruntu) await goruntuAl();
  } catch (e) { hataGoster(e); }
}

async function obsKatmanEkle(sessiz) {
  const j = await api("/api/obs/altyazi_ekle", {});
  obsKatmanEklendi = true;
  $("obs-katman-durum").textContent = "Türkçe yazı katmanı OBS'teki “" + j.sahne + "” sahnesine eklendi.";
  if (!sessiz) bildir("Türkçe yazı OBS'e eklendi.");
}
$("obs-katman").onclick = () => mesgul($("obs-katman"), () => obsKatmanEkle(false));

async function obsMonitorler() {
  const kutu = $("obs-monitorler");
  kutu.textContent = "";
  try {
    const j = await api("/api/obs/monitorler");
    j.monitorler.forEach((m) => {
      const b = el("button", "dugme kucuk", (m.index + 1) + ". ekran" + (m.genislik ? " (" + m.genislik + "×" + m.yukseklik + ")" : ""));
      b.onclick = () => mesgul(b, async () => {
        if (!obsKatmanEklendi) await obsKatmanEkle(true);
        await api("/api/obs/projektor_ac", { index: m.index });
        $("obs-projektor-durum").textContent = "Oyun " + (m.index + 1) + ". ekranda tam ekran açıldı; Türkçe yazı orada görünür. Kapatmak için o ekranda Esc.";
      });
      kutu.appendChild(b);
    });
  } catch (e) {}
}

// ================= ne çevrilsin: seçilen alanlar / tüm ekran =================
function tamEkranGoster() {
  const t = durum.tam_ekran || {}, acik = !!t.acik && !obsModu();
  secimIsaretle($("te-kip"), acik ? "tam" : "alan");
  secimIsaretle($("te-yerlesim"), t.yerlesim || "ustune");
  secimIsaretle($("te-aralik"), String(+(t.aralik || 1)));
  $("te-secenekler").style.display = acik ? "" : "none";
  $("alan-kartlari").style.display = acik && !kurulumModu ? "none" : "";
  $("te-aciklama").textContent = acik ? "Ekranın tamamı taranıyor: bulunan her İngilizce yazı çevrilir."
    : "Yalnız aşağıda gösterdiğiniz alan(lar) çevrilir: altyazı için en hızlısı.";
}
async function tamEkranAyarla(v) {
  try { durum.tam_ekran = (await api("/api/tam_ekran", v)).tam_ekran; } catch (e) { hataGoster(e); }
  tamEkranGoster();
}
hepsi("#te-kip button").forEach((b) => (b.onclick = () => tamEkranAyarla({ acik: b.dataset.v === "tam" })));
hepsi("#te-yerlesim button").forEach((b) => (b.onclick = () => tamEkranAyarla({ yerlesim: b.dataset.v })));
hepsi("#te-aralik button").forEach((b) => (b.onclick = () => tamEkranAyarla({ aralik: +b.dataset.v })));

// ================= ekran ve altyazı alanı =================
let alanlar = [], seciliAlan = 0, alanYuklendi = false, cizim = null;

async function alanAcildi() {
  if (alanYuklendi) return;
  alanYuklendi = true;
  alanlar = [Object.assign({ ad: "Ana altyazı" }, durum.bolge)].concat((durum.ek_bolgeler || []).map((b) => Object.assign({}, b)));
  alanListesiCiz();
  kaynakTuruGoster();
  if (obsModu()) return;  // OBS: bağlanınca kaynaklar ve görüntü gelir (obsKontrol)
  await ekranlariYukle();
  await goruntuAl();
}

async function ekranlariYukle() {
  const kutu = $("ekranlar");
  try {
    const j = await api("/api/ekran/listesi");
    kutu.textContent = "";
    const secili = j.secili || durum.ekran_no || 1;
    j.ekranlar.forEach((e) => {
      const b = el("button", "ekran-oge" + (e.no === secili ? " secili" : ""));
      const r = el("img"); r.src = e.resim || ""; b.appendChild(r);
      b.appendChild(el("span", "", "Ekran " + e.no + (e.ana ? " (ana)" : "") + " · " + e.genislik + "×" + e.yukseklik));
      b.onclick = async () => {
        try {
          await api("/api/ekran/sec", { no: e.no });
          durum.ekran_no = e.no;
          hepsi(".ekran-oge", kutu).forEach((x) => x.classList.toggle("secili", x === b));
          await goruntuAl();
        } catch (err) { hataGoster(err); }
      };
      kutu.appendChild(b);
    });
  } catch (e) { kutu.textContent = ""; kutu.appendChild(el("div", "bos-not", e.message)); }
}

async function goruntuAl() {
  if (obsModu() && !((durum.obs || {}).baglandi && (durum.obs || {}).kaynak_adi)) { kutulariCiz(); return; }
  try {
    const j = await api("/api/goruntu");
    $("cizim-resim").src = j.resim;
    oyunResmi = j.resim;
  } catch (e) { hataGoster(e); }
  kutulariCiz();
}

function kutulariCiz() {
  const c = $("cizim");
  hepsi(".alan-kutu", c).forEach((k) => k.remove());
  alanlar.forEach((a, i) => {
    const k = el("div", "alan-kutu" + (i ? " ek" : "") + (i === seciliAlan ? " secili" : ""));
    k.style.left = a.x * 100 + "%"; k.style.top = a.y * 100 + "%"; k.style.width = a.w * 100 + "%"; k.style.height = a.h * 100 + "%";
    k.appendChild(el("b", "", a.ad || (i ? "Alan " + (i + 1) : "Ana altyazı")));
    c.appendChild(k);
  });
}

function alanListesiCiz() {
  const kutu = $("alan-liste");
  kutu.textContent = "";
  alanlar.forEach((a, i) => {
    const o = el("div", "alan-oge" + (i === seciliAlan ? " secili" : ""));
    o.onclick = (e) => { if (e.target.tagName === "INPUT" || e.target.tagName === "BUTTON") return; seciliAlan = i; alanListesiCiz(); kutulariCiz(); };
    o.appendChild(el("span", "nokta " + (i ? "sari" : "yesil")));
    if (!i) {
      const ad = el("b", "", "Ana altyazı"); ad.style.flex = "1"; o.appendChild(ad);
      o.appendChild(el("span", "aciklama", "Oyunun konuşma altyazısı"));
    } else {
      const ad = el("input"); ad.type = "text"; ad.value = a.ad || ""; ad.maxLength = 40;
      ad.oninput = () => { a.ad = ad.value; kutulariCiz(); };
      o.appendChild(ad);
      const etiket = el("label", "sira aciklama"); etiket.style.gap = "6px";
      const kutucuk = el("input"); kutucuk.type = "checkbox"; kutucuk.checked = !!a.seslendir;
      kutucuk.onchange = () => { a.seslendir = kutucuk.checked; };
      etiket.appendChild(kutucuk); etiket.appendChild(document.createTextNode("Sesli oku"));
      o.appendChild(etiket);
      const sil = el("button", "dugme kucuk", "Sil");
      sil.onclick = () => { alanlar.splice(i, 1); seciliAlan = 0; alanListesiCiz(); kutulariCiz(); };
      o.appendChild(sil);
    }
    kutu.appendChild(o);
  });
  $("al-ekle").disabled = alanlar.length > 6;
}

const sinir = (d, az, cok) => Math.max(az, Math.min(cok, d));
function normal(e, kutu) {
  const r = kutu.getBoundingClientRect();
  return [sinir((e.clientX - r.left) / r.width, 0, 1), sinir((e.clientY - r.top) / r.height, 0, 1)];
}
$("cizim").addEventListener("mousedown", (e) => {
  const [x, y] = normal(e, $("cizim"));
  cizim = { x, y, eski: Object.assign({}, alanlar[seciliAlan]) };
  e.preventDefault();
});
window.addEventListener("mousemove", (e) => {
  if (cizim) {
    const [x, y] = normal(e, $("cizim")), a = alanlar[seciliAlan];
    a.x = +Math.min(x, cizim.x).toFixed(4); a.y = +Math.min(y, cizim.y).toFixed(4);
    a.w = +Math.abs(x - cizim.x).toFixed(4); a.h = +Math.abs(y - cizim.y).toFixed(4);
    kutulariCiz();
  }
  if (surukleme) onizlemeSurukle(e);
});
window.addEventListener("mouseup", () => {
  if (cizim) {
    const a = alanlar[seciliAlan];
    if (a.w < 0.02 || a.h < 0.015) Object.assign(a, cizim.eski);  // tıklama ya da çok küçük kutu: eskisi kalır
    cizim = null; kutulariCiz();
    $("al-durum").textContent = "Kaydetmeyi unutmayın.";
  }
  if (surukleme) { surukleme = false; $("onizleme").classList.remove("surukle"); }
});

function alanSonuc(metin, iyi) {
  const s = $("al-sonuc");
  s.textContent = metin; s.classList.add("acik");
  s.style.borderColor = iyi ? "rgba(61,220,151,.5)" : "rgba(255,184,74,.5)";
}
$("al-yenile").onclick = () => mesgul($("al-yenile"), goruntuAl);
$("al-bul").onclick = () => mesgul($("al-bul"), async () => {
  const j = await api("/api/bolge_bul");
  Object.assign(alanlar[0], j.bolge);
  seciliAlan = 0;
  $("cizim-resim").src = j.resim;
  alanListesiCiz(); kutulariCiz();
  alanSonuc("Altyazı bulundu: “" + j.metin + "”", true);
  $("al-durum").textContent = "Kaydetmeyi unutmayın.";
});
$("al-dene").onclick = () => mesgul($("al-dene"), async () => {
  const a = alanlar[seciliAlan], bolge = { x: a.x, y: a.y, w: a.w, h: a.h };
  const j = await api(seciliAlan ? "/api/alanlar/dene" : "/api/okuma_testi", { bolge });
  if (j.metin && (seciliAlan || j.anlamli)) alanSonuc("Okunan yazı: “" + j.metin + "”", true);
  else alanSonuc("Bu alanda yazı okunamadı. Oyunda altyazı görünürken “Görüntüyü yenile”ye basıp tekrar deneyin ya da kutuyu altyazının üstüne çizin.", false);
});
$("al-ekle").onclick = () => {
  alanlar.push({ ad: "Alan " + (alanlar.length + 1), x: 0.03, y: 0.05, w: 0.3, h: 0.1, seslendir: false });
  seciliAlan = alanlar.length - 1;
  alanListesiCiz(); kutulariCiz();
  bildir("Görüntünün üstünde fareyle bu alanın kutusunu çizin.");
};
$("al-kaydet").onclick = () => mesgul($("al-kaydet"), async () => {
  const a = alanlar[0];
  if (obsModu()) {
    if (!(durum.obs || {}).baglandi) throw new Error("Önce OBS'e bağlanılmalı (OBS açık ve WebSocket etkin olmalı).");
    if (!(durum.obs || {}).kaynak_adi) throw new Error("Önce OBS'teki oyun görüntüsünü (capture card) seçin.");
    if (!obsKatmanEklendi && kurulumModu) await obsKatmanEkle(true);  // Türkçe yazı OBS'te görünsün
  }
  await api("/api/bolge_kaydet", { bolge: { x: a.x, y: a.y, w: a.w, h: a.h } });
  const j = await api("/api/alanlar/kaydet", { ek_bolgeler: alanlar.slice(1) });
  durum.bolge = { x: a.x, y: a.y, w: a.w, h: a.h };
  durum.ek_bolgeler = j.ek_bolgeler;
  alanlar = [alanlar[0]].concat(j.ek_bolgeler.map((b) => Object.assign({}, b)));  // alanların görünümü korunur
  $("al-durum").textContent = "";
  if (kurulumModu) {
    await api("/api/bitir");
    kurulumBitti();
    sayfaAc("ana");
    bildir("Kurulum tamam. Oyunu açıp Başlat'a basın.");
  } else bildir("Kaydedildi.");
});

function kurulumBitti() {
  kurulumModu = false; durum.kurulum_tamam = true;
  tamEkranGoster();
  hepsi("#nav button").forEach((b) => (b.disabled = false));
  $("kurulum-adimlar").style.display = "none";
  $("al-kaydet").textContent = "Kaydet";
}

// ================= görünüm =================
const RENK_LISTELERI = {
  RENKLER: AltyaziStil.RENKLER, KUTU_RENKLERI: AltyaziStil.KUTU_RENKLERI,
  KENAR_RENKLERI: [["#000000", "Siyah"], ["#ffffff", "Beyaz"], ["#14213d", "Lacivert"], ["#5a0d0d", "Bordo"], ["#0f2e1c", "Koyu yeşil"]],
  KAPAK_RENKLERI: [["#08080a", "Siyah"], ["#14213d", "Lacivert"], ["#2b2b33", "Gri"], ["#3a0d0d", "Bordo"]],
  ING_RENKLERI: [["#d9d9d9", "Açık gri"], ["#ffffff", "Beyaz"], ["#ffe04a", "Sarı"], ["#9fd8ff", "Açık mavi"]],
  ETIKET_RENKLERI: [["#ffe04a", "Sarı"], ["#9fd8ff", "Açık mavi"], ["#a8f0a0", "Yeşil"], ["#ffb86b", "Turuncu"], ["#ffb3d9", "Pembe"]],
};
const STIL_ANAHTARLARI = Object.keys(AltyaziStil.VARSAYILAN).concat(["orijinali_kapat", "ingilizce_goster"]);
const cqw = (px) => (px / 19.2).toFixed(3) + "cqw";  // 1080p pikseli -> önizleme genişliğinin yüzdesi
let onEl = null, kayitZ = null, surukleme = false, oyunResmi = "", yaziTipleriYuklendi = false, sonKayit = 0;

// Görünüm sayfası hangi alanı düzenliyor: 0 = ana altyazı, 1.. = ek alanlar (her birinin kendi görünümü olabilir)
let gorunumHedef = 0;
const ekBoyut = (b) => Math.round(Math.min(durum.goruntu.yazi_boyutu * 0.8, Math.max(18, b.h * 1080 * 0.42)));
const hedefBolge = () => (gorunumHedef ? (durum.ek_bolgeler || [])[gorunumHedef - 1] : null) || durum.bolge;

function hedefAyari() {
  if (!gorunumHedef) return Object.assign({}, durum.goruntu);
  const b = durum.ek_bolgeler[gorunumHedef - 1];
  // ayarlanmamış ek alan: kendi yerinde, üstü kapalı, ana altyazının yazı tipi ve rengiyle
  return Object.assign({}, durum.goruntu, { orijinali_kapat: true, konum: "orijinal", yazi_boyutu: ekBoyut(b) }, b.gorunum || {});
}

function hedefleriCiz() {
  const ekler = durum.ek_bolgeler || [], kutu = $("g-hedef");
  if (gorunumHedef > ekler.length) gorunumHedef = 0;
  $("g-hedef-kart").style.display = ekler.length ? "" : "none";
  kutu.textContent = "";
  [{ ad: "Ana altyazı" }].concat(ekler).forEach((b, i) => {
    const d = el("button", i === gorunumHedef ? "secili" : "", b.ad || "Alan " + (i + 1)); d.dataset.v = String(i);
    d.onclick = () => { gorunumHedef = i; G = hedefAyari(); hedefleriCiz(); gorunumDoldur(); onizle(); };
    kutu.appendChild(d);
  });
}

function gorunumKaydet() {
  clearTimeout(kayitZ);
  sonKayit = Date.now();
  const hedef = gorunumHedef;
  kayitZ = setTimeout(async () => {
    const v = { ornek: true };
    STIL_ANAHTARLARI.forEach((k) => (v[k] = G[k]));
    try {
      if (hedef) durum.ek_bolgeler = (await api("/api/alan_gorunum", { no: hedef, gorunum: v, ornek: true })).ek_bolgeler;
      else durum.goruntu = (await api("/api/gorunum_kaydet", v)).goruntu;
    } catch (e) { hataGoster(e); }
    sonKayit = Date.now();
  }, 160);
}
function gorunumDegisti(k, deger) { G[k] = deger; gorunumDoldur(); onizle(); gorunumKaydet(); }

function araliklariYaz(girdi) {
  const d = +girdi.value * (+girdi.dataset.carp || 1), ondalik = +girdi.dataset.ondalik || 0;
  girdi.nextElementSibling.textContent = d.toFixed(ondalik) + (girdi.dataset.birim || "");
}

function gorunumKur() {
  const tip = $("g-yazi-tipi");
  Object.keys(AltyaziStil.YAZI_TIPLERI).forEach((k) => { const o = el("option", "", AltyaziStil.YAZI_TIPLERI[k].ad); o.value = k; tip.appendChild(o); });
  hepsi("input[type=range][data-g]").forEach((g) => (g.oninput = () => { G[g.dataset.g] = +g.value; araliklariYaz(g); onizle(); gorunumKaydet(); }));
  hepsi("input[type=checkbox][data-g]").forEach((g) => (g.onchange = () => gorunumDegisti(g.dataset.g, g.checked)));
  hepsi("select[data-g]").forEach((g) => (g.onchange = () => {
    if (g.dataset.g === "yazi_tipi" && g.value === "ozel") yaziTipleriYukle(true);
    gorunumDegisti(g.dataset.g, g.value);
  }));
  hepsi(".secim[data-g]").forEach((s) => hepsi("button", s).forEach((b) => (b.onclick = () => gorunumDegisti(s.dataset.g, b.dataset.v))));
  hepsi(".renkler").forEach((kutu) => {
    const alan = kutu.dataset.renk;
    if (kutu.dataset.bos) {
      const b = el("button", "dugme kucuk", kutu.dataset.bos); b.dataset.v = ""; b.style.width = "auto"; b.style.height = "28px"; b.style.borderRadius = "8px";
      b.onclick = () => gorunumDegisti(alan, "");
      kutu.appendChild(b);
    }
    RENK_LISTELERI[kutu.dataset.liste].forEach(([renk, ad]) => {
      const b = el("button"); b.style.background = renk; b.title = ad; b.dataset.v = renk;
      b.onclick = () => gorunumDegisti(alan, renk);
      kutu.appendChild(b);
    });
    const ozel = el("input"); ozel.type = "color"; ozel.title = "Başka bir renk seç";
    ozel.oninput = () => gorunumDegisti(alan, ozel.value);
    kutu.appendChild(ozel);
  });
  const konum = $("g-konum");
  AltyaziStil.HAZIR_KONUMLAR.forEach((k) => {
    const b = el("button", "", k.ad); b.dataset.v = k.id;
    b.onclick = () => { Object.assign(G, k.ayar); gorunumDoldur(); onizle(); gorunumKaydet(); };
    konum.appendChild(b);
  });
  const hazir = $("g-hazir");
  (durum.hazir_gorunumler || []).forEach((h) => {
    const acikZemin = h.ayar.yazi_rengi === "#101014" && !(h.ayar.kutu_saydamlik > 0);
    const b = el("button", "hazir" + (acikZemin ? " acik-zemin" : "")); b.dataset.v = h.id; b.title = h.ad;
    const ic = AltyaziStil.kur(b);
    AltyaziStil.uygula(ic, Object.assign({}, AltyaziStil.VARSAYILAN, h.ayar, { kutu_bicimi: "sar" }), (px) => (px * 0.34).toFixed(2) + "px", 44);
    ic.tr.textContent = h.ad; ic.en.style.display = "none";
    b.onclick = () => { Object.assign(G, h.ayar); gorunumDoldur(); onizle(); gorunumKaydet(); };
    hazir.appendChild(b);
  });
  hepsi("#on-zemin button").forEach((b) => (b.onclick = async () => {
    if (b.dataset.v === "oyun" && !oyunResmi) {
      try { oyunResmi = (await api("/api/goruntu")).resim; } catch (e) { return hataGoster(e); }
    }
    secimIsaretle($("on-zemin"), b.dataset.v);
    const arka = $("on-arka");
    arka.className = b.dataset.v === "oyun" ? "" : b.dataset.v;
    arka.style.backgroundImage = b.dataset.v === "oyun" ? "url(" + oyunResmi + ")" : "";
    onizle();
  }));
  $("g-serit-kaldir").onclick = () => gorunumDegisti("orijinali_kapat", false);
  $("g-sifirla").onclick = async () => {
    if (gorunumHedef) {  // ek alan: kendi görünümü silinir, varsayılana (kendi yerinde, üstü kapalı) döner
      clearTimeout(kayitZ);
      try { durum.ek_bolgeler = (await api("/api/alan_gorunum", { no: gorunumHedef, gorunum: null })).ek_bolgeler; } catch (e) { hataGoster(e); }
      G = hedefAyari();
      gorunumDoldur(); onizle();
      return;
    }
    Object.assign(G, AltyaziStil.VARSAYILAN, { orijinali_kapat: true, ingilizce_goster: false });
    gorunumDoldur(); onizle(); gorunumKaydet();
  };
  $("onizleme").addEventListener("mousedown", (e) => { surukleme = true; $("onizleme").classList.add("surukle"); onizlemeSurukle(e); e.preventDefault(); });
  onEl = AltyaziStil.kur($("on-kutu"));
}

function onizlemeSurukle(e) {
  const [x, y] = normal(e, $("onizleme"));
  G.konum = "serbest";
  G.konum_x = +sinir(x, AltyaziStil.SINIR.konum_x[0], AltyaziStil.SINIR.konum_x[1]).toFixed(3);
  G.konum_y = +sinir(y, AltyaziStil.SINIR.konum_y[0], AltyaziStil.SINIR.konum_y[1]).toFixed(3);
  gorunumDoldur(); onizle(); gorunumKaydet();
}

async function yaziTipleriYukle(ilkiniSec) {
  const secim = $("g-ozel");
  if (!yaziTipleriYuklendi) {
    yaziTipleriYuklendi = true;
    try {
      const j = await api("/api/yazi_tipleri");
      j.yazi_tipleri.forEach((ad) => { const o = el("option", "", ad); o.value = ad; o.style.fontFamily = '"' + ad + '"'; secim.appendChild(o); });
    } catch (e) { hataGoster(e); }
  }
  if (ilkiniSec && !G.yazi_tipi_ozel && secim.options.length) {
    G.yazi_tipi_ozel = (Array.from(secim.options).find((o) => o.value === "Segoe UI") || secim.options[0]).value;
    gorunumDoldur(); onizle(); gorunumKaydet();
  }
  secim.value = G.yazi_tipi_ozel || "";
}

function gorunumDoldur() {
  const a = AltyaziStil.tamamla(G);
  hepsi("input[type=range][data-g]").forEach((g) => { g.value = a[g.dataset.g]; araliklariYaz(g); });
  hepsi("input[type=checkbox][data-g]").forEach((g) => (g.checked = !!(g.dataset.g in a ? a[g.dataset.g] : G[g.dataset.g])));
  hepsi("select[data-g]").forEach((g) => (g.value = a[g.dataset.g]));
  hepsi(".secim[data-g]").forEach((s) => secimIsaretle(s, a[s.dataset.g]));
  hepsi(".renkler").forEach((kutu) => {
    const deger = String(a[kutu.dataset.renk] || "").toLowerCase();
    hepsi("button", kutu).forEach((b) => b.classList.toggle("secili", b.dataset.v === deger));
    const ozel = kutu.querySelector("input[type=color]");
    if (deger) ozel.value = deger;
  });
  $("g-ozel-satir").style.display = a.yazi_tipi === "ozel" ? "" : "none";
  $("g-serit-not").classList.toggle("acik", AltyaziStil.seritIcinde(G));
  if (a.yazi_tipi === "ozel") yaziTipleriYukle(false);
  const konumId = a.konum === "orijinal" ? "orijinal" :
    (AltyaziStil.HAZIR_KONUMLAR.find((k) => k.ayar.konum === "serbest" && Math.abs(k.ayar.konum_x - a.konum_x) < 0.005 && Math.abs(k.ayar.konum_y - a.konum_y) < 0.005) || {}).id;
  secimIsaretle($("g-konum"), konumId || "");
  hepsi("#g-hazir .hazir").forEach((b) => {
    const h = (durum.hazir_gorunumler || []).find((x) => x.id === b.dataset.v);
    b.classList.toggle("secili", !!h && Object.keys(h.ayar).every((k) => a[k] === h.ayar[k]));
  });
}

function onizle() {
  if (!onEl || !G) return;
  const b = hedefBolge(), y = AltyaziStil.yerlesim(G, b);
  const ing = $("on-ing"), kapak = $("on-kapak"), kutu = $("on-kutu");
  Object.assign(ing.style, { left: b.x * 100 + "%", top: b.y * 100 + "%", width: b.w * 100 + "%", height: b.h * 100 + "%", zIndex: 1 });
  ing.textContent = durum.ornek.en;
  kapak.style.display = y.kapak ? "block" : "none"; kapak.style.zIndex = 2;
  if (y.kapak) Object.assign(kapak.style, y.kapak);
  Object.assign(kutu.style, { flexDirection: "", justifyContent: "", zIndex: 3 }, y.kutu, { display: y.goster });
  AltyaziStil.uygula(onEl, G, cqw);
  AltyaziStil.yaz(onEl, (G.etiket_rengi ? "LUCIA: " : "") + durum.ornek.tr, durum.ornek.en, G);
  onEl.en.style.display = G.ingilizce_goster ? "block" : "none";
  kutu.style.opacity = G.altyazi_goster === false ? "0.25" : "1";
}

// ================= çeviri =================
const MOTORLAR = [
  { id: "cevrimdisi", ad: "Hazır çeviri", rozet: ["yesil", "En hızlı · İnternetsiz · Ücretsiz"], anahtarsiz: true,
    ozet: "Bilgisayarınızda çalışır; yaklaşık 0,1 saniyede çevirir. Hiçbir şey yapmanız gerekmez, metin bilgisayarınızdan çıkmaz." },
  { id: "gemini", ad: "Google Gemini", rozet: ["mavi", "Ücretsiz anahtar"],
    ozet: "Argo ve uzun cümlelerde daha doğal Türkçe. Google hesabıyla 1 dakikada ücretsiz anahtar alınır.",
    adimlar: ["“Anahtar sayfasını aç” düğmesine basın ve Google hesabınızla girin.", "“Create API key” düğmesine basın.", "Çıkan anahtarı kopyalayıp aşağıya yapıştırın."],
    not: "Ücretsiz kullanımda dakikada belirli sayıda çeviri hakkı vardır; Google gönderilen metni hizmetini geliştirmek için kullanabilir." },
  { id: "groq", ad: "Groq", rozet: ["mavi", "Ücretsiz anahtar"],
    ozet: "İnternetli servislerin en hızlılarından. Ücretsiz anahtar, kart istemez.",
    adimlar: ["“Anahtar sayfasını aç” düğmesine basın ve giriş yapın.", "“Create API Key” düğmesine basın, bir ad yazın.", "Anahtarı kopyalayıp aşağıya yapıştırın (yalnızca bir kez gösterilir)."],
    not: "Ücretsiz kullanımda dakikada ve günde belirli sayıda istek hakkı vardır." },
  { id: "deepl", ad: "DeepL", rozet: ["", "Ayda 500 bin karakter ücretsiz"],
    ozet: "Düzgün dilbilgisi. Kayıtta kart doğrulaması ister, ücretsiz planda ücret alınmaz.",
    adimlar: ["“Anahtar sayfasını aç” → DeepL API Free planına kaydolun.", "Hesap → API Keys bölümünden anahtarı kopyalayın.", "Aşağıya yapıştırın (sonu :fx ile biter)."] },
  { id: "claude", ad: "Claude", rozet: ["", "Ücretli"],
    ozet: "Argo ve esprileri iyi aktarır. Kullandıkça ödenir.",
    adimlar: ["“Anahtar sayfasını aç” → Anthropic Console'a girin.", "Billing bölümünden bakiye yükleyin, API Keys → Create Key.", "Anahtarı kopyalayıp aşağıya yapıştırın."] },
  { id: "llm", ad: "Bilgisayarımdaki yapay zekâ (Ollama)", rozet: ["", "İnternetsiz · Ekran kartı ister"], anahtarsiz: true, yerel: true,
    ozet: "Ollama gibi bir programla bilgisayarınızda çalışan dil modelini kullanır. Güçlü ekran kartında doğal çeviri verir; Hazır çeviriden yavaştır." },
];

function motorlariCiz() {
  const kutu = $("motorlar"), c = durum.ceviri;
  kutu.textContent = "";
  MOTORLAR.forEach((m) => {
    const secili = c.motor === m.id;
    const kart = el("div", "kart" + (secili ? " secili-motor" : ""));
    const ust = el("div", "motor"), sol = el("div");
    const baslik = el("h3", "", m.ad);
    baslik.appendChild(el("span", "rozet " + m.rozet[0], m.rozet[1]));
    if (secili) baslik.appendChild(el("span", "rozet yesil", "Kullanılıyor"));
    else if (!m.anahtarsiz && c.anahtar_var[m.id]) baslik.appendChild(el("span", "rozet", "Anahtar kayıtlı"));
    sol.appendChild(baslik); sol.appendChild(el("div", "aciklama", m.ozet));
    ust.appendChild(sol);
    const ayrinti = el("div", "motor-ayrinti"), sonuc = el("div", "sonuc-kutu sec-yazi");
    const dene = async (dugme, ek) => mesgul(dugme, async () => {
      const j = await api("/api/ceviri_testi", Object.assign({ motor: m.id }, ek || {}));
      durum.ceviri.motor = m.id;
      if (ek && ek.anahtarlar) durum.ceviri.anahtar_var[m.id] = true;
      motorlariCiz();
      bildir(m.ad + " kullanılıyor · “" + j.ceviri + "” (" + j.sure_ms + " ms)");
    });
    if (m.id === "cevrimdisi") {
      const b = el("button", "dugme kucuk" + (secili ? "" : " ana"), secili ? "Yeniden dene" : "Kullan");
      b.onclick = () => dene(b);
      ust.appendChild(b);
    } else {
      const ac = el("button", "dugme kucuk", secili ? "Ayarlar" : "Ayarla");
      ac.onclick = () => ayrinti.classList.toggle("acik");
      ust.appendChild(ac);
      if (m.yerel) {
        ayrinti.appendChild(el("div", "aciklama", "Ollama'yı kurup bir model indirin (ör. komut satırında: ollama pull qwen2.5:7b), sonra model adını yazıp deneyin."));
        const satir = el("div", "sira"); satir.style.marginTop = "8px";
        const model = el("input"); model.type = "text"; model.placeholder = "Model adı"; model.value = c.llm_model || ""; model.style.width = "200px";
        const adres = el("input"); adres.type = "text"; adres.placeholder = "Adres"; adres.value = c.llm_url || ""; adres.style.flex = "1";
        const b = el("button", "dugme kucuk ana", "Dene ve kullan");
        b.onclick = async () => { await dene(b, { llm_model: model.value.trim(), llm_url: adres.value.trim() }); durum.ceviri.llm_model = model.value.trim(); durum.ceviri.llm_url = adres.value.trim(); };
        satir.appendChild(model); satir.appendChild(adres); satir.appendChild(b);
        ayrinti.appendChild(satir);
      } else {
        const liste = el("ol"); (m.adimlar || []).forEach((a) => liste.appendChild(el("li", "", a)));
        ayrinti.appendChild(liste);
        const satir = el("div", "sira");
        const anahtar = el("input"); anahtar.type = "password"; anahtar.style.flex = "1"; anahtar.autocomplete = "off";
        anahtar.placeholder = c.anahtar_var[m.id] ? "Kayıtlı anahtar kullanılacak (değiştirmek için yenisini yapıştırın)" : "Anahtarı buraya yapıştırın";
        const sayfa = el("button", "dugme kucuk", "Anahtar sayfasını aç");
        sayfa.onclick = () => api("/api/disari_ac", { url: (durum.anahtar_sayfalari || {})[m.id] }).catch(hataGoster);
        const b = el("button", "dugme kucuk ana", "Dene ve kullan");
        b.onclick = () => {
          const deger = anahtar.value.trim();
          if (!deger && !c.anahtar_var[m.id]) return bildir("Önce anahtarı yapıştırın.", true);
          dene(b, deger ? { anahtarlar: { [m.id]: deger } } : {});
        };
        satir.appendChild(anahtar); satir.appendChild(sayfa); satir.appendChild(b);
        ayrinti.appendChild(satir);
        if (m.not) { const n = el("div", "aciklama", m.not); n.style.marginTop = "8px"; ayrinti.appendChild(n); }
      }
    }
    kart.appendChild(ust); kart.appendChild(ayrinti); kart.appendChild(sonuc);
    kutu.appendChild(kart);
  });
  $("c-yedek").checked = !!c.yedek_motor;
}
$("c-yedek").onchange = () => api("/api/ceviri_ayarla", { yedek_motor: $("c-yedek").checked ? "cevrimdisi" : "" })
  .then(() => { durum.ceviri.yedek_motor = $("c-yedek").checked ? "cevrimdisi" : ""; }).catch(hataGoster);
$("c-dene").onclick = () => mesgul($("c-dene"), async () => {
  const j = await api("/api/ceviri_testi", { metin: $("c-metin").value });
  const s = $("c-sonuc");
  s.textContent = ""; s.classList.add("acik");
  s.appendChild(el("b", "", j.ceviri));
  s.appendChild(el("div", "aciklama", j.sure_ms + " ms" + (j.model ? " · " + j.model : "")));
});
$("c-metin").addEventListener("keydown", (e) => { if (e.key === "Enter") $("c-dene").click(); });

// ================= seslendirme =================
let sesYuklendi = false, kisiZ = null;
const SES_SIMGE = '<svg viewBox="0 0 24 24"><path d="M8 5.500v13l11-6.500z"/></svg>';

async function sesAcildi() {
  kisileriYenile();
  sesDenemeYenile();
  if (sesYuklendi) return;
  sesYuklendi = true;
  let d = durum.dublaj || {};
  try { const j = await api("/api/dublaj/durum"); d = j.ayar || d; durum.dublaj = d; } catch (e) { hataGoster(e); }
  $("d-acik").checked = !!d.acik;
  $("d-dogal").checked = d.dogal_ses !== false;
  $("d-karakter").checked = d.karakter_sesleri !== false;
  $("d-kis").checked = d.okurken_kis !== false;
  [["d-seviye", d.seviye != null ? d.seviye : 1, (x) => Math.round(x * 100) + "%"], ["d-hiz", d.hiz || 1.15, (x) => (+x).toFixed(2) + "×"]].forEach(([id, deger, yaz]) => {
    const g = $(id); g.value = deger; g.nextElementSibling.textContent = yaz(+g.value);
    g.oninput = () => (g.nextElementSibling.textContent = yaz(+g.value));
    g.onchange = () => dublajKaydet({ [id === "d-seviye" ? "seviye" : "hiz"]: +g.value });
  });
  await dogalYenile();
}
function dublajKaydet(v) { return api("/api/dublaj/kaydet", v).then(() => Object.assign(durum.dublaj, v)).catch(hataGoster); }
$("d-acik").onchange = () => modSec($("d-acik").checked ? (G.altyazi_goster === false ? "ses" : "ikisi") : "altyazi");
$("d-dogal").onchange = () => dublajKaydet({ dogal_ses: $("d-dogal").checked }).then(dogalYenile);
$("d-karakter").onchange = () => dublajKaydet({ karakter_sesleri: $("d-karakter").checked });
$("d-kis").onchange = () => dublajKaydet({ okurken_kis: $("d-kis").checked });
$("d-motor").onchange = () => dublajKaydet({ dogal_motor: $("d-motor").value }).then(dogalYenile);
$("d-sifirla").onclick = () => api("/api/dublaj/kisileri_sifirla").then(kisileriYenile).catch(hataGoster);

async function dogalYenile() {
  const kutu = $("sesler"), rozet = $("d-dogal-rozet");
  let j;
  try { j = await api("/api/dogal/durum"); } catch (e) { return hataGoster(e); }
  $("d-motor-satir").style.display = j.hafif_var && j.guclu_var ? "" : "none";
  $("d-motor").value = j.tercih || "otomatik";
  const adlar = { kapali: ["", "Beklemede"], basliyor: ["sari", "Yükleniyor…"], hazir: ["yesil", "Hazır"], hata: ["sari", "Sorun var"] };
  const r = j.kurulu ? (adlar[j.durum] || ["", j.durum]) : ["", "Yok"];
  rozet.className = "rozet " + r[0]; rozet.textContent = r[1];
  kutu.textContent = "";
  if (!j.kurulu || !(j.sesler || []).length) {
    const b = el("button", "dugme", "Windows sesini dinle");
    b.onclick = () => mesgul(b, () => api("/api/dublaj/dinle", {}));
    kutu.appendChild(b);
    $("d-ses-durum").textContent = "Doğal sesler bu kurulumda yok; Windows'un Türkçe sesi kullanılır.";
    return;
  }
  $("d-ses-durum").textContent = j.hata || (j.sesler.length + " ses · ilk dinlemede sesler birkaç saniyede yüklenir");
  j.sesler.forEach((s) => {
    const o = el("div", "ses-oge");
    o.innerHTML = SES_SIMGE;
    const ad = el("div"); ad.appendChild(el("b", "", s.ad)); ad.appendChild(el("small", "", s.cinsiyet === "kadin" ? "Kadın" : "Erkek"));
    o.appendChild(ad);
    o.onclick = async () => {
      $("d-ses-durum").textContent = s.ad + " hazırlanıyor…";
      try { await api("/api/dogal/dinle", { id: s.id }); $("d-ses-durum").textContent = s.ad + " okunuyor."; }
      catch (e) { $("d-ses-durum").textContent = e.message; }
    };
    kutu.appendChild(o);
  });
}

// ---------- ses motorlarını karşılaştır (deneme) ----------
let sdZ = null, sdCalan = null, sdMetinKondu = false;
const sn = (x) => String(x).replace(".", ",");

async function sesDenemeYenile() {
  clearTimeout(sdZ);
  if (!$("s-ses").classList.contains("aktif") || durum.magaza) return;
  let j;
  try { j = await api("/api/ses_deneme/durum"); } catch (e) { return; }
  $("sd-yok").classList.toggle("acik", !j.motor_var);
  $("sd-govde").style.display = j.motor_var ? "" : "none";
  if (!sdMetinKondu) {
    sdMetinKondu = true;
    $("sd-metin").value = j.ornek_metin;
    j.sesler.forEach((s) => { const o = el("option", "", s.ad + " · " + (s.cinsiyet === "kadin" ? "kadın" : "erkek")); o.value = s.id; $("sd-ses").appendChild(o); });
    if (j.sesler.some((s) => s.id === "sert_erkek")) $("sd-ses").value = "sert_erkek";
  }
  const kutu = $("sd-modeller");
  kutu.textContent = "";
  let iniyor = false;
  j.modeller.forEach((m) => {
    const satir = el("div", "sd-model" + (sdCalan === m.id ? " caliyor" : "")), sol = el("div");
    const baslik = el("b", "", m.ad);
    sol.appendChild(baslik);
    if (j.yuklu === m.id) { const r = el("span", "rozet yesil", "Bellekte"); r.style.marginLeft = "8px"; sol.appendChild(r); }
    sol.appendChild(el("div", "aciklama", m.aciklama + " (" + m.lisans + ")"));
    if (m.son) sol.appendChild(el("div", "olcum", sn(m.son.ses_sn) + " sn ses, " + sn(m.son.uretim_sn) + " sn'de üretildi" +
      (m.son.yukleme_sn > 0.5 ? " · model " + sn(m.son.yukleme_sn) + " sn'de yüklendi" : "") + " · " + m.son.ses));
    satir.appendChild(sol);
    const ind = m.indirme;
    if (m.kurulu) {
      const b = el("button", "dugme kucuk ana", sdCalan === m.id ? "Hazırlanıyor…" : "Dinle");
      b.disabled = !!sdCalan;
      b.onclick = () => sesDenemeDinle(m.id);
      satir.appendChild(b);
    } else if (ind && !ind.hata && !ind.bitti) {
      iniyor = true;
      satir.appendChild(el("span", "rozet mavi", "İndiriliyor %" + Math.floor((ind.oran || 0) * 100)));
    } else {
      if (ind && ind.hata) sol.appendChild(el("div", "aciklama", "İndirilemedi: " + ind.hata));
      const b = el("button", "dugme kucuk", "İndir (" + sn(m.boyut_gb) + " GB)");
      b.onclick = () => api("/api/ses_deneme/indir", { id: m.id }).then(sesDenemeYenile).catch(hataGoster);
      satir.appendChild(b);
    }
    kutu.appendChild(satir);
  });
  if (!sdCalan) $("sd-durum").textContent = j.hata || (j.sunucu === "basliyor" ? "Model yükleniyor…" : "");
  if (iniyor || sdCalan || j.sunucu === "basliyor") sdZ = setTimeout(sesDenemeYenile, 1500);
}

async function sesDenemeDinle(id) {
  if (sdCalan) return;
  if (motorDurum === "calisiyor" || motorDurum === "basliyor") {
    return bildir("Altyazı çalışırken ses denemesi yapılamıyor: önce Ana sayfadan Durdur'a basın (ekran kartı sürücüsü kilitlenebiliyor).", true);
  }
  sdCalan = id;
  $("sd-durum").textContent = "Hazırlanıyor… (ilk seferde model yüklenir)";
  sesDenemeYenile();
  try {
    await api("/api/ses_deneme/dinle", { id, metin: $("sd-metin").value, ses: $("sd-ses").value, abarti: +$("sd-abarti").value });
    $("sd-durum").textContent = "";
  } catch (e) { $("sd-durum").textContent = ""; hataGoster(e); }
  sdCalan = null;
  sesDenemeYenile();
}
$("sd-abarti").oninput = () => ($("sd-abarti").nextElementSibling.textContent = (+$("sd-abarti").value).toFixed(2));

async function kisileriYenile() {
  clearTimeout(kisiZ);
  if (!$("s-ses").classList.contains("aktif")) return;
  try {
    const j = await api("/api/dublaj/kisiler"), kutu = $("kisiler");
    if (!kutu.contains(document.activeElement) || document.activeElement.tagName !== "SELECT") {
      kutu.textContent = "";
      if (!j.kisiler.length) kutu.appendChild(el("div", "bos-not", "Henüz kimse tanınmadı. Seslendirme açıkken oyunda konuşanlar burada listelenir."));
      j.kisiler.forEach((k) => {
        const o = el("div", "kisi");
        o.appendChild(el("span", "nokta" + (j.son === k.no ? " yesil" : "")));
        o.appendChild(el("span", "", k.ad + " · " + k.cinsiyet + " · " + k.sayi + " satır"));
        const secim = el("select");
        [{ id: "otomatik", ad: "Kendiliğinden" }].concat(j.sesler || []).forEach((s) => { const op = el("option", "", s.ad); op.value = s.id; secim.appendChild(op); });
        secim.value = k.elle ? k.ses : "otomatik";
        secim.onchange = () => api("/api/dublaj/kisi_ses", { no: k.no, ses: secim.value }).catch(hataGoster);
        o.appendChild(secim);
        kutu.appendChild(o);
      });
    }
  } catch (e) {}
  kisiZ = setTimeout(kisileriYenile, 3000);
}

// ================= ayarlar =================
function ayarlariDoldur() {
  const u = durum.uygulama_ayar || {};
  $("a-tepsi").checked = u.tepsiye_kucult !== false;
  $("a-baslat").checked = !!u.windows_ile_baslat;
  if (!u.kurulu) { $("a-baslat").disabled = true; $("a-baslat-not").textContent = "Bu ayar yalnızca kurulu programda çalışır (geliştirme kipinde kapalı)."; }
  $("a-surum").textContent = durum.surum;
  $("a-klasor").textContent = durum.veri_klasoru;
  $("surum").textContent = "Sürüm " + durum.surum;
}
$("a-tepsi").onchange = () => api("/api/uygulama_ayar", { tepsiye_kucult: $("a-tepsi").checked }).catch(hataGoster);
$("a-baslat").onchange = () => api("/api/uygulama_ayar", { windows_ile_baslat: $("a-baslat").checked })
  .catch((e) => { $("a-baslat").checked = !$("a-baslat").checked; hataGoster(e); });
$("a-baslangic-ac").onclick = () => api("/api/baslangic_ayarlari").catch(hataGoster);
$("a-rapor").onclick = () => mesgul($("a-rapor"), async () => {
  const j = await api("/api/sorun_raporu");
  const s = $("a-rapor-durum"); s.classList.add("acik");
  s.textContent = "Rapor hazır: " + j.dosya + " — bu dosyayı appic.studio@outlook.com adresine gönderin.";
});

// ================= açılış =================
async function basla() {
  try { durum = await api("/api/durum"); } catch (e) { uyari("u-hata", e.message); sayfaAc("ana"); return; }
  G = Object.assign({}, durum.goruntu);
  document.body.classList.toggle("magaza", !!durum.magaza);  // Store sürümü: seslendirme "geliştiriliyor" bildirimleri
  gorunumKur(); gorunumDoldur(); modGoster(); motorlariCiz(); ayarlariDoldur();
  uyari("u-not", durum.katman_notu || "");
  kurulumModu = !durum.kurulum_tamam;
  if (kurulumModu) {
    hepsi("#nav button").forEach((b) => (b.disabled = b.dataset.sayfa !== "alan"));
    $("kurulum-adimlar").style.display = "";
    $("al-kaydet").textContent = "Kurulumu bitir";
    sayfaAc("alan");
  } else {
    let sayfa = "ana";
    try { sayfa = sessionStorage.getItem("sayfa") || "ana"; } catch (e) {}
    sayfaAc($("s-" + sayfa) ? sayfa : "ana");
  }
  tamEkranGoster();
  ozetYenile();
  setInterval(ozetYenile, 800);
  // tepsi menüsünden yapılan değişiklikler (boyut, görünüm, kip) açık pencereye de yansısın
  setInterval(async () => {
    const t0 = Date.now();
    if (surukleme || t0 - sonKayit < 1200) return;  // burada ayar yapılıyor: kendi değişikliğimizin üstüne yazma
    try {
      const j = await api("/api/durum");
      if (sonKayit > t0 - 1200) return;
      const degisti = JSON.stringify(j.goruntu) !== JSON.stringify(durum.goruntu) || (j.dublaj || {}).acik !== (durum.dublaj || {}).acik;
      durum.goruntu = j.goruntu; durum.dublaj = j.dublaj;
      if (degisti && !document.querySelector("#s-gorunum input:active")) { G = hedefAyari(); gorunumDoldur(); onizle(); modGoster(); }
    } catch (e) {}
  }, 2500);
  document.body.dataset.hazir = "1";
}
basla();
