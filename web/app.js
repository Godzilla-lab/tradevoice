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

// every screen word comes from ui_text.py (/api/ui); a missing word falls back to English, never to the key
const t = (k, d = "") => S.T[k] || d || "";
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
  if (!r.ok) throw new Error((body && (body.error || (typeof body.detail === "string" && body.detail))) || t("error", "Something went wrong."));
  return body;
}
const post = (path, data) => api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });

// ------------------------------------------------------------------ language + words on screen

async function loadWords() {
  try { S.T = await api(`/api/ui?lang=${encodeURIComponent(S.lang)}`); } catch { S.T = {}; }
  document.querySelectorAll("[data-t]").forEach((el) => { if (S.T[el.dataset.t]) el.textContent = S.T[el.dataset.t]; });
  document.querySelectorAll(".read").forEach((b) => (b.textContent = t("read", "🔊 Read it to me")));
  $("#text").placeholder = t("message", "Message");
  $("#recHint").textContent = t("recording", "Recording… let go to send");
  $("#sub").textContent = t("online", "online");
  $("#speakLang span").textContent = SPEAK_LANGS.find((l) => l[0] === S.speak)?.[1] || S.speak;
  document.documentElement.lang = { Yoruba: "yo", Hausa: "ha", Igbo: "ig", Pidgin: "pcm" }[S.lang] || "en";
  document.documentElement.dir = (S.T._dir) || "ltr";
  Object.keys(TYPES).forEach((k) => { if (S.T["t_" + k]) TYPES[k][1] = S.T["t_" + k]; });
  const cur = document.querySelector(".tabs button.on")?.dataset.tab;
  if (cur && cur !== "talk") showTab(cur);  // redraw the open screen in the new language
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
    if (!audio.src) {
      try { audio.src = src || (await speakUrl(speakId)); } catch { wrap.remove(); return; }
    }
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

function showReply(r, { autoplay = false } = {}) {
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
    const r = await post("/api/message", { session: S.session, text, shop: S.shop || null });
    wait.remove(); showReply(r);
  } catch (e) { wait.remove(); bubble("in err", esc(e.message)); }
}

// ------------------------------------------------------------------ hold to talk

const mic = $("#mic"), input = $("#text");
// idle -> starting (mic permission / warm-up) -> recording -> idle.  Two ways to use it, like WhatsApp:
// hold and let go to send, OR tap once to start and tap again to send (a lifted finger can never leave it stuck).
let rec = null, stream = null, chunks = [], recStart = 0, recTimer = null, startX = 0;
let state = "idle", held = false, pressAt = 0, tapMode = false, cancelRec = false;

function micIcon() { mic.textContent = input.value.trim() ? "➤" : "🎤"; }
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
    state = "idle"; return toast("Allow the microphone to talk, or type instead.", 4000);
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
  fd.append("file", blob, "note" + ext); fd.append("session", S.session); fd.append("lang", S.speak);
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
  if (!S.consent) return showWelcome();
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

$("#photo").addEventListener("change", async (e) => {
  const file = e.target.files[0]; e.target.value = "";
  if (!file) return;
  if (!S.consent) return showWelcome();
  bubble("out", `<img class="snap" src="${URL.createObjectURL(file)}" alt="book page">`, { ticks: true });
  const wait = typing();
  const fd = new FormData(); fd.append("file", await shrink(file)); fd.append("consent", "yes");
  try {
    const r = await api("/api/photo", { method: "POST", body: fd, timeout: 120000 });
    wait.remove(); photoRows(r);
  } catch (err) { wait.remove(); bubble("in err", esc(err.message)); }
});

function photoRows(r) {
  if (!r.rows.length) return bubble("in", esc(t("photo_none", "I couldn't find money records in this photo.")));
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
      bubble("in", `✅ ${esc(t("saved_n", "Saved {n}.").replace("{n}", res.saved))}` + (res.problems.length ? `<div class="en">⚠️ ${esc(res.problems.join("; "))}</div>` : ""));
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
  const load = { book: loadBook, debts: loadDebts, customers: () => loadCustomers(), insights: loadInsights, profile: loadProfile }[name];
  if (load) { try { await load(); } catch (e) { toast(e.message); } }
  if (name === "talk") scrollDown();
}
document.querySelectorAll(".tabs button").forEach((b) => (b.onclick = () => showTab(b.dataset.tab)));

