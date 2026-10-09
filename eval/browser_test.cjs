/* The whole TradeVoice 2.0 app in a real browser: website, sign-up, records, "You got", a customer, a reminder draft,
   the Ask tab, the Me tab, password change, log out and back in.

   Needs Node + Playwright (Chromium). It starts its own server with AUTH_DEMO=1 and a fresh temp database every run
   (sign-up fails if the number already exists), and made-up names and numbers only.

     NODE_PATH=$(npm root -g) node eval/browser_test.cjs            # PORT=8765 by default; HEADED=1 to watch it
*/
const { chromium } = require("playwright");
const { spawn } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const PORT = +(process.env.PORT || 8765);
const BASE = `http://127.0.0.1:${PORT}`;
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), "tv-browser-"));
const SHOTS = path.join(TMP, "shots");
fs.mkdirSync(SHOTS);

const PHONE = "8030000417";           // made up
const PW1 = "Market2026x", PW2 = "Balogun2027y";
const NAME = "Ada Testtrader", BIZ = "Ada Test Stores";

let passed = 0;
const failed = [], todos = [];
let page, shot = 0;
async function check(name, fn) {
  try {
    const ok = await fn();
    if (ok === false) throw new Error("returned false");
    passed++; console.log(`✓ ${name}`);
    if (process.env.SHOT_ALL) await page.screenshot({ path: path.join(SHOTS, `ok-${String(passed).padStart(2, "0")}-${name.replace(/\W+/g, "_").slice(0, 40)}.png`) }).catch(() => {});
  } catch (e) {
    failed.push(name);
    const file = path.join(SHOTS, `${String(++shot).padStart(2, "0")}-${name.replace(/\W+/g, "_").slice(0, 40)}.png`);
    try { await page.screenshot({ path: file }); } catch (_) {}
    console.log(`✗ ${name}: ${String(e.message || e).split("\n")[0]}  (${file})`);
  }
}
async function todo(name, fn) {   // known to-dos for the designer: reported, not counted as failures
  try { await fn(); passed++; console.log(`✓ ${name}`); } catch (e) { todos.push(name); console.log(`• to-do: ${name}: ${e.message}`); }
}
const sleep = ms => new Promise(r => setTimeout(r, ms));
const naira = n => "₦" + n.toLocaleString("en-NG");

function startServer() {
  const env = Object.assign({}, process.env, {
    AUTH_DEMO: "1", ACCOUNTS_DB: path.join(TMP, "accounts.db"), BOOKS_DIR: path.join(TMP, "books"),
    DB_PATH: path.join(TMP, "tradevoice.db"), PORT: String(PORT), TRADEVOICE_ADMIN: "0", AUTO_REMINDERS: "0",
    // offline: no AI, no WhatsApp, no payments (the rules understand the sentences below)
    NATLAS_URL: "", NATLAS_ASR_URL: "", NVIDIA_API_KEY: "", LOCAL_LLM_URL: "", WHATSAPP_TOKEN: "", PAYSTACK_SECRET_KEY: "",
    INTRON_API_KEY: "", ADMIN_TOKEN: "browser-team-key",
  });
  const p = spawn(process.env.PYTHON || "python", ["src/web.py"], { cwd: ROOT, env, stdio: ["ignore", "pipe", "pipe"] });
  const log = fs.createWriteStream(path.join(TMP, "server.log"));
  p.stdout.pipe(log); p.stderr.pipe(log);
  return p;
}
async function waitUp() {
  for (let i = 0; i < 120; i++) {
    try { if ((await fetch(BASE + "/api/status")).ok) return; } catch (_) {}
    await sleep(500);
  }
  throw new Error("server didn't start, see " + path.join(TMP, "server.log"));
}

// the book the server holds (the numbers the screens must show: code does the maths, never the test or the AI)
const book = () => page.evaluate(async () => (await fetch("/api/v2/book")).json());
async function say(text) {   // what Talk sends after N-ATLaS hears a voice note, then "Save"
  return page.evaluate(async t => {
    const post = b => fetch("/api/message", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(Object.assign({ session: "browser-test", lang: "English" }, b)) }).then(r => r.json());
    const a = await post({ text: t });
    const b = a.pending ? await post({ text: "yes" }) : null;
    return { a, b };
  }, text);
}
const toastText = async () => (await page.locator(".toast").last().textContent({ timeout: 5000 })) || "";
const gone = sel => page.locator(sel).waitFor({ state: "detached", timeout: 5000 });
async function tab(k) { await page.click(`#tabs [data-k=${k}]`); await page.waitForSelector(`#${k}.on`); }

