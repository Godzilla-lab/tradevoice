// TradeVoice web app: WhatsApp-style chat over the same Python brains (web.py -> converse.py, ledger.py ...).
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const store = {
  get(k, d) { try { return localStorage.getItem(k) ?? d; } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch {} },
};
const S = {
  lang: store.get("tv_lang", "English"),          // ONE language for everything: screens, replies, voice, hearing
  shop: store.get("tv_shop", ""),
  consent: store.get("tv_consent", "") === "yes",
  session: store.get("tv_session", "") || (crypto.randomUUID ? crypto.randomUUID() : String(Math.random()).slice(2)),
  voice: null, T: {}, pending: null,
};
store.set("tv_session", S.session);
const LANGS = ["English", "Pidgin", "Yoruba", "Hausa", "Igbo"];
const TYPES = {
  sale: ["🛒", "Sold (paid)"], credit_sale: ["📝", "Sold on credit"], payment_received: ["💰", "Paid me back"],
  expense: ["💸", "Spent"], credit_purchase: ["📦", "Bought on credit (I owe)"], payment_made: ["↩️", "I paid back"],
};

// every screen word comes from ui_text.py (/api/ui); a missing word falls back to English, never to the key
const t = (k, d = "") => S.T[k] || d || "";

// One icon style for the interface (thin line, currentColor). Emoji stay only inside conversation text.
const ICONS = {
  mark: '<path d="M8 10v4M12 7v10M16 9v6" stroke-width="2.2"/>',
  chat: '<path d="M4.5 5.5h15v10.5h-9.5l-5.5 4z"/>',
  book: '<path d="M6 4.5h11.5v15H7.5A1.5 1.5 0 0 1 6 18z"/><path d="M6 18a1.5 1.5 0 0 1 1.5-1.5h10"/><path d="M9.5 8.5h5"/>',
  users: '<circle cx="9" cy="8.5" r="3.2"/><path d="M3 19.5a6 6 0 0 1 12 0"/><path d="M15.5 5.3a3.2 3.2 0 0 1 0 6.4M17.5 13.8a6 6 0 0 1 3.5 5.7"/>',
  chart: '<path d="M4 20h16M7 16.5v-5M12 16.5V6.5M17 16.5v-8"/>',
  bank: '<path d="M3.5 9.5 12 4l8.5 5.5"/><path d="M6 10v7M10 10v7M14 10v7M18 10v7M4 19.5h16"/>',
  mic: '<rect x="9" y="3.5" width="6" height="11" rx="3"/><path d="M5.5 11.5a6.5 6.5 0 0 0 13 0M12 18v2.5"/>',
  camera: '<path d="M4 8.5h3.2l1.8-2.5h6l1.8 2.5H20v10.5H4z"/><circle cx="12" cy="13.5" r="3.3"/>',
  send: '<path d="M5 12h12M12 6l6 6-6 6"/>',
  speaker: '<path d="M4.5 9.5h3.5l4.5-4v13l-4.5-4H4.5z"/><path d="M16 9a4 4 0 0 1 0 6M18.5 6.5a7.5 7.5 0 0 1 0 11"/>',
  more: '<circle cx="12" cy="5.5" r="1.2"/><circle cx="12" cy="12" r="1.2"/><circle cx="12" cy="18.5" r="1.2"/>',
  chev: '<path d="M7 10l5 5 5-5"/>',
  grid: '<rect x="4" y="4" width="7" height="7" rx="1.5"/><rect x="13" y="4" width="7" height="7" rx="1.5"/><rect x="4" y="13" width="7" height="7" rx="1.5"/><rect x="13" y="13" width="7" height="7" rx="1.5"/>',
  back: '<path d="M15 5l-7 7 7 7"/>',
  home: '<path d="M4 11 12 4.5 20 11"/><path d="M6.5 9.5V19.5h11V9.5"/><path d="M10 19.5v-5h4v5"/>',
  person: '<circle cx="12" cy="8.5" r="3.8"/><path d="M4.5 20a7.5 7.5 0 0 1 15 0"/>',
  bell: '<path d="M6 16.5V11a6 6 0 0 1 12 0v5.5l1.5 1.5h-15z"/><path d="M10 20.5a2 2 0 0 0 4 0"/>',
  doc: '<path d="M6.5 3.5h7l4 4v13h-11z"/><path d="M13.5 3.5v4h4M9 12.5h6M9 16h6"/>',
  eye: '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="3"/>',
  eyeoff: '<path d="M3 3l18 18"/><path d="M10.6 5.6A9.7 9.7 0 0 1 12 5.5c6 0 9.5 6.5 9.5 6.5a17 17 0 0 1-2.8 3.6M6.4 6.9C3.9 8.6 2.5 12 2.5 12S6 18.5 12 18.5c1.7 0 3.2-.5 4.5-1.2"/><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  out: '<path d="M14 4.5h5.5v15H14"/><path d="M10 8l-4 4 4 4M6 12h10"/>',
  bulb: '<path d="M9 17.5h6M10 20.5h4"/><path d="M12 3.5a6 6 0 0 0-3.5 10.9V16h7v-1.6A6 6 0 0 0 12 3.5z"/>',
  globe: '<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c2.5 2.5 3.5 5.5 3.5 8.5s-1 6-3.5 8.5c-2.5-2.5-3.5-5.5-3.5-8.5s1-6 3.5-8.5z"/>',
  shop: '<path d="M4 9.5 5.5 4.5h13L20 9.5"/><path d="M4 9.5a2.7 2.7 0 0 0 5.3 0 2.7 2.7 0 0 0 5.4 0 2.7 2.7 0 0 0 5.3 0"/><path d="M5.5 11.5v8h13v-8"/>',
  trash: '<path d="M4.5 7h15M9.5 7V4.5h5V7M6.5 7l1 13h9l1-13"/>',
  sparkle: '<path d="M12 3.5l1.8 5 5 1.8-5 1.8-1.8 5-1.8-5-5-1.8 5-1.8z"/>',
};
const svg = (n, size = 22) => `<svg class="ic" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[n] || ""}</svg>`;
function mountIcons(root = document) {
  root.querySelectorAll("[data-icon]").forEach((el) => {
    const n = el.dataset.icon, size = n === "chev" ? 16 : el.closest(".fab") ? 30 : el.closest(".tabs") ? 24 : 22;
    if (el.tagName === "LABEL") { const keep = el.querySelector("input"); el.innerHTML = svg(n, size); if (keep) el.appendChild(keep); }
    else el.innerHTML = svg(n, size);
  });
}
mountIcons();
const naira = (x) => (x < 0 ? "-₦" : "₦") + Math.round(Math.abs(x || 0)).toLocaleString("en-NG");
const nm = (x) => `<span class="money">${naira(x)}</span>`;  // an amount the eye button can hide
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (s) => esc(s).replace(/\*(.+?)\*/g, "<b>$1</b>").replace(/_(.+?)_/g, "<i>$1</i>").replace(/\n/g, "<br>");
const day = (iso) => { if (!iso) return ""; const d = new Date(iso + "T12:00:00"); return isNaN(d) ? iso : d.toLocaleDateString("en-GB", { day: "numeric", month: "short" }); };
const WEEK = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const wd = (en) => { const i = WEEK.indexOf(en); return i < 0 ? en : t("wd_" + i, en); };
const now = () => new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

function toast(msg, ms = 2500) {
  const el = $("#toast");
  el.textContent = msg; el.classList.add("on");
  clearTimeout(toast.h); toast.h = setTimeout(() => el.classList.remove("on"), ms);
}

