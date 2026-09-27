// TradeVoice web app: WhatsApp-style chat over the same Python brains (web.py -> converse.py, ledger.py ...).
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const store = {
  get(k, d) { try { return localStorage.getItem(k) ?? d; } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch {} },
};
const S = {
  lang: store.get("tv_lang", "English"),          // app language (screens + read-aloud)
  speak: store.get("tv_speak", "English"),        // language of voice notes (Intron needs it)
  shop: store.get("tv_shop", ""),
  consent: store.get("tv_consent", "") === "yes",
  session: store.get("tv_session", "") || (crypto.randomUUID ? crypto.randomUUID() : String(Math.random()).slice(2)),
  voice: null, T: {}, pending: null,
};
store.set("tv_session", S.session);
const SPEAK_LANGS = [["English", "English / Pidgin"], ["Yoruba", "Yorùbá"], ["Hausa", "Hausa"], ["Igbo", "Igbo"]];
const TYPES = {
  sale: ["🛒", "Sold (paid)"], credit_sale: ["📝", "Sold on credit"], payment_received: ["💰", "Paid me back"],
  expense: ["💸", "Spent"], credit_purchase: ["📦", "Bought on credit (I owe)"], payment_made: ["↩️", "I paid back"],
};

const t = (k, d = "") => S.T[k] || d || k;

// inline SVG icons for buttons/chrome (spec: no emoji as structural icons; emojis stay in message content)
const I = {
  speak: '<svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M8 10.5a4 4 0 0 1 8 0v2a4 4 0 0 1-8 0z"/><path d="M14 7.8a5.6 5.6 0 0 1 0 9.4"/></svg>',
  play: '<svg class="i-pl" width="15" height="15" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M7 4.8v14.4c0 .8.9 1.3 1.6.9l11-7.2c.6-.4.6-1.4 0-1.8l-11-7.2c-.7-.4-1.6.1-1.6.9z"/></svg>',
  pause: '<svg class="i-pa" width="15" height="15" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><rect x="6" y="4" width="4" height="16" rx="1.2"/><rect x="14" y="4" width="4" height="16" rx="1.2"/></svg>',
  yes: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 12.5l5 5L20 6.5"/></svg>',
  no: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>',
  down: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 4v13"/><path d="M6 12l6 6 6-6"/></svg>',
  wa: '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M12 3a9 9 0 0 0-7.8 13.5L3 21l4.6-1.2A9 9 0 1 0 12 3z" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/><path d="M9 8.5c.6 2.8 3.7 5.9 6.5 6.5l1.3-1.6 2.2 1.1-.6 1.9c-.2.6-.8 1-1.5.9-4.3-.6-8.2-4.5-8.8-8.8-.1-.7.3-1.3.9-1.5l1.9-.6 1.1 2.2z" fill="currentColor"/></svg>',
  pin: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 17v5"/><path d="M9 4h6l1 7 2 2H6l2-2z"/></svg>',
  cal: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="4" y="5" width="16" height="16" rx="2"/><path d="M4 10h16M9 3v4M15 3v4"/></svg>',
  cam: '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 7h3l2-2h6l2 2h3v12H4z"/><circle cx="12" cy="13" r="3.4"/></svg>',
  warn: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 4L2.5 20h19z"/><path d="M12 10v4M12 17.5v.5"/></svg>',
  user: '<svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="8" r="4"/><path d="M4 21c1.5-4 5-6 8-6s6.5 2 8 6"/></svg>',
  shop: '<svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 9l1-4h14l1 4"/><path d="M5 9v11h14V9"/><path d="M9 20v-6h6v6"/></svg>',
};
const stripIc = (s) => esc(s).replace(/^[\u2190-\u2BFF\uFE0F\u274C\u2705]+\s*/u, "");
const naira = (x) => (x < 0 ? "-₦" : "₦") + Math.round(Math.abs(x || 0)).toLocaleString("en-NG");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (s) => esc(s).replace(/\*(.+?)\*/g, "<b>$1</b>").replace(/_(.+?)_/g, "<i>$1</i>").replace(/\n/g, "<br>");
const day = (iso) => { if (!iso) return ""; const d = new Date(iso + "T12:00:00"); return isNaN(d) ? iso : d.toLocaleDateString("en-GB", { day: "numeric", month: "short" }); };
const now = () => new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

