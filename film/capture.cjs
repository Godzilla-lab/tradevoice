/* The real app screens for the film: the app runs here (no keys, a made-up trader and customers), records are saved
   through the real server, and each screen is captured at 3x (390x844 -> 1170x2532) into film/shots/.
   Only what can't run here is fed in, the same way eval/browser_test.cjs does it: the words live talk hears (Intron's
   stream), a silent reply voice, and the lines a photo gives (the vision model). The rest is the real app.
   Run: NODE_PATH=$(npm root -g) node film/capture.cjs
*/
const fs = require("fs"), os = require("os"), path = require("path");
const { spawn } = require("child_process");
const { chromium } = require("playwright");

const ROOT = path.join(__dirname, "..");
const OUT = path.join(__dirname, "shots");
const PORT = +(process.env.PORT || 8791), BASE = `http://127.0.0.1:${PORT}`;
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), "tv-film-"));
const PHONE = "8030000417", PW = "Market2026x";            // made up
const NAME = "Kemi Adebayo", BIZ = "Kemi Foodstuff";        // made up
const SAID = "Iya Bisi took 2 bags of rice for 60000, she will pay Friday";
const sleep = ms => new Promise(r => setTimeout(r, ms));
fs.mkdirSync(OUT, { recursive: true });

function wavSilence(sec = 0.4, rate = 16000) {
  const n = Math.round(sec * rate), b = Buffer.alloc(44 + n * 2);
  b.write("RIFF", 0); b.writeUInt32LE(36 + n * 2, 4); b.write("WAVEfmt ", 8); b.writeUInt32LE(16, 16); b.writeUInt16LE(1, 20);
  b.writeUInt16LE(1, 22); b.writeUInt32LE(rate, 24); b.writeUInt32LE(rate * 2, 28); b.writeUInt16LE(2, 32); b.writeUInt16LE(16, 34);
  b.write("data", 36); b.writeUInt32LE(n * 2, 40); return b;
}

