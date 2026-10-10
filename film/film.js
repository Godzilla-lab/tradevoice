/* The TradeVoice film. One paused GSAP timeline; window.seek(t) draws any moment exactly (render.cjs calls it for
   every frame). Timing is musical: 112 BPM, every shot starts on a bar line. Voice lengths come from the real clips
   when they are there (window.FILMDATA.voices), else from an estimate, and the shots grow by whole bars to fit.
   window.FILM = {duration, shots, cues} tells sound.py where every sound goes.
   House rules: made-up names only, no phone numbers, no emojis, no long dashes; every claim true today. */
(async () => {
// fonts first: text is measured and split into words only once the real faces are in
const SAMPLE = "TradeVoice Ẹẹ ọ̀ ṣ́ àáèéìíòóùú ɓɗƙƴ ụ ị ₦·%“” 0123456789";
await Promise.all(["450", "500", "550", "600", "650"].map(w => document.fonts.load(`${w} 100px "Inter Variable"`, SAMPLE)).concat(
  ["500", "600"].map(w => document.fonts.load(`${w} 60px "Caveat"`, "Iya Bisi 60,000"))));
await document.fonts.ready;
const D = window.FILMDATA || {};
const BAR = 240 / 112, BEAT = BAR / 4, FPS = 60;
gsap.registerPlugin(SplitText, CustomEase, MorphSVGPlugin);
gsap.ticker.lagSmoothing(0);
gsap.ticker.remove(gsap.updateRoot);   // nothing runs on the clock: only seek() moves time
const tl = gsap.timeline({ paused: true });
const hooks = [], cues = [], shots = [];
const stage = document.getElementById("stage");
const $ = (s, el = document) => el.querySelector(s), $$ = (s, el = document) => [...el.querySelectorAll(s)];
const html = (s, parent = stage) => { const t = document.createElement("template"); t.innerHTML = s.trim(); const el = t.content.firstElementChild; parent.appendChild(el); return el; };
const cue = (kind, t, extra) => cues.push(Object.assign({ kind, t: +t.toFixed(4) }, extra || {}));
const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
function rng(seed) { return () => { seed |= 0; seed = seed + 0x6D2B79F5 | 0; let t = Math.imul(seed ^ seed >>> 15, 1 | seed); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }

/* ---------------------------------------------------------------- motion vocabulary */
CustomEase.create("sheet", "0.32,0.72,0,1");          // iOS sheet
CustomEase.create("apple", "0.16,1,0.3,1");           // expo-out feel, for text and camera
function spring(d, bounce = 0) {                      // Apple's duration + bounce spring, as a GSAP ease
  const z = 1 - bounce, w = 2 * Math.PI / d, wd = w * Math.sqrt(Math.max(1e-9, 1 - z * z));
  const x = t => z >= 1 ? 1 - Math.exp(-w * t) * (1 + w * t) : 1 - Math.exp(-z * w * t) * (Math.cos(wd * t) + (z * w / wd) * Math.sin(wd * t));
  let T = d * 0.5;
  for (; T < 8 * d; T += d / 200) { const env = z >= 1 ? Math.exp(-w * T) * (1 + w * T) : Math.exp(-z * w * T) * (1 + z * w / wd); if (env < 0.0015) break; }
  return { ease: p => p >= 1 ? 1 : x(p * T), duration: T };
}
const SNAPPY = spring(0.55, 0.15), SMOOTH = spring(0.6, 0), SOFT = spring(0.9, 0.1);
function split(el, type = "words,lines") { return SplitText.create(el, { type, mask: "lines", linesClass: "sl", wordsClass: "sw", charsClass: "sc" }); }
function rise(el, t, o = {}) {
  const by = o.by || "words", s = split(el, by === "chars" ? "chars,words,lines" : "words,lines");
  tl.fromTo(s[by], { yPercent: 118 }, { yPercent: 0, duration: o.dur || 1.05, ease: "apple", stagger: o.stagger ?? 0.045 }, t);
  return s;
}
function sink(s, t, o = {}) {
  const by = o.by || "words";
  tl.to(s[by], { yPercent: -118, duration: o.dur || 0.42, ease: "power3.in", stagger: o.stagger ?? 0.018 }, t);
}
function fadeOut(el, t, dur = 0.35) { tl.to(el, { autoAlpha: 0, duration: dur, ease: "power2.in" }, t); }
function show(el, t0, t1) { tl.set(el, { visibility: "visible" }, t0); if (t1 != null) tl.set(el, { visibility: "hidden" }, t1); }
function zoomOut(el, t) { tl.to(el, { scale: 1.18, filter: "blur(12px)", opacity: 0, duration: 0.3, ease: "power3.in" }, t - 0.3); cue("whoosh", t - 0.32, { gain: 0.5 }); }
function zoomIn(el, t) { tl.fromTo(el, { scale: 0.8, filter: "blur(12px)", opacity: 0 }, { scale: 1, filter: "blur(0px)", opacity: 1, duration: 0.6, ease: "apple" }, t); }
function drift(cam, t0, t1, to = 1.035) { tl.fromTo(cam, { scale: 1 }, { scale: to, duration: t1 - t0, ease: "none" }, t0); }
function ripple(parent, x, y, t) {
  const r = html(`<i class="ripple" style="left:${x}px;top:${y}px"></i>`, parent);
  gsap.set(r, { opacity: 0 });
  tl.set(r, { scale: 0.35, opacity: 0.95 }, t);
  tl.to(r, { scale: 1.7, opacity: 0, duration: 0.5, ease: "power2.out" }, t);
  cue("tap", t);
}

/* ---------------------------------------------------------------- voices (Spitch clips, or an estimate until they come) */
const LINES = D.lines || {};
function voice(id) {
  const v = (D.voices || {})[id], line = LINES[id] || {};
  if (v) return { id, dur: v.dur, env: v.env, file: v.file, sub: line.subtitle || "", text: line.text || "" };
  const text = line.text || "", dur = Math.max(0.9, text.length / 13.5 + 0.25), r = rng(text.length * 97 + 7), env = [];
  for (let i = 0; i < dur * FPS; i++) { const syl = 0.5 + 0.5 * Math.sin(i / FPS * 2 * Math.PI * 4.2 + r() * 0.6); env.push(clamp(0.25 + 0.6 * syl * (0.6 + 0.4 * r()))); }
  return { id, dur, env, file: null, sub: line.subtitle || "", text, estimate: true };
}
const envAt = (v, t) => { if (t < 0 || t > v.dur) return 0; const i = Math.min(v.env.length - 1, Math.floor(t * FPS)); return v.env[i] || 0; };
function speak(v, t) { cue("voice", t, { id: v.id, file: v.file, dur: +v.dur.toFixed(3) }); return t + v.dur; }

/* ---------------------------------------------------------------- subtitles */
const subEl = $("#subs span"), subs = [];
function sub(text, t0, t1) { if (text) subs.push({ text, t0, t1: Math.max(t1, t0 + 0.9) }); }
hooks.push(t => {
  const s = subs.find(x => t >= x.t0 && t < x.t1);
  if (!s) { subEl.style.opacity = 0; return; }
  if (subEl.textContent !== s.text) subEl.textContent = s.text;
  subEl.style.opacity = Math.min(clamp((t - s.t0) / 0.14), clamp((s.t1 - t) / 0.14));
});

/* ---------------------------------------------------------------- grain */
{
  const c = document.createElement("canvas"); c.width = c.height = 256; const g = c.getContext("2d"), im = g.createImageData(256, 256), r = rng(11);
  for (let i = 0; i < im.data.length; i += 4) { const v = 128 + (r() - 0.5) * 255; im.data[i] = im.data[i + 1] = im.data[i + 2] = v; im.data[i + 3] = 255; }
  g.putImageData(im, 0, 0); const grain = $("#grain"); grain.style.backgroundImage = `url(${c.toDataURL()})`;
  hooks.push(t => { const f = Math.round(t * FPS), r2 = rng(f * 31 + 5); grain.style.transform = `translate(${Math.round(r2() * 64 - 32)}px,${Math.round(r2() * 64 - 32)}px)`; });
}

/* ---------------------------------------------------------------- the phone with real app layers */
const ICONS = `<svg width="72" height="14" viewBox="0 0 72 14"><g fill="#111"><rect x="0" y="9" width="3" height="5" rx="1"/><rect x="5" y="6" width="3" height="8" rx="1"/><rect x="10" y="3" width="3" height="11" rx="1"/><rect x="15" y="0" width="3" height="14" rx="1"/></g><path d="M31 4.2a9.5 9.5 0 0 1 13 0l-1.5 1.6a7.3 7.3 0 0 0-10 0zM34 7.3a5.2 5.2 0 0 1 7 0l-1.6 1.6a3 3 0 0 0-3.8 0zM37.5 11l1.4-1.4 1.4 1.4-1.4 1.4z" fill="#111"/><rect x="48.5" y="1.5" width="20" height="11" rx="3.2" fill="none" stroke="#111" opacity=".45"/><rect x="50.5" y="3.5" width="14" height="7" rx="1.6" fill="#111"/><rect x="69.6" y="5" width="1.6" height="4" rx=".8" fill="#111" opacity=".45"/></svg>`;
function makePhone(parent, x, y, k) {
  const p = html(`<div class="phone" style="left:${x - 209}px;top:${y - 458}px"><i class="btn-side"></i><i class="btn-side l1"></i><i class="btn-side l2"></i>
    <div class="screen"><div class="statusbar"><span>10:08</span>${ICONS}</div><div class="island"></div><div class="app"></div><div class="homebar"></div></div></div>`, parent);
  gsap.set(p, { scale: k });
  return { el: p, app: $(".app", p) };
}
function layer(app, src, y = 0, z = 1) {
  const L = html(`<div class="layer" style="z-index:${z}"><img src="${src}" style="top:${y}px"></div>`, app);
  return L;
}
const SH = "shots/", LY = "shots/layers/", G = D.layers || {};

/* ---------------------------------------------------------------- the notebook page (shots 2 and 8) */
const ENTRIES = [["Iya Bisi", "2 bags rice", "60,000"], ["Mama Ngozi", "eggs, 3 crates", "13,500"], ["Oga Emeka", "goods", "25,000"],
  ["Alhaji Musa", "indomie", "18,500"], ["Madam Funke", "garri", "9,000"]];
const ROW = i => 234 + (i + 1) * 79;   // each entry sits on a ruled line
function makePage(parent, x, y, rot) {
  const p = html(`<div class="page" style="left:${x}px;top:${y}px;transform:rotate(${rot}deg)">
    ${[180, 520, 860].map(h => `<i class="hole" style="top:${h}px"></i>`).join("")}
    <div class="entry" style="top:159px;left:150px;font-size:54px;opacity:.75">Credit, October</div>
    ${ENTRIES.map((e, i) => `<div class="entry e${i}" style="top:${ROW(i)}px">${e[0]} &nbsp;${e[1]} &nbsp;<b>${e[2]}</b></div>`).join("")}
  </div>`, parent);
  return p;
}
function writeEntries(page, t, gap = 0.3, dur = 0.55) {
  $$(".entry", page).forEach((e, i) => {
    tl.fromTo(e, { clipPath: "inset(0 100% 0 0)" }, { clipPath: "inset(0 0% 0 0)", duration: i ? dur : 0.4, ease: "power1.inOut" }, t + i * gap);
    cue("pen", t + i * gap, { dur: i ? dur : 0.4 });
  });
}

/* ---------------------------------------------------------------- the logo, part by part (web/logo.svg) */
const BUBBLE = "M 340 150 H 684 A 190 190 0 0 1 874 340 V 610 A 190 190 0 0 1 684 800 H 420 C 360 800 300 850 238 888 C 222 898 204 886 210 868 C 222 832 232 800 230 770 A 190 190 0 0 1 150 610 V 340 A 190 190 0 0 1 340 150 Z";
const CIRCLE = "M 512 285 A 190 190 0 1 1 511.9 285 Z";
let logoN = 0;
function makeLogo(parent, x, y, size) {
  const id = "lg" + (logoN++);
  const el = html(`<svg class="logo" viewBox="132 142 760 760" width="${size}" height="${size}" style="left:${x}px;top:${y}px">
    <defs><linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1" gradientUnits="objectBoundingBox"><stop offset="0" stop-color="#3B4CE0"/><stop offset="1" stop-color="#2A36B8"/></linearGradient></defs>
    <path class="bubble" fill="url(#${id})" d="${BUBBLE}"/>
    <rect class="cap" x="412" y="246" width="200" height="344" rx="100" fill="#FBF8F1"/>
    <g class="bars"><rect class="b1" x="444" y="480" width="36" height="60" rx="11" fill="#8C9BFF"/><rect class="b2" x="494" y="435" width="36" height="105" rx="11" fill="#5B6BEA"/><rect class="b3" x="544" y="390" width="36" height="150" rx="11" fill="#2A36B8"/></g>
    <path class="u" d="M 362 456 V 500 A 150 150 0 0 0 662 500 V 456" fill="none" stroke="#FBF8F1" stroke-width="40" stroke-linecap="round"/>
    <path class="stem" d="M 512 650 V 730" fill="none" stroke="#FBF8F1" stroke-width="40" stroke-linecap="round"/></svg>`, parent);
  $$(".bars rect", el).forEach(r => gsap.set(r, { transformOrigin: "50% 100%" }));
  gsap.set($(".cap", el), { transformOrigin: "50% 50%" });
  return el;
}
// the logo's own bar animation (web/logo.svg keyframes), as a function of time
const KF = [[1.1, 0, [[0, 1], [.3, 1.55], [.6, .7], [1, 1]]], [1.3, -0.4, [[0, 1], [.35, .6], [.7, 1.25], [1, 1]]], [1.5, -0.8, [[0, 1], [.4, .62], [.75, .9], [1, 1]]]];
function barScale(i, t) {
  const [dur, delay, k] = KF[i]; let p = ((t - delay) / dur) % 1; if (p < 0) p += 1;
  for (let j = 1; j < k.length; j++) if (p <= k[j][0]) { const a = k[j - 1], b = k[j], u = (p - a[0]) / (b[0] - a[0]), e = u < .5 ? 2 * u * u : 1 - Math.pow(-2 * u + 2, 2) / 2; return a[1] + (b[1] - a[1]) * e; }
  return 1;
}
function danceBars(svg, from, to, amount = 1) {
  const bars = $$(".bars rect", svg);
  hooks.push(t => { if (t < from || t > to) return; const a = clamp((t - from) / 0.6) * amount; bars.forEach((b, i) => { b.style.transform = `scaleY(${1 + (barScale(i, t) - 1) * a})`; }); });
}

/* ---------------------------------------------------------------- the live-talk parts, drawn with the app's own CSS */
if (D.orbCss) { const s = document.createElement("style"); s.textContent = D.orbCss + "\n.filmorb,.filmorb *{transition:none!important}"; document.head.appendChild(s); }
function makeLive(parent) {
  const el = html(`<div class="live filmorb"><div class="tvc" data-st="listen"><span class="tvc-pill"><i></i><span class="st">Listening</span></span>
    <div class="orbwrap"><span class="tvc-orb"><b><u><i></i><i></i><i></i></u></b></span></div>
    <p class="tvc-say"></p><p class="tvc-hint"></p></div></div>`, parent);
  return { el, tvc: $(".tvc", el), st: $(".st", el), orb: $(".tvc-orb", el), say: $(".tvc-say", el), hint: $(".tvc-hint", el) };
}
const STATE = { listen: "Listening", think: "Understanding", speak: "Speaking" };
function driveLive(L, from, to, plan) {   // plan: {states:[[t,st]], says:[[t,html,hint]], lv:t=>0..1}
  const anims = () => L.el.getAnimations({ subtree: true });
  hooks.push(t => {
    if (t < from - 0.5 || t > to + 0.5) return;
    const st = [...plan.states].reverse().find(s => t >= s[0]); if (st && L.tvc.dataset.st !== st[1]) { L.tvc.dataset.st = st[1]; L.st.textContent = STATE[st[1]]; }
    const sy = [...plan.says].reverse().find(s => t >= s[0]);
    const h = sy ? (typeof sy[1] === "function" ? sy[1](t) : sy[1]) : "&nbsp;";
    if (L.say.innerHTML !== h) L.say.innerHTML = h;
    const hint = sy && sy[2] || ""; if (L.hint.textContent !== hint) L.hint.textContent = hint;
    L.orb.style.setProperty("--lv", (plan.lv ? plan.lv(t) : 0).toFixed(3));
    anims().forEach(a => { try { a.pause(); a.currentTime = (t - from + 40) * 1000; } catch (e) {} });
  });
}

/* ================================================================ the shots */
let T = 0;
function begin(id, cls, bars) { const sec = html(`<section class="shot ${cls}" id="${id}"><div class="cam"></div></section>`); const s = { id, el: sec, cam: $(".cam", sec), start: T, bars }; s.end = T + bars * BAR; shots.push(s); T = s.end; show(sec, s.start, s.end + 0.001); return s; }
const textBlock = (parent, cls, txt, style) => html(`<div class="${cls}" style="${style}">${txt}</div>`, parent);

/* 1. Cold open: what credit sounds like in the market */
{
  const s = begin("open", "dark", 2), t0 = s.start;
  if (D.openFrames) {   // real market footage, darkened, when the clip is there
    const v = html(`<img class="abs" style="left:0;top:0;width:1920px;height:1080px;object-fit:cover;filter:brightness(.42) saturate(.9)">`, s.cam);
    hooks.push(t => { if (t < s.start || t > s.end) return; const f = Math.min(D.openFrames.count - 1, Math.floor((t - s.start) * D.openFrames.fps)); const src = `${D.openFrames.dir}/${String(f + 1).padStart(5, "0")}.jpg`; if (v.getAttribute("src") !== src) v.setAttribute("src", src); });
  }
  const P = D.photos || {};
  if (P[3] && P[4] && P[1] && P[5]) {   // real Nigerian markets, cut on the half bars: the aerial, the traders, the trader, the sale
    const cuts = [[P[3], "50% 50%", 1.0, 1.1, 0, -30], [P[4], "50% 62%", 1.1, 1.04, -40, 10], [P[1], "38% 35%", 1.04, 1.12, 30, 0], [P[5], "35% 50%", 1.12, 1.05, 0, -20]];
    cuts.forEach(([src, pos, s0, s1, dx, dy], i) => {
      const a0 = t0 + i * BAR / 2, a1 = i === 3 ? s.end : a0 + BAR / 2;
      const im = html(`<img class="abs" src="${src}" style="left:0;top:0;width:1920px;height:1080px;object-fit:cover;object-position:${pos};filter:brightness(.5) saturate(.85) contrast(1.06);visibility:hidden">`, s.cam);
      show(im, a0, a1 + 0.001);
      tl.fromTo(im, { scale: s0, x: 0, y: 0 }, { scale: s1, x: dx, y: dy, duration: a1 - a0 + 0.2, ease: "none" }, a0);
      if (i) cue("cut", a0);
    });
    html(`<div class="abs" style="inset:0;background:radial-gradient(ellipse 70% 60% at 50% 50%,rgba(8,8,12,.45),rgba(8,8,12,.2) 70%,rgba(8,8,12,.55))"></div>`, s.cam);
  } else if (!D.openFrames) {
    const r = rng(42), cols = ["#F2A93B", "#E8743B", "#F6D27A", "#C9653A", "#FFE3A3"];
    for (let i = 0; i < 16; i++) {
      const sz = 120 + r() * 300, x = r() * 1920, y = 240 + r() * 700, c = cols[i % cols.length];
      const b = html(`<i class="abs" style="left:${x - sz / 2}px;top:${y - sz / 2}px;width:${sz}px;height:${sz}px;border-radius:50%;background:radial-gradient(circle,${c} 0%,${c}00 70%);opacity:${0.10 + r() * 0.16};filter:blur(${8 + r() * 18}px)"></i>`, s.cam);
      tl.fromTo(b, { x: -40 + r() * 80, opacity: 0 }, { x: -120 + r() * 240, opacity: 0.12 + r() * 0.2, duration: 4.3, ease: "sine.inOut" }, t0);
    }
  }
  const a = textBlock(s.cam, "h xl center", "Take it.", "top:410px;color:#fff");
  const b = textBlock(s.cam, "h xl center", "Pay me Friday.", "top:410px;color:#fff");
  drift(s.cam, t0, s.end, 1.05);
  const sa = rise(a, t0 + 0.45, { stagger: 0.08 }); sink(sa, t0 + 1.75);
  rise(b, t0 + 1.95, { stagger: 0.07 });
  zoomOut(s.cam, s.end);
  cue("ambience", t0, { fade: 1.4 });
}

/* 2. The notebook: where debts live, and get lost */
let notebookDot;
{
  const s = begin("notebook", "light", 2), t0 = s.start;
  s.el.style.background = "var(--paper)";
  const page = makePage(s.cam, 120, 70, -3.2);
  const h1 = textBlock(s.cam, "h m abs", "Debts live<br>in a notebook.", "left:1060px;top:360px;width:780px");
  const h2 = textBlock(s.cam, "h m abs", "Some are<br>forgotten<span class='dot'>.</span>", "left:1060px;top:360px;width:780px");
  zoomIn(s.cam, t0); drift(page, t0, s.end, 1.04); cue("page", t0 + 0.02);
  writeEntries(page, t0 + 0.15, 0.32, 0.5);
  const s1 = rise(h1, t0 + 0.55, { stagger: 0.05 });
  // two debts settled and crossed out; one fades, forgotten
  [2, 3].forEach((i, j) => {
    const e = $(".e" + i, page), w = 600;
    const sv = html(`<svg class="strike" width="${w}" height="40" style="top:${ROW(i) + 26}px"><path d="M4 22 C 160 14, 360 28, ${w - 6} 16" stroke="#22306E" stroke-width="5" fill="none" stroke-linecap="round"/></svg>`, page);
    const path = $("path", sv), len = w + 20; gsap.set(path, { strokeDasharray: len, strokeDashoffset: len });
    tl.to(path, { strokeDashoffset: 0, duration: 0.32, ease: "power2.inOut" }, t0 + 2.05 + j * 0.26); cue("pen", t0 + 2.05 + j * 0.26, { dur: 0.3, strike: true });
    tl.to(e, { opacity: 0.55, duration: 0.3 }, t0 + 2.2 + j * 0.26);
  });
  sink(s1, t0 + 2.35);
  const s2 = rise(h2, t0 + 2.55, { stagger: 0.05 });
  tl.to($(".e4", page), { opacity: 0, filter: "blur(6px)", duration: 1.4, ease: "power1.in" }, t0 + 2.6);
  // the full stop of "forgotten." leaves the page: it becomes the logo
  notebookDot = $(".dot", h2);
  tl.to([page, ...s2.words.slice(0, -1)], { opacity: 0, filter: "blur(8px)", duration: 0.45, ease: "power2.in" }, s.end - 0.55);
  cue("swell", t0 + 2.4, { dur: s.end - t0 - 2.4 });
}

/* 3. The logo: the dot becomes TradeVoice */
let endLogo;
{
  const s = begin("logo", "light", 2), t0 = s.start;
  const size = 300, lx = 960 - size / 2, ly = 540 - size / 2 - 40;
  const logo = makeLogo(s.cam, lx, ly, size);
  const bubble = $(".bubble", logo);
  gsap.set(bubble, { attr: { d: CIRCLE } });
  // the full stop from shot 2 flies to the centre and grows into the bubble's circle (a match cut)
  const dot = html(`<div class="abs" style="left:0;top:0;width:40px;height:40px;border-radius:50%;background:#17171B;z-index:5;visibility:hidden"></div>`, stage);
  const dr = notebookDot.getBoundingClientRect(), dsz = Math.max(10, dr.height * 0.16);
  tl.set(dot, { visibility: "visible", x: dr.left + dr.width / 2 - 20, y: dr.top + dr.height * 0.74 - 20, scale: dsz / 40 }, t0 - 0.5);
  tl.set(notebookDot, { opacity: 0 }, t0 - 0.5);
  tl.to(dot, { x: 960 - 20, y: 540 - 40 - 20 + 6, scale: size * (380 / 760) / 40, background: "#3B4CE0", duration: 0.5, ease: "power3.inOut" }, t0 - 0.5);
  tl.set(dot, { visibility: "hidden" }, t0 + 0.02);
  tl.to(bubble, { morphSVG: BUBBLE, duration: SNAPPY.duration, ease: SNAPPY.ease }, t0 + 0.02);
  const cap = $(".cap", logo), u = $(".u", logo), stem = $(".stem", logo), bars = $$(".bars rect", logo);
  tl.fromTo(cap, { scale: 0 }, { scale: 1, duration: SNAPPY.duration, ease: SNAPPY.ease }, t0 + 0.18);
  [u, stem].forEach((p, i) => { const L = p.getTotalLength(); gsap.set(p, { strokeDasharray: L, strokeDashoffset: L }); tl.to(p, { strokeDashoffset: 0, duration: 0.5, ease: "power2.inOut" }, t0 + 0.28 + i * 0.12); });
  bars.forEach((b, i) => { tl.fromTo(b, { scaleY: 0 }, { scaleY: 1, duration: SNAPPY.duration, ease: SNAPPY.ease }, t0 + i * BEAT); cue("tick", t0 + i * BEAT, { gain: 0.35, pitch: i }); });
  danceBars(logo, t0 + 3 * BEAT + 0.4, s.end, 0.8);
  // the wordmark arrives: the logo steps left
  const word = textBlock(s.cam, "wordmark abs", "TradeVoice", "font-size:156px;left:0;top:0;opacity:0");
  const ww = word.getBoundingClientRect().width, gap = 44, total = size * 0.9 + gap + ww, left = (1920 - total) / 2;
  gsap.set(word, { x: left + size * 0.9 + gap, y: 540 - 40 - 92, opacity: 1 });
  tl.to(logo, { x: left - lx - size * 0.05, scale: 0.9, duration: SMOOTH.duration, ease: SMOOTH.ease }, t0 + 0.95);
  rise(word, t0 + 1.05, { by: "chars", stagger: 0.026, dur: 0.9 });
  const tag = textBlock(s.cam, "sub2 center", "Records that speak your language.", "top:680px;font-size:52px");
  rise(tag, t0 + 1.75, { stagger: 0.04 });
  drift(s.cam, t0, s.end, 1.03);
  tl.to(s.cam, { y: -230, opacity: 0, duration: 0.34, ease: "power4.in" }, s.end - 0.34);
  cue("drop", t0); cue("whoosh", s.end - 0.36, { gain: 0.4 });
}

/* 4. Speak: live talk, the check card, Save */
{
  const ask = voice("yo_ask"), saved = voice("yo_saved");
  // the length this shot needs, in whole bars
  const need = 4.3 + ask.dur + 0.25 + 2.5 + Math.max(saved.dur, 1.0) + 0.9;
  const s = begin("speak", "light", Math.ceil(need / BAR)), t0 = s.start;
  const ph = makePhone(s.cam, 1290, 518, 1.0), app = ph.app;
  layer(app, SH + "home_before.png", 0, 1);
  const homeAfter = layer(app, SH + "home.png", 0, 2); gsap.set(homeAfter, { opacity: 0 });
  const dim = layer(app, LY + "talk_dim.png", 0, 3); gsap.set(dim, { opacity: 0 });
  const sheet = html(`<div class="layer" style="z-index:4"><img src="${LY}talk_sheet.png" style="top:0"></div>`, app);
  gsap.set(sheet, { y: 844 });
  const liveBox = html(`<div class="abs" style="left:0;top:0;width:390px;height:622px"></div>`, sheet);
  const L = makeLive(liveBox);
  gsap.set(sheet, { y: 844 }); $("img", sheet).style.top = "0px";
  const cardDim = layer(app, LY + "card_dim.png", 0, 5); gsap.set(cardDim, { opacity: 0 });
  const card = layer(app, LY + "card_sheet.png", 0, 6); gsap.set(card, { y: 844 });
  const toast = html(`<div class="layer" style="z-index:8"><img src="${LY}toast.png" style="left:8px;top:673px;width:358px"></div>`, app); gsap.set(toast, { opacity: 0, y: 18 });
  const SHEET_Y = (G.talk_sheet || { y: 222 }).y, CARD_Y = (G.card_sheet || { y: 295 }).y;
  $("img", sheet).style.top = "0px"; sheet.style.top = SHEET_Y + "px"; card.style.top = "0px"; $("img", card).style.top = CARD_Y + "px";

  // the phone turns in
  tl.fromTo(ph.el, { y: 160, rotationY: -26, rotationX: 10, opacity: 0, scale: 0.92 }, { y: 0, rotationY: 0, rotationX: 0, opacity: 1, scale: 1.0, duration: SOFT.duration, ease: SOFT.ease }, t0);
  cue("whoosh", t0, { gain: 0.45, up: true });
  drift(s.cam, t0, s.end, 1.03);
  const head1 = textBlock(s.cam, "h l abs", "Say it.", "left:150px;top:300px;width:900px");
  const head2 = textBlock(s.cam, "h l abs", "We keep<br>the book.", "left:150px;top:450px;width:900px;color:var(--label2)");
  const r1 = rise(head1, t0 + 0.35), r2 = rise(head2, t0 + 0.75);
  // tap the mic: live talk opens
  const tTap = t0 + 1.0;
  ripple(app, 195, 797, tTap);
  tl.to(dim, { opacity: 1, duration: 0.3, ease: "power1.out" }, tTap + 0.08);
  tl.to(sheet, { y: 0, duration: 0.55, ease: "sheet" }, tTap + 0.08);
  cue("sheet", tTap + 0.08);
  // she talks (Yoruba); her words show as live talk hears them
  const HER = "Mo ta àpò ìrẹsì 2 fún Iya Bisi ní 60,000, gbèsè ni, yóò san lọ́jọ́ Ẹtì.".split(" ");
  const tHer = tTap + 0.75, herDur = 2.7, tThink = tHer + herDur + 0.15, tSpeak = tThink + 0.55;
  const herWords = t => HER.slice(0, Math.max(1, Math.ceil((t - tHer) / herDur * HER.length))).join(" ");
  const herLv = t => { if (t < tHer || t > tHer + herDur) return 0.05; const x = t - tHer; return clamp(0.35 + 0.45 * Math.abs(Math.sin(x * 9.1)) * (0.6 + 0.4 * Math.sin(x * 2.3))); };
  sub("I sold 2 bags of rice to Iya Bisi for 60,000. It's on credit, she'll pay on Friday.", tHer + 0.2, tThink + 0.4);
  const pending = `<b>₦60,000</b> · Iya Bisi · Sold on credit · Friday`;
  const tAskEnd = speak(ask, tSpeak);
  sub(ask.sub, tSpeak, tAskEnd + 0.2);
  driveLive(L, tTap, tAskEnd + 1, {
    states: [[0, "listen"], [tThink, "think"], [tSpeak, "speak"]],
    says: [[0, "&nbsp;"], [tHer, herWords], [tThink, () => `“${HER.join(" ")}”`], [tSpeak, pending, "Tap to check it on screen"]],
    lv: t => t < tSpeak ? herLv(t) : 0.08 + 0.92 * envAt(ask, t - tSpeak),
  });
  // headline: it reads it back
  sink(r1, tThink - 0.2); sink(r2, tThink - 0.1);
  const head3 = textBlock(s.cam, "h m abs", "It reads it back,<br>in your language.", "left:150px;top:380px;width:900px");
  const r3 = rise(head3, tSpeak + 0.1);
  // tap the words: check it on screen
  const tCard = tAskEnd + 0.25;
  ripple(app, 195, 222 + 425 + 22, tCard);
  tl.to(sheet, { y: 844, duration: 0.32, ease: "power2.in" }, tCard + 0.06);
  tl.to(dim, { opacity: 0, duration: 0.2 }, tCard + 0.3);
  tl.to(cardDim, { opacity: 1, duration: 0.25 }, tCard + 0.3);
  tl.fromTo(card, { y: 844 }, { y: 0, duration: 0.55, ease: "sheet" }, tCard + 0.34);
  cue("sheet", tCard + 0.34);
  sink(r3, tCard + 0.2);
  const head4 = textBlock(s.cam, "h m abs", "Nothing is saved<br>until you say yes.", "left:150px;top:380px;width:900px");
  const r4 = rise(head4, tCard + 0.55);
  // push in on the amount, then back
  tl.to(ph.el, { scale: 1.42, x: 60, y: 170, duration: 1.1, ease: "power3.inOut" }, tCard + 0.85);
  tl.to(ph.el, { scale: 1.0, x: 0, y: 0, duration: 0.8, ease: "power3.inOut" }, tCard + 2.0);
  // Save
  const tSave = tCard + 2.55;
  ripple(app, 83, 295 + (730.5 - 326.8) + 26 + 31, tSave);
  tl.to(card, { y: 844, duration: 0.32, ease: "power2.in" }, tSave + 0.08);
  tl.to(cardDim, { opacity: 0, duration: 0.25 }, tSave + 0.3);
  tl.set(homeAfter, { opacity: 1 }, tSave + 0.3);
  tl.to(toast, { opacity: 1, y: 0, duration: SNAPPY.duration, ease: SNAPPY.ease }, tSave + 0.35);
  cue("chime", tSave + 0.38);
  const tSaid = tSave + 0.45, tSavedEnd = speak(saved, tSaid);
  sub(saved.sub, tSaid, tSavedEnd + 0.3);
  sink(r4, s.end - 0.45);
  zoomOut(s.cam, s.end);
}

/* 5. Four voices, one book */
{
  const ids = ["en", "yo", "ha", "ig"], NAMES = { en: "English", yo: "Yorùbá", ha: "Hausa", ig: "Igbo" };
  const full = ids.map(i => voice("four_" + i)), short = ids.map(i => voice("saved_" + i));
  const per = vs => vs.map(v => Math.ceil((v.dur + 0.55) / (BAR / 2)) * (BAR / 2));
  let use = full, slots = per(full);
  if (slots.reduce((a, b) => a + b, 0) + BAR > 6 * BAR) { use = short; slots = per(short).map(x => Math.max(x, BAR)); }
  const bars = Math.ceil((BAR + slots.reduce((a, b) => a + b, 0) + 0.4) / BAR);
  const s = begin("voices", "dark", bars), t0 = s.start;
  zoomIn(s.cam, t0);
  const title = textBlock(s.cam, "h l center", "Four voices.<br><span style='color:var(--night2)'>One book.</span>", "top:350px");
  const rt = rise(title, t0 + 0.15, { stagger: 0.06 });
  sink(rt, t0 + BAR - 0.62);
  // the orb, in the app's dark colours, speaks each language
  const orbBox = html(`<div class="live filmorb" style="position:absolute;left:0;top:0;width:1920px;height:1080px;--accent:#8C9BFF;--fill:#212127;--label2:#9A9AA3;--d1:.15s;--d3:.5s"><div class="tvc" data-st="speak" style="position:absolute;inset:0"><div class="orbwrap" style="left:868px;top:150px;width:184px;height:184px;transform:scale(1.25)"><span class="tvc-orb"><b><u><i></i><i></i><i></i></u></b></span></div></div></div>`, s.cam);
  const orb = $(".tvc-orb", orbBox); gsap.set(orbBox, { opacity: 0 });
  tl.to(orbBox, { opacity: 1, duration: 0.6, ease: "power1.out" }, t0 + BAR - 0.18);
  let t = t0 + BAR;
  const placed = [];
  use.forEach((v, i) => {
    const id = ids[i];
    const name = textBlock(s.cam, "h xl center", NAMES[id], "top:430px");
    const words = textBlock(s.cam, "center", v.text.split(" ").map(w => `<span class="kw">${w}</span>`).join(" "), "top:650px;font-size:54px;font-weight:500;font-variation-settings:'opsz' 28;letter-spacing:-.018em;color:#55555e;padding:0 240px;line-height:1.3");
    const rn = rise(name, t - 0.05, { by: "chars", stagger: 0.02, dur: 0.8 });
    tl.fromTo(words, { opacity: 0, y: 14 }, { opacity: 1, y: 0, duration: 0.5, ease: "apple" }, t);
    const tv = t + 0.25, tEnd = speak(v, tv);
    if (id !== "en") sub(v.sub, tv, tEnd + 0.25);
    const kws = $$(".kw", words), chars = v.text.length;
    hooks.push(tt => { if (tt < tv - 0.3 || tt > tEnd + 1) return; let acc = 0; const p = (tt - tv) / v.dur * chars; kws.forEach(k => { acc += k.textContent.length + 1; k.style.color = acc - k.textContent.length <= p ? "#fff" : "#55555e"; }); });
    placed.push([tv, v]);
    const tNext = t + slots[i];
    if (i < use.length - 1) { sink(rn, tNext - 0.35, { by: "chars", stagger: 0.012 }); tl.to(words, { opacity: 0, y: -10, duration: 0.3, ease: "power2.in" }, tNext - 0.35); }
    t = tNext;
  });
  // the bar left over: the last voice steps aside for the full list of what TradeVoice understands
  if (s.end - t > 1.2) {
    const lastName = $$(".h.xl.center", s.cam).pop(), lastWords = $$(".center", s.cam).pop();
    tl.to([lastName, lastWords], { opacity: 0, y: -16, duration: 0.35, ease: "power2.in" }, t - 0.1);
    const all = textBlock(s.cam, "h s center", "Understands English, Pidgin,<br>Yorùbá, Hausa and Igbo.", "top:470px;color:#fff");
    rise(all, t + 0.2, { stagger: 0.035 });
  }
  hooks.push(tt => {
    if (tt < s.start || tt > s.end) return;
    const on = placed.find(([tv, v]) => tt >= tv && tt <= tv + v.dur);
    orb.style.setProperty("--lv", (on ? 0.1 + 0.9 * envAt(on[1], tt - on[0]) : 0.05).toFixed(3));
    orb.getAnimations({ subtree: true }).forEach(a => { try { a.pause(); a.currentTime = (tt - s.start + 10) * 1000; } catch (e) {} });
  });
  drift(s.cam, t0, s.end, 1.04);
  zoomOut(s.cam, s.end);
  cue("thin", t0, { bars });
}

/* 6. The AI reads the words. Code does every sum. */
{
  const s = begin("sums", "light", 3), t0 = s.start;
  zoomIn(s.cam, t0);
  const ph = makePhone(s.cam, 560, 528, 1.0);
  layer(ph.app, SH + "home.png", 0, 1);
  tl.fromTo(ph.el, { y: 80, opacity: 0 }, { y: 0, opacity: 1, duration: SMOOTH.duration, ease: SMOOTH.ease }, t0);
  const h1 = textBlock(s.cam, "h s abs", "The AI reads the words.", "left:1000px;top:150px;width:860px;color:var(--label2)");
  const h2 = textBlock(s.cam, "h s abs", "Code does every sum.", "left:1000px;top:238px;width:860px");
  rise(h1, t0 + 0.3); rise(h2, t0 + 1.3);
  const rows = [["Iya Bisi", 60000], ["Alhaji Musa", 18500], ["Oga Emeka", 15000], ["Mama Ngozi", 13500], ["Madam Funke", 9000]];
  const box = html(`<div class="abs" style="left:1000px;top:400px;width:760px"></div>`, s.cam);
  rows.forEach(([n, a], i) => {
    const r = html(`<div style="display:flex;justify-content:space-between;align-items:baseline;height:62px;border-bottom:1px solid #E4E2DC"><span style="font-size:36px;font-weight:450;color:var(--label2);letter-spacing:-.01em">${n}</span><span class="num" style="font-size:44px;font-weight:550;letter-spacing:-.02em">₦${a.toLocaleString("en-NG")}</span></div>`, box);
    tl.fromTo(r, { opacity: 0, x: 40 }, { opacity: 1, x: 0, duration: 0.6, ease: "apple" }, t0 + 1.9 + i * 0.16);
    cue("tick", t0 + 1.9 + i * 0.16, { gain: 0.28, pitch: i });
  });
  const tot = html(`<div style="display:flex;justify-content:space-between;align-items:baseline;margin-top:26px"><span style="font-size:40px;font-weight:600;letter-spacing:-.015em">To collect</span><span class="num tot" style="font-size:120px;font-weight:650;letter-spacing:-.04em;color:var(--accent)">₦0</span></div>`, box);
  tl.fromTo(tot, { opacity: 0 }, { opacity: 1, duration: 0.4 }, t0 + 2.85);
  const totEl = $(".tot", tot), tc0 = t0 + 2.9, tc1 = tc0 + 1.3;
  hooks.push(t => { if (t < tc0 - 0.1 || t > s.end) return; const p = clamp((t - tc0) / (tc1 - tc0)), e = 1 - Math.pow(1 - p, 4); totEl.textContent = "₦" + (Math.round(116000 * e / 500) * 500).toLocaleString("en-NG"); });
  for (let i = 0; i < 9; i++) cue("tick", tc0 + i * 0.13 * (1 + i * 0.08), { gain: 0.16, pitch: 2 + (i % 3) });
  cue("hit", tc1, { gain: 0.5 }); cue("cash", tc0 - 0.05, { dur: tc1 - tc0 + 0.25 });
  ripple(ph.app, 195, 482, s.end - 0.95);
  tl.to([h1, h2, box], { opacity: 0, x: -30, duration: 0.4, ease: "power2.in" }, s.end - 0.7);
  tl.to(ph.el, { x: 1310 - 560, y: -10, duration: 0.75, ease: "power3.inOut" }, s.end - 0.75);
  cue("whoosh", s.end - 0.7, { gain: 0.35 });
}

/* 7. You send it */
{
  const s = begin("send", "light", 2), t0 = s.start;   // the phone arrives from shot 6 (same place, no fade)
  const ph = makePhone(s.cam, 1310, 518, 1.0), app = ph.app;
  layer(app, SH + "customer.png", 0, 1);
  const dim = layer(app, LY + "reminder_dim.png", 0, 2); gsap.set(dim, { opacity: 0 });
  const sh = layer(app, LY + "reminder_sheet.png", 0, 3); $("img", sh).style.top = (G.reminder_sheet || { y: 428 }).y + "px"; gsap.set(sh, { y: 844 });
  ripple(app, 195, 185 + 0, t0 + 0.55);
  tl.to(dim, { opacity: 1, duration: 0.3 }, t0 + 0.62);
  tl.to(sh, { y: 0, duration: 0.55, ease: "sheet" }, t0 + 0.62); cue("sheet", t0 + 0.62);
  const h1 = textBlock(s.cam, "h m abs", "Reminders,<br>written for you.", "left:150px;top:330px;width:900px");
  const r1 = rise(h1, t0 + 0.3);
  sink(r1, t0 + 2.15);
  const h2 = textBlock(s.cam, "h m abs", "You send them.", "left:150px;top:360px;width:900px");
  const h3 = textBlock(s.cam, "sub2 abs", "TradeVoice never messages<br>your customers.", "left:150px;top:500px;width:900px;font-size:48px");
  rise(h2, t0 + 2.3); rise(h3, t0 + 2.55, { stagger: 0.03 });
  ripple(app, 195, 428 + 224, t0 + 3.3);
  drift(s.cam, t0, s.end, 1.03);
  zoomOut(s.cam, s.end);
}

/* 8. Old pages count too */
{
  const s = begin("pages", "light", 2), t0 = s.start;
  s.el.style.background = "var(--paper)";
  const holder = html(`<div class="abs" style="left:0;top:0;width:1920px;height:1080px"></div>`, s.cam);
  const page = makePage(holder, 520, 40, 2.4); gsap.set(page, { scale: 0.86, transformOrigin: "50% 40%" });
  $$(".entry", page).forEach(e => gsap.set(e, { clipPath: "inset(0 0% 0 0)" }));
  gsap.set($(".e4", page), { opacity: 1 });
  const corners = [[460, 40, "border-right:0;border-bottom:0"], [1400, 40, "border-left:0;border-bottom:0"], [460, 970, "border-right:0;border-top:0"], [1400, 970, "border-left:0;border-top:0"]]
    .map(([x, y, st]) => html(`<i class="photoframe" style="left:${x}px;top:${y}px;${st}"></i>`, holder));
  zoomIn(s.cam, t0); cue("page", t0 + 0.02);
  const flash = html(`<div class="abs" style="inset:0;background:#fff;opacity:0;z-index:30"></div>`, s.el);
  const tShot = t0 + 0.55;
  tl.to(flash, { opacity: 0.85, duration: 0.05 }, tShot); tl.to(flash, { opacity: 0, duration: 0.4, ease: "power2.out" }, tShot + 0.05);
  cue("shutter", tShot);
  tl.to(corners, { opacity: 0, duration: 0.2 }, tShot + 0.1);
  // the photo goes into the phone; the lines come out, checked
  const ph = makePhone(s.cam, 1350, 518, 1.0), app = ph.app;
  layer(app, SH + "home.png", 0, 1);
  const dim = layer(app, LY + "scan_dim.png", 0, 2);
  const sh = layer(app, LY + "scan_sheet.png", 0, 3); const SY = (G.scan_sheet || { y: 381 }).y; $("img", sh).style.top = SY + "px";
  gsap.set(ph.el, { opacity: 0, y: 60 }); gsap.set(dim, { opacity: 0 }); gsap.set(sh, { y: 844 });
  tl.to(holder, { scale: 0.22, x: 840, y: 120, opacity: 0, duration: 0.7, ease: "power3.inOut" }, tShot + 0.35);
  tl.to(ph.el, { opacity: 1, y: 0, duration: SMOOTH.duration, ease: SMOOTH.ease }, tShot + 0.45);
  tl.to(dim, { opacity: 1, duration: 0.3 }, tShot + 0.9);
  tl.to(sh, { y: 0, duration: 0.55, ease: "sheet" }, tShot + 0.9); cue("sheet", tShot + 0.9);
  // the rows of "4 lines found" appear one by one (masked), each with a tick
  const rowY = [SY + 87, SY + 133, SY + 179, SY + 225, SY + 278];
  const covers = rowY.slice(0, 4).map((y, i) => html(`<div class="abs" style="left:24px;width:342px;top:${y - 2}px;height:${(rowY[i + 1] || y + 50) - y}px;background:#F7F6F3;z-index:4"></div>`, app));
  covers.forEach((c, i) => { tl.fromTo(c, { opacity: 1 }, { opacity: 0, duration: 0.25, ease: "power1.out" }, tShot + 1.5 + i * 0.22); cue("tick", tShot + 1.5 + i * 0.22, { gain: 0.3, pitch: i }); });
  tl.set(covers, { opacity: 1 }, t0);
  const h1 = textBlock(s.cam, "h m abs", "Old pages<br>count too.", "left:150px;top:330px;width:900px");
  const h2 = textBlock(s.cam, "sub2 abs", "You check every line<br>before it is saved.", "left:150px;top:560px;width:900px;font-size:44px");
  gsap.set([h1, h2], { opacity: 0 });
  tl.set([h1, h2], { opacity: 1 }, tShot + 0.5);
  rise(h1, tShot + 0.5); rise(h2, tShot + 1.4, { stagger: 0.03 });
  zoomOut(s.cam, s.end);
}

/* 9. N-ATLaS */
{
  const s = begin("natlas", "dark", 3), t0 = s.start, X = 250;
  zoomIn(s.cam, t0);
  const eb = textBlock(s.cam, "eyebrow abs", "Built on N-ATLaS", `left:${X}px;top:178px;color:var(--accent-d);font-size:36px`);
  const h = textBlock(s.cam, "h l abs", "Made for Nigerian<br>languages.", `left:${X}px;top:228px;width:1500px;color:#fff`);
  tl.fromTo(eb, { opacity: 0, y: 12 }, { opacity: 1, y: 0, duration: 0.6, ease: "apple" }, t0 + 0.15);
  rise(h, t0 + 0.3, { stagger: 0.05 });
  const rowsN = [["N-ATLaS", 69, "#8C9BFF", "#fff"], ["Llama 3 8B", 51, "#3A3A46", "#9A9AA3"]];
  rowsN.forEach(([n, v, c, tc], i) => {
    const y = 560 + i * 118, x0 = X + 330, W = 980;
    const lab = textBlock(s.cam, "abs", n, `left:${X}px;top:${y + 10}px;font-size:44px;font-weight:600;letter-spacing:-.02em;color:${tc}`);
    const bar = html(`<div class="bar" style="left:${x0}px;top:${y}px;height:78px;border-radius:16px;width:${v / 100 * W}px;background:${c};transform-origin:0 50%"></div>`, s.cam);
    const val = textBlock(s.cam, "abs num", "0%", `left:${x0 + v / 100 * W + 30}px;top:${y - 4}px;font-size:80px;font-weight:650;letter-spacing:-.04em;line-height:1;color:${tc}`);
    const tb = t0 + 1.05 + i * 0.28;
    tl.fromTo([lab, val], { opacity: 0 }, { opacity: 1, duration: 0.4 }, tb);
    tl.fromTo(bar, { scaleX: 0 }, { scaleX: 1, duration: 1.3, ease: "apple" }, tb);
    hooks.push(t => { if (t < tb || t > s.end) return; const p = clamp((t - tb) / 1.3), e = 1 - Math.pow(1 - p, 4); val.textContent = Math.round(v * e) + "%"; });
    cue("tick", tb, { gain: 0.3, pitch: i + 1 });
  });
  const cap = textBlock(s.cam, "abs", "Records read right, on 1,000 test sentences.<br>Llama 3 8B is the model N-ATLaS was built from.", `left:${X}px;top:822px;width:1400px;font-size:32px;font-weight:450;color:#9A9AA3;letter-spacing:-.012em;line-height:1.35`);
  tl.fromTo(cap, { opacity: 0 }, { opacity: 1, duration: 0.6 }, t0 + 2.1);
  const attr = textBlock(s.cam, "abs", "N-ATLaS is an initiative of the Federal Ministry of Communications, Innovation and Digital Economy, and powered by Awarri Technologies.", `left:${X}px;top:972px;width:1500px;font-size:24px;font-weight:450;color:#80808a;letter-spacing:-.005em;line-height:1.35`);
  tl.fromTo(attr, { opacity: 0 }, { opacity: 1, duration: 0.6 }, t0 + 0.4);
  drift(s.cam, t0, s.end, 1.025);
  zoomOut(s.cam, s.end);
  cue("natlas", t0, { bars: 3 });
}

/* 10. End card */
{
  const s = begin("end", "light", 3), t0 = s.start;
  zoomIn(s.cam, t0);
  const size = 190, logo = makeLogo(s.cam, 0, 0, size);
  const word = textBlock(s.cam, "wordmark abs", "TradeVoice", "font-size:124px;left:0;top:0");
  const ww = word.getBoundingClientRect().width, gap = 34, total = size * 0.92 + gap + ww, left = (1920 - total) / 2, cy = 330;
  gsap.set(logo, { x: left - size * 0.04, y: cy - size / 2 });
  gsap.set(word, { x: left + size * 0.92 + gap, y: cy - 74 });
  tl.fromTo(logo, { scale: 0.6, opacity: 0 }, { scale: 1, opacity: 1, duration: SNAPPY.duration, ease: SNAPPY.ease }, t0 + 0.05);
  danceBars(logo, t0 + 0.3, s.end + 1, 0.7);
  rise(word, t0 + 0.15, { by: "chars", stagger: 0.022, dur: 0.85 });
  const tag = textBlock(s.cam, "sub2 center", "Records that speak your language.", "top:470px;font-size:54px;color:var(--ink)");
  rise(tag, t0 + 0.5, { stagger: 0.04 });
  const url = textBlock(s.cam, "center", "tradevoice.duckdns.org", "top:600px;font-size:44px;font-weight:600;letter-spacing:-.02em;color:var(--accent)");
  const tg = textBlock(s.cam, "center", "Free on Telegram: @TradeVoiceNGbot &nbsp;·&nbsp; WhatsApp coming soon", "top:672px;font-size:32px;font-weight:450;color:var(--label2);letter-spacing:-.01em");
  tl.fromTo([url, tg], { opacity: 0, y: 12 }, { opacity: 1, y: 0, duration: 0.7, ease: "apple", stagger: 0.12 }, t0 + 0.9);
  const attr = textBlock(s.cam, "center", "N-ATLaS is an initiative of the Federal Ministry of Communications, Innovation and Digital Economy,<br>and powered by Awarri Technologies.", "top:900px;font-size:24px;font-weight:450;color:var(--label2);line-height:1.4");
  tl.fromTo(attr, { opacity: 0 }, { opacity: 1, duration: 0.6 }, t0 + 0.2);
  const tagV = voice("tagline");
  speak(tagV, t0 + 0.55);
  cue("end", t0);
  drift(s.cam, t0, s.end, 1.02);
}

/* ---------------------------------------------------------------- render API */
const duration = T;
window.FILM = { duration, fps: FPS, bar: BAR, shots: shots.map(s => ({ id: s.id, start: +s.start.toFixed(4), end: +s.end.toFixed(4), bars: s.bars })), cues: cues.sort((a, b) => a.t - b.t),
  subs: subs.map(s => ({ text: s.text, t0: +s.t0.toFixed(3), t1: +s.t1.toFixed(3) })), estimates: Object.keys(LINES).filter(id => !(D.voices || {})[id]) };
window.seek = t => { tl.totalTime(Math.min(t, duration - 1e-4), true); hooks.forEach(h => h(t)); };
tl.totalTime(0, true); hooks.forEach(h => h(0));
window.FILM_READY = true;
})();
