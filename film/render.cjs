/* Renders the film: serves film/ locally, opens film.html in Chromium (Playwright), calls seek(t) for each frame and
   screenshots it. Frames go to film/out/frames/, then ffmpeg makes the MP4 (and adds film/out/mix.wav when it exists).
     NODE_PATH=$(npm root -g) node film/render.cjs --info                 timing, shots, cues -> film/out/film.json
     NODE_PATH=$(npm root -g) node film/render.cjs --stills 1,5.5,12      PNG stills -> film/out/stills/
     NODE_PATH=$(npm root -g) node film/render.cjs --sheet 30             a contact sheet of 30 moments
     NODE_PATH=$(npm root -g) node film/render.cjs --video [--fps 120]    the film (120 = rendered at 120, blended to 60:
                                                                           real motion blur on fast moves)
   Data put into the page: the app's live-talk CSS (from web/live.js), the lines (lines.json), the voice clips chosen
   (voices/chosen.json, from sound.py --voices), the layer positions (shots/layers.json), market footage frames.
*/
const fs = require("fs"), path = require("path"), http = require("http");
const { execFileSync, spawnSync } = require("child_process");
const { chromium } = require("playwright");

const HERE = __dirname, OUT = path.join(HERE, "out");
const arg = (k, d) => { const i = process.argv.indexOf(k); return i < 0 ? d : (process.argv[i + 1] && !process.argv[i + 1].startsWith("--") ? process.argv[i + 1] : true); };
fs.mkdirSync(OUT, { recursive: true });

function filmData() {
  const live = fs.readFileSync(path.join(HERE, "..", "web", "live.js"), "utf8");
  const m = live.match(/const ORB_CSS = `([\s\S]*?)`;/);
  if (!m) throw new Error("ORB_CSS not found in web/live.js");
  const lines = {};
  for (const l of JSON.parse(fs.readFileSync(path.join(HERE, "lines.json"), "utf8")).lines) lines[l.id] = { text: l.text, subtitle: l.subtitle, language: l.language };
  const read = f => fs.existsSync(f) ? JSON.parse(fs.readFileSync(f, "utf8")) : null;
  const data = { orbCss: m[1], lines, layers: read(path.join(HERE, "shots", "layers.json")) || {} };
  const chosen = read(path.join(HERE, "voices", "chosen.json"));
  if (chosen) data.voices = chosen;
  const open = path.join(HERE, "assets", "frames", "open");
  if (fs.existsSync(open)) { const n = fs.readdirSync(open).filter(f => f.endsWith(".jpg")).length; if (n) data.openFrames = { dir: "assets/frames/open", count: n, fps: 60 }; }
  return data;
}

function serve() {
  const types = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".png": "image/png", ".jpg": "image/jpeg", ".woff2": "font/woff2", ".json": "application/json", ".svg": "image/svg+xml" };
  const srv = http.createServer((req, res) => {
    const p = path.join(HERE, decodeURIComponent(req.url.split("?")[0]));
    if (!p.startsWith(HERE) || !fs.existsSync(p) || fs.statSync(p).isDirectory()) { res.writeHead(404); return res.end(); }
    res.writeHead(200, { "Content-Type": types[path.extname(p)] || "application/octet-stream", "Cache-Control": "max-age=3600" });
    fs.createReadStream(p).pipe(res);
  });
  return new Promise(r => srv.listen(0, "127.0.0.1", () => r(srv)));
}

async function openPage(browser, port, data) {
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
  page.on("pageerror", e => console.log("page error:", e.message));
  page.on("console", m => { if (m.type() === "error") console.log("console:", m.text()); });
  await page.addInitScript(d => { window.FILMDATA = d; }, data);
  await page.goto(`http://127.0.0.1:${port}/film.html`);
  await page.waitForFunction(() => window.FILM_READY === true, null, { timeout: 60000 });
  await page.evaluate(async () => { await Promise.all([...document.images].map(i => i.decode().catch(() => {}))); });
  return page;
}

async function frameAt(page, t, file, type = "png") {
  await page.evaluate(async t => { window.seek(t); await Promise.all([...document.images].filter(i => !i.complete).map(i => i.decode().catch(() => {}))); }, t);
  await page.screenshot({ path: file, type, quality: type === "jpeg" ? 94 : undefined, animations: "allow" });
}

