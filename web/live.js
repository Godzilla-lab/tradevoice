/* TradeVoice 2.0: the design (design/tradevoice-2.0/app.html) made real.
   Loaded after the design's own scripts. It gives the design's buttons real behaviour: your book from the
   server, your voice heard by N-ATLaS, records saved only when you tap Save, real reminders, scan and lender links.
   It never changes the design's look: every screen below is the design's own markup and words.
   scripts/build_app.py makes the few small logic swaps (accounts, passwords) inside the design's script. */
(() => {
  const LANG = { en: "English", pcm: "English", yo: "Yoruba", ha: "Hausa", ig: "Igbo" };
  const CODE = { English: "en", Yoruba: "yo", Hausa: "ha", Igbo: "ig" };
  const SID = "s" + Math.random().toString(36).slice(2);          // one conversation per open page
  const demo = /[?&]demo=1\b/.test(location.search);              // the design's test tools, only with ?demo=1

  async function api(path, opt = {}) {
    const o = { method: opt.method || (opt.body !== undefined || opt.form ? "POST" : "GET"), headers: {} };
    if (opt.form) o.body = opt.form;
    else if (opt.body !== undefined) { o.headers["Content-Type"] = "application/json"; o.body = JSON.stringify(opt.body); }
    let r;
    try { r = await fetch(path, o); } catch (e) { return { ok: false, status: 0, data: { error: "offline" } }; }
    let data = {};
    try { data = await r.json(); } catch (e) {}
    return { ok: r.ok, status: r.status, data };
  }
  const lang = () => LANG[L] || "English";
  // the design hides "Offline. Saved, will send later" with the hidden attribute, but its .chip rule (display:
  // inline-flex) wins over hidden, so it showed online too. This puts hidden back in charge, for that banner only.
  { const s = document.createElement("style"); s.textContent = "#off[hidden]{display:none}"; document.head.append(s); }

  /* spoken replies: after a voice note TradeVoice answers out loud (Me > Voice replies turns it off).
     Phones only let a page play sound it was allowed to during a tap, so the tap on the mic unlocks the player. */
  const player = new Audio();
  const SILENT = "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA=";
  const voiceOn = () => { try { return localStorage.getItem("tv-voice") !== "off"; } catch (e) { return true; } };
  function unlock() { try { player.src = SILENT; const p = player.play(); if (p) p.then(() => player.pause()).catch(() => {}); } catch (e) {} }
  function say(sid) {
    if (!sid || !voiceOn()) return;
    try { player.pause(); player.src = `/api/speak/${sid}`; const p = player.play(); if (p) p.catch(() => {}); } catch (e) {}
  }
  document.addEventListener("click", e => {
    const b = e.target.closest("[data-a=voice]"); if (!b) return;
    const on = !voiceOn();
    try { localStorage.setItem("tv-voice", on ? "on" : "off"); } catch (x) {}
    b.setAttribute("aria-checked", String(on));
    if (!on) player.pause();
    toast(on ? "Voice replies on: I answer out loud after a voice note." : "Voice replies off.");
  });

  function fromServer(m) {
    return { phone: m.phone, name: m.name, biz: m.biz, type: m.type, mk: m.mk, addr: m.addr, rc: m.rc, photo: m.photo,
      email: m.email, emailOk: m.emailOk, bank: m.bank, acctNo: m.acctNo, acctName: m.acctName, notif: m.notif,
      dev: (m.dev || []).map(d => ({ id: d.this ? "this" : d.id, name: d.name, t: Date.parse(d.t) || Date.now() })),
      delAt: m.delAt ? Date.parse(m.delAt) : undefined, created: Date.parse(m.created) || Date.now() };
  }

  async function loadBook() {
    const r = await api("/api/v2/book");
    if (!r.ok) return;
    const openId = C[cur] && C[cur].id, hist = {};
    C.forEach(c => { if (c.id && c.full) hist[c.id] = c.h; });   // full histories already opened stay
    // until a customer's full history is opened, their latest record stands in (the Customers filters read its age)
    const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);   // a new record since: the kept history is old
    C = r.data.customers.map(c => Object.assign(c, hist[c.id] && same(hist[c.id][0], c.last) ? { h: hist[c.id], full: true } : { h: c.last ? [c.last] : [] }));
    inN = r.data.in; outN = r.data.out;
    if (openId) { const i = C.findIndex(c => c.id === openId); if (i >= 0) cur = i; }   // the same customer stays open
    all();
    if ($("#det.on")) openDet(cur);
  }
  async function openDet(i) {
    const c = C[i]; if (!c || !c.id) return;
    const r = await api(`/api/v2/customer/${c.id}`);
    if (r.ok && C[i] === c) { c.h = r.data.h; c.full = true; det(); }
  }

  const TVL = window.TVL = {
    demo, A: null, voiceOn, say,
    async boot() {
      const r = await api("/api/v2/me");
      if (r.ok) {
        A = TVL.A = fromServer(r.data);
        if (r.data.lang && CODE[r.data.lang]) L = CODE[r.data.lang];
        if (!st.get("tv-sess") && !ss.get("tv-sess")) st.set("tv-sess", A.phone);
        all(); await loadBook();
        if (A.delAt) return GO.restore();
        if (pin) return pinGate("unlock");
        drop();
      } else {
        A = TVL.A = null; C = []; inN = outN = 0; all();
        (st.get("tv-sess") || ss.get("tv-sess")) ? GO.login() : welcome();
      }
    },
    async exists(phone) { const r = await api("/api/auth/v2/exists", { body: { phone } }); return !!(r.ok && r.data.exists); },
    async signup(su, a) {
      const r = await api("/api/auth/v2/signup", { body: { login_id: su.lid, pw: su.pw, name: a.name, biz: a.biz,
        type: a.type, mk: a.mk, lang: lang() } });
      if (!r.ok) return false;
      A = TVL.A = fromServer(r.data.me); st.set("tv-sess", A.phone); ss.del("tv-sess"); return true;
    },
    async login(phone, pw, keep) {
      const r = await api("/api/auth/v2/login", { body: { phone, pw, keep } });
      if (r.ok) { A = TVL.A = fromServer(r.data.me); if (r.data.delAt) A.delAt = Date.parse(r.data.delAt); loadBook(); return "ok"; }
      return r.data.error === "missing" ? "missing" : r.status === 429 || r.data.locked ? "locked" : "wrong";
    },
    async loginCode(lid, keep) {
      const r = await api("/api/auth/v2/login_code", { body: { login_id: lid, keep } });
      if (!r.ok) return false;
      A = TVL.A = fromServer(r.data.me); if (r.data.delAt) A.delAt = Date.parse(r.data.delAt);
      startSession(keep); loadBook(); return true;
    },
    async reset(lid, pw) { const r = await api("/api/auth/v2/reset", { body: { login_id: lid, pw } }); return r.ok; },
    logout() { api("/api/auth/v2/logout", { body: {} }); },
    async persist(a) {
      const r = await api("/api/v2/profile", { body: { name: a.name, biz: a.biz, type: a.type, mk: a.mk, addr: a.addr,
        rc: a.rc, photo: a.photo, notif: a.notif, lang: lang() } });
      if (a.acctNo !== undefined)
        await api("/api/bank", { body: { bank_name: a.bank || "", account_number: a.acctNo || "", account_name: a.acctName || "" } });
      if ((a.email || "") !== (TVL._email || "")) { await api("/api/v2/email", { body: { email: a.email || "" } }); }
      TVL._email = a.email || "";
      if (!r.ok) toast("Couldn't save. Check your connection and try again.");
    },
    async email(e) { const r = await api("/api/v2/email", { body: { email: e } }); TVL._email = e; return r.status === 409 ? "taken" : r.ok ? "ok" : "error"; },
    async password(cur, nw) {
      const r = await api("/api/v2/password", { body: { current: cur, new: nw } });
      if (r.ok) { A.dev = fromServer(r.data).dev; return "ok"; }
      return r.data.error || "error";
    },
    async devOut(id) { const r = await api("/api/v2/devices/logout", { body: { id } }); if (r.ok) A.dev = fromServer(r.data).dev; },
    async phone(lid) {
      const r = await api("/api/v2/phone", { body: { login_id: lid } });
      if (!r.ok) { toast(r.data.error === "taken" ? "Another account already uses that number." : "Couldn't change it. Try again."); return false; }
      A.phone = r.data.phone; return true;
    },
    async del(biz, pw) {
      const r = await api("/api/v2/delete", { body: { biz, pw } });
      return r.ok ? Date.parse(r.data.delAt) : r.data.error || "error";
    },
    async restore() { await api("/api/v2/restore", { body: {} }); },
    async resolve(bank, acct) { const r = await api("/api/v2/bank_resolve", { body: { bank, account: acct } }); return r.ok ? r.data.name : null; },
    async got(c, v) {
      const x = Math.min(v, c.b) || v;
      const r = await api(`/api/customers/${c.id}/record`, { body: { type: "payment_received", amount: x } });
      if (!r.ok) return toast("Couldn't save. Try again.");
      await loadBook(); const n = C.find(y => y.id === c.id) || c;
      toast(`${f(x)} recorded. ${n.b ? "Still owes " + f(n.b) + "." : "Fully paid."}`);
    },
    async gave(c, v) {
      let r = await api(`/api/customers/${c.id}/record`, { body: { type: "credit_sale", amount: v } });
      if (r.status === 409) r = await api(`/api/customers/${c.id}/record`, { body: { type: "credit_sale", amount: v, over_limit_ok: true } });
      if (!r.ok) return toast("Couldn't save. Try again.");
      await loadBook(); const n = C.find(y => y.id === c.id) || c;
      toast(`${f(v)} added. ${first(n.n)} owes ${f(n.b)}.`);
    },
    async askFree(q) {
      const out = $("#out"); if (!out) return;
      out.innerHTML = `<div class="ans"><div class="wave">${"<i></i>".repeat(16)}</div></div>`;
      const r = await api("/api/message", { body: { session: SID, text: q, lang: lang() } });
      if (!r.ok) { out.innerHTML = `<div class="ans"><b style="font-weight:500">I can't calculate that yet.</b><small>Try one of the questions above.</small></div>`; return; }
      const text = r.data.text || "", m = text.match(/₦[\d,]+/);
      if (r.data.pending) api("/api/message", { body: { session: SID, text: "no", lang: lang() } });  // Ask never saves
      out.innerHTML = m ? ansH(m[0], esc(text)) : `<div class="ans"><b style="font-weight:500">${esc(text)}</b></div>`;
    },
  };

  /* ---------------------------------------------------------------- codes by WhatsApp (the design's verify) */
  verify = function (host, o) {
    let n = 0, iv, lid = null;
    const ch = "whatsapp";
    const clock = () => {
      let left = 30; clearInterval(iv);
      const tick = () => { const r = $("#rs", host); if (!r || !r.isConnected) { clearInterval(iv); return; }
        if (left > 0) { r.textContent = `Get a new code in ${left}s`; left--; }
        else { clearInterval(iv); r.innerHTML = n >= 5 ? "Too many codes asked for. Try again in an hour." : `<button data-vb="resend" style="text-decoration:underline">Send a new code</button>`; } };
      tick(); iv = setInterval(tick, 1000);
    };
    const check = async i => {
      const e = $("#o-e", host);
      if (!lid) { i.value = ""; e.textContent = "That code isn't right. Get a new code."; return; }   // no account (reset): never says so
      const r = await api("/api/auth/v2/code/check", { body: { login_id: lid, code: i.value, purpose: o.purpose } });
      if (!r.ok) { i.value = ""; e.textContent = r.data.error || "That code isn't right."; if (/Too many|expired|new one/i.test(r.data.error || "")) i.disabled = true; return; }
      clearInterval(iv); o.onOk(lid);
    };
    const go = async () => {
      if (offline()) { host.innerHTML = `<p class="er" role="alert" style="margin:0 0 var(--s3)">You're offline. We need internet to send your code.</p><button class="btn w" data-vb="again">Try again</button>`; return; }
      const r = await api("/api/auth/v2/code/start", { body: { phone: o.phone, purpose: o.purpose, lang: lang() } });
      let error = "";
      if (r.ok) lid = r.data.login_id;
      else if (r.status === 404 && o.purpose === "reset") lid = null;          // ghost: same screen, nothing sent
      else if (r.status === 503) error = "We can't send codes on WhatsApp right now. Try again soon.";
      else if (r.status === 409) error = "This number already has an account.";
      else error = "Couldn't send the code. Try again.";
      host.innerHTML = (error ? "" : `<p style="color:var(--label2);margin-bottom:var(--s4)">We sent a 6-digit code ${ch == "sms" ? "by SMS to" : "to WhatsApp"} <b style="color:var(--label);font-weight:500">${o.label}</b>.</p>`) +
        (error ? `<p class="er" role="alert" style="margin:0 0 var(--s3)">${error}</p><button class="btn w" data-vb="again">Try again</button>` :
          `<input class="otp" id="otp" inputmode="numeric" autocomplete="one-time-code" maxlength="6" aria-label="6-digit code" placeholder="······"><p class="er" id="o-e" role="alert"></p><p class="fine" id="rs"></p>`) +
        (o.back ? `<p class="fine"><button data-vb="back" style="text-decoration:underline">${o.back}</button></p>` : "");
      if (r.ok && r.data.demo_code) setTimeout(() => wab("WhatsApp", `Your TradeVoice code is <b>${r.data.demo_code}</b>. Don't share it with anyone.`), 700);
      if (!error) { const i = $("#otp", host); i.focus({ preventScroll: true });
        i.oninput = async () => { i.value = i.value.replace(/\D/g, ""); $("#o-e", host).textContent = ""; if (i.value.length == 6) { await sleep(150); check(i); } }; clock(); }
    };
    host.onclick = e => { const b = e.target.closest("[data-vb]"); if (!b) return; const k = b.dataset.vb;
      if (k == "back") { clearInterval(iv); o.onBack(); } else { if (k == "resend") n++; go(); } };
    go();
  };

  /* ---------------------------------------------------------------- Talk: your voice, heard by N-ATLaS */
  const TYPE = { credit_sale: "↑ Sold on credit", sale: "↓ Cash sale", payment_received: "↓ Paid me", expense: "↑ Spent",
    credit_purchase: "I took on credit", payment_made: "I paid back" };
  const day = d => { if (!d) return ""; const x = new Date(d + "T12:00:00"); return isNaN(x) ? d : x.toLocaleDateString("en-NG", { weekday: "long" }); };

  const cardTalk = async function (pre) {
    unlock();   // during the tap: lets the spoken reply play later on phones
    const o = sheet(""), box = $(".in", o);
    if (pre && pre.draft) return pre.draft.amount == null ? re(1, pre.draft) : card(pre.draft);   // from the live talk: check it on screen
    api("/api/warm", { body: {} });
    const live = s => `<div class="wave">${"<i></i>".repeat(24)}</div><ol class="steps">${["listen", "hear", "think"].map((k, i) => `<li class="${i < s ? "done" : i == s ? "on" : ""}">${t(k)}</li>`).join("")}</ol><div class="quote" id="qt">&nbsp;</div>`;
    const err = (h, p) => { box.innerHTML = `<h3>${h}</h3><p class="s">${p}</p><div class="btns"><button class="btn p w" id="re">Try again</button></div>`; $("#re", o).onclick = () => { shut(o); setTimeout(talk, 300); }; };
    let stream;
    try { stream = await navigator.mediaDevices.getUserMedia({ audio: { noiseSuppression: true, echoCancellation: true, autoGainControl: true } }); }
    catch (e) { return err("Microphone is off", "Turn it on in your browser: Site settings, Microphone, Allow. Then try again."); }
    box.innerHTML = `<h3>${t("listen")}…</h3>` + live(0);
    // record until the trader stops talking (about 1.2 s of quiet after speech), taps the sheet, or 30 s
    const rec = new MediaRecorder(stream), parts = [];
    rec.ondataavailable = e => e.data.size && parts.push(e.data);
    const stopped = new Promise(r => (rec.onstop = r));
    rec.start();
    const ctx = new (window.AudioContext || window.webkitAudioContext)(), an = ctx.createAnalyser();
    ctx.createMediaStreamSource(stream).connect(an); an.fftSize = 1024;
    const buf = new Uint8Array(an.fftSize); let spoke = false, quietSince = 0; const t0 = Date.now();
    // noise floor: learned from the first quarter second, follows the background down at once and up only slowly,
    // so in a noisy market "quiet" means back to the market's level, not silence (which never comes there)
    const first = []; let floor = 0;
    const stop = () => { if (rec.state == "recording") rec.stop(); };
    $(".wave", box).style.cursor = "pointer"; $(".wave", box).onclick = stop;
    $("#qt", box).textContent = "Tap when you're done";   // the quiet line under the steps; the words appear here next
    (function watch() {
      if (rec.state != "recording") return;
      if (!o.isConnected) return stop();
      an.getByteTimeDomainData(buf); let s = 0; for (const v of buf) s += (v - 128) ** 2;
      const rms = Math.sqrt(s / buf.length);
      if (first.length < 15) {   // learn the background first (the stream starts with empty frames: skip them)
        if (rms > 0.5) first.push(rms);
        floor = first.length ? first.slice().sort((a, b) => a - b)[first.length >> 1] : 0;
        if (!spoke && Date.now() - t0 > 8000) return stop();
        return requestAnimationFrame(watch);
      }
      floor = rms < floor ? rms : floor + (rms - floor) * 0.002;
      const loud = rms > Math.max(6, floor * 1.8 + 3);
      if (loud) { spoke = true; quietSince = 0; } else if (spoke && !quietSince) quietSince = Date.now();
      if ((spoke && quietSince && Date.now() - quietSince > 1200) || Date.now() - t0 > 20000 || (!spoke && Date.now() - t0 > 8000)) return stop();
      requestAnimationFrame(watch);
    })();
    await stopped; stream.getTracks().forEach(x => x.stop()); ctx.close();
    if (!o.isConnected) return;
    if (!spoke) return err("I couldn't hear you", "It was too noisy or too short. Move closer and say it again.");
    box.innerHTML = `<h3>${t("hear")}…</h3>` + live(1);
    const fd = new FormData();
    fd.append("file", new Blob(parts, { type: rec.mimeType || "audio/webm" }), "note.webm");
    fd.append("session", SID); fd.append("lang", lang()); fd.append("consent", "yes"); fd.append("shop", A ? A.biz : "");
    const slow = setTimeout(() => { const s = $(".steps .on", o); if (s) s.textContent = "Still working…"; }, 9000);
    const r = await api("/api/voice", { form: fd });
    clearTimeout(slow);
    if (!o.isConnected) return;
    if (!r.ok) return err("I couldn't hear you", r.data.error || "It was too noisy or too short. Move closer and say it again.");
    const words = (r.data.heard || "").split(" "); let s = "";
    for (const w of words) { if (!o.isConnected) return; s += (s ? " " : "") + w; const q = $("#qt", o); if (q) q.textContent = s; await sleep(60); }
    box.innerHTML = `<h3>${t("think")}…</h3>` + live(2); $("#qt", o).textContent = s; await sleep(500);
    if (!o.isConnected) return;
    show(r.data);

    function show(d) {
      say(d.speak);
      const dr = d.draft;
      if (!dr) {   // a question or a chat answer, not a record
        box.innerHTML = `<h3>${esc(d.text)}</h3><div class="btns"><button class="btn p w" id="ok">Done</button></div>`;
        $("#ok", o).onclick = () => shut(o); return;
      }
      if (dr.amount == null) return re(1, dr);
      card(dr);
    }
    function card(dr) {
      const credit = /credit_sale|credit_purchase/.test(dr.type), chk = k => (dr.unsure || []).includes(k);
      const item = dr.item ? (dr.item[0].toUpperCase() + dr.item.slice(1)) + (dr.quantity ? `, ${dr.quantity} ${dr.unit || ""}`.trimEnd() + (dr.quantity > 1 && dr.unit && !/s$/.test(dr.unit) ? "s" : "") : "") : "";
      const kv = (k, v, c) => `<div class="kv${c ? " chk" : ""}"><span>${k}</span><b>${esc(v)}${c ? "<em>Check this</em>" : ""}</b></div>`;
      box.innerHTML = `<h3>${t("under")}</h3><div class="card"><div class="money big ${/payment_received|sale$/.test(dr.type) && dr.type != "credit_sale" ? "pos" : dr.type == "credit_sale" ? "pos" : "neg"}">${f(dr.amount)}</div>` +
        `<div class="kv" style="margin-top:var(--s3)"><span>Type</span><b>${TYPE[dr.type] || esc(dr.type)}${chk("type") ? "<em>Check this</em>" : ""}</b></div>` +
        (dr.customer || chk("customer") ? kv("Customer", dr.customer || "?", chk("customer")) : "") +
        (item ? kv("Item", item) : "") +
        (credit ? kv("Pay by", day(dr.due_date) || "?", chk("due_date")) : "") +
        `</div>${dr.note ? `<p class="s" style="margin-top:var(--s3)">${esc(dr.note)}</p>` : ""}<div class="btns" style="grid-template-columns:1.4fr 1fr 1fr;display:grid"><button class="btn p" data-s="save" style="padding:0 var(--s2)">${t("save")}</button><button class="btn" data-s="chg" style="padding:0 var(--s2)">${t("change")}</button><button class="btn g" data-s="x" style="padding:0 var(--s2)">${t("cancel")}</button></div><p class="note">${t("nothing")}</p>`;
      const q = k => $(`[data-s=${k}]`, box);
      q("save").onclick = async () => {
        q("save").disabled = true;
        const s = await api("/api/message", { body: { session: SID, text: "yes", lang: lang() } });
        shut(o);
        if (!s.ok) return toast("Couldn't save. Check your connection and try again.");
        await loadBook();
        const c = dr.customer && C.find(x => x.n.toLowerCase() == dr.customer.toLowerCase());
        const msg = offline() ? `Saved offline. Will send when you're back online.` :
          c && c.b ? `Saved. ${c.n} owes ${f(c.b)}${c.due ? ", pay " + c.due : ""}.` : `Saved. ${f(dr.amount)}.`;
        toast(msg, async () => { await api("/api/v2/undo_last", { body: {} }); loadBook(); });
      };
      q("chg").onclick = () => re(0, dr);
      q("x").onclick = () => { api("/api/message", { body: { session: SID, text: "no", lang: lang() } }); shut(o); };
    }
    function re(m, dr) {
      // the design's Change: the amount, big. A record about a person also gets the name (the design's own form field),
      // so a misheard name can be fixed without starting again; it's ready to type when the card flagged it.
      const person = /credit_sale|payment_received|credit_purchase|payment_made/.test(dr.type) || !!dr.customer;
      const nameFirst = person && (dr.unsure || []).includes("customer");
      box.innerHTML = `<h3>${m ? "I didn't catch the amount." : person ? "Change the details" : "Change the amount"}</h3><p class="s">Say it again or type it.</p><label class="inp">₦<input id="am" inputmode="numeric" autocomplete="off" placeholder="${dr.amount ? Number(dr.amount).toLocaleString("en-NG") : "0"}" aria-label="Amount"></label>` +
        (person ? `<div style="margin-top:var(--s4)">${fld("cn", "Customer", { ac: "off", v: dr.customer || "", ph: "Their name, e.g. Mama Tunde" })}</div>` : "") +
        `<div class="btns"><button class="btn p w" id="go">Continue</button></div>`;
      const i = $("#am", o), n = $("#cn", o);
      (nameFirst && n ? n : i).focus();
      const g = async () => {
        const v = +i.value.replace(/\D/g, "") || +dr.amount || 0;
        if (!v) return i.focus();
        const name = n ? n.value.trim() : null;
        if (n && !name && nameFirst) return n.focus();
        const body = { session: SID, lang: lang(), amount: v };
        if (n && name !== (dr.customer || "")) body.customer = name;
        const x = await api("/api/draft", { body });
        if (x.ok && x.data.draft) card(x.data.draft);
        else toast("Couldn't change it. Check your connection and try again.");   // never show a card the server doesn't hold
      };
      $("#go", o).onclick = g;
      for (const el of [i, n]) if (el) el.onkeydown = e => { if (e.key == "Enter") g(); };   // (returning false would block every key)
    }
  };

  /* ---------------------------------------------------------------- Talk, live: a spoken conversation.
     Tap the mic: TradeVoice listens, answers out loud, and listens again, without buttons or reading. The orb breathes
     while it waits, follows your voice while you talk and its own voice while it answers; tap it to cut in.
     Nothing is saved until you say yes (it asks "Should I save it?"). Voice replies off (Me) -> the card flow above. */
  const LW = {   // words the design doesn't have yet (Yoruba, Hausa, Igbo: for the native speaker check)
    en: { speak: "Speaking", rest: "Paused", hello: "Go ahead, I'm listening.", tap: "Tap to cut in", again: "I didn't catch that. Say it again?",
      slow: "Still working…", bye: "Talk soon.", stop: "I'll stop here. Tap me when you need me.", check: "Tap to check it on screen", done: "Done", off: "Sorry, I couldn't hear that." },
    pcm: { speak: "I dey talk", rest: "I don pause", hello: "Talk, I dey hear you.", tap: "Touch am make I stop", again: "I no catch am. Talk am again?",
      slow: "I still dey work on am…", bye: "We go talk.", stop: "I go stop here. Touch me when you need me.", check: "Touch am to check am", done: "Done", off: "Sorry, I no hear am well." },
    yo: { speak: "Mò ń sọ̀rọ̀", rest: "Mo dúró", hello: "Sọ ọ́, mò ń gbọ́.", tap: "Fọwọ́ kàn án láti dá mi dúró", again: "Mi ò gbọ́ ọ. Tún un sọ?",
      slow: "Mo ṣì ń ṣiṣẹ́ lé e…", bye: "Ó dàbọ̀.", stop: "Màá dúró báyìí. Fọwọ́ kàn mí tí o bá nílò mi.", check: "Tẹ̀ ẹ́ láti yẹ̀ ẹ́ wò", done: "Ó tó", off: "Má bínú, mi ò gbọ́ ọ dáadáa." },
    ha: { speak: "Ina magana", rest: "Na tsaya", hello: "Faɗa, ina saurare.", tap: "Taɓa don ka tsayar da ni", again: "Ban ji ba. Sake faɗa?",
      slow: "Ina kan aiki…", bye: "Sai anjima.", stop: "Zan tsaya nan. Taɓa ni idan kana bukata ta.", check: "Taɓa don ka duba", done: "Shikenan", off: "Yi haƙuri, ban ji sosai ba." },
    ig: { speak: "Ana m ekwu", rest: "Akwụsịrị m", hello: "Kwuo, ana m ege ntị.", tap: "Metụ ya aka ka m kwụsị", again: "Anụghị m ya. Kwughachi ya?",
      slow: "Ana m arụ ya…", bye: "Ka ọ dị.", stop: "Aga m akwụsị ebe a. Metụ m aka mgbe ịchọrọ m.", check: "Pịa ka i lelee ya", done: "Ọ zuola", off: "Ndo, anụghị m nke ọma." },
  };
  const BYE = /\b(that'?s all|that is all|bye( bye)?|goodbye|good bye|na im be that|o da ?bo|sai an ?jima|ka o di)\b/;
  const plain = x => (x || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
  const calm = matchMedia("(prefers-reduced-motion: reduce)").matches;
  // the orb: built only from the design's tokens (accent, canvas, fill, labels, radii, spacing), so it follows the theme
  const ORB_CSS = `
.tvc{display:flex;flex-direction:column;align-items:center;text-align:center;min-height:min(560px,76vh);padding-top:var(--s2)}
.tvc-pill{display:inline-flex;align-items:center;gap:var(--s2);height:28px;padding:0 var(--s3);border-radius:var(--pill);background:var(--fill);color:var(--label2);font-size:.8125rem;font-weight:500;letter-spacing:-.01em}
.tvc-pill i{width:6px;height:6px;border-radius:50%;background:var(--accent);animation:tvc-dot 1.6s ease-in-out infinite}
.tvc[data-st=think] .tvc-pill i{background:var(--label2);animation-duration:.8s}
.tvc[data-st=rest] .tvc-pill i{animation:none;background:var(--label2)}
.tvc-stage{flex:1;display:grid;place-items:center;width:100%;min-height:260px;padding:var(--s6) 0;-webkit-tap-highlight-color:transparent;outline:0}
.tvc-orb{--lv:0;position:relative;width:184px;height:184px;animation:tvc-breathe 5.6s ease-in-out infinite}
.tvc-orb:before{content:"";position:absolute;inset:-22%;border-radius:50%;background:radial-gradient(closest-side,color-mix(in srgb,var(--accent) 42%,transparent),transparent);opacity:calc(.5 + var(--lv) * .5);transform:scale(calc(.92 + var(--lv) * .32));transition:opacity var(--d1),transform var(--d1)}
.tvc-orb b{position:absolute;inset:0;border-radius:50%;transform:scale(calc(1 + var(--lv) * .14));transition:transform .1s linear;
 background:radial-gradient(circle at 34% 26%,color-mix(in srgb,var(--accent) 30%,#fff) 0%,color-mix(in srgb,var(--accent) 80%,#fff) 18%,var(--accent) 56%,color-mix(in srgb,var(--accent) 52%,#000) 100%);
 box-shadow:0 28px 72px -24px var(--accent),inset 0 -20px 44px color-mix(in srgb,var(--accent) 45%,#000),inset 0 12px 28px rgba(255,255,255,.32)}
.tvc-orb u{position:absolute;inset:0;border-radius:50%;overflow:hidden;clip-path:circle(50%);-webkit-mask-image:radial-gradient(circle,#000 70%,#000 71%);isolation:isolate;transform:translateZ(0)}
.tvc-orb b i{position:absolute;width:72%;height:72%;border-radius:50%;filter:blur(20px);mix-blend-mode:screen;opacity:.8;animation:tvc-swirl 12s linear infinite}
.tvc-orb b i:nth-child(1){left:-12%;top:34%;background:color-mix(in srgb,var(--accent) 42%,#FF62A5);transform-origin:85% 15%}
.tvc-orb b i:nth-child(2){right:-14%;top:-8%;background:color-mix(in srgb,var(--accent) 48%,#5AD8FF);transform-origin:15% 85%;animation-duration:15s;animation-direction:reverse}
.tvc-orb b i:nth-child(3){left:22%;bottom:-26%;background:color-mix(in srgb,var(--accent) 25%,#fff);opacity:.45;transform-origin:50% 0;animation-duration:9s}
.tvc[data-st=think] .tvc-orb{animation-duration:1.8s}
.tvc[data-st=think] .tvc-orb b i{animation-duration:2.4s}
.tvc[data-st=rest] .tvc-orb{animation-duration:8s;filter:saturate(.4);opacity:.75}
.tvc-orb,.tvc-orb b{transition:filter var(--d3),opacity var(--d3),transform .1s linear}
.tvc-say{min-height:3em;max-width:30ch;color:var(--label2);font-size:1.0625rem;line-height:1.45;letter-spacing:-.01em;margin-bottom:var(--s2)}
.tvc-say b{color:var(--label);font-weight:500}
button.tvc-say{text-decoration:none}
.tvc-hint{color:var(--label2);font-size:.8125rem;min-height:1.3em;margin-bottom:var(--s3)}
.tvc .btns{width:100%}
@keyframes tvc-breathe{0%,100%{transform:scale(1)}50%{transform:scale(1.055)}}
@keyframes tvc-swirl{to{transform:rotate(360deg)}}
@keyframes tvc-dot{50%{opacity:.35;transform:scale(.7)}}`;

  const chat = async function () {
    const w = k => (LW[L] || LW.en)[k];
    api("/api/warm", { body: {} });   // a sleeping N-ATLaS starts now, while you talk, not after
    // during the tap (phones allow sound and audio meters only from a tap): the reply's player and the meters
    let ac = null; try { ac = new (window.AudioContext || window.webkitAudioContext)(); ac.resume(); } catch (e) {}
    const voice = new Audio();
    try { voice.src = SILENT; const p = voice.play(); if (p) p.then(() => voice.pause()).catch(() => {}); } catch (e) {}
    if (!$("#tvc-css")) { const s = document.createElement("style"); s.id = "tvc-css"; s.textContent = ORB_CSS; document.head.append(s); }
    const o = sheet(`<div class="tvc" data-st="listen"><span class="tvc-pill"><i></i><span id="st">${t("listen")}</span></span>` +
      `<button class="tvc-stage" id="orb" aria-label="${w("tap")}"><span class="tvc-orb"><b><u><i></i><i></i><i></i></u></b></span></button>` +
      `<p class="tvc-say" id="cap" aria-live="polite">${w("hello")}</p><p class="tvc-hint" id="hint"></p>` +
      `<div class="btns"><button class="btn w" id="dn">${w("done")}</button></div></div>`);
    const box = $(".tvc", o), orb = $(".tvc-orb", o);
    const set = st => { box.dataset.st = st; $("#st", o).textContent = { listen: t("listen"), think: t("think"), speak: w("speak"), rest: w("rest") }[st]; };
    const caption = (h, hint = "") => { const c = $("#cap", o); if (c.tagName != "P") c.outerHTML = `<p class="tvc-say" id="cap" aria-live="polite"></p>`; $("#cap", o).innerHTML = h; $("#hint", o).textContent = hint; };
    let stream;
    try { stream = await navigator.mediaDevices.getUserMedia({ audio: { noiseSuppression: true, echoCancellation: true, autoGainControl: true } }); }
    catch (e) { $(".in", o).innerHTML = `<h3>Microphone is off</h3><p class="s">Turn it on in your browser: Site settings, Microphone, Allow. Then try again.</p>`; ac && ac.close(); return; }
    if (!o.isConnected) { stream.getTracks().forEach(x => x.stop()); ac && ac.close(); return; }

    // meters: your voice (the mic) and TradeVoice's (the reply), both read by the orb
    let micAn = null, outAn = null, wired = false;
    if (ac) { micAn = ac.createAnalyser(); micAn.fftSize = 1024; ac.createMediaStreamSource(stream).connect(micAn); }
    const buf = new Uint8Array(1024);
    const rms = an => { an.getByteTimeDomainData(buf); let s = 0; for (const v of buf) s += (v - 128) ** 2; return Math.sqrt(s / buf.length); };
    function wire() {   // the reply goes through the meter only when the audio engine is really running (else: silence)
      if (wired || !ac || ac.state != "running") return;
      try { outAn = ac.createAnalyser(); outAn.fftSize = 1024; const src = ac.createMediaElementSource(voice); src.connect(outAn); outAn.connect(ac.destination); wired = true; } catch (e) { outAn = null; }
    }
    let lv = 0, floor = 0; const first = [];
    // the mic, read once a frame by the orb loop. Speech flickers (loud, soft, loud…), so "talking" = enough loud
    // moments in the last 0.4 s, and "quiet" is counted from the last loud moment
    const V = { loud: false, hits: [], lastLoud: 0, talking: false };
    (function glow() {   // the orb's size follows whoever is talking
      if (!o.isConnected) return;
      const st = box.dataset.st; let target = 0;
      if (st != "speak") hearMic();   // (not while it speaks: it would hear itself)
      if (!calm && st == "listen" && micAn && first.length >= 15) target = Math.min(1, Math.max(0, rms(micAn) - floor) / 22);
      else if (!calm && st == "speak") target = outAn ? Math.min(1, rms(outAn) / 26) : (Math.sin(Date.now() / 140) + 1) * .22;
      lv += (target - lv) * (target > lv ? .35 : .12);
      orb.style.setProperty("--lv", lv.toFixed(3));
      requestAnimationFrame(glow);
    })();

    let cutIn = null;   // tap the orb: stop listening (and send), or stop talking (and listen)
    $("#orb", o).onclick = () => { if (cutIn) cutIn(); else if (box.dataset.st == "rest") run(); };
    $("#dn", o).onclick = () => shut(o);
    const end = setInterval(() => {   // closed (Done, swipe, tap outside): the mic and the voice stop at once
      if (o.isConnected) return;
      clearInterval(end); if (cutIn) cutIn(); voice.pause(); stream.getTracks().forEach(x => x.stop()); ac && ac.close();
    }, 250);

    // ---- turn-taking: when have you really finished talking?
    // A short pause (0.6 s) starts the hearing early, in the background, while it keeps listening. It answers only
    // after a real stop: 1.3 s of quiet AND your words back. Talk again before that: the early hearing is thrown
    // away and the whole thing, old words and new, is heard again. Talk while it is preparing the reply: it doesn't
    // talk over you; what you said is kept as your next turn. (Nothing is recorded while it speaks: it would hear itself.)
    const PAUSE = 600, DONE = 1300, MAX = 40000, NOTHING = 8000;
    function hearMic() {
      if (!micAn) return;
      const r = rms(micAn);
      if (first.length < 15) {   // the background, learned once per conversation (same rule as the card flow)
        if (r > 0.5) first.push(r);
        floor = first.length ? first.slice().sort((a, b) => a - b)[first.length >> 1] : 0;
        V.loud = false;
      } else {
        floor = r < floor ? r : floor + (r - floor) * 0.002;
        V.loud = r > Math.max(6, floor * 1.8 + 3);
      }
      const now = Date.now();
      if (V.loud) { V.hits.push(now); V.lastLoud = now; }
      while (V.hits.length && now - V.hits[0] > 400) V.hits.shift();
      V.talking = V.hits.length >= 6;
    }
    function record() {   // a recording you can read while it goes on (in 0.2 s pieces)
      const rec = new MediaRecorder(stream), parts = [], R = { t0: Date.now(), spoke: false };
      rec.ondataavailable = e => e.data.size && parts.push(e.data);
      R.stopped = new Promise(r => (rec.onstop = r));
      R.blob = () => new Blob(parts, { type: rec.mimeType || "audio/webm" });
      R.stop = () => { if (rec.state == "recording") rec.stop(); return R.stopped; };
      rec.start(200);
      return R;
    }
    function hearNow(blob) {   // words only: nothing in the book or the chat changes, so it can be thrown away
      const ctrl = new AbortController(), e = { ctrl, result: null };
      const fd = new FormData();
      fd.append("file", blob, "note.webm"); fd.append("lang", lang()); fd.append("consent", "yes");
      e.promise = fetch("/api/hear", { method: "POST", body: fd, signal: ctrl.signal })
        .then(async r => ({ ok: r.ok, status: r.status, data: await r.json().catch(() => ({})) }))
        .catch(x => ({ ok: false, status: 0, aborted: x.name == "AbortError", data: { error: w("off") } }))
        .then(x => (e.result = x));
      return e;
    }
    // one turn: returns what you said ({ok, data:{heard}}), or null if nothing was said
    function listen(carry) {
      set("listen");
      const R = carry || record();
      let spoke = !!(carry && carry.spoke), tapped = false, early = null;
      cutIn = () => { tapped = true; };   // tap: "I'm done", answer now
      return new Promise(done => {
        const finish = async () => {
          cutIn = null;
          await R.stop();
          if (!spoke && !tapped) return done(null);
          // the early hearing missed nothing if you stayed quiet; otherwise (a tap mid-word) hear the whole recording
          if (!early || early.result && !early.result.ok && early.result.status != 422) { if (early) early.ctrl.abort(); early = hearNow(R.blob()); }
          done(await early.promise);
        };
        (function watch() {
          if (!o.isConnected || stopAll) { R.stop(); cutIn = null; return done(null); }
          const now = Date.now();
          if (!micAn) { if (tapped || now - R.t0 > 10000) { spoke = true; return finish(); } return setTimeout(watch, 100); }
          if (V.talking) {   // talking (again): not finished after all
            spoke = true;
            if (early) { early.ctrl.abort(); early = null; }
          }
          const quiet = spoke && !V.talking ? now - V.lastLoud : 0;
          if (quiet >= PAUSE && !early) early = hearNow(R.blob());   // a pause: start hearing, keep listening
          if (tapped || now - R.t0 > MAX) return finish();
          if (early && early.result && quiet >= DONE) return finish();   // a real stop, and the words are back
          if (!spoke && now - R.t0 > NOTHING) return finish();
          requestAnimationFrame(watch);
        })();
      });
    }
    // TradeVoice's answer, out loud (made on the server while the words were being worked out)
    // The clip is fetched first: no voice (off, or Intron failed) moves on at once (a player left to find a missing
    // clip by itself waits 5 to 10 s before giving up, while you wait in silence)
    async function speak(sid) {
      if (!sid || !o.isConnected) return;
      set("speak"); wire();
      let stop = false;
      cutIn = () => { stop = true; voice.pause(); };
      const r = await fetch(`/api/speak/${sid}`).catch(() => null);
      const clip = r && r.ok ? await r.blob().catch(() => null) : null;
      if (!clip || stop || !o.isConnected) { cutIn = null; return; }
      const url = URL.createObjectURL(clip);
      await new Promise(done => {
        const fin = () => { voice.onended = voice.onerror = null; cutIn = null; URL.revokeObjectURL(url); done(); };
        voice.onended = voice.onerror = fin;
        cutIn = () => { voice.pause(); fin(); };
        voice.src = url;
        const p = voice.play(); if (p) p.catch(fin);
      });
    }
    // one quiet line: the key facts of what's waiting to be saved, or the short answer
    function line(d) {
      const dr = d.draft;
      if (d.pending && dr && dr.amount != null) {
        const bits = [`<b>${f(dr.amount)}</b>`, dr.customer && esc(dr.customer), (TYPE[dr.type] || "").replace(/^[↑↓] /, ""), dr.due_date && day(dr.due_date)].filter(Boolean);
        caption(bits.join(" · "), w("check"));
        const c = $("#cap", o); c.outerHTML = `<button class="tvc-say" id="cap" aria-live="polite">${c.innerHTML}</button>`;
        $("#cap", o).onclick = () => { stopAll = true; if (cutIn) cutIn(); shut(o); setTimeout(() => cardTalk(d), 300); };
        return;
      }
      const s = (d.text || "").replace(/[*_]/g, "").split("\n")[0];
      caption(esc(s.length > 140 ? s.slice(0, 137).trimEnd() + "…" : s));
    }

    let stopAll = false, running = false;
    async function run() {
      if (running) return; running = true;
      let quiet = 0, fails = 0, carry = null;
      caption(w("hello"));
      while (o.isConnected && !stopAll) {
        const h = await listen(carry); carry = null;
        if (!o.isConnected || stopAll) break;
        if (!h || h.status == 422) {   // nothing said: once, ask again; twice, rest (tap the orb to go on)
          if (++quiet >= 2) { caption(w("stop")); set("rest"); break; }
          if ($("#cap", o).tagName == "BUTTON") $("#hint", o).textContent = w("again"); else caption(w("again"));   // the facts stay
          continue;
        }
        quiet = 0;
        if (!h.ok) { if (++fails >= 3) { caption(esc(h.data.error || w("off"))); set("rest"); break; } caption(esc(h.data.error || w("off"))); continue; }
        fails = 0;
        const said = h.data.heard || "", heard = plain(said);
        if (BYE.test(heard) && heard.split(/\s+/).length <= 5) { caption(w("bye")); set("rest"); setTimeout(() => shut(o), 900); break; }
        // the reply. The mic stays open meanwhile: if you go on talking, that's kept for your next turn
        set("think"); caption(`“${esc(said.length > 120 ? said.slice(0, 117) + "…" : said)}”`);
        const next = micAn ? record() : null;
        const minding = setInterval(() => { if (next && V.talking) next.spoke = true; }, 50);
        const slow = setTimeout(() => $("#hint", o).textContent = w("slow"), 12000);
        const r = await api("/api/say", { body: { session: SID, text: said, lang: lang(), shop: A ? A.biz : "" } });
        clearTimeout(slow); clearInterval(minding); $("#hint", o).textContent = "";
        if (!o.isConnected || stopAll) { if (next) next.stop(); break; }
        if (!r.ok) { if (next) next.stop(); caption(esc(r.data.error || w("off"))); continue; }
        const d = r.data;
        line(d);
        loadBook();   // a yes saved it: the book behind the sheet is already up to date when it closes
        if (d.saved) toast(esc((d.text || "").replace(/\*/g, "").split("\n")[0]), async () => { await api("/api/v2/undo_last", { body: {} }); loadBook(); });
        if (next && next.spoke) { carry = next; continue; }   // you were talking: listen on, the reply stays on screen
        if (next) next.stop();
        await speak(d.speak);
      }
      running = false;
    }
    run();
  };
  talk = () => (voiceOn() && window.MediaRecorder && navigator.mediaDevices ? chat() : cardTalk());
  TVL.chat = chat;

  /* ---------------------------------------------------------------- reminders: drafted by TradeVoice, sent by YOU */
  remind = async function () {
    const c = C[cur]; if (!c) return;
    const r = await api(`/api/customers/${c.id}/reminder`, { body: { lang: lang(), shop: A ? A.biz : "" } });
    const text = r.ok && r.data.message ? r.data.message : `Hello ${c.n.split(" ").slice(0, 2).join(" ")}, this is ${biz()}. A friendly reminder: you owe ${f(c.b)}.`;
    const payUrl = (text.match(/https?:\/\/\S+\/pay\/\S+/) || [])[0];
    const o = sheet(`<h3>Reminder draft</h3><p class="s">TradeVoice prepared this. You send it.</p><textarea class="msg" id="mg" aria-label="Message">${esc(text)}</textarea><div class="btns"><button class="btn p w" id="wa">Send on WhatsApp</button>${payUrl ? `<button class="btn w" id="pv">See what ${first(c.n)} sees</button>` : ""}</div>`);
    const to = (r.data && r.data.phone || "").replace(/\D/g, "");
    $("#wa", o).onclick = () => window.open(`https://wa.me/${to}?text=` + encodeURIComponent($("#mg", o).value), "_blank", "noopener");
    if (payUrl) $("#pv", o).onclick = () => window.open(payUrl, "_blank", "noopener");
  };
  pay = function () { remind(); };   // the real pay page opens from the reminder ("See what … sees")

  /* ---------------------------------------------------------------- scan an old notebook page */
  scan = async function () {
    const o = sheet(`<h3>Scan your book</h3><p class="s">Take a photo of a page. You check every line before it is saved.</p><div class="btns"><button class="btn p w" id="ph">Choose photo</button></div><input type="file" id="pf" accept="image/*" capture="environment" hidden>`), box = $(".in", o);
    $("#ph", o).onclick = () => $("#pf", o).click();
    $("#pf", o).onchange = async e => {
      const file = e.target.files[0]; if (!file) return;
      box.innerHTML = `<h3>Reading…</h3><div class="wave">${"<i></i>".repeat(24)}</div>`;
      const fd = new FormData(); fd.append("file", file); fd.append("consent", "yes");
      const r = await api("/api/photo", { form: fd });
      if (!o.isConnected) return;
      if (!r.ok || !r.data.rows || !r.data.rows.length) {
        box.innerHTML = `<h3>I couldn't read that page</h3><p class="s">Try again in good light, with the whole page in the photo.</p><div class="btns"><button class="btn p w" id="re">Try again</button></div>`;
        $("#re", o).onclick = () => { shut(o); setTimeout(scan, 300); }; return;
      }
      const rows = r.data.rows;
      box.innerHTML = `<h3>${rows.length} lines found</h3><p class="s">Amber lines need a look.</p>${rows.map((x, i) => `<div class="ln ${x.save ? "" : "u"}"><input type="checkbox" ${x.save ? "checked" : ""} aria-label="Include ${esc(x.customer || x.line)}"><label class="inp"><input value="${esc(x.customer || x.item || x.line)}" aria-label="Name"></label><label class="inp"><input value="${x.amount ? Number(x.amount).toLocaleString("en-NG") : ""}" inputmode="numeric" aria-label="Amount"></label></div>`).join("")}<div class="btns"><button class="btn p w" id="sv">Save ticked</button></div>`;
      $("#sv", o).onclick = async () => {
        const out = $$(".ln", o).map((el, i) => { const [a, b] = $$("input:not([type=checkbox])", el), x = rows[i];
          return Object.assign({}, x, { save: $("[type=checkbox]", el).checked, customer: x.customer ? a.value.trim() : x.customer,
            item: x.customer ? x.item : a.value.trim(), amount: +b.value.replace(/\D/g, "") || null }); });
        const s = await api("/api/save_rows", { body: { rows: out } });
        shut(o); await loadBook();
        const k = s.ok ? s.data.saved : 0; toast(`${k} line${k == 1 ? "" : "s"} saved.`);
      };
    };
  };

  /* ---------------------------------------------------------------- lender report: a real, expiring link */
  report = async function () {
    const r = await api("/api/v2/report"); const d = r.ok ? r.data : { in30: 0, customers: C.length, owed: 0 };
    const until = new Date(Date.now() + 30 * 864e5).toLocaleDateString("en-NG", { day: "numeric", month: "short" });
    const o = sheet(`<h3>Lender report</h3><p class="s">${biz()} · last 30 days</p><div class="card"><div class="money big">${f(d.in30)}</div><small style="color:var(--label2)">Money in, 30 days</small><div class="kv"><span>Customers</span><b>${d.customers}</b></div><div class="kv"><span>Owed to the shop</span><b class="money">${f(d.owed)}</b></div><div class="kv"><span>Phone</span><b>${A ? mphone(A.phone) : "+234 ••• 4567"}</b></div><div class="kv"><span>Shared until</span><b>${until}</b></div></div><div class="btns two"><button class="btn" id="pr">Print</button><button class="btn p" id="sh">Share link</button></div>`);
    $("#pr", o).onclick = () => window.print();
    $("#sh", o).onclick = async () => {
      const s = await api("/api/share", { body: { consent: true, days: 30 } });
      if (!s.ok) return toast("Couldn't make the link. Try again.");
      try { await navigator.clipboard.writeText(s.data.url); } catch (e) {}
      shut(o); toast("Link copied. You choose who gets it.");
    };
  };

  /* ---------------------------------------------------------------- Connect my WhatsApp: when the bot is live */
  wac = function () { toast("Connecting WhatsApp opens when the TradeVoice bot number is live."); };

  /* ---------------------------------------------------------------- the design's local "Ask" answers use the real book;
     anything else goes to N-ATLaS (via the same chat brain as WhatsApp) */
  document.addEventListener("click", e => { const a = e.target.closest("[data-a=open]"); if (a) openDet(+a.dataset.i); });
  addEventListener("online", loadBook);
  TVL.loadBook = loadBook;
})();
TVL.boot();
