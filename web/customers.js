// 👥 Customers: one WhatsApp-style conversation per customer, built on the real book (by customer id).
// Records are shown as TradeVoice entries, the trader's notes as their own bubbles, and reminders as drafts that
// TradeVoice prepared and the trader sends from their own WhatsApp. Customer replies are never invented.
"use strict";

const C = { list: [], filter: "all", q: "", open: null, data: null, draft: null };

const initials = (n) => (n || "?").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join("");
function when(iso) {
  if (!iso) return "";
  const d = new Date(iso), today = new Date();
  const diff = Math.round((new Date(today.toDateString()) - new Date(d.toDateString())) / 864e5);
  if (diff === 0) return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  if (diff === 1) return t("yesterday", "Yesterday");
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}
function dayLabel(iso) {
  const d = new Date(iso), today = new Date();
  const diff = Math.round((new Date(today.toDateString()) - new Date(d.toDateString())) / 864e5);
  return diff === 0 ? t("today", "Today") : diff === 1 ? t("yesterday", "Yesterday")
    : d.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" });
}
const typeLabel = (ty) => t("t_" + ty, ty);
const TYPE_ICON = { sale: "🛒", credit_sale: "📝", payment_received: "💰", expense: "💸", credit_purchase: "📦", payment_made: "↩️" };

function balanceLine(c) {
  if (c.owes_me > 0) return t("owes_you", "owes you {m}").replace("{m}", naira(c.owes_me));
  if (c.i_owe > 0) return t("you_owe", "you owe {m}").replace("{m}", naira(c.i_owe));
  return t("paid_up", "Paid up");
}

function preview(c) {
  const l = c.last;
  if (!l) return "";
  if (c.last_is_message) return (l.kind === "reminder" ? "TradeVoice: " : `${t("you", "You")}: `) + l.content;
  return `${TYPE_ICON[l.type] || ""} ${typeLabel(l.type)} ${naira(l.amount)}${l.item ? " · " + l.item : ""}`;
}

// ------------------------------------------------------------------ list