(async () => {
  const env = Object.assign({}, process.env, {
    AUTH_DEMO: "1", ACCOUNTS_DB: path.join(TMP, "accounts.db"), BOOKS_DIR: path.join(TMP, "books"),
    DB_PATH: path.join(TMP, "tradevoice.db"), PORT: String(PORT), TRADEVOICE_ADMIN: "0", AUTO_REMINDERS: "0",
    NATLAS_URL: "", NATLAS_ASR_URL: "", NVIDIA_API_KEY: "", LOCAL_LLM_URL: "", WHATSAPP_TOKEN: "", PAYSTACK_SECRET_KEY: "",
    INTRON_API_KEY: "", TELEGRAM_BOT_TOKEN: "", ADMIN_TOKEN: "film-team-key",
  });
  const server = spawn(process.env.PYTHON || "python", ["src/web.py"], { cwd: ROOT, env, stdio: ["ignore", "pipe", "pipe"] });
  const log = fs.createWriteStream(path.join(TMP, "server.log")); server.stdout.pipe(log); server.stderr.pipe(log);
  let browser;
  const boxes = {};
  try {
    for (let i = 0; i < 120; i++) { try { if ((await fetch(BASE + "/api/status")).ok) break; } catch (_) {} await sleep(500); }
    browser = await chromium.launch({ args: ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"] });
    const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 3, locale: "en-NG",
      colorScheme: "light", permissions: ["microphone"], isMobile: true, hasTouch: true });
    const page = await ctx.newPage();
    let wsFake = null;
    await page.routeWebSocket(/\/api\/live\/hear/, ws => (wsFake ? wsFake(ws) : ws.connectToServer()));
    page.on("pageerror", e => console.log("page error:", e.message));

    const still = async () => {   // every animation stopped where it is: a clean, sharp still
      await page.evaluate(async () => { await document.fonts.ready; document.getAnimations().forEach(a => { try { a.pause(); } catch (e) {} }); });
      await sleep(150);
    };
    const shot = async (name, sel, keepToast) => {
      await page.evaluate(k => { document.querySelectorAll(".wab").forEach(x => x.remove());   // the demo code banner
        if (!k) document.querySelectorAll(".toast").forEach(x => x.remove()); }, !!keepToast);
      await still();
      const file = path.join(OUT, name + ".png");
      if (sel) await page.locator(sel).last().screenshot({ path: file, animations: "disabled" });
      else await page.screenshot({ path: file });
      const box = sel ? await page.locator(sel).last().boundingBox() : null;
      if (box) boxes[name] = box;
      console.log("captured", name + ".png", sel ? `(${sel})` : "");
    };
    const play = () => page.evaluate(() => document.getAnimations().forEach(a => { try { a.play(); } catch (e) {} }));
    const box = async (name, sel) => { boxes[name] = await page.locator(sel).last().boundingBox(); };
    const say = text => page.evaluate(async t => {
      const post = b => fetch("/api/message", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(Object.assign({ session: "film", lang: "English" }, b)) }).then(r => r.json());
      const a = await post({ text: t });
      if (a.pending) await post({ text: "yes" });
      return a;
    }, text);
    const tab = async k => { await page.click(`#tabs [data-k=${k}]`); await page.waitForSelector(`#${k}.on`); await sleep(400); };
    const closeSheets = () => page.evaluate(() => document.querySelectorAll(".ov").forEach(o => o.remove()));

    /* sign up, the way a trader does */
    await page.goto(BASE + "/app", { waitUntil: "networkidle" });
    await page.waitForSelector("#gate [data-g=signup]");
    await shot("welcome");
    await page.click("#gate [data-g=signup]");
    await page.fill("#ph", PHONE); await page.check("#ag");
    const codeResp = page.waitForResponse(r => r.url().endsWith("/api/auth/v2/code/start"));
    await page.click("#go");
    const code = (await (await codeResp).json()).demo_code;
    if (code) { await page.fill("#otp", code); }
    await page.waitForSelector("#pgo");
    await page.fill("#pw", PW); await page.fill("#pw2", PW); await page.click("#pgo");
    await page.waitForSelector("#bn");
    await page.fill("#on", NAME); await page.fill("#bn", BIZ);
    await page.locator("[data-ty]").first().click();
    await page.fill("#mk", "Balogun Market");
    await page.click("#go");
    await page.waitForSelector(".ov.on #tn", { timeout: 15000 });
    await page.click(".ov.on #tn");
    await sleep(800); await closeSheets();

    /* the book: saved through the real server (the rules read these sentences; no AI here) */
    for (const s of ["Mama Ngozi took 3 crates of eggs for 13500 on credit",
                     "Oga Emeka bought goods on credit 25000", "Oga Emeka paid 10000",
                     "Madam Funke took garri 9000 on credit, she will pay Saturday",
                     "Alhaji Musa took indomie 18500 on credit",
                     "I sold 5 bags of rice for 75000", "I sold beans for 6000", "I spent 2000 on transport"]) {
      const r = await say(s);
      if (!r.pending && !r.saved) console.log("not understood:", s, JSON.stringify(r).slice(0, 120));
    }
    await page.evaluate(() => TVL.loadBook());
    await tab("home"); await shot("home_before");

    /* live talk: Intron's stream is fed the sentence; the real server makes the draft */
    const wav = wavSilence();
    await page.route("**/api/warm", r => r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ live: true }) }));
    await page.route(/\/api\/speak\/.*/, r => r.fulfill({ status: 200, contentType: "audio/wav", body: wav }));
    let turn = 0; const said = [SAID];
    wsFake = ws => {
      let told = false;
      ws.onMessage(m => {
        if (typeof m != "string") { if (!told) { told = true; ws.send(JSON.stringify({ type: "partial", text: (said[turn] || "").split(" ").slice(0, 3).join(" ") })); } return; }
        if (JSON.parse(m).type == "commit") ws.send(JSON.stringify({ type: "final", text: turn++ ? "" : SAID }));   // only the first turn speaks
      });
    };
    await page.click("#tabs [data-a=talk]");
    await page.waitForSelector(".ov.on .tvc[data-st=listen]");
    await sleep(1200);
    await page.evaluate(() => { const c = document.querySelector(".ov.on #cap"); window.__cap = c.innerHTML; c.innerHTML = "&nbsp;"; document.querySelector(".ov.on #hint").textContent = ""; });
    await shot("talk_listen");
    await page.addStyleTag({ content: ".tvc-orb{visibility:hidden}" });
    await shot("talk_listen_noorb");
    await box("orb", ".ov.on .tvc-stage"); await box("cap", ".ov.on #cap"); await box("sheet", ".ov.on .in"); await box("pill", ".ov.on .tvc-pill");
    await page.addStyleTag({ content: ".tvc-orb{visibility:visible}" });
    await play();
    await page.waitForSelector(".ov.on .tvc[data-st=listen]"); await sleep(700);
    await page.click(".ov.on #orb");                                       // she stops: the final words go to the server
    await page.waitForFunction(() => /60,000 · Iya Bisi/.test(document.querySelector(".ov.on #cap")?.textContent || ""), null, { timeout: 15000 });
    await sleep(500);
    await shot("talk_pending");
    await page.addStyleTag({ content: ".tvc-orb{visibility:hidden}" });
    await shot("talk_pending_noorb");
    await box("cap_pending", ".ov.on #cap"); await box("hint_pending", ".ov.on #hint");
    await page.addStyleTag({ content: ".tvc-orb{visibility:visible}" });
    await play();

    /* tap the words: the check card, from the real draft */
    await page.click(".ov.on #cap");
    await page.waitForSelector(".ov.on .card", { timeout: 10000 }); await sleep(700);
    await shot("card");
    await shot("card_sheet", ".ov.on .in");
    await box("card_save", ".ov.on [data-s=save]");
    await play();
    await page.click(".ov.on [data-s=save]");
    await page.waitForSelector(".toast", { timeout: 8000 }); await sleep(600);
    await shot("saved", null, true);
    await shot("saved_toast", ".toast", true);
    await page.evaluate(() => TVL.loadBook());
    await sleep(6500);   // the toast goes
    await tab("home"); await shot("home");
    await box("home_collect", "#home h2");

    /* the customer and the reminder draft */
    await tab("cust"); await shot("customers");
    await page.locator("#cust .row", { hasText: "Iya Bisi" }).click();
    await page.waitForSelector("#det.on"); await sleep(600); await shot("customer");
    await page.click("#det [data-a=remind]");
    await page.waitForSelector(".ov.on #mg", { timeout: 8000 }); await sleep(700);
    await shot("reminder"); await shot("reminder_sheet", ".ov.on .in");
    await page.keyboard.press("Escape"); await closeSheets();
    await page.evaluate(() => { const d = document.querySelector("#det.on [data-a=back]") || document.querySelector("#det.on .back"); if (d) d.click(); });

    /* scan a notebook page: the vision model's lines are fed in (the photo itself is the film's notebook page) */
    await page.route("**/api/photo", r => r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ rows: [
      { save: true, type: "credit_sale", amount: 13500, customer: "Mama Ngozi", item: "eggs", line: "Mama Ngozi 3 crates eggs 13,500 credit" },
      { save: true, type: "payment_received", amount: 10000, customer: "Oga Emeka", item: "", line: "Oga Emeka paid 10,000" },
      { save: true, type: "expense", amount: 2000, customer: null, item: "Transport", line: "Transport 2,000" },
      { save: false, type: "credit_sale", amount: null, customer: "Iya Bisi", item: "beans", line: "Iya Bisi beans ?" }] }) }));
    await tab("home");
    await page.click("#home [data-a=scan]");
    await page.waitForSelector(".ov.on #pf", { state: "attached" }); await sleep(500);
    await shot("scan_start");
    const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==", "base64");
    await page.setInputFiles(".ov.on #pf", { name: "page.png", mimeType: "image/png", buffer: PNG });
    await page.waitForSelector(".ov.on .ln", { timeout: 10000 }); await sleep(700);
    await shot("scan"); await shot("scan_sheet", ".ov.on .in");
    boxes.scan_rows = await page.$$eval(".ov.on .ln", els => els.map(e => { const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height }; }));
    fs.writeFileSync(path.join(OUT, "boxes.json"), JSON.stringify(boxes, null, 1));
    console.log("boxes:", Object.keys(boxes).join(", "));
  } finally {
    if (browser) await browser.close();
    server.kill();
  }
})().catch(e => { console.error(e); process.exit(1); });