// ngrok's free links show a warning page to browsers unless this header is sent (harmless elsewhere)
const HDR = { "ngrok-skip-browser-warning": "1" };
async function api(path, opts = {}) {
  const ctl = new AbortController(), timer = setTimeout(() => ctl.abort(), opts.timeout || 60000);
  let r;
  try {
    r = await fetch(path, { ...opts, signal: ctl.signal, headers: { ...HDR, ...(opts.headers || {}) } });
  } catch (e) {
    throw new Error(e.name === "AbortError" ? t("error", "No answer from the server. Try again.")
                                            : t("offline", "Can't reach TradeVoice. Check your internet."));
  } finally { clearTimeout(timer); }
  let body = null;
  try { body = await r.json(); } catch {}
  if (r.status === 401 && body && body.login && !path.startsWith("/api/auth/me")) { showLogin(); }
  if (!r.ok) throw new Error((body && (body.error || (typeof body.detail === "string" && body.detail))) || t("error", "Something went wrong."));
  return body;
}
const post = (path, data) => api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });

// ------------------------------------------------------------------ language + words on screen

async function loadWords() {
  try { S.T = await api(`/api/ui?lang=${encodeURIComponent(S.lang)}`); } catch { S.T = {}; }
  document.querySelectorAll("[data-t]").forEach((el) => { if (S.T[el.dataset.t]) el.textContent = S.T[el.dataset.t]; });
  const readWord = t("ask", "Ask");
  document.querySelectorAll(".read span").forEach((b) => (b.textContent = readWord));
  document.querySelectorAll(".read").forEach((b) => b.setAttribute("aria-label", readWord));
  $("#text").placeholder = t("message", "Message");
  $("#recHint").textContent = t("recording", "Recording… let go to send");
  $("#sub").textContent = S.shop || "TradeVoice";  // whose book this is; not a fake "online" status
  const h = new Date().getHours();
  $("#hi").textContent = t(h < 12 ? "good_morning" : h < 17 ? "good_afternoon" : "good_evening", "Hello");
  $("#speakLang span").textContent = LANG_NAMES[S.lang] || S.lang;
  document.documentElement.lang = { Yoruba: "yo", Hausa: "ha", Igbo: "ig", Pidgin: "pcm" }[S.lang] || "en";
  document.documentElement.dir = (S.T._dir) || "ltr";
  Object.keys(TYPES).forEach((k) => { if (S.T["t_" + k]) TYPES[k][1] = S.T["t_" + k]; });
  const cur = document.querySelector(".tabs button.on")?.dataset.tab;
  if (cur && cur !== "talk" && S.me) showTab(cur);  // redraw the open screen in the new language
  mountIcons();
}

function setLang(lang) {
  S.lang = lang; store.set("tv_lang", lang);
  if (S.me) post("/api/auth/me", { lang }).catch(() => {});
  return loadWords().then(() => { if (S.me && !chat.querySelector(".msg.out")) greet(); });  // fresh chat: greet again in the new language
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
function voiceNote(src, { speakId = null, autoplay = false, seconds = null } = {}) {
  const wrap = document.createElement("div");
  wrap.className = "vn";
  const bars = Array.from({ length: 28 }, () => `<i style="height:${25 + Math.round(Math.random() * 75)}%"></i>`).join("");
  wrap.innerHTML = `<button class="play" aria-label="Play">▶</button><span class="wave">${bars}</span><span class="len">0:00</span>`;
  const audio = new Audio();
  audio.preload = "none";
  const btn = $(".play", wrap), len = $(".len", wrap), waves = [...wrap.querySelectorAll(".wave i")];
  const mmss = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
  if (seconds) len.textContent = mmss(seconds);  // browser recordings often report no length
  audio.onloadedmetadata = () => { if (isFinite(audio.duration)) len.textContent = mmss(audio.duration); };
  audio.ontimeupdate = () => {
    const p = audio.duration ? audio.currentTime / audio.duration : 0;
    waves.forEach((w, i) => w.classList.toggle("done", i / waves.length < p));
    len.textContent = mmss(audio.currentTime);
  };
  audio.onended = () => { btn.textContent = "▶"; waves.forEach((w) => w.classList.remove("done"));
    if (seconds) len.textContent = mmss(seconds); };
  audio.onerror = () => { wrap.remove(); };
  const play = async () => {
    if (!audio.src) audio.src = src || `/api/speak/${speakId}`;  // a plain URL, started inside the tap
    if (audio.paused) {
      document.querySelectorAll("audio").forEach((a) => a !== audio && a.pause());
      voiceNote.current?.pause(); voiceNote.current = audio;
      audio.play().then(() => (btn.textContent = "❚❚")).catch(() => {});
    } else { audio.pause(); btn.textContent = "▶"; }
  };
  btn.onclick = play;
  if (autoplay) setTimeout(play, 50);
  return wrap;
}

function quickReplies() {
  const q = document.createElement("div");
  q.className = "quick";
  q.innerHTML = `<button data-v="yes">${esc(t("yes_save", "✅ Yes, save"))}</button><button data-v="no">${esc(t("no", "❌ No"))}</button>`;
  q.onclick = (e) => {
    const v = e.target.dataset.v; if (!v) return;
    q.querySelectorAll("button").forEach((b) => (b.disabled = true));
    sendText(v === "yes" ? "yes" : "no", e.target.textContent);
  };
  chat.appendChild(q); scrollDown();
}

// "Which Feranmi?": one button per customer (balance + last activity), plus "new customer"
function choiceReplies(choices) {
  const q = document.createElement("div");
  q.className = "quick choices";
  q.innerHTML = choices.map(([id, label]) => `<button data-v="${esc(id)}">${esc(label)}</button>`).join("");
  q.onclick = (e) => {
    const b = e.target.closest("button"); if (!b) return;
    q.querySelectorAll("button").forEach((x) => (x.disabled = true));
    sendText(b.dataset.v, b.textContent);
  };
  chat.appendChild(q); scrollDown();
}

// the app follows what the trader actually speaks or writes: speak Yoruba and the whole app turns Yoruba
function followLanguage(r) {
  const local = ["Yoruba", "Hausa", "Igbo"];
  const next = local.includes(r.detected) ? r.detected : local.includes(r.lang) ? r.lang : null;
  if (next && next !== S.lang) { setLang(next); toast(`🗣️ ${LANG_NAMES[next]}`, 1800); }
}

function showReply(r, { autoplay = false } = {}) {
  followLanguage(r);
  let html = fmt(r.text);
  if (r.english) html += `<div class="en">🇬🇧 ${fmt(r.english)}</div>`;
  if (r.message) {
    html += `<div class="quote">${fmt(r.message)}</div><a class="wa" href="${esc(r.link)}" target="_blank" rel="noopener">📲 ${esc(t("open_whatsapp", "Open WhatsApp"))}</a><div class="en">${esc(t("draft_note", ""))}</div>`;
  }
  const el = bubble("in", html);
  if (r.speak && S.voice) el.insertBefore(voiceNote(null, { speakId: r.speak, autoplay }), el.querySelector(".meta"));
  document.querySelectorAll(".quick").forEach((q) => q.querySelectorAll("button").forEach((b) => (b.disabled = true)));
  if (r.choices && r.choices.length) choiceReplies(r.choices);
  else if (r.pending) quickReplies();
  scrollDown();
}

async function sendText(text, shown) {
  text = text.trim(); if (!text) return;
  bubble("out", fmt(shown || text), { ticks: true });
  const wait = typing();
  try {
    const r = await post("/api/message", { session: S.session, text, shop: S.shop || null, lang: S.lang });
    wait.remove(); showReply(r);
  } catch (e) { wait.remove(); bubble("in err", esc(e.message)); }
}

// ------------------------------------------------------------------ hold to talk

const mic = $("#mic"), input = $("#text");
// idle -> starting (mic permission / warm-up) -> recording -> idle.  Two ways to use it, like WhatsApp:
// hold and let go to send, OR tap once to start and tap again to send (a lifted finger can never leave it stuck).
let rec = null, stream = null, chunks = [], recStart = 0, recTimer = null, startX = 0;
let state = "idle", held = false, pressAt = 0, tapMode = false, cancelRec = false;

function micIcon() {
  const want = input.value.trim() ? "send" : "mic";
  if (mic.dataset.icon !== want) { mic.dataset.icon = want; mic.innerHTML = svg(want); }
  mic.setAttribute("aria-label", want === "send" ? t("save", "Send") : t("hold", "Hold to talk"));
}
input.addEventListener("input", micIcon);
input.addEventListener("keydown", (e) => { if (e.key === "Enter") { sendText(input.value); input.value = ""; micIcon(); } });

function pickMime() {
  const opts = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];
  return opts.find((m) => window.MediaRecorder && MediaRecorder.isTypeSupported(m)) || "";
}

