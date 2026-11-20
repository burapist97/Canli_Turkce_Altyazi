/* Canlı Türkçe Altyazı — sihirbaz ve panelin ortak kodu */
"use strict";
const $ = (id) => document.getElementById(id);

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

function git(yol) { location.href = yol + "#" + BELIRTEC; }

async function api(yol, veri) {
  let r;
  try {
    r = await fetch(yol, { method: "POST", headers: { "Content-Type": "application/json", "X-Belirtec": BELIRTEC }, body: JSON.stringify(veri || {}) });
  } catch (e) { throw new Error("Uygulamanın arka planına ulaşılamadı. Programı kapatıp yeniden açın."); }
  if (r.status === 403) throw new Error("Oturum süresi doldu. Programı kapatıp yeniden açın.");
  const j = await r.json();
  if (!j.ok) throw new Error(j.hata || "Bilinmeyen hata");
  return j;
}

function mesaj(id, tur, yazi) { const e = $(id); e.className = "mesaj " + tur; e.textContent = yazi; return e; }
function mesajGizle(id) { $(id).className = "mesaj"; }
function bekle(dugme, aktif, yazi) {
  if (aktif) { dugme.dataset.eski = dugme.innerHTML; dugme.textContent = yazi || "Bekleyin"; dugme.classList.add("yukleniyor"); dugme.disabled = true; }
  else { if (dugme.dataset.eski) dugme.innerHTML = dugme.dataset.eski; dugme.classList.remove("yukleniyor"); dugme.disabled = false; }
}
function disariAc(url) { api("/api/disari_ac", { url }).catch(() => {}); }

// Neon ekran logosu (paket/logo_ciz.py UYGULAMA_ICI ile aynı)
const LOGO_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke-linecap="round" stroke-linejoin="round"><defs><linearGradient id="logo-lg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#2ef0ff"/><stop offset="1" stop-color="#c04dff"/></linearGradient></defs><path d="M3 8V3h5M16 3h5v5M21 16v5h-5M8 21H3v-5" stroke="url(#logo-lg)" stroke-width="2.6"/><path d="M7.5 12.5h9M9.5 16h5" stroke="#fff" stroke-width="2.4"/></svg>';
document.querySelectorAll(".logo-isaret").forEach((e) => (e.innerHTML = LOGO_SVG));

// Çizgi simgeler (bu uygulama için çizildi; emoji yerine, her temada tek renk)
const SIMGE = {
  kol: '<svg viewBox="0 0 24 24"><path d="M7 7.5h10a4.5 4.5 0 0 1 4.4 5.4l-.6 3a2.6 2.6 0 0 1-4.6 1.1L14.5 15h-5l-1.7 2a2.6 2.6 0 0 1-4.6-1.1l-.6-3A4.5 4.5 0 0 1 7 7.5z"/><path d="M7.5 10v3M6 11.5h3"/><circle cx="15.5" cy="10.5" r=".6"/><circle cx="17.5" cy="12.5" r=".6"/></svg>',
  kart: '<svg viewBox="0 0 24 24"><rect x="6.5" y="8" width="11" height="8" rx="2"/><path d="M2.5 12h4M17.5 12h4M10 8V5.5M14 8V5.5"/></svg>',
  bilgisayar: '<svg viewBox="0 0 24 24"><rect x="5" y="5" width="14" height="10" rx="1.8"/><path d="M2.5 18.5h19"/></svg>',
  ekran: '<svg viewBox="0 0 24 24"><rect x="3" y="4.5" width="18" height="12" rx="2"/><path d="M9 20h6M12 16.5V20"/></svg>',
  altyazi: '<svg viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="14" rx="3"/><path d="M7 14h6M15.5 14H17"/></svg>',
  ses: '<svg viewBox="0 0 24 24"><path d="M4 9.5v5h3.5l4.5 3.5V6L7.5 9.5H4z"/><path d="M15.5 9a4.5 4.5 0 0 1 0 6M18 6.5a8 8 0 0 1 0 11"/></svg>',
  sihir: '<svg viewBox="0 0 24 24"><path d="M11 4l1.7 4.3L17 10l-4.3 1.7L11 16l-1.7-4.3L5 10l4.3-1.7L11 4z"/><path d="M18 15l.8 2.2L21 18l-2.2.8L18 21l-.8-2.2L15 18l2.2-.8L18 15z"/></svg>',
  yenile: '<svg viewBox="0 0 24 24"><path d="M20 12a8 8 0 1 1-2.6-5.9"/><path d="M20 4.5V9h-4.5"/></svg>',
  goz: '<svg viewBox="0 0 24 24"><path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="2.8"/></svg>',
  disari: '<svg viewBox="0 0 24 24"><path d="M8 16l8-8M9.5 8H16v6.5"/></svg>',
  onay: '<svg viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
  baslangic: '<svg viewBox="0 0 24 24"><path d="M9 6.5v11l9-5.5-9-5.5z"/></svg>',
  onaykutu: '<svg viewBox="0 0 24 24"><rect x="4" y="4" width="16" height="16" rx="3.5"/><path d="M8 12.5l3 3 5.5-6"/></svg>',
};
function sim(ad) { return '<span class="sim">' + (SIMGE[ad] || "") + "</span>"; }
function simgeleriCiz(kok) { (kok || document).querySelectorAll("[data-sim]").forEach((e) => { e.innerHTML = SIMGE[e.dataset.sim] || ""; }); }
simgeleriCiz();