async function loadCustomers() {
  const box = $("#crows");
  try { C.list = (await api("/api/customers")).customers; } catch (e) { box.innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
  const owe = C.list.reduce((a, c) => a + c.owes_me, 0), mine = C.list.reduce((a, c) => a + c.i_owe, 0);
  $("#csum").innerHTML = `<span>${esc(t("owe_me", "Owe me"))} <b>${naira(owe)}</b></span><span>${esc(t("i_owe", "I owe"))} <b>${naira(mine)}</b></span>`;
  $("#csearch").placeholder = t("search", "Search customers");
  $("#newCust").textContent = "+ " + t("new_customer", "New customer");
  $("#cfilters").innerHTML = [["all", "all"], ["owe", "owe_me"], ["mine", "i_owe"], ["late", "late"]]
    .map(([k, key]) => `<button data-f="${k}" class="${C.filter === k ? "on" : ""}">${esc(t(key, k))}</button>`).join("");
  renderRows();
  if (C.open && window.matchMedia("(min-width: 900px)").matches) openThread(C.open, { keep: true });
  else if (!C.open) $("#cthread").innerHTML = `<div class="empty">${esc(t("nav_customers", "Customers"))}</div>`;
}

function renderRows() {
  const q = C.q.trim().toLowerCase();
  const rows = C.list.filter((c) => (!q || c.name.toLowerCase().includes(q) || (c.phone || "").includes(q)) &&
    (C.filter === "all" || (C.filter === "owe" && c.owes_me > 0) || (C.filter === "mine" && c.i_owe > 0) ||
     (C.filter === "late" && c.overdue)));
  $("#crows").innerHTML = rows.length ? rows.map((c) => `
    <button class="crow ${C.open === c.id ? "sel" : ""}" data-cid="${c.id}">
      <span class="cav">${esc(initials(c.name))}</span>
      <span class="cmain">
        <span class="cline"><span class="cname">${esc(c.name)}</span><span class="ctime">${esc(when(c.last_at))}</span></span>
        <span class="cline"><span class="cprev">${esc(preview(c))}</span>
          ${c.unread ? `<span class="unread">${c.unread}</span>` : ""}</span>
        ${c.same_name || c.owes_me || c.i_owe ? `<span class="cbal ${c.overdue ? "late-amt" : ""}">${esc(balanceLine(c))}${
          c.overdue ? " · " + esc(t("days_late", "{n} days late").replace("{n}", c.days_late)) : ""}${
          c.same_name && c.phone ? " · " + esc(c.phone) : ""}</span>` : ""}
      </span>
    </button>`).join("") : `<div class="empty">${esc(C.list.length ? "…" : t("no_customers", "No customers yet."))}</div>`;
}

$("#crows").addEventListener("click", (e) => { const b = e.target.closest(".crow"); if (b) openThread(+b.dataset.cid); });
$("#csearch").addEventListener("input", (e) => { C.q = e.target.value; renderRows(); });
$("#cfilters").addEventListener("click", (e) => { const f = e.target.dataset.f; if (f) { C.filter = f; loadCustomers(); } });
$("#newCust").addEventListener("click", () => contactSheet(null));

// ------------------------------------------------------------------ thread

async function openThread(id, { keep = false } = {}) {
  C.open = id;
  $("#customers").classList.add("open"); $("#app").classList.add("in-thread");
  if (!keep) $("#cthread").innerHTML = '<div class="empty"><span class="typing"><i></i><i></i><i></i></span></div>';
  try {
    C.data = await api(`/api/customers/${id}`);
  } catch (e) {
    C.open = null;
    $("#cthread").innerHTML = `<div class="empty">${esc(t("customer_deleted", "This customer was deleted."))}</div>`;
    setTimeout(() => { closeThread(); loadCustomers(); }, 1500);
    return;
  }
  renderThread();
  api(`/api/customers/${id}/read`, { method: "POST" }).then(() => {
    const row = C.list.find((c) => c.id === id); if (row) { row.unread = 0; renderRows(); }
  }).catch(() => {});
}

function closeThread() {
  C.open = null; C.draft = null;
  $("#customers").classList.remove("open"); $("#app").classList.remove("in-thread");
  renderRows();
}

function renderThread() {
  const c = C.data.customer, ev = C.data.thread;
  const context = [c.due_date ? t("due", "Due {d}").replace("{d}", day(c.due_date)) : "",
                   c.last && c.last.item ? t("last_item", "Last: {x}").replace("{x}", c.last.item + (c.last.quantity ? ` (${c.last.quantity} ${c.last.unit || ""})`.replace(" )", ")") : "")) : ""]
    .filter(Boolean).map(esc).join(" · ");
  let lastDay = "", html = "";
  for (const e of ev) {
    const d = e.created_at.slice(0, 10);
    if (d !== lastDay) { html += `<div class="day">${esc(dayLabel(e.created_at))}</div>`; lastDay = d; }
    html += e.event === "record" ? recordCard(e) : e.kind === "reminder" ? reminderBubble(e, c) : noteBubble(e);
  }
  if (!ev.length) html = `<div class="empty">${esc(t("empty_thread", "Nothing here yet.").replace("{n}", c.name))}</div>`;
  $("#cthread").innerHTML = `
    <div class="thead">
      <button class="icon back" aria-label="${esc(t("back", "Back"))}">←</button>
      <span class="cav">${esc(initials(c.name))}</span>
      <div class="tinfo"><div class="tname">${esc(c.name)}</div>
        <div class="tsub ${c.overdue ? "late-amt" : ""}">${esc(balanceLine(c))}${c.overdue ? " · " + esc(t("days_late", "{n} days late").replace("{n}", c.days_late)) : ""}</div></div>
      <button class="icon" data-act="contact" aria-label="${esc(t("edit_contact", "Edit contact"))}">⋮</button>
    </div>
    <div class="tcontext">${context ? `<span>${context}</span>` : ""}
      ${c.phone ? `<span>📞 ${esc(c.phone)}</span>` : `<button class="linkbtn" data-act="contact">📞 ${esc(t("add_phone", "Add phone"))}</button>`}</div>
    <div class="tmsgs" id="tmsgs">${html}${C.draft ? draftCard() : ""}</div>
    <div class="tactions">
      <button data-act="pay">💰 ${esc(t("record_payment", "Record payment"))}</button>
      <button data-act="sale">🛒 ${esc(t("record_sale", "Record sale"))}</button>
      ${c.owes_me > 0 ? `<button data-act="remind">📲 ${esc(t("prepare_reminder", "Prepare reminder"))}</button>` : ""}
    </div>
    <form class="tcomposer" id="tform"><input id="tinput" autocomplete="off" placeholder="${esc(t("note_hint", "Write a note"))}">
      <button class="round small-round" aria-label="${esc(t("save", "Save"))}">➤</button></form>`;
  const m = $("#tmsgs"); requestAnimationFrame(() => (m.scrollTop = m.scrollHeight));
}

function recordCard(e) {
  const bits = [e.item && (e.quantity ? `${e.item} (${e.quantity} ${e.unit || ""})`.replace(" )", ")") : e.item),
                e.due_date ? t("due", "Due {d}").replace("{d}", day(e.due_date)) : ""].filter(Boolean);
  return `<div class="rec"><span class="ric">${TYPE_ICON[e.type] || "•"}</span>
    <span class="rmain"><b>${esc(typeLabel(e.type))}</b> ${naira(e.amount)}${bits.length ? `<br><small>${esc(bits.join(" · "))}</small>` : ""}</span>
    <span class="rtime">${esc(when(e.created_at))}</span></div>`;
}

function noteBubble(e) {
  return `<div class="msg out"><span>${fmt(e.content)}</span><span class="meta">${esc(when(e.created_at))}</span></div>`;
}

function reminderBubble(e, c) {
  const opened = e.status === "opened";
  return `<div class="msg in tv" data-mid="${e.id}">
    <div class="tvlabel">TradeVoice · ${esc(opened ? t("opened_note", "Opened in WhatsApp") : t("draft_note", "TradeVoice prepared this."))}</div>
    <div class="rtext">${fmt(e.content)}</div>
    ${c.phone ? "" : `<div class="en">${esc(t("no_phone", "No phone saved."))}</div>`}
    <div class="rbtns"><button data-act="editmsg">${esc(t("edit_message", "Edit message"))}</button>
      <button class="wa-btn" data-act="openwa">${esc(t("open_whatsapp", "Open WhatsApp"))}</button></div>
    <span class="meta">${esc(when(e.created_at))}</span></div>`;
}

function draftCard() {
  const d = C.draft;
  return `<div class="rec draft"><span class="ric">${TYPE_ICON[d.type] || "•"}</span>
    <span class="rmain"><b>${esc(typeLabel(d.type))}</b> ${naira(d.amount)}${d.item ? `<br><small>${esc(d.item)}</small>` : ""}
      <br><small>${esc(t("check_save", "Check, then save"))}</small></span>
    <span class="rbtns"><button data-act="draftno">${esc(t("cancel", "Cancel"))}</button>
      <button class="primary-sm" data-act="draftyes">${esc(t("save", "Save"))}</button></span></div>`;
}

async function refreshThread(data) {
  if (data && data.thread) { C.data.thread = data.thread; }
  if (data && data.customer) { C.data.customer = data.customer; }
  if (!data || !data.customer) { try { C.data = await api(`/api/customers/${C.open}`); } catch { return openThread(C.open); } }
  renderThread();
  // the trader's own actions here are already "read"; only activity from elsewhere (chat, WhatsApp) shows as unread
  api(`/api/customers/${C.open}/read`, { method: "POST" }).catch(() => {})
    .then(() => api("/api/customers")).then((r) => { C.list = r.customers; renderRows(); }).catch(() => {});
}

// actions inside a conversation
$("#cthread").addEventListener("click", async (e) => {
  const b = e.target.closest("button"); if (!b) return;
  if (b.classList.contains("back")) return closeThread();
  const act = b.dataset.act, c = C.data && C.data.customer;
  if (!act || !c) return;
  try {
    if (act === "contact") return contactSheet(c);
    if (act === "pay") return recordSheet(c, "payment_received");
    if (act === "sale") return recordSheet(c, "credit_sale");
    if (act === "remind") {
      const lang = ["English", "Pidgin", "Yoruba"].includes(S.lang) ? S.lang : "Pidgin";
      const r = await post(`/api/customers/${c.id}/reminder`, { lang, shop: S.shop || null });
      if (!r.message) return toast(t("remind_none", "{n} doesn't owe you anything").replace("{n}", c.name));
      return refreshThread(r);
    }
    const bub = b.closest("[data-mid]");
    if (act === "editmsg" && bub) {
      const txt = $(".rtext", bub);
      if (txt.tagName !== "TEXTAREA") {
        const ta = document.createElement("textarea"); ta.className = "rtext"; ta.value = txt.innerText; ta.rows = 4;
        txt.replaceWith(ta); ta.focus(); b.textContent = t("save", "Save");
      } else {
        await api(`/api/messages/${bub.dataset.mid}`, { method: "PATCH", headers: { "Content-Type": "application/json" },
                                                        body: JSON.stringify({ content: txt.value }) });
        refreshThread();
      }
      return;
    }
    if (act === "openwa" && bub) {
      const txt = $(".rtext", bub), msg = txt.value ?? txt.innerText;
      let phone = (c.phone || "").replace(/\D/g, "");
      if (phone.startsWith("0") && phone.length === 11) phone = "234" + phone.slice(1);
      window.open(`https://wa.me/${phone}?text=${encodeURIComponent(msg)}`, "_blank", "noopener");
      await api(`/api/messages/${bub.dataset.mid}`, { method: "PATCH", headers: { "Content-Type": "application/json" },
                                                      body: JSON.stringify({ status: "opened", content: msg }) });
      return refreshThread();
    }
    if (act === "draftno") { C.draft = null; return renderThread(); }
    if (act === "draftyes") {
      const d = C.draft; C.draft = null;
      return refreshThread(await post(`/api/customers/${c.id}/record`, d));
    }
  } catch (err) { toast(err.message || t("error", "Something went wrong.")); }
});

$("#cthread").addEventListener("submit", async (e) => {
  e.preventDefault();
  const inp = $("#tinput"), text = inp.value.trim(); if (!text || !C.open) return;
  inp.value = "";
  try {
    const r = await post(`/api/customers/${C.open}/say`, { text });
    if (r.draft && r.draft.amount) { C.draft = { ...r.draft, raw_text: text }; renderThread(); }
    else refreshThread(r);
  } catch (err) { toast(err.message); }
});

// ------------------------------------------------------------------ sheets (same sheet component as Settings)

function recordSheet(c, type) {
  const due = [["", t("none", "None")], [isoPlus(0), t("today", "Today")], [isoPlus(1), t("tomorrow", "Tomorrow")], [nextFriday(), t("friday", "Friday")]];
  const isPay = type === "payment_received";
  sheet(`<h3>${esc(isPay ? t("record_payment", "Record payment") : t("record_sale", "Record sale"))} · ${esc(c.name)}</h3>
    <label>${esc(t("amount", "Amount (₦)"))}<input id="rAmt" inputmode="numeric" value="${isPay && c.owes_me ? Math.round(c.owes_me) : ""}"></label>
    ${isPay ? "" : `<label>${esc(t("item", "Item"))}<input id="rItem" autocomplete="off"></label>
    <div class="opts" id="rKind"><button data-k="sale">${esc(t("paid_now", "Paid now"))}</button><button data-k="credit_sale" class="on">${esc(t("on_credit", "On credit"))}</button></div>
    <h3>${esc(t("will_pay", "Will pay"))}</h3><div class="opts" id="rDue">${due.map(([v, l], i) => `<button data-d="${v}" class="${i === 0 ? "on" : ""}">${esc(l)}</button>`).join("")}</div>`}
    <button class="primary" id="rSave">${esc(t("save", "Save"))}</button>`);
  let kind = isPay ? "payment_received" : "credit_sale", dueV = "";
  $("#sheetBody").onclick = async (e) => {
    const b = e.target.closest("button"); if (!b) return;
    if (b.dataset.k) { kind = b.dataset.k; $("#rKind").querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b)); }
    if (b.dataset.d !== undefined && b.closest("#rDue")) { dueV = b.dataset.d; $("#rDue").querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b)); }
    if (b.id === "rSave") {
      const amount = parseFloat(($("#rAmt").value || "").replace(/[₦,\s]/g, "").replace(/k$/i, "000"));
      if (!(amount > 0)) return toast(t("amount", "Amount (₦)"));
      b.disabled = true;
      try {
        const r = await post(`/api/customers/${c.id}/record`, { type: kind, amount, item: $("#rItem")?.value || null,
                                                                due_date: kind === "credit_sale" ? dueV || null : null });
        $("#sheet").hidden = true; refreshThread(r);
      } catch (err) { b.disabled = false; toast(err.message); }
    }
  };
}