function hint(text) { $("#recHint").textContent = text; }

async function startRec() {
  state = "starting"; cancelRec = false; tapMode = false;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch {
    state = "idle"; return toast("Allow the microphone to talk to TradeVoice.", 4000);
  }
  const mime = pickMime();
  rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
  chunks = [];
  rec.ondataavailable = (ev) => ev.data.size && chunks.push(ev.data);
  rec.onstop = () => { stream.getTracks().forEach((tr) => tr.stop()); finishRec(); };
  rec.start(); recStart = Date.now(); state = "recording";
  mic.classList.add("rec"); $("#recbar").classList.add("on");
  hint(t("recording", "Recording… let go to send"));
  recTimer = setInterval(() => {
    const s = Math.floor((Date.now() - recStart) / 1000);
    $("#recTime").textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
    if (s >= 110) stopRec(); // Intron takes up to 2 minutes
  }, 250);
  if (!held) { tapMode = true; hint(t("tap_send", "Tap 🎤 again to send")); } // finger lifted while the mic warmed up
}

function stopRec(cancel = false) {
  cancelRec = cancel;
  clearInterval(recTimer);
  mic.classList.remove("rec"); $("#recbar").classList.remove("on"); $("#recTime").textContent = "0:00";
  if (rec && rec.state === "recording") rec.stop(); else state = "idle";
}

async function finishRec() {
  state = "idle";
  const ms = Date.now() - recStart;
  if (cancelRec) return toast(t("cancelled", "Cancelled"));
  if (ms < 700) return toast(t("hold", "Hold 🎤 to talk"));
  const blob = new Blob(chunks, { type: rec.mimeType || "audio/webm" });
  const ext = (rec.mimeType || "").includes("mp4") ? ".m4a" : (rec.mimeType || "").includes("ogg") ? ".ogg" : ".webm";
  const mine = bubble("out", "", { ticks: true });
  mine.insertBefore(voiceNote(URL.createObjectURL(blob), { seconds: ms / 1000 }), mine.querySelector(".meta"));
  const wait = typing();
  const fd = new FormData();
  fd.append("file", blob, "note" + ext); fd.append("session", S.session); fd.append("lang", S.lang);
  fd.append("consent", "yes"); fd.append("shop", S.shop || "");
  try {
    const r = await api("/api/voice", { method: "POST", body: fd, timeout: 90000 });
    wait.remove();
    const heard = document.createElement("div");
    heard.className = "heard"; heard.textContent = `“${r.heard}”`;
    mine.insertBefore(heard, mine.querySelector(".meta"));
    showReply(r, { autoplay: true }); // they spoke, so answer out loud
  } catch (e) { wait.remove(); bubble("in err", esc(e.message)); }
}

mic.addEventListener("pointerdown", (e) => {
  e.preventDefault();
  if (input.value.trim()) { sendText(input.value); input.value = ""; micIcon(); return; }
  if (state === "recording" && tapMode) return stopRec();  // second tap = send
  if (state !== "idle") return;
  if (!S.consent) return showLogin();
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
    return toast("This browser can't record. Type instead (the link must be https).", 4000);
  }
  mic.setPointerCapture?.(e.pointerId);
  held = true; pressAt = Date.now(); startX = e.clientX;
  startRec();
});
mic.addEventListener("pointermove", (e) => {
  if (held && state === "recording" && !tapMode && startX - e.clientX > 90) { held = false; stopRec(true); }
});
["pointerup", "pointercancel"].forEach((ev) => mic.addEventListener(ev, () => {
  if (!held) return;
  held = false;
  if (state !== "recording" || tapMode) return;                 // still warming up: startRec switches to tap mode
  if (Date.now() - pressAt < 450) { tapMode = true; hint(t("tap_send", "Tap 🎤 again to send")); return; }
  stopRec();                                                     // held and let go = send
}));
$("#recbar").addEventListener("click", () => { if (state === "recording") stopRec(true); }); // tap the bar = cancel
mic.addEventListener("contextmenu", (e) => e.preventDefault());

// ------------------------------------------------------------------ photo of the book

$("#photo").addEventListener("change", (e) => { const file = e.target.files[0]; e.target.value = ""; if (file) sendPhoto(file); });
async function sendPhoto(file) {
  if (!S.consent) return showLogin();
  bubble("out", `<img class="snap" src="${URL.createObjectURL(file)}" alt="book page">`, { ticks: true });
  const wait = typing();
  const fd = new FormData(); fd.append("file", await shrink(file)); fd.append("consent", "yes");
  try {
    const r = await api("/api/photo", { method: "POST", body: fd, timeout: 120000 });
    wait.remove(); photoRows(r);
  } catch (err) { wait.remove(); bubble("in err", esc(err.message)); }
}

function photoRows(r) {
  if (!r.rows.length) return bubble("in", esc(t("photo_none", "I couldn't find money records in this photo.")));
  const opts = (sel) => Object.entries(TYPES).map(([k, [, lb]]) => `<option value="${k}" ${k === sel ? "selected" : ""}>${lb}</option>`).join("");
  const rows = r.rows.map((x, i) => `
    <div class="row" data-i="${i}">
      <input type="checkbox" ${x.save ? "checked" : ""}>
      <div class="fields">
        <select>${opts(x.type)}</select>
        <input class="f amt" inputmode="numeric" value="${x.amount ?? ""}" placeholder="₦ amount">
        <input class="f who" value="${esc(x.customer)}" placeholder="name">
      </div>
      ${x.line ? `<div class="from">“${esc(x.line)}”${x.meaning ? `<br><span class="mean">${esc(x.meaning)}</span>` : ""}</div>` : ""}
      ${x.checks.length ? `<div class="chk">⚠️ ${esc(x.checks.join(" · "))}</div>` : ""}
    </div>`).join("");
  const el = bubble("in", `📸 ${esc(t("photo_read", "I read {n} lines.").replace("{n}", r.rows.length))}
    <div class="rows">${rows}</div><button class="save">${esc(t("save_ticked", "✅ Save ticked"))}</button>`);
  $(".save", el).onclick = async (ev) => {
    const out = [...el.querySelectorAll(".row")].map((row) => {
      const x = r.rows[row.dataset.i];
      return { ...x, save: $("input[type=checkbox]", row).checked, type: $("select", row).value,
               amount: $(".amt", row).value, customer: $(".who", row).value };
    });
    ev.target.disabled = true;
    try {
      const res = await post("/api/save_rows", { rows: out });
      el.querySelectorAll("input,select").forEach((x) => (x.disabled = true));
      ev.target.textContent = `✓ ${t("saved_n", "Saved {n}.").replace("{n}", res.saved)}`;
      const done = bubble("in", `${esc(t("saved_n", "Saved {n}.").replace("{n}", res.saved))}` +
        (res.problems.length ? `<div class="en">${esc(res.problems.join("; "))}</div>` : "") +
        `<div class="rbtns"><button data-go="home">${esc(t("nav_home", "Home"))}</button></div>`);
      $("[data-go]", done).onclick = () => showTab("home");
    } catch (e) { ev.target.disabled = false; bubble("in err", esc(e.message)); }
  };
}

