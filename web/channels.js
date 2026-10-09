/* The website says what works today (window.TV_CH from the server, src/v2.py channels()). The design is written for
   a live WhatsApp bot; until it is, its WhatsApp buttons become "Open the app" (and "Use on Telegram" when the
   Telegram bot is set up), sign-up is described as number + password, and nothing promises a WhatsApp message.
   With WhatsApp live, nothing here changes the page. */
(() => {
  const C = window.TV_CH || { wa: true, codes: "whatsapp" };
  if (C.wa) return;
  const $$ = s => [...document.querySelectorAll(s)];
  const tg = C.tg ? `https://t.me/${C.tg}` : "";
  const say = (el, html) => { if (el) el.innerHTML = html; };
  const swap = (sel, from, to) => $$(sel).forEach(el => { if (el.innerHTML.includes(from)) el.innerHTML = el.innerHTML.split(from).join(to); });

  // the two "Use on WhatsApp" / "Try it on the web" pairs: the web app first, Telegram second (if there is a bot)
  $$(".cta").forEach(cta => {
    const wa = cta.querySelector('a[href^="https://wa.me/"]'), web = cta.querySelector('a[href="/app"]');
    if (!wa) return;
    if (web) { web.classList.add("p"); web.textContent = "Open the app"; cta.prepend(web); }
    if (tg && web) { wa.classList.remove("p"); wa.href = tg; wa.target = "_blank"; wa.rel = "noopener"; wa.textContent = "Use on Telegram"; }
    else if (web) wa.remove();
    else { wa.href = tg || "/app"; wa.textContent = tg ? "Start a chat on Telegram" : "Open the app"; if (tg) { wa.target = "_blank"; wa.rel = "noopener"; } }
  });

  // the WhatsApp section: Telegram today if there is a bot, WhatsApp next
  const sec = document.getElementById("whatsapp");
  if (sec) {
    say(sec.querySelector(".k"), tg ? "On Telegram" : "Coming next: WhatsApp");
    say(sec.querySelector(".sub"), tg
      ? "Prefer chatting? TradeVoice also answers on Telegram, in short messages with buttons you can press with one thumb. Send a voice note, a photo or a question. WhatsApp is coming next."
      : "TradeVoice inside WhatsApp, in short messages with buttons you can press with one thumb, is coming next. Until then, the app on the web does everything, on any phone.");
  }
  $$('a[href="#whatsapp"]').forEach(a => { a.textContent = tg ? "Telegram" : "WhatsApp (soon)"; });

  // words that promised WhatsApp
  swap("p", "Hold the mic, or send a WhatsApp voice note the way you would tell a friend.",
    tg ? "Hold the mic, or send a Telegram voice note the way you would tell a friend." : "Hold the mic and talk the way you would tell a friend.");
  if (C.nocode) {
    swap("p", "A phone number and a 6-digit code. No long forms. No card.", "A phone number and a password. No long forms. No card.");
    swap("details p", "A WhatsApp number, a 6-digit code and a password you choose.", "A phone number and a password you choose.");
  } else if (C.codes == "sms") {
    swap("p", "A phone number and a 6-digit code. No long forms. No card.", "A phone number and a 6-digit code by SMS. No long forms. No card.");
    swap("details p", "A WhatsApp number, a 6-digit code and a password you choose.", "A phone number, a 6-digit code by SMS and a password you choose.");
  }
  swap("details p", "Reset it in a minute with a code on WhatsApp or email. When you do, we log you out of your other phones.",
    (C.codes == "sms" ? "Reset it in a minute with a code by SMS."
      : tg ? "Reset it with a code from TradeVoice on Telegram, if you shared your number with the bot. Otherwise the TradeVoice team resets it for you."
      : "The TradeVoice team resets it for you.") + " When it is reset, we log you out of your other phones.");
  if (!C.codes) swap("details p", "Changing your number needs a fresh code, so nobody else can take over your book.",
    "Changing your number needs a fresh code, so nobody else can take over your book. Until codes can be sent, the TradeVoice team does it for you.");

  // App Store / Google Play "Soon": no WhatsApp message to promise; the web app works on any phone today
  const note = document.getElementById("soonnote");
  if (note) note.textContent = "Not in the stores yet. The app on the web works on any phone today: open it and add it to your home screen.";
  $$("[data-store]").forEach(a => { if (a.href.startsWith("https://wa.me/")) { a.href = "#download"; a.removeAttribute("target"); } });
})();