async function loadBook() {
  const d = await api("/api/today"), s = d.summary;
  const due = d.due.map((r) => `<div class="item"><div class="ic">📌</div><div class="main"><div class="t">${esc(r.customer)}</div>
      <div class="s">${naira(r.balance)}</div></div><button class="small" data-remind="${esc(r.customer)}">${esc(t("remind", "Remind"))}</button></div>`).join("");
  const list = d.entries.map((e) => {
    const [ic, lb] = TYPES[e.type] || ["•", e.type];
    const what = [lb, e.item, e.customer].filter(Boolean).join(" · ");
    return `<div class="item"><div class="ic">${ic}</div><div class="main"><div class="t">${esc(what)}</div>
      <div class="s">${esc(e.created_at.slice(5, 16).replace("T", " "))}${e.due_date ? " · " + esc(t("due", "Due {d}").replace("{d}", day(e.due_date))) : ""}</div></div>
      <div class="amt">${naira(e.amount)}</div><button class="x" data-del="${e.id}" aria-label="Delete">✕</button></div>`;
  }).join("");
  $("#bookBody").innerHTML = `
    <div class="stats">
      <div class="stat"><div class="k">${esc(t("sold", "Sold"))}</div><div class="v">${naira(s.sales)}</div></div>
      <div class="stat"><div class="k">${esc(t("spent", "Spent"))}</div><div class="v">${naira(s.expenses)}</div></div>
      <div class="stat"><div class="k">${esc(t("came_in", "Came in"))}</div><div class="v">${naira(s.cash_sales + s.payments_received)}</div></div>
    </div>
    ${due ? `<div class="card"><h2>📌 ${esc(t("today", "Today"))}</h2>${due}</div>` : ""}
    <div class="card"><h2>${esc(t("recent", "Recent"))}</h2>${list || `<div class="empty">${esc(t("empty_book", "Nothing yet."))}</div>`}</div>`;
}

async function loadDebts() {
  const d = await api("/api/debts");
  const total = d.owed_to_me.reduce((a, x) => a + x.balance, 0), mine = d.i_owe.reduce((a, x) => a + x.balance, 0);
  const person = (x, remind) => `<div class="item"><div class="ic">${remind ? "🧑🏾" : "🏪"}</div><div class="main">
      <div class="t">${esc(x.customer)}</div><div class="s">${x.overdue
        ? `<span class="badge late">${esc(t("days_late", "{n} days late").replace("{n}", x.days_late))}</span>`
        : `<span class="badge ok">${esc(t("on_time", "on time"))}</span>`}${x.due_date ? " · " + esc(day(x.due_date)) : ""}</div></div>
      <div class="amt${x.overdue ? " late-amt" : ""}">${naira(x.balance)}</div>${remind ? `<button class="small" data-remind="${esc(x.customer)}">${esc(t("remind", "Remind"))}</button>` : ""}</div>`;
  $("#debtsBody").innerHTML = `
    <div class="card"><h2>${esc(t("owe_me", "Owe me"))} <small>· ${d.owed_to_me.length}</small></h2><div class="big">${naira(total)}</div>
      ${d.owed_to_me.map((x) => person(x, true)).join("") || `<div class="empty">${esc(t("nobody_owes", "Nobody owes you"))}</div>`}</div>
    <div class="card"><h2>${esc(t("i_owe", "I owe"))} <small>· ${d.i_owe.length}</small></h2><div class="big">${naira(mine)}</div>
      ${d.i_owe.map((x) => person(x, false)).join("") || `<div class="empty">${esc(t("you_owe_nobody", "You owe nobody"))}</div>`}</div>`;
}

async function loadInsights() {
  const { forecast: f, top } = await api("/api/insights");
  if (!f) { $("#insightsBody").innerHTML = '<div class="empty">Record a few days of sales, then I can see what is coming.</div>'; return; }
  const max = Math.max(...f.plan.map((p) => p.sales), 1);
  const bars = f.plan.map((p) => `<div class="${p.weekday === f.busiest_day ? "peak" : ""}"><span style="height:${Math.round((p.sales / max) * 100)}%"></span>${esc(p.weekday.slice(0, 3))}</div>`).join("");
  $("#insightsBody").innerHTML = `
    <div class="card"><h2>${esc(t("next_week", "Next 7 days"))}</h2><div class="big">${naira(f.week_sales)}</div>
      <div class="note">${esc(t("cash_left", "Cash left after normal spending"))}: <b>${naira(f.expected_cash)}</b></div><div class="bars">${bars}</div></div>
    <div class="card"><h2>${esc(t("busiest", "Busiest day"))}</h2><div class="big">${esc(f.busiest_day)}</div>
      <div class="note">${esc(t("stock_tip", "Stock up the day before."))}</div></div>
    ${f.due_soon.length ? `<div class="card"><h2>📥 ${esc(t("promised_week", "Promised this week"))}</h2>${f.due_soon.map((d) => `<div class="item"><div class="ic">📅</div><div class="main"><div class="t">${esc(d.customer)}</div><div class="s">${esc(day(d.due_date))}</div></div><div class="amt">${naira(d.balance)}</div></div>`).join("")}</div>` : ""}
    <div class="card"><h2>${esc(t("best_sellers", "Best sellers"))} <small>· 14 days</small></h2>
      ${top.map((x, i) => `<div class="item"><div class="ic">${["🥇", "🥈", "🥉"][i] || "⭐"}</div><div class="main"><div class="t">${esc(x.item)}</div>
        <div class="s">${x.qty && x.unit ? `${Math.round(x.qty)} ${esc(x.unit)}${x.qty !== 1 ? "s" : ""}` : ""}</div></div><div class="amt">${naira(x.revenue)}</div></div>`).join("")}</div>
    <p class="note">${esc(t("forecast_note", ""))}</p>`;
}