// ------------------------------------------------------------------ screens

async function showTab(name) {
  document.querySelectorAll(".screen").forEach((s) => s.classList.toggle("active", s.id === name));
  document.querySelectorAll(".tabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === name));
  $("#composer").style.display = name === "talk" ? "" : "none";
  if (name !== "customers") $("#app").classList.remove("in-thread");
  else if (typeof C !== "undefined" && C.open) $("#app").classList.add("in-thread");
  const load = { home: loadHome, customers: () => loadCustomers(), insights: loadInsights, profile: loadProfile }[name];
  if (load) { try { await load(); } catch (e) { toast(e.message); } }
  if (name === "talk") scrollDown();
}
document.querySelectorAll(".tabs button").forEach((b) => (b.onclick = () => showTab(b.dataset.tab)));

// 🏠 Home: today in one big card, who owes, four big actions, one insight, the last records
const IN_TYPES = ["sale", "payment_received"], OUT_TYPES = ["expense", "payment_made", "credit_purchase"];
function recordRow(e, today) {
  const cls = IN_TYPES.includes(e.type) ? "in" : e.type === "credit_sale" ? "credit" : "out";
  const sign = cls === "in" ? "+" : cls === "out" ? "−" : "";
  const arrow = cls === "in" ? "↓" : cls === "out" ? "↑" : "⏳";
  return `<button class="lrow entry" data-entry='${esc(JSON.stringify(e))}'>
    <span class="ricon ${cls}">${arrow}</span>
    <span class="main"><span class="t">${esc([TYPES[e.type]?.[1] || e.type, e.customer].filter(Boolean).join(" · "))}</span>
      <span class="s">${esc([e.item, e.due_date ? t("due", "Due {d}").replace("{d}", day(e.due_date)) : ""].filter(Boolean).join(" · "))}</span></span>
    <span class="amt ${cls}"><span class="money">${sign}${naira(e.amount)}</span>
      <small>${esc(e.created_at.slice(0, 10) === today ? e.created_at.slice(11, 16) : day(e.created_at.slice(0, 10)))}</small></span></button>`;
}

async function loadHome() {
  const [d, debts, ins] = await Promise.all([api("/api/today"), api("/api/debts"), api("/api/insights").catch(() => ({}))]);
  const s = d.summary, profit = s.sales - s.expenses;
  const owed = debts.owed_to_me.reduce((a, x) => a + x.balance, 0), mine = debts.i_owe.reduce((a, x) => a + x.balance, 0);
  const late = debts.owed_to_me.filter((x) => x.overdue).length;
  const f = ins && ins.forecast;
  $("#homeBody").innerHTML = `
    <div class="hero">
      <div class="hrow"><span class="hlabel">${esc(t("today", "Today"))} · ${esc(day(s.date))}</span>
        <button class="read ask" data-screen="today">${svg("mic", 18)}<span>${esc(t("ask", "Ask"))}</span></button></div>
      <div class="main-fig ${profit < 0 ? "neg" : ""}">${nm(profit)}</div>
      <div class="cap">${esc(t("profit_today", "Sold minus spent"))}</div>
      <div class="pair">
        <div><div class="k"><span class="arrow in">↓</span>${esc(t("sold", "Sold"))}</div><div class="v">${nm(s.sales)}</div></div>
        <div><div class="k"><span class="arrow out">↑</span>${esc(t("spent", "Spent"))}</div><div class="v">${nm(s.expenses)}</div></div>
      </div>
    </div>
    <div class="debts">
      <button class="debt owed" data-go="customers"><span class="k">${esc(t("people_owe", "People owe you"))}</span>
        <span class="v">${nm(owed)}</span>${late ? `<span class="s">${esc(t("days_late", "{n} days late").replace("{n} days", late + " ×").replace("{n}", late))}</span>` : ""}</button>
      <button class="debt mine" data-go="customers"><span class="k">${esc(t("you_owe_people", "You owe"))}</span>
        <span class="v">${nm(mine)}</span></button>
    </div>
    <div class="actions">
      <button class="act main" data-go="talk"><span class="tile">${svg("mic", 26)}</span><span>${esc(t("act_voice", "Say it"))}</span></button>
      <label class="act"><span class="tile">${svg("camera", 26)}</span><span>${esc(t("act_snap", "Snap book"))}</span>
        <input type="file" accept="image/*" capture="environment" data-snap></label>
      <button class="act" data-go="customers"><span class="tile">${svg("bell", 26)}</span><span>${esc(t("act_remind", "Remind"))}</span></button>
      <button class="act" data-go="profile"><span class="tile">${svg("doc", 26)}</span><span>${esc(t("act_share", "For lender"))}</span></button>
    </div>
    ${f ? `<div class="card"><h2>${esc(t("next_week", "Next 7 days"))}<button data-go="insights">${esc(t("see_all", "See all"))}</button></h2>
      <div class="insight"><span class="ico">${svg("bulb", 24)}</span><span><span class="big">${nm(f.week_sales)}</span>
        <span class="s" style="display:block">${esc(t("busiest", "Busiest day"))}: <b>${esc(wd(f.busiest_day))}</b></span></span></div></div>` : ""}
    ${d.due.length ? `<div class="card"><h2>${esc(t("remind", "Remind"))}</h2>${d.due.map((r) => `<div class="lrow"><span class="ricon credit">⏳</span>
      <span class="main"><span class="t">${esc(r.customer)}</span><span class="s">${esc(t("owes_you", "owes you {m}").replace("{m}", naira(r.balance)))}</span></span>
      <button class="textbtn" data-remind="${esc(r.customer)}">${esc(t("remind", "Remind"))}</button></div>`).join("")}</div>` : ""}
    <div class="card"><h2>${esc(t("recent", "Recent"))}</h2>
      ${d.entries.slice(0, 8).map((e) => recordRow(e, s.date)).join("") || `<p class="empty">${esc(t("empty_book", "Nothing yet."))}</p>`}</div>`;
  $("#homeBody").querySelector(".ask").onclick = () => openAssist("today");
  $("#homeBody").querySelector("[data-snap]").onchange = (e) => { const f2 = e.target.files[0]; e.target.value = ""; if (f2) { showTab("talk"); sendPhoto(f2); } };
}
document.addEventListener("click", (e) => { const g = e.target.closest("[data-go]"); if (g && g.tagName === "BUTTON" && !g.closest(".msg")) showTab(g.dataset.go); });

// tap a record: details + delete, kept apart from the list so a stray tap can't delete money
document.addEventListener("click", (ev) => {
  const row = ev.target.closest(".lrow.entry"); if (!row) return;
  const e = JSON.parse(row.dataset.entry);
  sheet(`<h3>${esc(TYPES[e.type]?.[1] || e.type)} · ${naira(e.amount)}</h3>
    <p>${esc([e.customer, e.item, e.quantity ? `${e.quantity} ${e.unit || ""}` : "", e.due_date ? t("due", "Due {d}").replace("{d}", day(e.due_date)) : "",
             e.created_at.replace("T", " ").slice(0, 16)].filter(Boolean).join(" · "))}</p>
    <button class="primary" id="eClose">OK</button><p></p>
    <button class="danger" id="eDel">${esc(t("delete", "Delete"))}</button>`);
  $("#sheetBody").onclick = async (x) => {
    if (x.target.id === "eClose") $("#sheet").hidden = true;
    if (x.target.id === "eDel" && confirm(t("delete", "Delete") + "?")) {
      await api(`/api/entry/${e.id}`, { method: "DELETE" }); $("#sheet").hidden = true; loadHome();
    }
  };
});

async function loadInsights() {
  const { forecast: f, top } = await api("/api/insights");
  if (!f) { $("#insightsBody").innerHTML = `<p class="empty">${esc(t("empty_insights", "Record a few more days."))}</p>`; return; }
  const max = Math.max(...f.plan.map((p) => p.sales), 1);
  const short = S.lang === "English" || S.lang === "Pidgin";
  const bars = f.plan.map((p) => `<div class="${p.weekday === f.busiest_day ? "peak" : ""}"><span style="height:${Math.round((p.sales / max) * 100)}%"></span><em>${esc(short ? p.weekday.slice(0, 3) : wd(p.weekday))}</em></div>`).join("");
  $("#insightsBody").innerHTML = `
    <div class="hero-fig">${naira(f.week_sales)}</div>
    <p class="muted">${esc(t("cash_left", "Cash left after normal spending"))}: <b>${naira(f.expected_cash)}</b></p>
    <div class="bars">${bars}</div>
    <p class="muted">${esc(t("busiest", "Busiest day"))}: <b>${esc(wd(f.busiest_day))}</b>. ${esc(t("stock_tip", ""))}</p>
    ${f.due_soon.length ? `<section class="sect"><h2>${esc(t("promised_week", "Promised this week"))}</h2>${f.due_soon.map((d) => `<div class="lrow"><span class="when">${esc(day(d.due_date))}</span><span class="main"><span class="t">${esc(d.customer)}</span></span><span class="amt">${naira(d.balance)}</span></div>`).join("")}</section>` : ""}
    <section class="sect"><h2>${esc(t("best_sellers", "Best sellers"))} <small>· 14 days</small></h2>
      ${top.map((x, i) => `<div class="lrow"><span class="when">${i + 1}</span><span class="main"><span class="t">${esc(x.item)}</span>
        <span class="s">${x.qty && x.unit ? `${Math.round(x.qty)} ${esc(x.unit)}${x.qty !== 1 ? "s" : ""}` : ""}</span></span><span class="amt">${naira(x.revenue)}</span></div>`).join("")}</section>
    <p class="note">${esc(t("forecast_note", ""))}</p>`;
}

// 👤 Me: who is logged in, the score + lender statement, the year + tax, then settings
function meHtml() {
  const me = S.me || {};
  return `<div class="idcard"><span class="cav">${esc(initials(me.shop || me.name || "TV"))}</span>
      <span><b>${esc(me.shop || S.shop || "TradeVoice")}</b><span class="muted">${esc(t("logged_as", "Logged in as {p}").replace("{p}", me.phone || ""))}</span></span></div>`;
}
function settingsHtml(empty) {
  return `<section class="sect"><h2>${esc(t("settings", "Settings"))}</h2><div class="menu">
    <button data-me="lang">${svg("globe")}<span class="grow">${esc(t("language", "Language"))}</span><span class="val">${esc(LANG_NAMES[S.lang])}</span></button>
    <button data-me="shop">${svg("shop")}<span class="grow">${esc(t("shop_name", "Shop name"))}</span><span class="val">${esc(S.shop || "")}</span></button>
    <button data-me="view">${svg("chat")}<span class="grow">WhatsApp view</span><span class="val">${S.view === "wa" ? "✓" : ""}</span></button>
    ${empty ? `<button data-me="sample">${svg("sparkle")}<span class="grow">${esc(t("sample_data", "Try with sample records"))}</span></button>` : ""}
    <a href="/api/statement?shop=${encodeURIComponent(S.shop)}" download target="_blank" rel="noopener">${svg("doc")}<span class="grow">${esc(t("tax_record", "Year record"))}</span></a>
    <button data-me="logout">${svg("out")}<span class="grow">${esc(t("logout", "Log out"))}</span></button>
    <button data-me="delete" class="red">${svg("trash")}<span class="grow">${esc(t("delete_account", "Delete my account and book"))}</span></button>
  </div><p class="note">${esc(t("privacy", ""))}</p></section>`;
}
$("#profileBody").addEventListener("click", async (e) => {
  const b = e.target.closest("[data-me]"); if (!b) return;
  const k = b.dataset.me;
  try {
    if (k === "lang") return $("#speakLang").click();
    if (k === "view") return setView(S.view === "wa" ? "app" : "wa");
    if (k === "shop") {
      const v = prompt(t("shop_name", "Shop name"), S.shop || ""); if (v === null) return;
      S.shop = v.trim(); store.set("tv_shop", S.shop); S.me = await post("/api/auth/me", { shop: S.shop }); loadWords(); return loadProfile();
    }
    if (k === "sample") { await post("/api/demo_data", {}); toast("✓"); return loadProfile(); }
    if (k === "logout") { await post("/api/auth/logout", {}); S.me = null; return showLogin(); }
    if (k === "delete" && prompt(t("delete_account", "Delete my account") + " — DELETE") === "DELETE") {
      await post("/api/auth/delete", { login_id: "-", code: "DELETE" }); S.me = null; toast("✓"); return showLogin();
    }
  } catch (err) { toast(err.message); }
});

async function loadProfile() {
  const { profile: p, year_data: y, tax } = await api(`/api/profile?lang=${encodeURIComponent(S.lang)}`);
  if (!p) { $("#profileBody").innerHTML = `${meHtml()}<p class="empty">${esc(t("empty_profile", "Your book is empty."))}</p>${taxHtml(y, tax)}${settingsHtml(true)}`; return; }
  $("#profileBody").innerHTML = `${meHtml()}
    <div class="card"><h2>${esc(t("score", "Record score"))}</h2>
    <div class="hero-fig">${p.score}<span class="of">/100</span> <span class="band">${esc(t("band_" + p.band, p.band))}</span></div>
    <div class="meter"><i style="width:${p.score}%"></i></div>
    <p class="muted">${esc(t("days_avg", "").replace("{d}", p.span_days).replace("{m}", naira(p.avg_daily_sales)))}</p>
    <a class="primary" href="/api/statement?shop=${encodeURIComponent(S.shop)}" download target="_blank" rel="noopener">${svg("doc")}${esc(t("share_lender", "Share with a lender"))}</a></div>
    <section class="sect"><h2>${esc(t("why_score", "Why this score"))}</h2>
      ${p.parts.map((x) => `<div class="part"><div class="pl"><span>${esc(t("sp_" + x.name, x.name))}</span><b>${Math.round(x.points)}/${x.max}</b></div>
        <div class="meter thin"><i style="width:${Math.round((x.points / x.max) * 100)}%"></i></div><div class="s">${esc(x.why)}</div></div>`).join("")}
      <p class="note">${esc(t("score_note", ""))}${p.has_demo_data ? " (demo data)" : ""}</p></section>
    ${yearHtml(y)}
    ${taxHtml(y, tax)}
    ${settingsHtml(false)}`;
}

// 📅 my year so far: the same numbers as the statement, laid out like the Book screen (no monospace text dump)
const longDay = (iso) => { const d = new Date(iso + "T12:00:00"); return isNaN(d) ? iso : d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }); };
function yearHtml(y) {
  if (!y) return `<section class="sect"><h2>${esc(t("my_year", "My year so far"))}</h2><p class="empty">${esc(t("no_year", "No records this year yet."))}</p></section>`;
  const top = Math.max(...y.by_type.map((x) => x.amount), 1);
  const months = y.months.length > 1 ? `<div class="bars year-bars">${y.months.map((m) => `<div class="${y.best_month && m.month === y.best_month.month ? "peak" : ""}"><span style="height:${Math.round((m.sales / Math.max(...y.months.map((x) => x.sales), 1)) * 100)}%"></span><em>${esc(m.month.slice(0, 3))}</em></div>`).join("")}</div>` : "";
  return `<section class="sect"><h2>${esc(t("my_year", "My year so far"))}</h2>
    <p class="muted">${esc(t("year_range", "{a} to {b} · {d} days recorded").replace("{a}", longDay(y.start)).replace("{b}", longDay(y.end)).replace("{d}", y.days_recorded))}</p>
    <div class="figures">
      <div><div class="k">${esc(t("sold", "Sold"))}</div><div class="v">${naira(y.sales)}</div>${y.credit_sales ? `<div class="s">${esc(t("on_credit", "{c} on credit").replace("{c}", naira(y.credit_sales)))}</div>` : ""}</div>
      <div><div class="k">${esc(t("spent", "Spent"))}</div><div class="v">${naira(y.expenses)}</div></div>
      <div><div class="k">${esc(t("sales_minus", "Sales minus spending"))}</div><div class="v ${y.profit < 0 ? "neg" : ""}">${naira(y.profit)}</div></div>
    </div>
    ${y.stock_note ? `<p class="callout">${esc(t("stock_note", ""))}</p>` : ""}
    <h3 class="sub">${esc(t("where_money", "Where the money went"))}</h3>
    ${y.by_type.map((x) => `<div class="part"><div class="pl"><span>${esc(t("xt_" + x.type, x.type))}</span><b>${naira(x.amount)}</b></div>
      <div class="meter thin"><i style="width:${Math.max(2, Math.round((x.amount / top) * 100))}%"></i></div></div>`).join("")}
    ${months ? `<h3 class="sub">${esc(t("best_month", "Best month"))}: ${esc(y.best_month.month)} · ${naira(y.best_month.sales)}</h3>${months}` : ""}
  </section>`;
}