function toast(msg, ms = 2500) {
  const el = $("#toast");
  el.textContent = msg; el.classList.add("on");
  clearTimeout(toast.h); toast.h = setTimeout(() => el.classList.remove("on"), ms);
}

// ngrok's free links show a warning page to browsers unless this header is sent (harmless elsewhere)
const HDR = { "ngrok-skip-browser-warning": "1" };
async function api(path, opts = {}) {
  const r = await fetch(path, { ...opts, headers: { ...HDR, ...(opts.headers || {}) } });
  let body = null;
  try { body = await r.json(); } catch {}
  if (!r.ok) throw new Error((body && (body.error || body.detail)) || `Error ${r.status}`);
  return body;
}
const post = (path, data) => api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });

// ------------------------------------------------------------------ language + words on screen

async function loadWords() {
  try { S.T = await api(`/api/ui?lang=${encodeURIComponent(S.lang)}`); } catch { S.T = {}; }
  document.querySelectorAll("[data-t]").forEach((el) => { if (S.T[el.dataset.t]) el.textContent = S.T[el.dataset.t]; });
  document.querySelectorAll(".read").forEach((b) => (b.innerHTML = I.speak + `<span>${esc(t("read", "Read it to me"))}</span>`));
  $("#text").placeholder = t("message", "Message");
  $("#recHint").textContent = t("recording", "Recording… let go to send");
  $("#sub").textContent = t("online", "online");
  $("#speakLang span").textContent = SPEAK_LANGS.find((l) => l[0] === S.speak)?.[1] || S.speak;
  document.documentElement.lang = { Yoruba: "yo", Hausa: "ha", Igbo: "ig", Pidgin: "pcm" }[S.lang] || "en";
}

function setLang(lang) {
  S.lang = lang; store.set("tv_lang", lang);
  S.speak = lang === "Pidgin" ? "English" : lang; store.set("tv_speak", S.speak);
  return loadWords();
}

// ------------------------------------------------------------------ chat bubbles

const chat = $("#chat");
function scrollDown() { const sc = $("#talk"); requestAnimationFrame(() => (sc.scrollTop = sc.scrollHeight)); }

function bubble(side, html, { ticks = false } = {}) {
  const el = document.createElement("div");
  el.className = `msg ${side}`;
  el.innerHTML = `${html}<span class="meta">${now()}${ticks ? '<span class="ticks">✓✓</span>' : ""}</span>`;
  chat.appendChild(el); scrollDown();
  return el;
}

function typing() {
  const el = document.createElement("div");
  el.className = "msg in"; el.innerHTML = '<span class="typing"><i></i><i></i><i></i></span>';
  chat.appendChild(el); scrollDown();
  return el;
}

// voice reply -> a local blob url (works through Vercel/ngrok, where <audio src> can't send headers)
async function speakUrl(id) {
  const r = await fetch(`/api/speak/${id}`, { headers: HDR });
  if (!r.ok) throw new Error("voice off");
  return URL.createObjectURL(await r.blob());
}

// shrink phone photos before upload: faster on market data, and under Vercel's 4.5 MB request limit
async function shrink(file, side = 1800) {
  try {
    const img = await createImageBitmap(file, { imageOrientation: "from-image" });
    const k = Math.min(1, side / Math.max(img.width, img.height));
    if (k === 1 && file.size < 3e6) return file;
    const c = document.createElement("canvas");
    c.width = Math.round(img.width * k); c.height = Math.round(img.height * k);
    c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
    const blob = await new Promise((res) => c.toBlob(res, "image/jpeg", 0.85));
    return blob ? new File([blob], "page.jpg", { type: "image/jpeg" }) : file;
  } catch { return file; }
}

