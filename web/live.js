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
    C.forEach(c => { if (c.id && c.h && c.h.length) hist[c.id] = c.h; });
    C = r.data.customers.map(c => Object.assign(c, { h: hist[c.id] || [] })); inN = r.data.in; outN = r.data.out;
    if (openId) { const i = C.findIndex(c => c.id === openId); if (i >= 0) cur = i; }   // the same customer stays open
    all();
    if ($("#det.on")) openDet(cur);
  }
  async function openDet(i) {
    const c = C[i]; if (!c || !c.id) return;
    const r = await api(`/api/v2/customer/${c.id}`);
    if (r.ok && C[i] === c) { c.h = r.data.h; det(); }
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

  talk = async function () {
    unlock();   // during the tap: lets the spoken reply play later on phones
    const o = sheet(""), box = $(".in", o);
    const live = s => `<div class="wave">${"<i></i>".repeat(24)}</div><ol class="steps">${["listen", "hear", "think"].map((k, i) => `<li class="${i < s ? "done" : i == s ? "on" : ""}">${t(k)}</li>`).join("")}</ol><div class="quote" id="qt">&nbsp;</div>`;
    const err = (h, p) => { box.innerHTML = `<h3>${h}</h3><p class="s">${p}</p><div class="btns"><button class="btn p w" id="re">Try again</button></div>`; $("#re", o).onclick = () => { shut(o); setTimeout(talk, 300); }; };
    let stream;
    try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }); }
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
    const stop = () => { if (rec.state == "recording") rec.stop(); };
    $(".wave", box).style.cursor = "pointer"; $(".wave", box).onclick = stop;
    (function watch() {
      if (rec.state != "recording") return;
      if (!o.isConnected) return stop();
      an.getByteTimeDomainData(buf); let s = 0; for (const v of buf) s += (v - 128) ** 2;
      const loud = Math.sqrt(s / buf.length) > 6;
      if (loud) { spoke = true; quietSince = 0; } else if (spoke && !quietSince) quietSince = Date.now();
      if ((spoke && quietSince && Date.now() - quietSince > 1200) || Date.now() - t0 > 30000 || (!spoke && Date.now() - t0 > 8000)) return stop();
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
      box.innerHTML = `<h3>${m ? "I didn't catch the amount." : "Change the amount"}</h3><p class="s">Say it again or type it.</p><label class="inp">₦<input id="am" inputmode="numeric" autocomplete="off" placeholder="0" aria-label="Amount"></label><div class="btns"><button class="btn p w" id="go">Continue</button></div>`;
      const i = $("#am", o); i.focus();
      const g = async () => { const v = +i.value.replace(/\D/g, ""); if (!v) return i.focus();
        const x = await api("/api/draft", { body: { session: SID, lang: lang(), amount: v } });
        if (x.ok && x.data.draft) card(x.data.draft); else { dr.amount = v; card(dr); } };
      $("#go", o).onclick = g; i.onkeydown = e => e.key == "Enter" && g();
    }
  };

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