// 🧾 tax: plain facts with sources + the trader's own year; never "you owe ₦X" (that is for the tax office)
function taxHtml(y, tax) {
  if (!tax) return "";
  const you = y ? `<p>${esc(t("tax_you", "").replace("{s}", naira(y.sales)).replace("{e}", naira(y.expenses)))}</p>` : "";
  const rent = y && y.rent_levies.count ? `<p class="muted">${esc(t("tax_rent", "").replace("{n}", y.rent_levies.count).replace("{m}", naira(y.rent_levies.amount)))}</p>` : "";
  return `<section class="sect" id="taxSect"><h2>${esc(t("tax_title", "Tax and your records"))}</h2>
    ${you}${rent}
    <a class="primary block ghost" href="/api/statement?shop=${encodeURIComponent(S.shop)}" download target="_blank" rel="noopener">${esc(t("tax_record", "Year record for the tax office"))}</a>
    <h3 class="sub">${esc(t("tax_facts", "What the new tax law means for you"))}</h3>
    <ol class="facts">${tax.facts.map((f) => `<li><span>${esc(f.text)}</span> <a href="${esc(f.source)}" target="_blank" rel="noopener">${esc(t("source", "Source"))}</a></li>`).join("")}</ol>
    <p class="callout warn">${esc(tax.check)}</p>
  </section>`;
}