// a voice note bubble; src = url, or a speak id we turn into audio only when played
function voiceNote(src, { speakId = null, autoplay = false } = {}) {
  const wrap = document.createElement("div");
  wrap.className = "vn";
  const bars = Array.from({ length: 28 }, () => `<i style="height:${25 + Math.round(Math.random() * 75)}%"></i>`).join("");
  wrap.innerHTML = `<button class="play" aria-label="Play">${I.play}${I.pause}</button><span class="wave">${bars}</span><span class="len">0:00</span>`;
  const audio = new Audio();
  audio.preload = "none";
  const btn = $(".play", wrap), len = $(".len", wrap), waves = [...wrap.querySelectorAll(".wave i")];
  const mmss = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
  audio.onloadedmetadata = () => { if (isFinite(audio.duration)) len.textContent = mmss(audio.duration); };
  audio.ontimeupdate = () => {
    const p = audio.duration ? audio.currentTime / audio.duration : 0;
    waves.forEach((w, i) => w.classList.toggle("done", i / waves.length < p));
    len.textContent = mmss(audio.currentTime);
  };
  audio.onended = () => { wrap.classList.remove("playing"); waves.forEach((w) => w.classList.remove("done")); };
  audio.onerror = () => { wrap.remove(); };
  const play = async () => {
    if (!audio.src) {
      try { audio.src = src || (await speakUrl(speakId)); } catch { wrap.remove(); return; }
    }
    if (audio.paused) {
      document.querySelectorAll("audio").forEach((a) => a !== audio && a.pause());
      voiceNote.current?.pause(); voiceNote.current = audio;
      audio.play().then(() => wrap.classList.add("playing")).catch(() => {});
    } else { audio.pause(); wrap.classList.remove("playing"); }
  };
  btn.onclick = play;
  if (autoplay) setTimeout(play, 50);
  return wrap;
}

function quickReplies() {
  const q = document.createElement("div");
  q.className = "quick";
  q.innerHTML = `<button data-v="yes">${I.yes}<span>${stripIc(t("yes_save", "Yes, save"))}</span></button><button data-v="no">${I.no}<span>${stripIc(t("no", "No"))}</span></button>`;
  q.onclick = (e) => {
    const v = e.target.dataset.v; if (!v) return;
    q.querySelectorAll("button").forEach((b) => (b.disabled = true));
    sendText(v === "yes" ? "yes" : "no", e.target.textContent);
  };
  chat.appendChild(q); scrollDown();
}

function showReply(r, { autoplay = false } = {}) {
  let html = fmt(r.text);
  if (r.english) html += `<div class="en">🇬🇧 ${fmt(r.english)}</div>`;
  if (r.message) {
    html += `<div class="quote">${fmt(r.message)}</div><a class="wa" href="${esc(r.link)}" target="_blank" rel="noopener">${I.wa}<span>Send on WhatsApp</span></a>`;
  }
  const el = bubble("in", html);
  if (r.speak && S.voice) el.insertBefore(voiceNote(null, { speakId: r.speak, autoplay }), el.querySelector(".meta"));
  document.querySelectorAll(".quick").forEach((q) => q.querySelectorAll("button").forEach((b) => (b.disabled = true)));
  if (r.pending) quickReplies();
  scrollDown();
}

async function sendText(text, shown) {
  text = text.trim(); if (!text) return;
  bubble("out", fmt(shown || text), { ticks: true });
  const wait = typing();
  try {
    const r = await post("/api/message", { session: S.session, text, shop: S.shop || null });
    wait.remove(); showReply(r);
  } catch (e) { wait.remove(); bubble("in err", esc(e.message)); }
}

// ------------------------------------------------------------------ hold to talk

const mic = $("#mic"), input = $("#text");
let rec = null, chunks = [], recStart = 0, recTimer = null, cancelRec = false, startX = 0;

function micIcon() { mic.textContent = input.value.trim() ? "➤" : "🎤"; }
input.addEventListener("input", micIcon);
input.addEventListener("keydown", (e) => { if (e.key === "Enter") { sendText(input.value); input.value = ""; micIcon(); } });