async function loadProfile() {
  const { profile: p, year } = await api("/api/profile");
  if (!p) { $("#profileBody").innerHTML = '<div class="empty">Your book is empty. Start by telling me a sale.</div>'; return; }
  const deg = Math.round((p.score / 100) * 360);
  $("#profileBody").innerHTML = `
    <div class="card" style="text-align:center"><h2>${esc(t("score", "Record score"))}</h2>
      <div class="ring" style="background:conic-gradient(var(--accent) ${deg}deg, var(--line) 0)"><div>${p.score}<small>/100 · ${esc(p.band)}</small></div></div>
      <div class="note">${p.span_days} days of records · average daily sales ${naira(p.avg_daily_sales)}</div></div>
    <div class="card"><h2>${esc(t("why_score", "Why this score"))}</h2>${p.parts.map((x) => `<div class="part"><b>${esc(x.name)}</b> · ${Math.round(x.points)}/${x.max}
      <div class="bar"><i style="width:${Math.round((x.points / x.max) * 100)}%"></i></div><div class="why">${esc(x.why)}</div></div>`).join("")}
      <p class="note">${esc(t("score_note", ""))}${p.has_demo_data ? " (demo data)" : ""}</p>
      <a class="btn" href="/api/statement?shop=${encodeURIComponent(S.shop)}" download target="_blank" rel="noopener">${esc(t("statement", "⬇️ Statement for lender / cooperative"))}</a></div>
    <div class="card"><h2>📒 ${esc(t("my_year", "My year so far"))}</h2><pre class="year">${esc(year)}</pre></div>`;
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
  sheet(`<h3>🗣️ ${esc(t("i_speak", "I'm speaking"))}</h3><div class="opts">${SPEAK_LANGS.map(([k, lb]) =>
    `<button data-speak="${k}" class="${k === S.speak ? "on" : ""}">${lb}</button>`).join("")}</div>
    <p>For voice notes. Typing works in any language, and you can switch any time in the same chat.</p>`);
  $("#sheetBody").onclick = (e) => {
    const k = e.target.dataset.speak; if (!k) return;
    S.speak = k; store.set("tv_speak", k); $("#sheet").hidden = true; loadWords();
    toast(`🗣️ ${SPEAK_LANGS.find((l) => l[0] === k)[1]}`);
  };
};

$("#menuBtn").onclick = () => {
  sheet(`<h2 class="sheet-title">⚙️ ${esc(t("settings", "Settings"))}</h2>
    <h3>🌍 ${esc(t("language", "Language"))}</h3><div class="opts">${(S.T._langs || ["English", "Pidgin", "Yoruba", "Hausa", "Igbo"])
      .map((l) => `<button data-lang="${l}" class="${l === S.lang ? "on" : ""}">${LANG_NAMES[l] || l}</button>`).join("")}</div>
    <h3>🏪 ${esc(t("shop_name", "Shop name"))}</h3><input id="shopIn" value="${esc(S.shop)}" placeholder="Chioma Stores">
    <h3>🔒 ${esc(t("my_data", "My data"))}</h3>
    <p>${esc(t("privacy", ""))}</p>
    <button class="danger" id="wipe">${esc(t("delete_all", "Delete all my records"))}</button>
    <p><a href="/admin/" style="color:var(--muted)">Advanced dashboard</a> · <a href="/" style="color:var(--muted)">TradeVoice website</a></p>`);
  $("#sheetBody").onclick = async (e) => {
    const l = e.target.dataset.lang;
    if (l) { await setLang(l); $("#sheet").hidden = true; toast(`🌍 ${LANG_NAMES[l] || l}`); }
    if (e.target.id === "wipe") {
      const c = prompt("DELETE");
      if (c === "DELETE") { await post("/api/wipe", { confirm: c }); toast("✓"); $("#sheet").hidden = true; }
    }
  };
  $("#shopIn").onchange = (e) => { S.shop = e.target.value.trim(); store.set("tv_shop", S.shop); };
};
const LANG_NAMES = { English: "English", Pidgin: "Pidgin", Yoruba: "Yorùbá", Hausa: "Hausa", Igbo: "Igbo" };

function showWelcome() {
  const box = $("#welcomeLangs");
  box.innerHTML = ["English", "Pidgin", "Yoruba", "Hausa", "Igbo"].map((l) => `<button data-l="${l}" class="${l === S.lang ? "on" : ""}">${LANG_NAMES[l]}</button>`).join("");
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
    d.due.forEach((r) => bubble("in", `📌 ${esc(t("remind", "Remind"))}: <b>${esc(r.customer)}</b> · ${naira(r.balance)}
      <div class="quick" style="margin-top:6px"><button data-remind="${esc(r.customer)}">📲 ${esc(t("remind", "Remind"))}</button></div>`));
  } catch {}
}

(async function start() {
  try { const st = await api("/api/status"); S.voice = st.voice; if (!S.shop) S.shop = st.shop; } catch {}
  await loadWords();
  micIcon();
  if (!S.consent) showWelcome(); else greet();
})();