// remind buttons (Book + Debts): show the message first, then WhatsApp
document.addEventListener("click", async (e) => {
  const who = e.target.dataset?.remind, del = e.target.dataset?.del;
  if (who) {
    const lang = ["English", "Pidgin", "Yoruba"].includes(S.lang) ? S.lang : "Pidgin";
    const r = await api(`/api/reminder?customer=${encodeURIComponent(who)}&lang=${lang}&shop=${encodeURIComponent(S.shop)}`);
    if (!r.message) return toast(t("remind_none", "{n} doesn't owe you anything").replace("{n}", who));
    sheet(`<h3>📲 ${esc(t("remind", "Remind"))} ${esc(who)}</h3><div class="quote">${fmt(r.message)}</div>
      <a class="wa" href="${esc(r.link)}" target="_blank" rel="noopener">${esc(t("open_whatsapp", "Open WhatsApp"))}</a>
      <p>${esc(t("draft_note", "TradeVoice prepared this. You send it yourself."))}</p>`);
  }
  if (del && confirm("Delete this record?")) { await api(`/api/entry/${del}`, { method: "DELETE" }); loadHome(); }
});

// 🎙️ Ask TradeVoice: explains the screen out loud, then answers spoken questions about the trader's own book
const SILENT = "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=";
function unlockAudio() { const p = $("#player"); if (!p.src) { p.src = SILENT; p.play().catch(() => {}); } }
function sayUrl(url) {   // plays on the same element the first tap unlocked (phones allow it after that)
  if (!S.voice || !url) return;
  const p = $("#player"); p.src = url; p.play().catch(() => {});
}
const A = { screen: "today", rec: null, chunks: [], stream: null };

function aBubble(side, html) {
  const el = document.createElement("div");
  el.className = `msg ${side}`; el.innerHTML = html;
  $("#alog").appendChild(el); $("#alog").scrollTop = $("#alog").scrollHeight;
  return el;
}

function openAssist(screen) {
  A.screen = screen;
  unlockAudio();
  if (S.voice) sayUrl(`/api/explain/${screen}/audio?lang=${encodeURIComponent(S.lang)}&t=${Date.now()}`); // inside the tap
  sheet(`<div class="assist">
    <div class="ahead"><h3>${esc(t("assist_title", "Ask TradeVoice"))}</h3><button class="icon" id="aClose" aria-label="Close">✕</button></div>
    <div class="alog" id="alog"></div>
    <div class="call" id="call">
      <button class="orb" id="orb" aria-label="Talk">${svg("mic", 30)}</button>
      <div class="cstate" id="cstate">${esc(t("assist_hint", "Tap and talk"))}</div>
      <button class="textbtn" id="cend" hidden>${esc(t("end_call", "End"))}</button>
    </div></div>`);  // voice only: talk to it like a phone call (typing stays in the main chat)
  $("#sheet").classList.add("tall");
  const wait = aBubble("in", '<span class="typing"><i></i><i></i><i></i></span>');
  api(`/api/explain/${screen}?lang=${encodeURIComponent(S.lang)}`)
    .then((r) => { wait.innerHTML = fmt(r.text); })
    .catch((e) => { wait.innerHTML = esc(e.message); });
  $("#aClose").onclick = closeAssist;
  $("#orb").onclick = () => (VC.on ? (VC.phase === "speaking" ? interrupt() : null) : startCall());
  $("#cend").onclick = endCall;
  startCall();  // hands-free from the first tap: it explains the screen, then listens
  $("#sheetBody").onclick = (e) => { const v = e.target.dataset?.say; if (v) askAssist({ text: v }); };
}

function closeAssist() {
  endCall();
  $("#player").pause(); $("#sheet").hidden = true; $("#sheet").classList.remove("tall");
}

// ---- hands-free call: listen -> (a second of quiet = done) -> answer out loud -> listen again
const VC = { on: false, phase: "idle", stream: null, ctx: null, an: null, rec: null, timer: null, idle: 0, fails: 0 };
function callState(phase, label) {
  VC.phase = phase;
  const o = $("#orb"), st = $("#cstate"); if (!o) return;
  o.className = `orb ${phase}`; if (label) st.textContent = label;
  $("#cend").hidden = !VC.on;
}