function pickMime() {
  const opts = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];
  return opts.find((m) => window.MediaRecorder && MediaRecorder.isTypeSupported(m)) || "";
}

async function startRec(e) {
  if (input.value.trim()) { sendText(input.value); input.value = ""; micIcon(); return; }
  if (!S.consent) return showWelcome();
  if (!navigator.mediaDevices?.getUserMedia) return toast("This browser can't record. Type instead (the link must be https).", 4000);
  startX = e.clientX; cancelRec = false;
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mime = pickMime();
    rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
    chunks = [];
    rec.ondataavailable = (ev) => ev.data.size && chunks.push(ev.data);
    rec.onstop = () => { stream.getTracks().forEach((tr) => tr.stop()); finishRec(); };
    rec.start(); recStart = Date.now();
    mic.classList.add("rec"); $("#recbar").classList.add("on");
    recTimer = setInterval(() => {
      const s = Math.floor((Date.now() - recStart) / 1000);
      $("#recTime").textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
      if (s >= 110) stopRec(); // Intron takes up to 2 minutes
    }, 250);
    if (!rec || rec.state !== "recording") stopRec();
  } catch { toast("Allow the microphone to talk, or type instead.", 4000); }
}

function stopRec() {
  clearInterval(recTimer);
  mic.classList.remove("rec"); $("#recbar").classList.remove("on"); $("#recTime").textContent = "0:00";
  if (rec && rec.state === "recording") rec.stop();
}

async function finishRec() {
  const ms = Date.now() - recStart;
  if (cancelRec) return toast("Cancelled");
  if (ms < 700) return toast(t("hold", "Hold 🎤 to talk"));
  const blob = new Blob(chunks, { type: rec.mimeType || "audio/webm" });
  const ext = (rec.mimeType || "").includes("mp4") ? ".m4a" : (rec.mimeType || "").includes("ogg") ? ".ogg" : ".webm";
  const mine = bubble("out", "", { ticks: true });
  mine.insertBefore(voiceNote(URL.createObjectURL(blob)), mine.querySelector(".meta"));
  const wait = typing();
  const fd = new FormData();
  fd.append("file", blob, "note" + ext); fd.append("session", S.session); fd.append("lang", S.speak);
  fd.append("consent", "yes"); fd.append("shop", S.shop || "");
  try {
    const r = await api("/api/voice", { method: "POST", body: fd });
    wait.remove();
    const heard = document.createElement("div");
    heard.className = "heard"; heard.textContent = `“${r.heard}”`;
    mine.insertBefore(heard, mine.querySelector(".meta"));
    showReply(r, { autoplay: true }); // they spoke, so answer out loud
  } catch (e) { wait.remove(); bubble("in err", esc(e.message)); }
}

mic.addEventListener("pointerdown", (e) => { e.preventDefault(); mic.setPointerCapture?.(e.pointerId); startRec(e); });
mic.addEventListener("pointermove", (e) => {
  if (rec && rec.state === "recording" && startX - e.clientX > 90) { cancelRec = true; stopRec(); }
});
["pointerup", "pointercancel"].forEach((ev) => mic.addEventListener(ev, () => { if (rec && rec.state === "recording") stopRec(); }));
mic.addEventListener("contextmenu", (e) => e.preventDefault());

// ------------------------------------------------------------------ photo of the book

$("#photo").addEventListener("change", async (e) => {
  const file = e.target.files[0]; e.target.value = "";
  if (!file) return;
  if (!S.consent) return showWelcome();
  bubble("out", `<img class="snap" src="${URL.createObjectURL(file)}" alt="book page">`, { ticks: true });
  const wait = typing();
  const fd = new FormData(); fd.append("file", await shrink(file)); fd.append("consent", "yes");
  try {
    const r = await api("/api/photo", { method: "POST", body: fd });
    wait.remove(); photoRows(r);
  } catch (err) { wait.remove(); bubble("in err", esc(err.message)); }
});