// ---------- çeviri motoru seçimi (sihirbaz + panel) ----------
const MOTORLAR = [
  { id: "cevrimdisi", ad: "Hazır çeviri", rozet: ["yesil", "Ücretsiz · Anahtarsız"], anahtarsiz: true,
    ozet: "Hiçbir şey yapmanız gerekmez. Bilgisayarınızda çalışır, internetsiz ve sınırsız.",
    bilgi: ["Kurulum gerektirmez, hemen çalışır.", "İnternet kesilse de çeviri devam eder.", "Sınırsız ve tamamen ücretsizdir; metin bilgisayarınızdan çıkmaz.",
      "Sokak ağzı ve esprilerde yapay zekâ servisleri (Gemini) daha doğal olabilir."],
    not: "Çeviri modeli: OPUS-MT, Helsinki Üniversitesi (CC BY 4.0)." },
  { id: "gemini", ad: "Google Gemini", rozet: ["mavi", "En doğal · Ücretsiz anahtar"],
    ozet: "Argo ve esprilerde en doğal Türkçe. Google hesabıyla 1 dakikada ücretsiz anahtar.",
    adimlar: ["Aşağıdaki <b>Anahtar sayfasını aç</b> düğmesine basın.", "Google hesabınızla giriş yapın.",
      "<b>Create API key</b> (API anahtarı oluştur) düğmesine basın.", "Çıkan anahtarı kopyalayıp aşağıya yapıştırın."],
    not: "Ücretsiz kullanımda dakikada belirli sayıda çeviri hakkı vardır. Ücretsiz katmanda Google gönderilen metni hizmetini geliştirmek için kullanabilir." },
  { id: "groq", ad: "Groq", rozet: ["yesil", "Ücretsiz"],
    ozet: "Çok hızlı. Ücretsiz anahtar, kart istemez. Gemini'ye iyi bir yedek.",
    adimlar: ["<b>Anahtar sayfasını aç</b> düğmesine basın.", "Google hesabınızla veya e-postayla giriş yapın.",
      "<b>Create API Key</b> düğmesine basın, bir isim yazın (ör. altyazi).", "Anahtarı kopyalayıp aşağıya yapıştırın. Anahtar sadece bir kez gösterilir."],
    not: "Ücretsiz kullanımda dakikada ve günde belirli sayıda istek hakkı vardır." },
  { id: "deepl", ad: "DeepL", rozet: ["mavi", "Ayda 500 bin karakter ücretsiz"],
    ozet: "Düzgün dilbilgisi. Kayıtta kart doğrulaması ister, ücret alınmaz.",
    adimlar: ["<b>Anahtar sayfasını aç</b> → <b>DeepL API Free</b> planına kaydolun.", "Kart doğrulamasını tamamlayın (ücretsiz planda ücret alınmaz).",
      "Hesap → <b>API Keys</b> bölümünden anahtarı kopyalayın.", "Aşağıya yapıştırın (sonu <b>:fx</b> ile biter)."],
    not: "Sokak ağzı ve esprilerde yapay zekâ motorları daha doğal olabilir." },
  { id: "claude", ad: "Claude", rozet: ["lava", "En doğal · Ücretli"],
    ozet: "Argoyu ve esprileri en iyi aktaran motor. Kullandıkça ödenir.",
    adimlar: ["<b>Anahtar sayfasını aç</b> → Anthropic Console'a giriş yapın.", "Billing bölümünden bakiye yükleyin.",
      "API Keys → <b>Create Key</b>.", "Anahtarı kopyalayıp aşağıya yapıştırın."],
    not: "Kısa altyazı satırlarında maliyet çok düşüktür ama ücretsiz değildir." },
];