async function startCall() {
  if (!S.consent) return showLogin();
  VC.on = true; VC.idle = 0; VC.fails = 0;
  try {
    VC.stream = VC.stream || await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    VC.ctx = VC.ctx || new (window.AudioContext || window.webkitAudioContext)();
    if (VC.ctx.state === "suspended") await VC.ctx.resume();
    if (!VC.an) { VC.an = VC.ctx.createAnalyser(); VC.an.fftSize = 1024; VC.ctx.createMediaStreamSource(VC.stream).connect(VC.an); }
  } catch { VC.on = false; callState("idle", t("assist_hint", "")); return toast("Allow the microphone to talk to TradeVoice.", 4000); }
  const p = $("#player");
  if (!p.paused && p.src && !p.src.startsWith("data:")) { callState("speaking", t("speaking", "Speaking… tap to talk")); p.onended = p.onerror = () => VC.on && listen(); }
  else listen();
}

function level() {
  const buf = new Float32Array(VC.an.fftSize); VC.an.getFloatTimeDomainData(buf);
  let sum = 0; for (const v of buf) sum += v * v; return Math.sqrt(sum / buf.length);
}

function listen() {
  if (!VC.on) return;
  clearInterval(VC.timer);
  const mime = pickMime(), chunks = [];
  VC.rec = new MediaRecorder(VC.stream, mime ? { mimeType: mime } : undefined);
  VC.rec.ondataavailable = (e) => e.data.size && chunks.push(e.data);
  let floor = 0, n = 0, talking = false, loud = 0, quiet = 0, t0 = Date.now();
  VC.rec.onstop = () => {
    clearInterval(VC.timer);
    if (!VC.on) return;
    if (!talking) {                        // nobody spoke: keep listening a while, then hang up to save data
      if (++VC.idle >= 3) return endCall();
      return listen();
    }
    VC.idle = 0;
    const blob = new Blob(chunks, { type: VC.rec.mimeType || "audio/webm" });
    const ext = (VC.rec.mimeType || "").includes("mp4") ? ".m4a" : (VC.rec.mimeType || "").includes("ogg") ? ".ogg" : ".webm";
    callState("thinking", t("thinking", "Thinking…"));
    askAssist({ blob, ext, silent: true }).then((r) => {
      if (!VC.on) return;
      if (!r) { if (++VC.fails >= 2) { endCall(); return toast(t("error", "Something went wrong."), 3000); } return setTimeout(listen, 600); }
      VC.fails = 0;
      if (r && r.speak && S.voice) {
        callState("speaking", t("speaking", "Speaking… tap to talk"));
        const p = $("#player"); p.onended = p.onerror = () => VC.on && listen();
        p.src = `/api/speak/${r.speak}`; p.play().catch(() => VC.on && listen());
      } else setTimeout(listen, 400);
    });
  };
  VC.rec.start(250);
  callState("listening", t("listening_call", "Listening… just talk"));
  VC.timer = setInterval(() => {
    const v = level(), ms = Date.now() - t0;
    if (ms < 400) { floor += v; n++; return; }            // learn the room's noise first (markets are loud)
    const th = Math.max(0.015, (floor / Math.max(n, 1)) * 2.2);
    $("#orb").style.setProperty("--lvl", Math.min(1, v / (th * 3)).toFixed(2));
    if (v > th) { loud++; quiet = 0; if (loud >= 3) talking = true; } else { loud = 0; if (talking) quiet += 60; }
    if ((talking && quiet >= 900) || ms > 25000 || (!talking && ms > 9000)) VC.rec.state === "recording" && VC.rec.stop();
  }, 60);
}

function interrupt() {                     // tap while it talks: stop and listen
  const p = $("#player"); p.onended = null; p.pause(); listen();
}

function endCall() {
  VC.on = false; clearInterval(VC.timer);
  if (VC.rec && VC.rec.state === "recording") VC.rec.stop();
  if (VC.stream) { VC.stream.getTracks().forEach((x) => x.stop()); VC.stream = null; }
  if (VC.ctx) { VC.ctx.close().catch(() => {}); VC.ctx = null; VC.an = null; }
  const p = $("#player"); p.onended = null;
  callState("idle", t("tap_to_talk", "Tap to talk"));
}

async function askAssist({ text = "", blob = null, ext = ".webm", silent = false }) {
  const mine = aBubble("out", blob ? '<span class="typing"><i></i><i></i><i></i></span>' : fmt(text));
  const wait = aBubble("in", `<span class="muted">${esc(t("thinking", "Thinking…"))}</span>`);
  const fd = new FormData();
  fd.append("screen", A.screen); fd.append("lang", S.lang); fd.append("speak_lang", S.lang);
  fd.append("session", S.session); fd.append("shop", S.shop || ""); fd.append("consent", S.consent ? "yes" : "");
  if (blob) fd.append("file", blob, "q" + ext); else fd.append("text", text);
  try {
    const r = await api("/api/assist", { method: "POST", body: fd, timeout: 90000 });
    if (blob) mine.innerHTML = fmt(r.heard);
    followLanguage(r);
    let html = fmt(r.text) + (r.english ? `<div class="en">🇬🇧 ${fmt(r.english)}</div>` : "");
    if (r.message) html += `<div class="quote">${fmt(r.message)}</div><a class="wa" href="${esc(r.link)}" target="_blank" rel="noopener">${esc(t("open_whatsapp", "Open WhatsApp"))}</a>`;
    if (r.choices && r.choices.length) html += `<div class="quick choices">${r.choices.map(([id, lb]) => `<button data-say="${esc(id)}">${esc(lb)}</button>`).join("")}</div>`;
    else if (r.pending) html += `<div class="quick"><button data-say="yes">${esc(t("yes_save", "Yes, save"))}</button><button data-say="no">${esc(t("no", "No"))}</button></div>`;
    wait.innerHTML = html;
    if (r.speak && !silent) sayUrl(`/api/speak/${r.speak}`);
    $("#alog").scrollTop = $("#alog").scrollHeight;
    return r;
  } catch (e) { mine.innerHTML = mine.innerHTML.includes("typing") ? "🎙️" : mine.innerHTML; wait.innerHTML = esc(e.message); return null; }
}

document.querySelectorAll(".read").forEach((b) => (b.onclick = () => openAssist(b.dataset.screen)));

// ------------------------------------------------------------------ sheets: speaking language, menu, welcome

function sheet(html) {
  $("#sheetBody").innerHTML = html; $("#sheet").hidden = false;
}
$("#sheet").onclick = (e) => { if (e.target.id === "sheet") $("#sheet").hidden = true; };

$("#speakLang").onclick = () => {   // one choice changes everything: screens, replies, voice and hearing
  sheet(`<h3>🌍 ${esc(t("language", "Language"))}</h3><div class="opts">${LANGS.map((k) =>
    `<button data-speak="${k}" class="${k === S.lang ? "on" : ""}">${LANG_NAMES[k]}</button>`).join("")}</div>`);
  $("#sheetBody").onclick = async (e) => {
    const k = e.target.dataset.speak; if (!k) return;
    $("#sheet").hidden = true; await setLang(k); toast(`🌍 ${LANG_NAMES[k]}`);
  };
};

const LANG_NAMES = { English: "English", Pidgin: "Pidgin", Yoruba: "Yorùbá", Hausa: "Hausa", Igbo: "Igbo" };