function photoRows(r) {
  if (!r.rows.length) return bubble("in", "I couldn't find money records in this photo. Try a flat page, in good light, whole page in view.");
  const opts = (sel) => Object.entries(TYPES).map(([k, [ic, lb]]) => `<option value="${k}" ${k === sel ? "selected" : ""}>${ic} ${lb}</option>`).join("");
  const rows = r.rows.map((x, i) => `
    <div class="row" data-i="${i}">
      <input type="checkbox" ${x.save ? "checked" : ""}>
      <div class="fields">
        <select>${opts(x.type)}</select>
        <input class="f amt" inputmode="numeric" value="${x.amount ?? ""}" placeholder="₦ amount">
        <input class="f who" value="${esc(x.customer)}" placeholder="name">
      </div>
      ${x.line ? `<div class="from">“${esc(x.line)}”</div>` : ""}
      ${x.checks.length ? `<div class="chk">${I.warn} ${esc(x.checks.join(" · "))}</div>` : ""}
    </div>`).join("");
  const el = bubble("in", `${I.cam} I read ${r.rows.length} line${r.rows.length > 1 ? "s" : ""}. Check the names and amounts, untick anything wrong, then save.
    <div class="rows">${rows}</div><button class="save">${I.yes}<span>${stripIc(t("save_ticked", "Save ticked"))}</span></button>`);
  $(".save", el).onclick = async (ev) => {
    const out = [...el.querySelectorAll(".row")].map((row) => {
      const x = r.rows[row.dataset.i];
      return { ...x, save: $("input[type=checkbox]", row).checked, type: $("select", row).value,
               amount: $(".amt", row).value, customer: $(".who", row).value };
    });
    ev.target.disabled = true;
    try {
      const res = await post("/api/save_rows", { rows: out });
      bubble("in", `✅ Saved ${res.saved} record${res.saved === 1 ? "" : "s"}.` + (res.problems.length ? `<div class="en">${I.warn} ${esc(res.problems.join("; "))}</div>` : ""));
    } catch (e) { ev.target.disabled = false; bubble("in err", esc(e.message)); }
  };
}

// ------------------------------------------------------------------ screens