(async () => {
  const data = filmData(), srv = await serve(), port = srv.address().port;
  const browser = await chromium.launch({ args: ["--disable-gpu-vsync", "--font-render-hinting=none"] });
  try {
    const page = await openPage(browser, port, data);
    const film = await page.evaluate(() => window.FILM);
    fs.writeFileSync(path.join(OUT, "film.json"), JSON.stringify(film, null, 1));
    console.log(`film: ${film.duration.toFixed(2)} s, ${film.shots.length} shots, ${film.cues.length} sound cues` +
      (film.estimates.length ? ` (voice lengths estimated for: ${film.estimates.join(", ")})` : ""));
    for (const s of film.shots) console.log(`  ${s.id.padEnd(9)} ${s.start.toFixed(2).padStart(6)} - ${s.end.toFixed(2).padStart(6)}  (${s.bars} bars)`);
    if (arg("--info")) return;

    if (arg("--stills") || arg("--sheet")) {
      const dir = path.join(OUT, "stills"); fs.mkdirSync(dir, { recursive: true });
      let times;
      if (arg("--stills")) times = String(arg("--stills")).split(",").map(Number);
      else { const n = +arg("--sheet") || 30; times = Array.from({ length: n }, (_, i) => +(0.2 + i * (film.duration - 0.4) / (n - 1)).toFixed(2)); }
      const files = [];
      for (const t of times) { const f = path.join(dir, `t${t.toFixed(2).padStart(6, "0")}.png`); await frameAt(page, t, f); files.push(f); }
      console.log(`${files.length} stills in ${dir}`);
      if (arg("--sheet")) {
        const sheet = path.join(OUT, "sheet.jpg"), cols = 5;
        const inputs = files.flatMap(f => ["-i", f]);
        const fl = files.map((_, i) => `[${i}:v]scale=384:-1,drawtext=text='${times[i].toFixed(1)}s':x=8:y=8:fontsize=18:fontcolor=white:box=1:boxcolor=black@0.5[v${i}]`).join(";");
        const layout = files.map((_, i) => `${(i % cols) * 384}_${Math.floor(i / cols) * 216}`).join("|");
        spawnSync("ffmpeg", ["-y", "-loglevel", "error", ...inputs, "-filter_complex", `${fl};${files.map((_, i) => `[v${i}]`).join("")}xstack=inputs=${files.length}:layout=${layout}:fill=black`, "-q:v", "3", sheet], { stdio: "inherit" });
        console.log("sheet:", sheet);
      }
      return;
    }

    if (arg("--video")) {
      const fps = +arg("--fps", 60) || 60, n = Math.ceil(film.duration * fps), workers = +arg("--workers", 4) || 4;
      const dir = path.join(OUT, "frames"); fs.rmSync(dir, { recursive: true, force: true }); fs.mkdirSync(dir, { recursive: true });
      const pages = [page]; for (let i = 1; i < workers; i++) pages.push(await openPage(browser, port, data));
      const per = Math.ceil(n / workers), t0 = Date.now(); let done = 0;
      await Promise.all(pages.map(async (p, w) => {
        for (let f = w * per; f < Math.min(n, (w + 1) * per); f++) {
          await frameAt(p, f / fps, path.join(dir, `${String(f).padStart(6, "0")}.jpg`), "jpeg");
          if (++done % 200 === 0) console.log(`  ${done}/${n} frames (${((Date.now() - t0) / done * (n - done) / 1000).toFixed(0)} s left)`);
        }
      }));
      console.log(`frames: ${n} in ${((Date.now() - t0) / 1000).toFixed(0)} s`);
      const mix = path.join(OUT, "mix.wav"), out = path.join(OUT, "TradeVoice-film.mp4");
      const vf = (fps === 120 ? "tmix=frames=2:weights='1 1',fps=60," : "") + "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p";
      const a = ["-y", "-loglevel", "error", "-framerate", String(fps), "-i", path.join(dir, "%06d.jpg")];
      if (fs.existsSync(mix)) a.push("-i", mix);
      a.push("-vf", vf, "-c:v", "libx264", "-profile:v", "high", "-preset", "slow", "-crf", "16", "-g", "30", "-bf", "2", "-flags", "+cgop",
        "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-movflags", "+faststart");
      if (fs.existsSync(mix)) a.push("-c:a", "aac", "-b:a", "384k", "-ar", "48000", "-shortest");
      a.push("-t", film.duration.toFixed(3), out);
      execFileSync("ffmpeg", a, { stdio: "inherit" });
      console.log("video:", out);
    }
  } finally {
    await browser.close(); srv.close();
  }
})().catch(e => { console.error(e); process.exit(1); });