function contactSheet(c) {
  sheet(`<h3>${esc(c ? t("edit_contact", "Edit contact") : t("new_customer", "New customer"))}</h3>
    <label>${esc(t("name", "Name"))}<input id="kName" value="${esc(c ? c.name : "")}" autocomplete="off"></label>
    <label>${esc(t("phone", "Phone number"))}<input id="kPhone" inputmode="tel" value="${esc(c ? c.phone || "" : "")}" placeholder="0803 123 4567"></label>
    <label>${esc(t("notes", "Notes"))}<input id="kNotes" value="${esc(c ? c.notes || "" : "")}" autocomplete="off"></label>
    <button class="primary" id="kSave">${esc(t("save", "Save"))}</button>
    ${c ? `<p></p><button class="danger" id="kDel">${esc(t("delete", "Delete"))} ${esc(c.name)}</button>` : ""}`);
  $("#sheetBody").onclick = async (e) => {
    const b = e.target.closest("button"); if (!b) return;
    try {
      if (b.id === "kSave") {
        const body = { name: $("#kName").value.trim(), phone: $("#kPhone").value.trim(), notes: $("#kNotes").value.trim() };
        if (!body.name) return toast(t("name", "Name"));
        if (c) {
          await api(`/api/customers/${c.id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
          $("#sheet").hidden = true; refreshThread();
        } else {
          const n = await post("/api/customers", body);
          $("#sheet").hidden = true; await loadCustomers(); openThread(n.id);
        }
      }
      if (b.id === "kDel" && confirm(t("confirm_delete_customer", "Delete this customer?"))) {
        await api(`/api/customers/${c.id}`, { method: "DELETE" });
        $("#sheet").hidden = true; closeThread(); loadCustomers();
      }
    } catch (err) { toast(err.message); }
  };
}

function isoPlus(n) { const d = new Date(); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10); }
function nextFriday() { const d = new Date(); d.setDate(d.getDate() + (((5 - d.getDay()) + 7) % 7 || 7)); return d.toISOString().slice(0, 10); }