(async () => {
  const server = startServer();
  const errors = [], bad = [];
  let browser;
  try {
    await waitUp();
    browser = await chromium.launch({ headless: !process.env.HEADED,   // a fake microphone (beeps) for the live talk
      args: ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"] });
    const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, locale: "en-NG", permissions: ["microphone"] });
    await ctx.route(/fonts\.(googleapis|gstatic)\.com/, r => r.abort());   // no internet needed
    page = await ctx.newPage();
    let wsFake = null;
    // live hearing sockets: Playwright fakes WebSockets with a script put in at page load, so the route is set here,
    // before the app opens. Normally they go to the real server; a check can put in a fake Intron (wsFake)
    await page.routeWebSocket(/\/api\/live\/hear/, ws => (wsFake ? wsFake(ws) : ws.connectToServer()));
    page.on("pageerror", e => errors.push(e.message));
    page.on("console", m => m.type() === "error" && !/Failed to load resource|ERR_FAILED/.test(m.text()) && errors.push(m.text()));
    page.on("response", r => r.url().startsWith(BASE) && r.status() >= 500 && bad.push(`${r.status()} ${r.url()}`));

    /* ------------------------------------------------------------ the website */
    await page.goto(BASE + "/", { waitUntil: "domcontentloaded" });
    await check("website: opens with the TradeVoice title", async () => /TradeVoice/.test(await page.title()));
    await check("website: every #link has a section", async () => {
      const miss = await page.evaluate(() => [...document.querySelectorAll('a[href^="#"]')].map(a => a.getAttribute("href"))
        .filter(h => h.length > 1 && !document.getElementById(h.slice(1))));
      if (miss.length) throw new Error("missing: " + miss.join(", "));
    });
    await check("website: 'Get the app' has App Store / Google Play (Soon) and 'Open in browser' goes to the app", async () => {
      const r = await page.evaluate(() => ({ stores: document.querySelectorAll("#download [data-store]").length,
        soon: !document.getElementById("soonnote").hidden, open: document.querySelector('#download a.btn[href="/app"]') !== null }));
      if (r.stores !== 2 || !r.soon || !r.open) throw new Error(JSON.stringify(r));
    });
    await check("website + app: installable ('Add to Home Screen' gets the TradeVoice name and icon)", async () => {
      const m = await page.evaluate(async () => { const l = document.querySelector('link[rel=manifest]'); const r = await fetch(l.href);
        return { type: r.headers.get("content-type"), j: await r.json() }; });
      if (!/manifest\+json/.test(m.type) || m.j.start_url !== "/app" || m.j.icons.length < 2) throw new Error(JSON.stringify(m));
      for (const i of m.j.icons) if ((await fetch(BASE + i.src)).status !== 200) throw new Error("missing " + i.src);
    });
    await check("website: no dashes (the line before each small heading is gone) and no emojis", async () =>
      page.evaluate(() => getComputedStyle(document.querySelector(".k"), "::before").display === "none"
        && !/[\u2014\u2013]|\p{Extended_Pictographic}/u.test(document.body.innerText.replace(/[↑↓✓✕]/g, ""))));
    await check("website: no sideways scroll on a phone", async () =>
      page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
    await check("website: shows the N-ATLaS attribution", async () => {
      const txt = await page.evaluate(() => document.body.innerText);
      if (!/Federal Ministry of Communications, Innovation and Digital Economy/.test(txt) || !/Awarri/.test(txt))
        throw new Error("the licence sentence isn't on the page");
    });
    await check("website: 'Open the app' goes to /app", async () => {
      await Promise.all([page.waitForURL(/\/app$/), page.locator('a[href="/app"]').first().click()]);
    });

    /* ------------------------------------------------------------ sign-up */
    await page.waitForSelector("#gate [data-g=signup]");
    await check("welcome: the 4 languages, no Pidgin button", async () => {
      const langs = await page.locator("#gate [data-a=lang]").allTextContents();
      if (langs.some(l => /pidgin/i.test(l))) throw new Error("tiles: " + langs.join(", "));
    });
    await page.click("#gate [data-g=signup]");
    await page.fill("#ph", PHONE);
    await page.check("#ag");
    const codeResp = page.waitForResponse(r => r.url().endsWith("/api/auth/v2/code/start"));
    await page.click("#go");
    const code = (await (await codeResp).json()).demo_code;
    await check("sign-up: a code is sent (demo shows it)", async () => /^\d{6}$/.test(code || ""));
    await page.fill("#otp", code);
    await page.waitForSelector("#pgo");
    await page.fill("#pw", PW1); await page.fill("#pw2", PW1); await page.click("#pgo");
    await page.waitForSelector("#bn");
    await page.fill("#on", NAME); await page.fill("#bn", BIZ);
    await page.locator("[data-ty]").first().click();
    await page.fill("#mk", "Test Market");
    await page.click("#go");
    await check("sign-up: welcome toast and the gate goes", async () => {
      if (!/Welcome/.test(await toastText())) throw new Error("no welcome toast");
      await gone("#gate");
    });
    await check("sign-up: then the separate 'Help make TradeVoice better' question; Yes is saved", async () => {
      await page.waitForSelector(".ov.on #ty", { timeout: 15000 });
      const t = await page.locator(".ov.on h3").textContent();
      if (t !== "Help make TradeVoice better") throw new Error(t);
      if (!(await page.locator(".ov.on #tn").count())) throw new Error("no 'No, thanks'");
      await page.click(".ov.on #ty");
      await page.waitForFunction(() => [...document.querySelectorAll(".toast")].some(t => /Thank you/.test(t.textContent)), null, { timeout: 5000 });
      const me = await page.evaluate(() => fetch("/api/v2/me").then(r => r.json()));
      if (me.train !== true) throw new Error(JSON.stringify(me.train));
      await gone(".ov.on");
    });

    /* ------------------------------------------------------------ records (what Talk saves after "Save") */
    const r1 = await say("Iya Bisi took 2 bags of rice for 60000, she will pay Friday");
    const r2 = await say("Oga Emeka bought goods on credit 25000");
    const r3 = await say("Iya Bisi paid 10000");
    await check("records: 3 saved", async () => {
      for (const r of [r1, r2, r3]) if (!r.b) throw new Error("not understood: " + JSON.stringify(r.a).slice(0, 160));
    });
    await page.evaluate(() => TVL.loadBook());
    let bk = await book();
    const owes = n => (bk.customers.find(c => c.n === n) || {}).b;
    await check("records: Iya Bisi owes ₦50,000, Oga Emeka ₦25,000", async () => {
      if (owes("Iya Bisi") !== 50000 || owes("Oga Emeka") !== 25000) throw new Error(JSON.stringify(bk.customers));
    });

    /* ------------------------------------------------------------ customers, "You got", reminder */
    await tab("cust");
    await check("customers: both rows, biggest debt first", async () => {
      const rows = await page.locator("#cust .row b:not(.money)").allTextContents();
      if (rows[0] !== "Iya Bisi" || !rows.includes("Oga Emeka")) throw new Error(rows.join(", "));
    });
    await page.locator("#cust .row", { hasText: "Iya Bisi" }).click();
    await page.waitForSelector("#det.on");
    await check("customer page: shows ₦50,000 and the history", async () => {
      await page.waitForFunction(() => document.querySelectorAll("#det .list li").length >= 2);
      return (await page.locator("#det .who .money").textContent()).includes("50,000");
    });
    await page.click("#det [data-a=got]");
    await page.click(".ov.on #am"); await page.keyboard.type("5000"); await page.click(".ov.on #go");   // typed like a person
    await check("You got ₦5,000: toast says she still owes ₦45,000", async () => {
      await page.waitForFunction(() => /recorded/.test(document.querySelector(".toast")?.textContent || ""));
      const t = await toastText();
      if (!t.includes("45,000")) throw new Error(t);
      bk = await book();
      if (owes("Iya Bisi") !== 45000) throw new Error("book says " + owes("Iya Bisi"));
    });
    await check("customer page: updates to ₦45,000", async () =>
      page.waitForFunction(() => document.querySelector("#det .who .money")?.textContent.includes("45,000")).then(() => true));
    const sentBefore = await page.evaluate(() => performance.getEntriesByType("resource").filter(e => /whatsapp\/send|send_text/.test(e.name)).length);
    await page.click("#det [data-a=remind]");
    await check("reminder: a draft the trader sends, with name and amount", async () => {
      const m = await page.locator(".ov.on #mg").inputValue({ timeout: 5000 });
      if (!/Bisi/.test(m) || !m.includes("45,000")) throw new Error(m);
      const sent = await page.evaluate(() => performance.getEntriesByType("resource").filter(e => /whatsapp\/send|send_text/.test(e.name)).length);
      if (sent !== sentBefore) throw new Error("something was sent to WhatsApp");
    });
    await page.keyboard.press("Escape");
    await page.evaluate(() => document.querySelectorAll(".ov").forEach(o => o.remove()));

    /* ------------------------------------------------------------ Home: Today / 7D / 30D / 1Y / Custom */
    await tab("home");
    const pick = async p => { await page.click("#home [data-a=perpick]"); await page.waitForSelector(`.ov.on [data-pp="${p}"]`); await page.click(`.ov.on [data-pp="${p}"]`); };
    await check("Home: one small period button top right (Today), its sheet lists Today, 7, 30 days, 12 months, dates", async () => {
      const btn = page.locator("#home [data-a=perpick]");
      if ((await btn.textContent()).trim() !== "Today") throw new Error(await btn.textContent());
      const [b, h] = await Promise.all([btn.boundingBox(), page.locator("#home h1").boundingBox()]);
      if (!(b.x > h.x + 150 && b.y < h.y + h.height)) throw new Error(`not top right: ${JSON.stringify(b)}`);
      if (await page.locator("#home .perseg").count()) throw new Error("the old row of buttons is still there");
      await page.click("#home [data-a=perpick]");
      await page.waitForFunction(() => document.querySelectorAll(".ov.on [data-pp]").length === 5);
      const names = (await page.locator(".ov.on [data-pp]").allTextContents()).map(x => x.replace("✓", "").trim());
      await page.keyboard.press("Escape"); await page.evaluate(() => document.querySelectorAll(".ov").forEach(o => o.remove()));
      if (names.join("|") !== "Today|Last 7 days|Last 30 days|Last 12 months|Choose dates") throw new Error(names.join("|"));
      return /Today/.test(await page.locator("#home h1").textContent()) && (await page.locator("#home .hero p").first().textContent()) === "Net today";
    });
    await check("Home: 7 days asks the server for the last 7 days; title, label and button follow; money in matches", async () => {
      const resp = page.waitForResponse(r => /\/api\/v2\/book\?period=7$/.test(r.url()));
      await pick("7");
      const d = await (await resp).json();
      await page.waitForFunction(() => /Last 7 days/.test(document.querySelector("#home h1").textContent));
      if ((await page.locator("#home .hero p").first().textContent()) !== "Net, last 7 days") throw new Error("label");
      if ((await page.locator("#home [data-a=perpick]").textContent()).trim() !== "7D") throw new Error("button");
      if (!(await page.locator("#home .hero").textContent()).includes(naira(d.in))) throw new Error("money in " + d.in);
      if (d.period !== "7") throw new Error(JSON.stringify(d).slice(0, 80));
    });
    await check("Home: Choose dates asks for the days (From, To); Cancel changes nothing", async () => {
      await pick("custom");
      await page.waitForSelector(".ov.on #pa");
      if (await page.locator(".ov.on #pa").getAttribute("type") !== "date") throw new Error("not a date field");
      await page.click(".ov.on #px");
      await page.waitForFunction(() => !document.querySelector(".ov.on #pa"));
      return (await page.locator("#home .hero p").first().textContent()) === "Net, last 7 days";
    });
    await check("Home: dates 1 Sep to 30 Sep: the server adds up those days; title '1 Sep to 30 Sep'", async () => {
      await pick("custom");
      await page.waitForSelector(".ov.on #pa");
      await page.fill(".ov.on #pa", "2026-09-30");     // the wrong way round on purpose: put in order
      await page.fill(".ov.on #pb", "2026-09-01");
      const resp = page.waitForResponse(r => /period=custom&start=2026-09-01&end=2026-09-30/.test(r.url()));
      await page.click(".ov.on #pg");
      const d = await (await resp).json();
      if (d.from !== "2026-09-01" || d.to !== "2026-09-30") throw new Error(JSON.stringify(d).slice(-90));
      await page.waitForFunction(() => /1 Sep to 30 Sep/.test(document.querySelector("#home h1").textContent));
      return (await page.locator("#home .hero p").first().textContent()) === "Net, 1 Sep to 30 Sep";
    });
    await check("Home: the choice is kept (with its days); back to Today", async () => {
      if (await page.evaluate(() => localStorage.getItem("tv-per")) !== "custom") throw new Error("not kept");
      if (!/2026-09-01/.test(await page.evaluate(() => localStorage.getItem("tv-per-range")))) throw new Error("days not kept");
      await pick("today");
      await page.waitForFunction(() => document.querySelector("#home .hero p").textContent === "Net today");
    });

    /* ------------------------------------------------------------ Ask: the chat with your book (design 3) */
    await tab("ask");
    const answers = () => page.locator("#thr .ab:not(.u):not(.ty)");
    const nextAnswer = async (n, ms = 15000) => {
      await page.waitForFunction(n => document.querySelectorAll("#thr .ab:not(.u):not(.ty)").length > n, n, { timeout: ms });
      return (await answers().last().textContent()).replace(/\s+/g, " ");
    };
    const askBtn = async q => { const n = await answers().count(); await page.locator(`#ask [data-a=aqs][data-t="${q}"]`).first().click(); return nextAnswer(n); };
    let speaks = 0, says = 0, resets = 0;
    page.on("request", r => { const u = r.url(); if (/\/api\/speak\//.test(u)) speaks++; if (/\/api\/ask\/say$/.test(u)) says++; if (/\/api\/ask\/reset$/.test(u)) resets++; });
    await check("Ask: the design's empty chat, with its four questions", async () => (await page.locator("#ask .sl [data-a=aqs]").count()) === 4);
    await check("Ask: who owes the most → Iya Bisi, big number ₦45,000 on top", async () => {
      const a = await askBtn("Who owes me the most?"), big = (await answers().last().locator(".an").textContent()).trim();
      if (!/Iya Bisi/.test(a) || big !== "₦45,000") throw new Error(`${a} | ${big}`);
    });
    await check("Ask: total owed → ₦70,000", async () => { const a = await askBtn("How much is owed in total?"); if (!/70,000/.test(a)) throw new Error(a); });
    await check("Ask: who is late → nobody", async () => { const a = await askBtn("Who is late?"); if (!/Nobody is late/.test(a)) throw new Error(a); });
    await check("Ask: money in today matches the book", async () => {
      bk = await book(); const a = await askBtn("How much did I get today?");
      if (!a.includes(naira(bk.in))) throw new Error(`${a} vs book ${bk.in}`);
    });
    await check("Ask: a typed question goes to the same brain: Oga Emeka ₦25,000", async () => {
      const n = await answers().count();
      await page.fill("#aq", "How much does Oga Emeka owe me?"); await page.press("#aq", "Enter");
      const a = await nextAnswer(n); if (!/25,000/.test(a)) throw new Error(a);
      const u = (await page.locator("#thr .ab.u").last().textContent()).trim();
      if (u !== "How much does Oga Emeka owe me?") throw new Error("question bubble: " + u);
    });
    await check("Ask: a dropped line is tried again once (the answer still comes)", async () => {
      let tries = 0;
      await page.route("**/api/ask", r => (++tries === 1 ? r.abort() : r.continue()));
      const n = await answers().count();
      await page.fill("#aq", "Who is late?"); await page.press("#aq", "Enter");
      const a = await nextAnswer(n); await page.unroute("**/api/ask");
      if (!/Nobody is late/.test(a) || tries !== 2) throw new Error(`${tries} tries: ${a}`);
    });
    await check("Ask: the server can't be reached but the phone is online: 'slow', never 'No network'", async () => {
      await page.route("**/api/ask", r => r.abort());
      const n = await answers().count();
      await page.fill("#aq", "Who is late?"); await page.press("#aq", "Enter");
      const a = await nextAnswer(n); await page.unroute("**/api/ask");
      if (!/slow right now/.test(a) || /No network/.test(a)) throw new Error(a);
    });
    await check("Ask: a book refresh while you type keeps your words (it used to wipe the box)", async () => {
      await page.fill("#aq", "How much does Iya");
      await page.evaluate(() => all());   // what every answer does (the book reloads, every tab redraws)
      const v = await page.inputValue("#aq");
      await page.fill("#aq", "");
      if (v !== "How much does Iya") throw new Error(`box now: "${v}"`);
    });
    await check("Ask: a typed answer doesn't speak by itself", async () => { await sleep(500); return speaks === 0; });
    await check("Ask: every answer is a voice note, play button in the design's accent colour", async () => {
      const vp = answers().last().locator(".vn .vp");
      const [bg, accent] = await Promise.all([vp.evaluate(el => getComputedStyle(el).backgroundColor), page.evaluate(() => {
        const d = document.createElement("div"); d.style.background = "var(--accent)"; document.body.append(d);
        const c = getComputedStyle(d).backgroundColor; d.remove(); return c; })]);
      if (bg !== accent) throw new Error(`${bg} vs accent ${accent}`);
      if ((await answers().last().locator(".vn .vb i").count()) < 20) throw new Error("no waveform");
    });
    // the voice (Intron) is off in this test: a 1-second WAV stands in for it
    const wav = (() => { const n = 8000, b = Buffer.alloc(44 + n * 2); b.write("RIFF", 0); b.writeUInt32LE(36 + n * 2, 4); b.write("WAVEfmt ", 8);
      b.writeUInt32LE(16, 16); b.writeUInt16LE(1, 20); b.writeUInt16LE(1, 22); b.writeUInt32LE(8000, 24); b.writeUInt32LE(16000, 28);
      b.writeUInt16LE(2, 32); b.writeUInt16LE(16, 34); b.write("data", 36); b.writeUInt32LE(n * 2, 40); return b; })();
    await page.route("**/api/speak/*", route => route.fulfill({ status: 200, contentType: "audio/wav", body: wav }));
    await check("Ask: tap play → the answer is spoken (a fresh id for the same words), its length shows", async () => {
      await answers().last().locator(".vp").click();
      await page.waitForFunction(() => { const v = [...document.querySelectorAll("#thr .vn")].pop(); return v && /\d:\d\d/.test(v.querySelector(".vd").textContent); }, null, { timeout: 10000 });
      if (says < 1 || speaks < 1) throw new Error(`say ${says}, speak ${speaks}`);
    });
    await page.route("**/api/hear", route => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ heard: "Who owes me the most?" }) }));
    await check("Ask: a voice question: recorded, heard, asked, shown with the mic mark; the answer comes as words", async () => {
      const n = await answers().count(), s0 = speaks;
      await page.click("#amic"); await page.waitForSelector("#cmp.rec", { timeout: 5000 });
      for (let i = 0; i < 30 && await page.locator("#cmp.rec").count(); i++) await sleep(200);   // stops itself after the voice
      if (await page.locator("#cmp.rec").count()) await page.click("#amic");                       // or the trader taps stop
      const a = await nextAnswer(n); if (!/Iya Bisi/.test(a)) throw new Error(a);
      const u = page.locator("#thr .ab.u").last();
      if (!(await u.locator(".vtag").count()) || !/Who owes me the most/.test(await u.textContent())) throw new Error("question bubble");
      await sleep(1500);
      if (speaks !== s0) throw new Error("the answer spoke by itself (Intron costs money: only on a tap)");
    });
    await page.unroute("**/api/hear");
    const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==", "base64");
    let saved = null;
    await page.route("**/api/ask/photo", route => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
      t: "I found 2 lines. Check them before I save.", act: "scan", lang: "English",
      rows: [{ save: true, type: "sale", amount: 5000, item: "rice", customer: null, line: "rice 5000" },
             { save: false, type: "credit_sale", amount: null, item: "beans", customer: "Mama Ada", line: "Mama Ada beans ?" }] }) }));
    await page.route("**/api/save_rows", route => { saved = route.request().postDataJSON(); route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ saved: 1, problems: [] }) }); });
    await check("Ask: + photo → preview → send → 'Check the lines'", async () => {
      await page.setInputFiles("#fgal", { name: "page.png", mimeType: "image/png", buffer: PNG });
      await page.waitForSelector("#ask .pv img", { timeout: 5000 });
      await page.click("#amic");   // the send button while a photo waits
      await page.waitForSelector("#thr [data-a=achk]", { timeout: 15000 });
    });
    await check("Ask: 'Check the lines' shows the lines found; only the ticked line is saved", async () => {
      await page.locator("#thr [data-a=achk]").last().click();
      await page.waitForSelector(".ov.on .ln", { timeout: 5000 });
      if ((await page.locator(".ov.on .ln").count()) !== 2) throw new Error("lines");
      await page.click(".ov.on #sv");
      for (let i = 0; i < 20 && !saved; i++) await sleep(250);
      if (!saved || saved.rows.filter(r => r.save).length !== 1) throw new Error(JSON.stringify(saved));
      await page.waitForFunction(() => /1 line saved/.test(document.querySelector("#thr").textContent), null, { timeout: 5000 });
    });
    await page.unroute("**/api/ask/photo"); await page.unroute("**/api/save_rows"); await page.unroute("**/api/speak/*");
    const LIST = "# Name Amount owed Chinedu ₦15,000 Aisha ₦45,000 Tunde ₦8,500 Akinwande ₦200,000 Victor 500,000 mike 7m";
    await check("Ask: a pasted list with N-ATLaS off: an honest line, never one guessed number", async () => {
      const n = await answers().count();
      await page.fill("#aq", LIST); await page.press("#aq", "Enter");
      const a = await nextAnswer(n);
      if (!/can't read a long list right now/.test(a) || /200,000/.test(a)) throw new Error(a);
    });
    saved = null;
    await page.route("**/api/ask", route => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
      t: "I found 3 people who owe you, ₦7,060,000 in all. Check them before I save.", n: null, lang: "English", say: "",
      speak: null, pending: false, act: "scan",
      rows: [{ save: true, type: "credit_sale", amount: 15000, customer: "Chinedu", item: "", line: "Chinedu ₦15,000" },
             { save: true, type: "credit_sale", amount: 45000, customer: "Aisha", item: "", line: "Aisha ₦45,000" },
             { save: false, type: "credit_sale", amount: 7000000, customer: "Mike", item: "", line: "mike 7m" }] }) }));
    await page.route("**/api/save_rows", route => { saved = route.request().postDataJSON(); route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ saved: 2, problems: [] }) }); });
    await check("Ask: a list read by N-ATLaS: 'Check the lines' lists every person; only the ticked ones are saved", async () => {
      const n = await answers().count();
      await page.fill("#aq", LIST); await page.press("#aq", "Enter");
      const a = await nextAnswer(n);
      if (!/I found 3 people who owe you/.test(a)) throw new Error(a);
      await page.locator("#thr [data-a=achk]").last().click();
      await page.waitForSelector(".ov.on .ln", { timeout: 5000 });
      if ((await page.locator(".ov.on .ln").count()) !== 3) throw new Error("lines");
      if ((await page.locator(".ov.on .ln.u").count()) !== 1) throw new Error("Mike should need a look");
      await page.click(".ov.on #sv");
      for (let i = 0; i < 20 && !saved; i++) await sleep(250);
      const ticked = saved && saved.rows.filter(r => r.save).map(r => r.customer).join(",");
      if (ticked !== "Chinedu,Aisha") throw new Error(JSON.stringify(saved));
      await page.waitForFunction(() => /2 lines saved/.test(document.querySelector("#thr").textContent), null, { timeout: 5000 });
    });
    await page.unroute("**/api/ask"); await page.unroute("**/api/save_rows");
    await check("Ask: the chat is kept on this phone, per account", async () => {
      const h = await page.evaluate(() => JSON.parse(localStorage.getItem("tv-ask-" + TVL.A.phone) || "[]"));
      if (h.length < 12) throw new Error(`${h.length} messages kept`);
    });
    await check("Ask: Clear history asks first, then the chat and the server's memory are cleared", async () => {
      await page.click("#ask [data-a=aclr]");
      await page.locator(".ov.on button", { hasText: "Clear history" }).last().click();
      await page.waitForSelector("#ask .sl", { timeout: 5000 });
      for (let i = 0; i < 20 && !resets; i++) await sleep(100);
      if (!resets) throw new Error("server not told");
    });
    await check("Ask: nothing was saved by asking", async () => {
      const b2 = await book(); return JSON.stringify(b2.customers.map(c => [c.n, c.b])) === JSON.stringify(bk.customers.map(c => [c.n, c.b]));
    });

    /* ------------------------------------------------------------ Me */
    await tab("me");
    await check("Me: name, business, masked phone", async () => {
      const t = await page.locator("#me .pcard").textContent();
      if (!t.includes(NAME) || !t.includes(BIZ)) throw new Error(t);
      if (t.includes(PHONE)) throw new Error("full phone number on screen: " + t);
    });
    await check("Me: N-ATLaS credited in About", async () => /N-ATLaS/.test(await page.locator("#me").textContent()));
    await check("Me: 'Help make TradeVoice better' shows On, and the privacy notice is a real page", async () => {
      const row = await page.locator('#me [data-a=train]').textContent();
      if (!/Help make TradeVoice better/.test(row) || !/On/.test(row)) throw new Error(row);
      const p = await page.evaluate(() => fetch("/privacy").then(r => r.text()));
      if (!/90 days/.test(p) || !/Helping make TradeVoice better/.test(p)) throw new Error("privacy page");
    });
    await check("Me: language change is saved on the server", async () => {
      await page.selectOption("#lg", "yo");
      await page.waitForFunction(async () => (await (await fetch("/api/v2/me")).json()).lang === "Yoruba", null, { timeout: 8000, polling: 500 });
      await page.selectOption("#lg", "en");
      await page.waitForFunction(async () => (await (await fetch("/api/v2/me")).json()).lang === "English", null, { timeout: 8000, polling: 500 });
      await page.waitForSelector("#tabs [data-k=me]");
    });
    await check("Me: Voice replies switch turns off and stays off after a refresh, then back on", async () => {
      const sw = () => page.locator('#me [data-a=voice]');
      if (await sw().getAttribute("aria-checked") !== "true") throw new Error("not on at first");
      await sw().click();
      if (await sw().getAttribute("aria-checked") !== "false") throw new Error("didn't turn off");
      await page.reload({ waitUntil: "domcontentloaded" });
      await page.waitForFunction(() => window.TVL && TVL.A && !document.querySelector("#gate"));
      await tab("me");
      if (await sw().getAttribute("aria-checked") !== "false") throw new Error("came back on after refresh");
      await sw().click();
      if (await sw().getAttribute("aria-checked") !== "true") throw new Error("didn't turn back on");
    });
    await check("Talk (live): listen, answer, 'yes' saves, 'that's all' closes", async () => {
      // N-ATLaS isn't here: what it "heard" is fed in, the rest is the real server (session, draft, save, book)
      // (the fake microphone beeps, so the page may hear "early" more than once: what was heard only moves on when the
      // page really replies, through the real /api/say)
      const said = ["Mama Ngozi took beans 3000 on credit", "yes please", "that's all"]; let replies = 0;
      await page.route("**/api/hear", route => route.fulfill({ status: 200, contentType: "application/json",
        body: JSON.stringify({ heard: said[replies] || "" }) }));
      await page.route("**/api/say", route => { replies++; route.continue(); });
      await page.click("#tabs [data-a=talk]");
      await page.waitForSelector(".ov.on .tvc[data-st=listen]");
      const turn = async () => { await page.waitForSelector(".ov.on .tvc[data-st=listen]"); await sleep(600); await page.click(".ov.on #orb"); };
      await turn();
      await page.waitForFunction(() => /3,000 · Mama Ngozi/.test(document.querySelector(".ov.on #cap")?.textContent || ""), null, { timeout: 8000 });
      await turn();
      await page.waitForFunction(() => /Saved/.test(document.querySelector(".ov.on #cap")?.textContent || ""), null, { timeout: 8000 });
      await turn();
      await gone(".ov .tvc");
      await page.unroute("**/api/hear"); await page.unroute("**/api/say");
      const got = ((await book()).customers.find(c => c.n === "Mama Ngozi") || {}).b;
      if (got !== 3000) throw new Error(`Mama Ngozi owes ${got}, not 3000`);
      if (replies !== 2) throw new Error(`${replies} replies ("that's all" ends it without one)`);
    });
    await check("Talk (live, Intron stream): the mic streams as 16-bit audio, your words show while you talk, the reply saves", async () => {
      // Intron isn't here: a fake hearing socket answers like Intron's stream (partial words, then the final words
      // on commit); the reply is the real server (/api/say), its voice in pieces (/api/speak/<id>/<n>)
      const said = ["Iya Bisi took garri 4500 on credit", "yes", "that's all"]; let turn = 0, frames = 0, odd = 0, pieces = 0;
      await page.route("**/api/warm", route => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ live: true }) }));
      await page.route(/\/api\/speak\/[0-9a-f]+\/\d+$/, route => { pieces++; route.fulfill({ status: 200, contentType: "audio/wav", body: wav }); });
      const before = ((await book()).customers.find(c => c.n === "Iya Bisi") || {}).b || 0;
      wsFake = ws => {
        let told = false;
        ws.onMessage(m => {
          if (typeof m != "string") { frames++; if (m.length % 2) odd++; if (!told) { told = true; ws.send(JSON.stringify({ type: "partial", text: said[turn].split(" ").slice(0, 2).join(" ") })); } return; }
          if (JSON.parse(m).type == "commit") ws.send(JSON.stringify({ type: "final", text: said[turn++] || "" }));
        });
      };
      await page.click("#tabs [data-a=talk]");
      await page.waitForSelector(".ov.on .tvc[data-st=listen]");
      await page.waitForFunction(() => /Iya Bisi/.test(document.querySelector(".ov.on #cap")?.textContent || ""), null, { timeout: 8000 });   // words while you talk
      const tap = async () => { await page.waitForSelector(".ov.on .tvc[data-st=listen]"); await sleep(700); await page.click(".ov.on #orb"); };
      await tap();
      await page.waitForFunction(() => /4,500 · Iya Bisi/.test(document.querySelector(".ov.on #cap")?.textContent || ""), null, { timeout: 8000 });
      await tap();
      await page.waitForFunction(() => /Saved/.test(document.querySelector(".ov.on #cap")?.textContent || ""), null, { timeout: 8000 });
      await tap();
      await gone(".ov .tvc");
      wsFake = null; await page.unroute("**/api/warm"); await page.unroute(/\/api\/speak\/[0-9a-f]+\/\d+$/);
      if (!frames || odd) throw new Error(`${frames} audio frames, ${odd} not 16-bit`);
      if (pieces < 2) throw new Error(`${pieces} voice pieces played`);
      const got = ((await book()).customers.find(c => c.n === "Iya Bisi") || {}).b;
      await page.evaluate(() => fetch("/api/v2/undo_last", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }));
      if (got !== before + 4500) throw new Error(`Iya Bisi owes ${got}, not ${before} + 4500`);
      const back = ((await book()).customers.find(c => c.n === "Iya Bisi") || {}).b;
      if (back !== before) throw new Error(`undo left ${back}`);
    });
    const fab = () => page.evaluate(() => {
      const b = document.querySelector(".addfab"), r = b.getBoundingClientRect();
      return { top: Math.round(r.top), left: Math.round(r.left), seen: getComputedStyle(b).visibility === "visible" };
    });
    await check("Customers: the round + stays in its corner while the list scrolls; only on Customers", async () => {
      await tab("home");
      if ((await fab()).seen) throw new Error("the + shows on Home");
      await tab("cust");
      await page.waitForFunction(() => getComputedStyle(document.querySelector(".addfab")).visibility === "visible");
      const at0 = await fab();
      await page.evaluate(() => { const v = document.querySelector("#cust"); v.scrollTop = v.scrollHeight; });
      const at1 = await fab();
      if (at0.top !== at1.top || at0.left !== at1.left) throw new Error(`it moved: ${JSON.stringify([at0, at1])}`);
      const hit = await page.evaluate(() => {   // scrolled to the end: the last customer is clear of it
        const b = document.querySelector(".addfab").getBoundingClientRect();
        return [...document.querySelectorAll("#cust .list .row")].map(r => r.getBoundingClientRect())
          .filter(r => r.left < b.right && b.left < r.right && r.top < b.bottom && b.top < r.bottom).length;
      });
      if (hit) throw new Error(`at the end of the list the + still covers ${hit} row(s)`);
      await page.evaluate(() => { document.querySelector("#cust").scrollTop = 0; });
      await page.click("#cust .list .row");
      await page.waitForSelector("#det.on");
      await page.waitForFunction(() => getComputedStyle(document.querySelector(".addfab")).visibility === "hidden");
      await page.click("#det [data-a=back]");
      await page.waitForFunction(() => !document.querySelector("#det.on"));
    });
    await check("Customers: a + to add a customer by hand: name, number, what they owe, what for, pay by", async () => {
      await page.click("[data-a=addcust]");
      await page.waitForSelector(".ov.on #cn");
      await page.click(".ov.on #cs");
      if (!/name/.test(await page.locator(".ov.on #cn-e").textContent())) throw new Error("no name: no error");
      await page.fill(".ov.on #cn", "Baba Kunle");
      await page.fill(".ov.on #cp", "12345");
      await page.click(".ov.on #cs");
      if (!/valid Nigerian number/.test(await page.locator(".ov.on #cp-e").textContent())) throw new Error("bad number accepted");
      await page.fill(".ov.on #cp", "803 555 0199");
      await page.fill(".ov.on #ca", "12500");
      if (await page.inputValue(".ov.on #ca") !== "12,500") throw new Error("amount not shown with commas");
      await page.fill(".ov.on #ci", "2 cartons of indomie");
      await page.click(".ov.on #cs");
      await gone(".ov.on #cn");
      const c = (await book()).customers.find(x => x.n === "Baba Kunle");
      if (!c || c.b !== 12500) throw new Error(JSON.stringify(c));
      await page.waitForFunction(() => /Baba Kunle/.test(document.querySelector("#cust").textContent));
    });
    await check("Customers: + with a name already in the book adds to that customer (no second Baba Kunle)", async () => {
      await page.click("[data-a=addcust]");
      await page.waitForSelector(".ov.on #cn");
      await page.fill(".ov.on #cn", "baba kunle");
      await page.fill(".ov.on #ca", "500");
      await page.click(".ov.on #cs");
      await gone(".ov.on #cn");
      const all = (await book()).customers.filter(x => x.n.toLowerCase() === "baba kunle");
      if (all.length !== 1 || all[0].b !== 13000) throw new Error(JSON.stringify(all));
      // back as it was for the checks below: the two records and Baba Kunle removed
      await page.evaluate(async () => { for (const _ of [1, 2]) await fetch("/api/v2/undo_last", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }); });
      const id = all[0].id;
      await page.evaluate(id => fetch(`/api/customers/${id}`, { method: "DELETE" }), id);
      await page.reload({ waitUntil: "domcontentloaded" });
      await page.waitForFunction(() => window.TVL && TVL.A && !document.querySelector("#gate"));
    });
    await check("Customers: 20 at a time, then 'Show more (N)' adds the rest", async () => {
      const ids = await page.evaluate(async () => {
        const out = [];
        for (let i = 1; i <= 22; i++) {
          const r = await fetch("/api/customers", { method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name: `Test Buyer ${String(i).padStart(2, "0")}` }) });
          out.push((await r.json()).id);
        }
        return out;
      });
      try {
        await page.reload({ waitUntil: "domcontentloaded" });
        await page.waitForFunction(() => window.TVL && TVL.A && !document.querySelector("#gate"));
        await tab("cust");
        const total = await page.evaluate(() => C.length);
        await page.waitForSelector("#cust [data-a=custmore]");
        const rows = await page.locator("#cust .list .row").count();
        const label = await page.locator("#cust [data-a=custmore]").textContent();
        if (rows !== 20 || label !== `Show more (${total - 20})`) throw new Error(`${rows} rows, '${label}', ${total} customers`);
        await page.click("#cust [data-a=custmore]");
        await page.waitForFunction(n => document.querySelectorAll("#cust .list .row").length === n, total);
        if (await page.locator("#cust [data-a=custmore]").count()) throw new Error("'Show more' still there with everyone shown");
        await page.fill("#q", "Test Buyer 0");   // a new search starts again from 20 (9 match here: no button)
        await page.waitForFunction(() => document.querySelectorAll("#cust .list .row").length === 9);
        await page.fill("#q", "");
        await page.waitForSelector("#cust [data-a=custmore]");
      } finally {
        await page.evaluate(async ids => { for (const id of ids) await fetch(`/api/customers/${id}`, { method: "DELETE" }); }, ids);
        await page.reload({ waitUntil: "domcontentloaded" });
        await page.waitForFunction(() => window.TVL && TVL.A && !document.querySelector("#gate"));
      }
    });
    await check("Customers filter: '₦10,000 to ₦100,000' shows the right people, with a removable chip", async () => {
      await tab("cust");
      await page.click("#cust [data-a=filt]");
      await page.click('.ov.on [data-fv="amt|1"]');
      const label = await page.locator(".ov.on #fgo").textContent();
      if (!/Show 2 customers/.test(label)) throw new Error("button: " + label);
      await page.click(".ov.on #fgo"); await gone(".ov .fh");
      const names = await page.locator("#cust .list").textContent();
      if (!names.includes("Iya Bisi") || !names.includes("Oga Emeka") || names.includes("Mama Ngozi")) throw new Error(names);
      await page.click("#cust .fx"); await page.waitForFunction(() => /Mama Ngozi/.test(document.querySelector("#cust .list")?.textContent || ""));
    });
    await check("Customers filter: 'Last activity: Today' knows when each customer was last active (from the server)", async () => {
      await page.click("#cust [data-a=filt]");
      await page.click('.ov.on [data-fv="act|today"]');
      const label = await page.locator(".ov.on #fgo").textContent();
      if (!/Show 3 customers/.test(label)) throw new Error("button: " + label);
      await page.click('.ov.on [data-fv="reset"]'); await page.click(".ov.on #fgo"); await gone(".ov .fh");
      await tab("me");
    });
    await check("online: the design's 'Offline. Saved, will send later' banner is hidden", async () =>
      page.evaluate(() => { const o = document.querySelector("#off"); return !o || getComputedStyle(o).display === "none"; }));
    await check("Me: no 'Connect my WhatsApp' while the bot is off (and no Telegram row without a Telegram bot)", async () => {
      return !(await page.locator('#me [data-a=wac]').count()) && !(await page.locator('#me [data-a=tgc]').count());
    });

    /* ------------------------------------------------------------ password change */
    await page.click('#me [data-a=pw]');
    await page.fill(".ov.on #cp", "WrongPass123"); await page.fill(".ov.on #pw", PW2); await page.fill(".ov.on #pw2", PW2);
    await page.click(".ov.on #pgo");
    await check("password: a wrong current password is refused", async () => {
      await page.waitForFunction(() => /isn't your current/.test(document.querySelector(".ov.on #cp-e")?.textContent || ""));
      return true;
    });
    await page.fill(".ov.on #cp", PW1); await page.click(".ov.on #pgo");
    await check("password: changed", async () => {
      await page.waitForFunction(() => /Password changed/.test(document.querySelector(".toast")?.textContent || ""));
      return true;
    });

    /* ------------------------------------------------------------ log out and back in */
    await page.click('#me [data-a=logout]');
    await page.click(".ov.on #y");
    await check("log out: back to the login screen, server session ended", async () => {
      await page.waitForSelector("#gate #lp");
      return !(await page.evaluate(async () => (await fetch("/api/v2/me")).ok));
    });
    await page.fill("#id", PHONE); await page.fill("#lp", PW1); await page.click("#go");
    await check("log in: the old password no longer works", async () => {
      await page.waitForFunction(() => /isn't right/.test(document.querySelector("#lp-e")?.textContent || ""));
      return true;
    });
    await page.fill("#lp", PW2); await page.click("#go");
    await check("log in: the new password works, the book is still there", async () => {
      await gone("#gate");
      await tab("cust");
      await page.waitForFunction(() => document.querySelectorAll("#cust .row").length >= 2);
      const t = await page.locator("#cust").textContent();
      if (!t.includes("Iya Bisi") || !t.includes("45,000")) throw new Error(t.slice(0, 200));
    });
    await check("reload: still logged in ('Keep me logged in')", async () => {
      await page.reload({ waitUntil: "domcontentloaded" });
      await page.waitForFunction(() => window.TVL && TVL.A && !document.querySelector("#gate"), null, { timeout: 8000 });
      return true;
    });

    /* ------------------------------------------------------------ a team-created account (no WhatsApp code) */
    const made = require("child_process").spawnSync(process.env.PYTHON || "python",
      ["scripts/add_account.py", "08030000533", "Kemi Testtrader", "Kemi Test Stores"],
      { cwd: ROOT, encoding: "utf8", env: Object.assign({}, process.env, { TV_NO_DOTENV: "1",
        ACCOUNTS_DB: path.join(TMP, "accounts.db"), BOOKS_DIR: path.join(TMP, "books"), DB_PATH: path.join(TMP, "tradevoice.db") }) });
    const temp = ((made.stdout || "").match(/^\s{4}(\S+)$/m) || [])[1];
    await check("team account: made with a temporary password", async () => { if (!temp) throw new Error(made.stdout + made.stderr); });
    await page.click('#tabs [data-k=me]'); await page.click('#me [data-a=logout]'); await page.click(".ov.on #y");
    await page.waitForSelector("#gate #lp");
    await page.fill("#id", "08030000533"); await page.fill("#lp", temp || "x"); await page.click("#go");
    await check("team account: logs in through the real login page; No to the improve question is saved", async () => {
      await gone("#gate");
      await page.waitForSelector(".ov.on #tn", { timeout: 15000 });
      await page.click(".ov.on #tn");
      await page.waitForFunction(() => [...document.querySelectorAll(".toast")].some(t => /We keep nothing/.test(t.textContent)), null, { timeout: 5000 });
      const me = await page.evaluate(() => fetch("/api/v2/me").then(r => r.json()));
      if (me.train !== false) throw new Error(JSON.stringify(me.train));
      await gone(".ov.on");
      await tab("me");
      const t = await page.locator("#me .pcard").textContent();
      if (!t.includes("Kemi Test Stores")) throw new Error(t);
    });

    /* ------------------------------------------------------------ sign-up when WhatsApp can't send the code */
    await check("sign-up without a code: 'Send it on WhatsApp' opens LOGIN <word> to the bot, the page carries on by itself", async () => {
      const c2 = await browser.newContext({ viewport: { width: 390, height: 844 }, locale: "en-NG" });
      await c2.route(/fonts\.(googleapis|gstatic)\.com/, r => r.abort());
      let polls = 0;   // a real server answers these when WhatsApp is set up; here they are played back
      await c2.route(/\/api\/auth\/v2\/code\/start$/, r => r.fulfill({ json: { login_id: "lid-wa", sent: false, demo_code: null, word: "MANGO-123", bot: "2348000000999" } }));
      await c2.route(/\/api\/auth\/v2\/code\/poll$/, r => { polls++; r.fulfill({ json: { ok: polls >= 2 } }); });
      const p2 = await c2.newPage();
      p2.on("pageerror", e => errors.push(e.message));
      await p2.goto(`${BASE}/app`);
      await p2.click("#gate [data-g=signup]");
      await p2.fill("#ph", "8030000777"); await p2.check("#ag"); await p2.click("#go");
      const a = p2.locator("#wa");
      await a.waitFor({ timeout: 8000 });
      const href = await a.getAttribute("href");
      if (href !== "https://wa.me/2348000000999?text=LOGIN%20MANGO-123") throw new Error(href);
      if (await p2.locator("#otp").count()) throw new Error("a code box although no code was sent");
      if (!/LOGIN MANGO-123/.test(await p2.locator("#gate").textContent())) throw new Error("the words to send are not shown");
      await p2.waitForSelector("#pgo", { timeout: 10000 });   // confirmed by WhatsApp: on to choosing a password
      await c2.close();
    });

    /* ------------------------------------------------------------ which ways in work (window.TV_CH, src/v2.py channels()) */
    const withCH = async (ctx, ch) => {   // the same server, but the page is told another set of channels
      for (const pathRe of [/\/app$/, /:\d+\/$/]) await ctx.route(pathRe, async r => {
        const res = await r.fetch(); const b = (await res.text()).replace(/window\.TV_CH=\{[^<]*\}/, "window.TV_CH=" + JSON.stringify(ch));
        await r.fulfill({ response: res, body: b });
      });
    };
    const NONE = { codes: "", wa: false, sms: false, tg: "", nocode: true, team: "privacy@example.com" };
    await check("no WhatsApp, no SMS: sign-up is number + password, no code screen; no 'log in with a code'; forgot password says ask the team", async () => {
      const c3 = await browser.newContext({ viewport: { width: 390, height: 844 }, locale: "en-NG" });
      await c3.route(/fonts\.(googleapis|gstatic)\.com/, r => r.abort());
      await withCH(c3, NONE);
      await c3.route(/\/api\/auth\/v2\/code\/start$/, r => r.fulfill({ json: { login_id: "lid-nocode", nocode: true, sent: false, demo_code: null, word: null, bot: null, channel: "" } }));
      const p3 = await c3.newPage();
      p3.on("pageerror", e => errors.push(e.message));
      await p3.goto(`${BASE}/app`);
      await p3.waitForSelector("#gate [data-g=signup]");
      if (!/A phone number and a password/.test(await p3.locator("#gate").textContent())) throw new Error("welcome still promises a code");
      await p3.click("#gate [data-g=login]");
      if (await p3.locator("[data-g=otpin]").count()) throw new Error("'log in with a code' shown with nothing to send it");
      await p3.click("[data-g=forgot]");
      const f = await p3.locator("#gate").textContent();
      if (!/Ask the TradeVoice team/.test(f) || !(await p3.locator('#gate a[href="mailto:privacy@example.com"]').count())) throw new Error(f);
      await p3.click("#gate [data-g=login]"); await p3.click("[data-g=signup]");
      const t = await p3.locator("#gate").textContent();
      if (/WhatsApp/.test(t) || !/It is how you log in/.test(t)) throw new Error(t);
      await p3.fill("#ph", "8030000778"); await p3.check("#ag"); await p3.click("#go");
      await p3.waitForSelector("#pgo", { timeout: 8000 });   // straight on to choosing a password
      if (await p3.locator("#otp").count()) throw new Error("a code box although sign-up needs no code");
      await c3.close();
    });
    await check("SMS codes: the code screen says 'by SMS', with the code box", async () => {
      const c4 = await browser.newContext({ viewport: { width: 390, height: 844 }, locale: "en-NG" });
      await c4.route(/fonts\.(googleapis|gstatic)\.com/, r => r.abort());
      await withCH(c4, { ...NONE, codes: "sms", sms: true, nocode: false });
      await c4.route(/\/api\/auth\/v2\/code\/start$/, r => r.fulfill({ json: { login_id: "lid-sms", sent: true, demo_code: null, word: null, bot: null, channel: "sms" } }));
      const p4 = await c4.newPage();
      p4.on("pageerror", e => errors.push(e.message));
      await p4.goto(`${BASE}/app`);
      await p4.click("#gate [data-g=signup]");
      await p4.fill("#ph", "8030000779"); await p4.check("#ag"); await p4.click("#go");
      await p4.waitForSelector("#otp", { timeout: 8000 });
      const t = await p4.locator("#gate").textContent();
      if (!/by SMS to/.test(t) || !/Check your phone/.test(t)) throw new Error(t);
      await c4.close();
    });
    await check("Phone-call codes (Termii voice): the code screen says we are calling, with the code box", async () => {
      const c5 = await browser.newContext({ viewport: { width: 390, height: 844 }, locale: "en-NG" });
      await c5.route(/fonts\.(googleapis|gstatic)\.com/, r => r.abort());
      await withCH(c5, { ...NONE, codes: "sms", sms: true, nocode: false });
      await c5.route(/\/api\/auth\/v2\/code\/start$/, r => r.fulfill({ json: { login_id: "lid-call", sent: true, demo_code: null, word: null, bot: null, channel: "call" } }));
      const p5 = await c5.newPage();
      p5.on("pageerror", e => errors.push(e.message));
      await p5.goto(`${BASE}/app`);
      await p5.click("#gate [data-g=signup]");
      await p5.fill("#ph", "8030000780"); await p5.check("#ag"); await p5.click("#go");
      await p5.waitForSelector("#otp", { timeout: 8000 });
      const t = await p5.locator("#gate").textContent();
      if (!/We are calling/.test(t) || !/read out your 6-digit code/.test(t)) throw new Error(t);
      await c5.close();
    });
    await check("Telegram users: 'Confirm on Telegram' opens the bot with the login word; the page carries on by itself", async () => {
      const c6 = await browser.newContext({ viewport: { width: 390, height: 844 }, locale: "en-NG" });
      await c6.route(/fonts\.(googleapis|gstatic)\.com/, r => r.abort());
      await withCH(c6, { ...NONE, tg: "TradeVoiceTestBot", nocode: false });
      let polls = 0;
      await c6.route(/\/api\/auth\/v2\/code\/start$/, r => r.fulfill({ json: { login_id: "lid-tg", sent: false, demo_code: null, word: "MANGO-123", bot: null, tg: "TradeVoiceTestBot", channel: "" } }));
      await c6.route(/\/api\/auth\/v2\/code\/poll$/, r => { polls++; r.fulfill({ json: { ok: polls >= 2 } }); });
      const p6 = await c6.newPage();
      p6.on("pageerror", e => errors.push(e.message));
      await p6.goto(`${BASE}/app`);
      await p6.click("#gate [data-g=signup]");
      await p6.fill("#ph", "8030000780"); await p6.check("#ag"); await p6.click("#go");
      const a = p6.locator("#tgo");
      await a.waitFor({ timeout: 8000 });
      const href = await a.getAttribute("href");
      if (href !== "https://t.me/TradeVoiceTestBot?start=login-MANGO-123") throw new Error(href);
      if (await p6.locator("#otp").count()) throw new Error("a code box although no code was sent");
      await p6.waitForSelector("#pgo", { timeout: 10000 });   // confirmed in Telegram: on to choosing a password
      await c6.close();
    });
    await check("website without WhatsApp: 'Open the app' first, 'Use on Telegram' second, no blank wa.me links, FAQ honest", async () => {
      const c5 = await browser.newContext({ viewport: { width: 390, height: 844 }, locale: "en-NG" });
      await c5.route(/fonts\.(googleapis|gstatic)\.com/, r => r.abort());
      await withCH(c5, { ...NONE, tg: "TradeVoiceTestBot" });
      const p5 = await c5.newPage();
      p5.on("pageerror", e => errors.push(e.message));
      await p5.goto(`${BASE}/`);
      await p5.waitForFunction(() => !document.querySelector('a[href^="https://wa.me/"]'));
      const hero = await p5.$$eval(".cta", cs => cs.map(c => [...c.querySelectorAll("a")].map(a => [a.textContent, a.getAttribute("href"), a.classList.contains("p")])));
      const first = hero[0];
      if (first[0][0] !== "Open the app" || !first[0][2] || first[1][0] !== "Use on Telegram" || first[1][1] !== "https://t.me/TradeVoiceTestBot") throw new Error(JSON.stringify(hero));
      const faq = await p5.locator("#faq").textContent();
      if (/WhatsApp number, a 6-digit code/.test(faq) || /through WhatsApp/.test(faq)) throw new Error(faq.slice(0, 400));
      await c5.close();
    });

    /* ------------------------------------------------------------ the team's live dashboard (this run's own actions) */
    await check("team dashboard: with the key, today's numbers, this run's actions live, and what the 'yes' trader said", async () => {
      await page.goto(`${BASE}/team?key=browser-team-key`);
      await page.waitForSelector("#kpis .tile.hero", { timeout: 10000 });
      await page.waitForFunction(() => /New trader signed up/.test(document.querySelector("#feed").textContent)
        && /Saved a record/.test(document.querySelector("#feed").textContent), null, { timeout: 10000 });
      await page.waitForFunction(() => document.querySelectorAll("#convos .cv").length > 0, null, { timeout: 10000 });
      const said = await page.locator("#convos").textContent();
      if (!/They said/.test(said) || !/TradeVoice replied/.test(said)) throw new Error(said.slice(0, 200));
      const sw = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
      if (sw > 0) throw new Error("sideways scroll " + sw);
      const r = await page.evaluate(() => fetch("/team/api/feed").then(r => r.status));
      if (r !== 403) throw new Error("data without the key: " + r);
    });

    /* ------------------------------------------------------------ the whole run */
    await check("no page errors", async () => { if (errors.length) throw new Error(errors.slice(0, 3).join(" | ")); });
    await check("no server errors (5xx)", async () => { if (bad.length) throw new Error(bad.slice(0, 3).join(" | ")); });
  } catch (e) {
    failed.push("run stopped: " + e.message.split("\n")[0]);
    console.log("✗ run stopped:", e.message.split("\n")[0]);
    try { await page.screenshot({ path: path.join(SHOTS, "stopped.png") }); } catch (_) {}
  } finally {
    if (browser) await browser.close();
    server.kill();
  }
  console.log(`\n${passed}/${passed + failed.length} browser checks pass${todos.length ? `, ${todos.length} designer to-do` : ""}   ${failed.length ? `(screenshots + server log: ${TMP})` : ""}`);
  if (!failed.length && !process.env.SHOT_ALL) fs.rmSync(TMP, { recursive: true, force: true });   // kept on failure (or SHOT_ALL=1)
  process.exit(failed.length ? 1 : 0);
})();
