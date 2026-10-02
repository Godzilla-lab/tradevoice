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
    INTRON_API_KEY: "",
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

    /* ------------------------------------------------------------ Ask */
    await tab("ask");
    const ans = async q => { await page.click(`#ask [data-q=${q}]`); return (await page.locator("#out .ans").textContent()).replace(/\s+/g, " "); };
    await check("Ask: who owes the most → Iya Bisi ₦45,000", async () => {
      const a = await ans("owe"); if (!/45,000/.test(a) || !/Iya Bisi/.test(a)) throw new Error(a);
    });
    await check("Ask: total owed → ₦70,000", async () => {
      const a = await ans("total"); if (!/70,000/.test(a)) throw new Error(a);
    });
    await check("Ask: who is late → nobody", async () => {
      const a = await ans("late"); if (!/Nobody is late/.test(a)) throw new Error(a);
    });
    await check("Ask: money in today matches the book", async () => {
      bk = await book(); const a = await ans("sold");
      if (!a.includes(naira(bk.in))) throw new Error(`${a} vs book ${bk.in}`);
    });
    await check("Ask: typed 'who is late' answers on the phone", async () => {
      await page.fill("#aq", "who is late"); await page.press("#aq", "Enter");
      const a = (await page.locator("#out .ans").textContent()).replace(/\s+/g, " ");
      if (!/Nobody is late/.test(a)) throw new Error(a);
    });
    await check("Ask: a free question goes to the brain and comes back with the right number", async () => {
      await page.fill("#aq", "How much does Oga Emeka owe me?"); await page.press("#aq", "Enter");
      await page.waitForFunction(() => document.querySelector("#out .ans") && !document.querySelector("#out .wave"), null, { timeout: 30000 });
      const a = (await page.locator("#out .ans").textContent()).replace(/\s+/g, " ");
      if (!/25,000/.test(a)) throw new Error(a);
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
    await check("Me: Connect my WhatsApp says it's coming", async () => {
      await page.click('#me [data-a=wac]'); return /bot/.test(await toastText());
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
    await check("team account: logs in through the real login page", async () => {
      await gone("#gate");
      await tab("me");
      const t = await page.locator("#me .pcard").textContent();
      if (!t.includes("Kemi Test Stores")) throw new Error(t);
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
  if (!failed.length) fs.rmSync(TMP, { recursive: true, force: true });   // keep the screenshots + server log only on failure
  process.exit(failed.length ? 1 : 0);
})();