// 🔐 log in with your phone number: language -> number -> code (or "Confirm with WhatsApp") -> shop name + consent
const L = { id: null, poll: null, step: "phone" };
function showLogin() {
  if (!$("#login").hidden && L.step !== "phone") return;
  S.me = null; $("#login").hidden = false; loginLangs(); loginPhone();
}
function loginLangs() {
  const box = $("#loginLangs");
  box.innerHTML = LANGS.map((l) => `<button data-l="${l}" class="${l === S.lang ? "on" : ""}">${LANG_NAMES[l]}</button>`).join("");
  box.onclick = async (e) => {
    const l = e.target.dataset.l; if (!l) return;
    S.lang = l; store.set("tv_lang", l); await loadWords(); loginLangs();
    ({ phone: loginPhone, code: () => loginCode(L.last), shop: loginShop }[L.step] || loginPhone)();
  };
}
function loginPhone(err = "") {
  L.step = "phone"; clearInterval(L.poll);
  $("#loginStep").innerHTML = `<h1>${esc(t("login_title", "Your phone number"))}</h1><p>${esc(t("login_why", ""))}</p>
    <form id="lf1"><div class="phone"><span class="cc">🇳🇬 +234</span><input id="lphone" type="tel" inputmode="tel" autocomplete="tel"
      placeholder="0803 123 4567" value="${esc(store.get("tv_phone", ""))}"></div>
    <div class="lerr">${esc(err)}</div><button class="primary">${esc(t("continue", "Continue"))}</button></form>`;
  $("#lf1").onsubmit = async (e) => {
    e.preventDefault();
    const v = $("#lphone").value.trim(); if (!v) return;
    const btn = $("#lf1 .primary"); btn.disabled = true;
    try { const r = await post("/api/auth/start", { phone: v, lang: S.lang }); store.set("tv_phone", v); loginCode(r); }
    catch (err2) { loginPhone(err2.message); }
  };
  setTimeout(() => $("#lphone")?.focus(), 50);
}
function loginCode(r, err = "") {
  L.step = "code"; L.last = r; L.id = r.login_id;
  $("#loginStep").innerHTML = `<h1>${esc(t("code_title", "Enter the code"))}</h1>
    <p>${esc(r.sent ? t("code_sent", "").replace("{p}", r.phone) : r.verify_link ? t("code_not_sent", "") : "")}</p>
    ${r.demo_code ? `<div class="demo">${esc(t("demo_code", "Demo: your code is {c}").replace("{c}", r.demo_code))}</div>` : ""}
    <form id="lf2"><input id="lcode" class="otp" inputmode="numeric" autocomplete="one-time-code" maxlength="6" placeholder="••••••">
      <div class="lerr">${esc(err)}</div><button class="primary">${esc(t("continue", "Continue"))}</button></form>
    ${r.verify_link ? `<div class="or">— or —</div><a class="primary wa-go" id="lwa" href="${esc(r.verify_link)}" target="_blank" rel="noopener">${esc(t("verify_wa", "Confirm with WhatsApp"))}</a>
      <p class="consent">${esc(t("verify_wa_hint", ""))}</p>` : ""}
    <button class="textbtn" id="lback">${esc(t("change_number", "Change number"))}</button>`;
  $("#lf2").onsubmit = async (e) => {
    e.preventDefault();
    try { const res = await post("/api/auth/verify", { login_id: L.id, code: $("#lcode").value }); loggedIn(res.me); }
    catch (err2) { loginCode(r, err2.message); }
  };
  $("#lcode").oninput = (e) => { if (e.target.value.replace(/\D/g, "").length === 6) $("#lf2").requestSubmit(); };
  $("#lback").onclick = () => loginPhone();
  if ($("#lwa")) $("#lwa").onclick = () => { $("#lwa").textContent = t("waiting_wa", "Waiting…"); };
  clearInterval(L.poll);   // WhatsApp confirmation: check every 2 s while this screen is open
  L.poll = setInterval(async () => {
    if (L.step !== "code") return clearInterval(L.poll);
    try { const res = await post("/api/auth/poll", { login_id: L.id }); if (res.ok) loggedIn(res.me); } catch {}
  }, 2000);
  setTimeout(() => $("#lcode")?.focus(), 50);
}
function loggedIn(me) {
  clearInterval(L.poll); S.me = me;
  if (me.lang && me.lang !== S.lang) { S.lang = me.lang; store.set("tv_lang", me.lang); }
  if (me.new) return loginShop();
  finishLogin();
}
function loginShop() {
  L.step = "shop";
  $("#loginStep").innerHTML = `<h1>${esc(t("shop_q", "What is your shop called?"))}</h1>
    <form id="lf3"><input id="lshop" autocomplete="organization" placeholder="Chioma Stores" value="${esc(S.shop || "")}">
    <p class="consent">${esc(t("consent", ""))}</p><button class="primary">${esc(t("start_book", "Open my book"))}</button></form>`;
  $("#lf3").onsubmit = async (e) => {
    e.preventDefault();
    const shop = $("#lshop").value.trim() || "My shop";
    try { S.me = await post("/api/auth/me", { shop, lang: S.lang }); S.shop = shop; store.set("tv_shop", shop); finishLogin(); }
    catch (err) { toast(err.message); }
  };
}
async function finishLogin() {
  L.step = "done"; $("#login").hidden = true;
  S.consent = true; store.set("tv_consent", "yes");
  if (S.me && S.me.shop) { S.shop = S.me.shop; store.set("tv_shop", S.shop); }
  await loadWords(); greet(); showTab("home");
}

// ------------------------------------------------------------------ start

async function greet() {
  chat.innerHTML = `<div class="day">${esc(t("today", "Today"))}</div>`;
  bubble("in", fmt(t("hello", "Hello 👋 I'm your book. Tell me what you sold, who owes you, or ask me anything.")));
  const ex = document.createElement("div");
  ex.className = "chips";
  ["Mama Tunde dey owe me forty-five thousand", "Ṣé mo ní gbèsè lọ́wọ́ Alhaji?", "Who owes me?", "Wetin sell pass this week?"]
    .forEach((s) => { const b = document.createElement("button"); b.textContent = s; b.onclick = () => sendText(s); ex.appendChild(b); });
  chat.appendChild(ex);
  try {
    const d = await api("/api/today");
    d.due.forEach((r) => bubble("in", `📌 ${esc(t("remind", "Remind"))}: <b>${esc(r.customer)}</b> · ${naira(r.balance)}
      <div class="quick" style="margin-top:6px"><button data-remind="${esc(r.customer)}">📲 ${esc(t("remind", "Remind"))}</button></div>`));
  } catch {}
}

// App view (chat + dashboards) or WhatsApp view (just the conversation, as a trader sees it on WhatsApp)
function setView(v) {
  S.view = v === "wa" ? "wa" : "app"; store.set("tv_view", S.view);
  document.body.classList.toggle("wa-view", S.view === "wa");
  const b = $("#viewBtn"); if (b) b.hidden = S.view !== "wa";
  if (b) { b.innerHTML = svg(S.view === "wa" ? "grid" : "chat", 20); b.title = S.view === "wa" ? "App view" : "WhatsApp view";
           b.setAttribute("aria-label", b.title); }
  if (S.view === "wa") showTab("talk");
}
$("#viewBtn").onclick = () => setView(S.view === "wa" ? "app" : "wa");
setView(store.get("tv_view", "app"));

(async function start() {
  try { const st = await api("/api/status"); S.voice = st.voice; } catch {}
  await loadWords();
  micIcon();
  try { S.me = await api("/api/auth/me"); } catch { S.me = null; }
  if (!S.me) return showLogin();
  if (S.me.new) { $("#login").hidden = false; loginLangs(); return loginShop(); }
  finishLogin();
})();

// 👁 hide amounts (people around the stall can see the phone)
function setEye(hide) {
  document.body.classList.toggle("hide-money", hide); store.set("tv_hide", hide ? "1" : "");
  $("#eyeBtn").innerHTML = svg(hide ? "eyeoff" : "eye", 22); $("#eyeBtn").setAttribute("aria-label", t("hide_amounts", "Hide amounts"));
}
$("#eyeBtn").onclick = () => setEye(!document.body.classList.contains("hide-money"));
setEye(store.get("tv_hide", "") === "1");
