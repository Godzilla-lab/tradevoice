/* The app icons from web/logo.svg, in the same layouts as before: the logo centred on white, 84% of the icon for
   the browser and home-screen icons, 60% for the maskable one (inside Android's round safe zone) and 64% for the
   WhatsApp profile picture. The bars stand still in a picture (the logo's animation is switched off here).
   Run it after changing the logo:   NODE_PATH=$(npm root -g) node scripts/make_icons.cjs
*/
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const WEB = path.join(__dirname, "..", "web");
const ICONS = [                       // file, size in px, share of the icon the logo takes
  ["apple-touch-icon.png", 180, 0.84],
  ["icon-192.png", 192, 0.84],
  ["icon-512.png", 512, 0.84],
  ["icon-maskable-512.png", 512, 0.60],
  ["whatsapp-profile-640.png", 640, 0.64],
];

(async () => {
  const svg = fs.readFileSync(path.join(WEB, "logo.svg"), "utf8")
    .replace("</style>", ".bar{animation:none!important}</style>");
  const src = "data:image/svg+xml;base64," + Buffer.from(svg).toString("base64");
  const browser = await chromium.launch();
  for (const [file, size, share] of ICONS) {
    const page = await browser.newPage({ viewport: { width: size, height: size }, deviceScaleFactor: 1 });
    const box = Math.round(size * share);
    await page.setContent(`<body style="margin:0;background:#fff"><div style="width:${size}px;height:${size}px;display:grid;place-items:center"><img src="${src}" width="${box}" height="${box}" alt=""></div></body>`);
    await page.waitForFunction(() => document.querySelector("img").complete);
    await page.screenshot({ path: path.join(WEB, file), clip: { x: 0, y: 0, width: size, height: size } });
    await page.close();
    console.log(`made web/${file} (${size} px, logo ${box} px)`);
  }
  await browser.close();
})();