/**
 * kutu: bileşenin çizileceği element. durum: /api/durum cevabındaki "ceviri".
 * kayitta: değişince çağrılır. ornekMetin(): test edilecek cümleyi döndürür.
 */
function ceviriBileseni(kutu, durum, secenek) {
  secenek = secenek || {};
  let secili = durum.motor && MOTORLAR.some((m) => m.id === durum.motor) ? durum.motor : "cevrimdisi";
  const anahtarVar = Object.assign({}, durum.anahtar_var || {});
  kutu.innerHTML = `
    <div class="motorlar">${MOTORLAR.map((m) => `
      <div class="motor" data-id="${m.id}" tabindex="0" role="radio">
        <span class="tik"></span><span class="rozet ${m.rozet[0]}">${m.rozet[1]}</span>
        <h3>${m.ad}</h3><p>${m.ozet}</p><div class="kayitli">${m.anahtarsiz ? "Hazır, çalışıyor" : "Anahtar kayıtlı"}</div>
      </div>`).join("")}</div>
    <div class="kart motor-detay">
      <div class="izgara-2">
        <div><p class="kart-baslik" data-ad></p><ol class="adimlar" data-adimlar style="margin-top:10px;"></ol></div>
        <div>
          <div data-anahtar-alani>
          <label class="etiket" data-etiket></label>
          <div class="anahtar-satir"><input type="password" data-anahtar autocomplete="off" spellcheck="false">
            <button class="dugme ikincil" data-goster title="Göster/gizle" aria-label="Göster/gizle">${sim("goz")}</button></div>
          </div>
          <div class="satir" style="margin-top:12px;">
            <button class="dugme ikincil" data-sayfa>Anahtar sayfasını aç ${sim("disari")}</button>
            <button class="dugme" data-dene>Kaydet ve dene</button>
          </div>
          <p class="kart-alt" data-not style="margin:12px 0 0;"></p>
        </div>
      </div>
      <div class="mesaj" data-mesaj></div>
      <div class="ceviri-sonuc" data-sonuc><small></small><span></span></div>
    </div>
    <div class="kart" data-yedek-kart style="display:none;">
      <div class="satir"><div class="ara"><p class="kart-baslik">Yedek motor</p>
        <p class="kart-alt" style="margin:0;">Kota dolarsa ya da internet kesilirse çeviri durmasın: bir dakikalığına buna geçilir.</p></div>
        <select data-yedek style="max-width:220px;"></select></div>
    </div>`;
  const q = (s) => kutu.querySelector(s);
  const anahtarInput = q("[data-anahtar]");

  function ciz() {
    const m = MOTORLAR.find((x) => x.id === secili);
    kutu.querySelectorAll(".motor").forEach((e) => {
      e.classList.toggle("secili", e.dataset.id === secili);
      e.classList.toggle("anahtarli", !!anahtarVar[e.dataset.id]);
      e.setAttribute("aria-checked", e.dataset.id === secili);
    });
    const anahtarsiz = !!m.anahtarsiz;
    q("[data-ad]").textContent = anahtarsiz ? "Hiçbir şey yapmanıza gerek yok" : m.ad + " anahtarı nasıl alınır?";
    q("[data-adimlar]").innerHTML = (anahtarsiz ? m.bilgi : m.adimlar).map((a) => `<li><span>${a}</span></li>`).join("");
    q("[data-anahtar-alani]").style.display = anahtarsiz ? "none" : "";
    q("[data-sayfa]").style.display = anahtarsiz ? "none" : "";
    q("[data-dene]").textContent = anahtarsiz ? "Çeviriyi dene" : "Kaydet ve dene";
    q("[data-etiket]").textContent = m.ad + " API anahtarı";
    anahtarInput.value = "";
    anahtarInput.placeholder = anahtarVar[secili] ? "Kayıtlı. Değiştirmek için yenisini yapıştırın." : "Anahtarı buraya yapıştırın (Ctrl+V)";
    q("[data-not]").textContent = m.not;
    q("[data-sonuc]").style.display = "none";
    q("[data-mesaj]").className = "mesaj";
    // yedek motor seçenekleri: anahtarı olan diğer motorlar
    const adaylar = MOTORLAR.filter((x) => x.id !== secili && anahtarVar[x.id]);
    q("[data-yedek-kart]").style.display = adaylar.length && !anahtarsiz ? "block" : "none";
    const sel = q("[data-yedek]");
    sel.innerHTML = `<option value="">Yedek yok</option>` + adaylar.map((x) => `<option value="${x.id}">${x.ad}</option>`).join("");
    sel.value = adaylar.some((x) => x.id === durum.yedek_motor) ? durum.yedek_motor : "";
  }

  async function sec(id) {
    secili = id; ciz();
    if (anahtarVar[id]) {
      try { await api("/api/ceviri_ayarla", { motor: id }); durum.motor = id; } catch (e) {}
    }
    // Anahtarı henüz denenmemiş motor seçilince de haber ver: sihirbaz "Devam"ı ancak çalışan bir motorla açar
    secenek.kayitta && secenek.kayitta();
  }
  kutu.querySelectorAll(".motor").forEach((e) => {
    e.onclick = () => sec(e.dataset.id);
    e.onkeydown = (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); sec(e.dataset.id); } };
  });
  q("[data-goster]").onclick = () => { anahtarInput.type = anahtarInput.type === "password" ? "text" : "password"; };
  q("[data-sayfa]").onclick = () => disariAc(SAYFALAR[secili]);
  q("[data-yedek]").onchange = async (e) => {
    try { await api("/api/ceviri_ayarla", { yedek_motor: e.target.value }); durum.yedek_motor = e.target.value; } catch (err) {}
  };
  anahtarInput.addEventListener("keydown", (e) => { if (e.key === "Enter") q("[data-dene]").click(); });
  q("[data-dene]").onclick = async () => {
    const d = q("[data-dene]");
    const yeni = anahtarInput.value.trim();
    const anahtarsiz = !!MOTORLAR.find((x) => x.id === secili).anahtarsiz;
    if (!anahtarsiz && !yeni && !anahtarVar[secili]) { mesajEl("bilgi", "Önce anahtarı yapıştırın."); return; }
    bekle(d, true, "Deneniyor");
    try {
      const veri = { motor: secili, test_motor: secili, metin: secenek.ornekMetin ? secenek.ornekMetin() : "" };
      if (yeni) veri.anahtarlar = { [secili]: yeni };
      const j = await api("/api/ceviri_testi", veri);
      anahtarVar[secili] = true; durum.motor = secili;
      const s = q("[data-sonuc]"); s.style.display = "block";
      s.querySelector("small").textContent = j.metin; s.querySelector("span").textContent = j.ceviri;
      ciz(); s.style.display = "block";
      mesajEl("ok", `Çeviri çalışıyor (${j.sure_ms} ms).` + (anahtarsiz ? "" : " Anahtar kaydedildi."));
      secenek.kayitta && secenek.kayitta();
    } catch (e) { mesajEl("hata", e.message); }
    bekle(d, false);
  };
  function mesajEl(tur, yazi) { const e = q("[data-mesaj]"); e.className = "mesaj " + tur; e.textContent = yazi; }

  ciz();
  return { hazir: () => !!anahtarVar[secili], secili: () => secili };
}
const SAYFALAR = {
  gemini: "https://aistudio.google.com/apikey",
  groq: "https://console.groq.com/keys",
  deepl: "https://www.deepl.com/pro-api",
  claude: "https://console.anthropic.com/settings/keys",
};