async function showTab(name) {
  document.querySelectorAll(".screen").forEach((s) => s.classList.toggle("active", s.id === name));
  document.querySelectorAll(".tabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === name));
  $("#composer").style.display = name === "talk" ? "" : "none";
  const load = { book: loadBook, debts: loadDebts, insights: loadInsights, profile: loadProfile }[name];
  if (load) { try { await load(); } catch (e) { toast(e.message); } }
  if (name === "talk") scrollDown();
}
document.querySelectorAll(".tabs button").forEach((b) => (b.onclick = () => showTab(b.dataset.tab)));

async function loadBook() {
  const d = await api("/api/today"), s = d.summary;
  const TONE = { sale: "in", payment_received: "in", expense: "out", credit_purchase: "out", payment_made: "out", credit_sale: "credit" };
  const due = d.due.map((r) => `<div class="item"><div class="ic due">${I.pin}</div><div class="main"><div class="t">${esc(r.customer)}</div>
      <div class="s">${naira(r.balance)}</div></div><button class="small" data-remind="${esc(r.customer)}">${esc(t("remind", "Remind"))}</button></div>`).join("");
  const list = d.entries.map((e) => {
    const [ic, lb] = TYPES[e.type] || ["•", e.type];
    const what = [lb, e.item, e.customer].filter(Boolean).join(" · ");
    return `<div class="item"><div class="ic ${TONE[e.type] || ""}">${ic}</div><div class="main"><div class="t">${esc(what)}</div>
      <div class="s">${esc(e.created_at.slice(5, 16).replace("T", " "))}${e.due_date ? " · pay by " + esc(day(e.due_date)) : ""}</div></div>
      <div class="amt">${naira(e.amount)}</div><button class="x" data-del="${e.id}" aria-label="Delete">${I.no}</button></div>`;
  }).join("");
  $("#bookBody").innerHTML = `
    <div class="stats">
      <div class="stat"><div class="k">${esc(t("sold", "Sold"))}</div><div class="v">${naira(s.sales)}</div></div>
      <div class="stat"><div class="k">${esc(t("spent", "Spent"))}</div><div class="v">${naira(s.expenses)}</div></div>
      <div class="stat"><div class="k">${esc(t("came_in", "Came in"))}</div><div class="v">${naira(s.cash_sales + s.payments_received)}</div></div>
    </div>
    ${due ? `<div class="card"><h2>📌 Today</h2>${due}</div>` : ""}
    <div class="card"><h2>${esc(t("recent", "Recent"))}</h2>${list || '<div class="empty">Nothing yet. Go to Chat and tell me a sale.</div>'}</div>`;
}

async function loadDebts() {
  const d = await api("/api/debts");
  const total = d.owed_to_me.reduce((a, x) => a + x.balance, 0), mine = d.i_owe.reduce((a, x) => a + x.balance, 0);
  const person = (x, remind) => `<div class="item"><div class="ic ${remind ? "in" : "out"}">${remind ? I.user : I.shop}</div><div class="main">
      <div class="t">${esc(x.customer)}</div><div class="s">${x.overdue
        ? `<span class="badge late">${esc(t("days_late", "{n} days late").replace("{n}", x.days_late))}</span>`
        : `<span class="badge ok">${esc(t("on_time", "on time"))}</span>`}${x.due_date ? " · " + esc(day(x.due_date)) : ""}</div></div>
      <div class="amt">${naira(x.balance)}</div>${remind ? `<button class="small" data-remind="${esc(x.customer)}">${esc(t("remind", "Remind"))}</button>` : ""}</div>`;
  $("#debtsBody").innerHTML = `
    <div class="card"><h2>${esc(t("owe_me", "Owe me"))} <small>· ${d.owed_to_me.length}</small></h2><div class="big">${naira(total)}</div>
      ${d.owed_to_me.map((x) => person(x, true)).join("") || '<div class="empty">Nobody owes you 🎉</div>'}</div>
    <div class="card"><h2>${esc(t("i_owe", "I owe"))} <small>· ${d.i_owe.length}</small></h2><div class="big">${naira(mine)}</div>
      ${d.i_owe.map((x) => person(x, false)).join("") || '<div class="empty">You owe nobody 🎉</div>'}</div>`;
}

async function loadInsights() {
  const { forecast: f, top } = await api("/api/insights");
  if (!f) { $("#insightsBody").innerHTML = '<div class="empty">Record a few days of sales, then I can see what is coming.</div>'; return; }
  const max = Math.max(...f.plan.map((p) => p.sales), 1);
  const bars = f.plan.map((p) => `<div class="${p.weekday === f.busiest_day ? "peak" : ""}"><span style="height:${Math.round((p.sales / max) * 100)}%"></span>${esc(p.weekday.slice(0, 3))}</div>`).join("");
  $("#insightsBody").innerHTML = `
    <div class="card"><h2>${esc(t("next_week", "Next 7 days"))}</h2><div class="big">${naira(f.week_sales)}</div>
      <div class="note">Cash left after normal spending: <b>${naira(f.expected_cash)}</b></div><div class="bars">${bars}</div></div>
    <div class="card"><h2>${esc(t("busiest", "Busiest day"))}</h2><div class="big">${esc(f.busiest_day)}</div>
      <div class="note">Stock up the day before.</div></div>
    ${f.due_soon.length ? `<div class="card"><h2>📥 Promised this week</h2>${f.due_soon.map((d) => `<div class="item"><div class="ic due">${I.cal}</div><div class="main"><div class="t">${esc(d.customer)}</div><div class="s">${esc(day(d.due_date))}</div></div><div class="amt">${naira(d.balance)}</div></div>`).join("")}</div>` : ""}
    <div class="card"><h2>${esc(t("best_sellers", "Best sellers"))} <small>· 14 days</small></h2>
      ${top.map((x, i) => `<div class="item"><div class="ic rank${i + 1}">${i + 1}</div><div class="main"><div class="t">${esc(x.item)}</div>
        <div class="s">${x.qty && x.unit ? `${Math.round(x.qty)} ${esc(x.unit)}${x.qty !== 1 ? "s" : ""}` : ""}</div></div><div class="amt">${naira(x.revenue)}</div></div>`).join("")}</div>
    <p class="note">Forecast = your average sales for each weekday over the last 4 weeks. Simple and explainable, not a guarantee.</p>`;
}

async function loadProfile() {
  const { profile: p, year } = await api("/api/profile");
  if (!p) { $("#profileBody").innerHTML = '<div class="empty">Your book is empty. Start by telling me a sale.</div>'; return; }
  const deg = Math.round((p.score / 100) * 360);
  $("#profileBody").innerHTML = `
    <div class="card" style="text-align:center"><h2>${esc(t("score", "Record score"))}</h2>
      <div class="ring" style="background:conic-gradient(var(--accent) ${deg}deg, var(--line) 0)"><div>${p.score}<small>/100 · ${esc(p.band)}</small></div></div>
      <div class="note">${p.span_days} days of records · average daily sales ${naira(p.avg_daily_sales)}</div></div>
    <div class="card"><h2>Why this score</h2>${p.parts.map((x) => `<div class="part"><b>${esc(x.name)}</b> · ${Math.round(x.points)}/${x.max}
      <div class="bar"><i style="width:${Math.round((x.points / x.max) * 100)}%"></i></div><div class="why">${esc(x.why)}</div></div>`).join("")}
      <p class="note">A simple published formula over your own records, no hidden AI. It helps you talk to a lender, cooperative or ajo group; it is not a loan decision.${p.has_demo_data ? " Includes demo data for the hackathon." : ""}</p>
      <a class="btn" href="/api/statement?shop=${encodeURIComponent(S.shop)}" download target="_blank" rel="noopener">${I.down}<span>${stripIc(t("statement", "Statement for lender / cooperative"))}</span></a></div>
    <div class="card"><h2>📒 My year so far</h2><pre class="year">${esc(year)}</pre></div>`;
}

// remind buttons (Book + Debts): show the message first, then WhatsApp
document.addEventListener("click", async (e) => {
  const who = e.target.dataset?.remind, del = e.target.dataset?.del;
  if (who) {
    const lang = ["English", "Pidgin", "Yoruba"].includes(S.lang) ? S.lang : "Pidgin";
    const r = await api(`/api/reminder?customer=${encodeURIComponent(who)}&lang=${lang}&shop=${encodeURIComponent(S.shop)}`);
    if (!r.message) return toast(`${who} doesn't owe you anything 🎉`);
    sheet(`<h3>📲 ${esc(t("remind", "Remind"))} ${esc(who)}</h3><div class="quote">${fmt(r.message)}</div>
      <a class="wa" href="${esc(r.link)}" target="_blank" rel="noopener">${I.wa}<span>Send on WhatsApp</span></a>
      <p>WhatsApp opens with the message ready. You choose the contact and press send yourself.</p>`);
  }
  if (del && confirm("Delete this record?")) { await api(`/api/entry/${del}`, { method: "DELETE" }); loadBook(); }
});

// 🔊 read it to me
document.querySelectorAll(".read").forEach((b) => (b.onclick = async () => {
  b.disabled = true;
  try {
    const r = await api(`/api/read/${b.dataset.screen}?lang=${encodeURIComponent(S.lang)}`);
    toast(r.text, 6000);
    if (S.voice && r.speak) { const p = $("#player"); p.src = await speakUrl(r.speak); await p.play().catch(() => {}); }
  } catch (e) { toast(e.message); }
  b.disabled = false;
}));

// ------------------------------------------------------------------ sheets: speaking language, menu, welcome

function sheet(html) {
  $("#sheetBody").innerHTML = html; $("#sheet").hidden = false;
}
$("#sheet").onclick = (e) => { if (e.target.id === "sheet") $("#sheet").hidden = true; };

$("#speakLang").onclick = () => {
  sheet(`<h3>${esc(t("i_speak", "I'm speaking"))}</h3><div class="opts">${SPEAK_LANGS.map(([k, lb]) =>
    `<button data-speak="${k}" class="${k === S.speak ? "on" : ""}">${lb}</button>`).join("")}</div>
    <p>For voice notes. Typing works in any language, and you can switch any time in the same chat.</p>`);
  $("#sheetBody").onclick = (e) => {
    const k = e.target.dataset.speak; if (!k) return;
    S.speak = k; store.set("tv_speak", k); $("#sheet").hidden = true; loadWords();
    toast(SPEAK_LANGS.find((l) => l[0] === k)[1]);
  };
};

$("#menuBtn").onclick = () => {
  sheet(`<h3>🌍 ${esc(t("app_language", "App language"))}</h3><div class="opts">${(S.T._langs || ["English", "Pidgin", "Yoruba", "Hausa", "Igbo"])
      .map((l) => `<button data-lang="${l}" class="${l === S.lang ? "on" : ""}">${l}</button>`).join("")}</div>
    <h3>🏪 ${esc(t("shop_name", "Shop name"))}</h3><input id="shopIn" value="${esc(S.shop)}" placeholder="Chioma Stores">
    <h3>🔒 ${esc(t("my_data", "My data"))}</h3>
    <p>Voice notes and photos are read and deleted straight away; only the records are kept. Speech is turned into text by Intron;
      the AI that understands your notes and reads your photos runs on our own NVIDIA Brev GPU. Nothing is saved until you say yes.
      Reminders are only sent if you press send.</p>
    <button class="danger" id="wipe">Delete all my records</button>
    <p><a href="/admin/" style="color:var(--muted)">Open the full dashboard (advanced)</a></p>`);
  $("#sheetBody").onclick = async (e) => {
    const l = e.target.dataset.lang;
    if (l) { await setLang(l); $("#sheet").hidden = true; toast(l); }
    if (e.target.id === "wipe") {
      const c = prompt("Type DELETE to erase all your records");
      if (c === "DELETE") { await post("/api/wipe", { confirm: c }); toast("All records deleted"); $("#sheet").hidden = true; }
    }
  };
  $("#shopIn").onchange = (e) => { S.shop = e.target.value.trim(); store.set("tv_shop", S.shop); };
};

function showWelcome() {
  const box = $("#welcomeLangs");
  box.innerHTML = ["English", "Pidgin", "Yoruba", "Hausa", "Igbo"].map((l) => `<button data-l="${l}" class="${l === S.lang ? "on" : ""}">${l}</button>`).join("");
  box.onclick = async (e) => {
    if (!e.target.dataset.l) return;
    await setLang(e.target.dataset.l);
    box.querySelectorAll("button").forEach((b) => b.classList.toggle("on", b.dataset.l === S.lang));
  };
  $("#welcome").hidden = false;
}
$("#agree").onclick = () => {
  S.consent = true; store.set("tv_consent", "yes"); $("#welcome").hidden = true; greet();
};

// ------------------------------------------------------------------ start

async function greet() {
  chat.innerHTML = '<div class="day">Today</div>';
  bubble("in", fmt(t("hello", "Hello 👋 I'm your book. Tell me what you sold, who owes you, or ask me anything.")));
  const ex = document.createElement("div");
  ex.className = "chips";
  ["Mama Tunde dey owe me forty-five thousand", "Ṣé mo ní gbèsè lọ́wọ́ Alhaji?", "Who owes me?", "Wetin sell pass this week?"]
    .forEach((s) => { const b = document.createElement("button"); b.textContent = s; b.onclick = () => sendText(s); ex.appendChild(b); });
  chat.appendChild(ex);
  try {
    const d = await api("/api/today");
    d.due.forEach((r) => bubble("in", `📌 <b>${esc(r.customer)}</b> · ${naira(r.balance)}
      <div class="quick" style="margin-top:6px"><button data-remind="${esc(r.customer)}">${I.wa}<span>${esc(t("remind", "Remind"))}</span></button></div>`));
  } catch {}
}

(async function start() {
  try { const st = await api("/api/status"); S.voice = st.voice; if (!S.shop) S.shop = st.shop; } catch {}
  await loadWords();
  micIcon();
  if (!S.consent) showWelcome(); else greet();
})();
