"""Build the live app from the design: design/tradevoice-2.0/app.html -> web/app.html (+ web/live.js).

    python scripts/build_app.py

The design file is NEVER edited. This copies it, swaps a short list of exact logic snippets so accounts and
passwords live on the server (not in the phone's local storage), hides the design's test tools unless ?demo=1,
and loads web/live.js (real book, N-ATLaS hearing, reminders, scan, lender link). CSS and page structure are not
touched: eval/test_design.py checks they stay byte-identical. If the designer changes a snippet below, this script
stops and names it, so nothing is silently lost.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from plain import no_emoji_keep_layout  # noqa: E402
SRC = os.path.join(ROOT, "design", "tradevoice-2.0", "app.html")
OUT = os.path.join(ROOT, "web", "app.html")
LANDING_SRC = os.path.join(ROOT, "design", "tradevoice-2.0", "landing2.html")
LANDING_OUT = os.path.join(ROOT, "web", "landing.html")
# the website: "Open the app" goes to our app (the design pointed at a preview link); the design editor button only
# with ?demo=1. The WhatsApp links get the bot's number when the server sends the page (WHATSAPP_BOT_NUMBER).
LANDING_PATCHES = [
    ("app links", 'href="https://claude.ai/artifact/6R1XDoNUaLC2YsE7JjyFJD"', 'href="/app"', 4),
    # its settings key: "tv-ed-site", as the app's new editor names it (the app clears the old shared "tv-ed" key)
    ("editor button", '<script>\n(()=>{const K="tv-ed"',
     '<script>window.TV_NO_FAB=!/[?&]demo=1\\b/.test(location.search)</script>\n<script>\n(()=>{const K="tv-ed-site"', 1),
    ("logo", '<a class="logo" href="#top" aria-label="TradeVoice home"><svg viewBox="0 0 44 44" aria-hidden="true"><rect width="44" height="44" rx="13" fill="var(--accent)" stroke="none"/><g stroke="var(--accent-fg)" stroke-width="3.2"><path d="M13 19v6M19 14v16M25 10v24M31 17v10"/></g></svg>TradeVoice</a>',
     '<a class="logo" href="#top" aria-label="TradeVoice home"><img src="/static/logo.svg" alt="" aria-hidden="true" width="30" height="30">TradeVoice</a>', 1),
    ("tab icon", '<title>TradeVoice: just talk am. Your book remembers.</title>',
     '<title>TradeVoice: just talk am. Your book remembers.</title>\n<link rel="stylesheet" href="/static/site.css"><link rel="icon" href="/static/logo.svg" type="image/svg+xml"><link rel="apple-touch-icon" href="/static/apple-touch-icon.png"><link rel="manifest" href="/static/manifest.webmanifest"><meta name="apple-mobile-web-app-title" content="TradeVoice">', 1),
    # --- the example's sum: owed ₦45,000, paid ₦12,000 -> ₦33,000 left (not ₦0)
    ("example sum", 'Mama Tunde just paid ₦12,000 online. Still owes you ₦0.',
     'Mama Tunde paid ₦12,000. She still owes you ₦33,000.', 1),
    # --- the N-ATLaS licence requires this sentence wherever TradeVoice credits N-ATLaS
    # --- a forgotten PIN: log in again with the password (web/live.js recover), not "through WhatsApp"
    ("PIN answer", 'and if you forget the PIN you can get back in through WhatsApp.',
     'and if you forget the PIN, log in again with your password.', 1),
    ("N-ATLaS attribution", 'Nigeria’s own multilingual AI model.</div>',
     'Nigeria’s own multilingual AI model.<br>N-ATLaS is an initiative of the Federal Ministry of Communications, Innovation and Digital Economy, and powered by Awarri Technologies.</div>', 1),
]

PATCHES = [
    # --- a deleted account is kept 90 days (src/v2.py DELETE_DAYS), and the privacy notice is a real page
    ("delete days", 'Your records, customers and settings are deleted after 7 days. Log in before then to cancel.',
     'Your records, customers and settings are deleted after 90 days. Log in before then to cancel.'),
    ("delete toast", 'Account scheduled for deletion. Log in within 7 days to cancel.',
     'Account scheduled for deletion. Log in within 90 days to cancel.'),
    ("privacy link", 'priv:()=>toast("Privacy notice opens here.")', 'priv:()=>open("/privacy","_blank")'),
    ("improve row", '${B("Privacy notice","","priv")}',
     '${B("Privacy notice","","priv")}${window.TVL&&TVL.trainRow?B(...TVL.trainRow(),"train"):""}'),
    ("improve action", 'del:delSheet};', 'del:delSheet,train:()=>TVL.trainSheet()};'),
    ("privacy at sign-up", 'I agree to the Terms and the Privacy Notice.',
     'I agree to the Terms and the <a href="/privacy" target="_blank" style="color:var(--accent)">Privacy Notice</a>.'),
    # --- 4 languages to choose (Pidgin is still understood: it is English's voice and the brain reads it)
    ("no Pidgin tile", 'LG=[["en","English"],["pcm","Pidgin"],', 'LG=[["en","English"],'),
    # --- the N-ATLaS licence sentence in Me > About
    ("N-ATLaS attribution (app)", 'R("Powered by N-ATLaS","Nigeria\'s own AI model","")',
     'R("Powered by N-ATLaS","Nigeria\'s own AI model. N-ATLaS is an initiative of the Federal Ministry of Communications, Innovation and Digital Economy, and powered by Awarri Technologies.","")'),
    # --- the TradeVoice logo (web/logo.svg, the animated mic in a speech bubble) and the browser tab / home screen icon
    ("logo", 'const LOGO=\'<svg class="lg" viewBox="0 0 44 44" aria-hidden="true"><rect width="44" height="44" rx="13" fill="var(--accent)" stroke="none"/><g stroke="var(--accent-fg)" stroke-width="3.2"><path d="M13 19v6M19 14v16M25 10v24M31 17v10"/></g></svg>\';',
     'const LOGO=\'<img class="lg" src="/static/logo.svg" alt="" aria-hidden="true" style="display:block">\';'),
    ("tab icon", '<title>TradeVoice</title>', '<title>TradeVoice</title>\n<link rel="icon" href="/static/logo.svg" type="image/svg+xml"><link rel="apple-touch-icon" href="/static/apple-touch-icon.png"><link rel="manifest" href="/static/manifest.webmanifest"><meta name="apple-mobile-web-app-title" content="TradeVoice">'),
    # --- typing an amount: the key handler returned false for every key but Enter, which cancels the key in a browser
    ("amount keys (You got/gave)", 'fn(v);shut(o)};$("#go",o).onclick=g;i.onkeydown=e=>e.key=="Enter"&&g()}',
     'fn(v);shut(o)};$("#go",o).onclick=g;i.onkeydown=e=>{if(e.key=="Enter")g()}}'),
    ("amount keys (design talk)", 'amt=+v;card()};$("#go",o).onclick=g;i.onkeydown=e=>e.key=="Enter"&&g()}',
     'amt=+v;card()};$("#go",o).onclick=g;i.onkeydown=e=>{if(e.key=="Enter")g()}}'),
    # --- Me > Voice replies: a real switch (web/live.js keeps the choice on this phone)
    ("voice switch", 'sw("voice",true,"Voice replies")', 'sw("voice",!window.TVL||TVL.voiceOn(),"Voice replies")'),
    # --- no sample customers on screen before the real book loads (the design starts with made-up ones)
    ("no sample data", 'let C=seed();', 'let C=[];'),
    ("no sample totals", 'inN=128500,outN=40000,', 'inN=0,outN=0,'),
    # --- accounts come from the server, not a list in local storage
    ("load", 'function load(){loadAll();const k=ss.get("tv-sess")||st.get("tv-sess");A=k&&AC[k]||null}',
     'function load(){A=null}'),
    ("persist", 'function persist(){if(A){AC[A.phone]=A;saveAll()}}', 'function persist(){if(A)TVL.persist(A)}'),
    ("logout", 'function logout(){ss.del("tv-sess")', 'function logout(){TVL.logout();ss.del("tv-sess")'),
    ("boot", 'if(A&&(ss.get("tv-sess")||st.get("tv-sess"))){if(A.delAt)GO.restore();else if(pin)pinGate("unlock")}'
             'else if(Object.keys(AC).length)GO.login();else welcome();', ''),
    # --- sign up: number -> WhatsApp code -> password -> business
    ("signup exists", '$("#go").onclick=()=>{err("ph","");$("#ag-e").textContent="";',
     '$("#go").onclick=async()=>{err("ph","");$("#ag-e").textContent="";'),
    ("signup exists 2", 'loadAll();if(AC[p])return err("ph",', 'if(await TVL.exists(p))return err("ph",'),
    ("signup code", 'verify($("#vh"),{label:mphone(SU.ph),onOk:GO.su3,',
     'verify($("#vh"),{phone:SU.ph,purpose:"signup",label:mphone(SU.ph),onOk:lid=>{SU.lid=lid;GO.su3()},'),
    ("signup finish", '$("#go").onclick=()=>{["on","bn"].forEach(i=>err(i,""));const n=val("on")',
     '$("#go").onclick=async()=>{["on","bn"].forEach(i=>err(i,""));const n=val("on")'),
    ("signup save", 'loadAll();AC[a.phone]=a;saveAll();A=a;SU={};st.set("tv-sess",a.phone);ss.del("tv-sess");C=[];',
     'if(offline())return err("bn","You\'re offline. Connect to create your account.");'
     'if(!await TVL.signup(SU,a))return err("bn","Something went wrong. Start again.");SU={};C=[];'),
    # --- log in with password (checked on the server; 5 wrong tries -> wait 30 s)
    ("login", 'const r=askId();if(!r)return;if(!r.acct)return err("id",`We couldn\'t find an account with that ${r.em?"email":"number"}. <button data-g="signup">Create one</button>`);\n'
              '  if((await hash($("#lp").value))!==r.acct.pw){lf++;if(lf>=5){lu=Date.now()+3e4;lf=0;return err("lp","Too many tries. Wait 30s, or reset your password.")}return err("lp",`That password isn\'t right.${lf>=2?` <button data-g="forgot">Reset it</button>`:""}`)}\n'
              '  lf=0;A=r.acct;startSession($("#kp").checked)}};',
     'const r=askId();if(!r)return;const x=await TVL.login(r.key,await hash($("#lp").value),$("#kp").checked);'
     'if(x=="missing")return err("id",`We couldn\'t find an account with that ${r.em?"email":"number"}. <button data-g="signup">Create one</button>`);'
     'if(x=="locked")return err("lp","Too many tries. Wait 30s, or reset your password.");'
     'if(x!="ok"){lf++;return err("lp",`That password isn\'t right.${lf>=2?` <button data-g="forgot">Reset it</button>`:""}`)}'
     'lf=0;startSession($("#kp").checked)}};'),
    ("askId", 'loadAll();return{em,key,acct:Object.values(AC).find(a=>em?(a.email&&a.emailOk&&a.email.toLowerCase()==key):a.phone==key)}}',
     'return{em,key,acct:null}}'),
    # --- log in with a WhatsApp code
    ("otp login", '$("#go").onclick=()=>{err("id","");const p=normPhone(val("id"));if(!okPhone(p))return err("id","Enter a valid Nigerian number, like 803 123 4567.");if(offline())return err("id","No network. Check your data and try again.");loadAll();const a=AC[p];if(!a)',
     '$("#go").onclick=async()=>{err("id","");const p=normPhone(val("id"));if(!okPhone(p))return err("id","Enter a valid Nigerian number, like 803 123 4567.");if(offline())return err("id","No network. Check your data and try again.");const a=await TVL.exists(p);if(!a)'),
    ("otp login 2", 'verify($("#ob"),{label:mphone(p),onOk:()=>{A=a;startSession(true)},',
     'verify($("#ob"),{phone:p,purpose:"login",label:mphone(p),onOk:lid=>TVL.loginCode(lid,true),'),
    # --- forgot password: code, then a new password (every other phone is logged out)
    ("forgot", 'FP={acct:r.acct};$("#fb").innerHTML="";verify($("#fb"),{label:maskId(r.em,r.key),ch:r.em?"email":"whatsapp",ghost:!r.acct,onOk:GO.fp3,',
     'if(r.em)return err("id","Use your phone number. Email reset comes later.");FP={phone:r.key};$("#fb").innerHTML="";'
     'verify($("#fb"),{phone:r.key,purpose:"reset",label:maskId(r.em,r.key),onOk:lid=>{FP.lid=lid;GO.fp3()},'),
    ("reset", 'old:FP.acct.pw,phone:FP.acct.phone,ok:h=>{const a=FP.acct;a.pw=h;a.dev=a.dev.filter(d=>d.id=="this");AC[a.phone]=a;saveAll();ag(',
     'phone:FP.phone,ok:async h=>{if(!await TVL.reset(FP.lid,h))return err("pw","Pick a password you haven\'t used here.");ag('),
    ("restore", '$("#rs").onclick=()=>{delete A.delAt;persist();', '$("#rs").onclick=async()=>{await TVL.restore();delete A.delAt;'),
    # --- passwords never compared on the phone
    ("pwUI", 'const h=await hash(p);if(o.cur&&(await hash($("#cp",box).value))!==A.pw)return err("cp","That isn\'t your current password.");\n'
             '  if(o.old&&h===o.old)return err("pw","Pick a password you haven\'t used here.");o.ok(h)}}',
     'const h=await hash(p);o.ok(h,o.cur?await hash($("#cp",box).value):null)}}'),
    ("pwSheet", 'phone:A.phone,old:A.pw,ok:h=>{A.pw=h;A.dev=A.dev.filter(d=>d.id=="this");persist();',
     'phone:A.phone,ok:async(h,c)=>{const x=await TVL.password(c,h);if(x=="wrong")return err("cp","That isn\'t your current password.");'
     'if(x=="same")return err("pw","Pick a password you haven\'t used here.");if(x!="ok")return err("pw2","Couldn\'t change it. Try again.");'),
    ("delete", 'if((await hash($("#dp").value))!==A.pw)return err("dp","That password isn\'t right.");A.delAt=Date.now()+7*864e5;persist();',
     'const x=await TVL.del(val("cf"),await hash($("#dp").value));if(x=="wrong")return err("dp","That password isn\'t right.");'
     'if(x=="biz")return err("cf","That isn\'t your business name.");if(typeof x!="number")return err("dp","Couldn\'t delete. Try again.");A.delAt=x;'),
    ("devices", 'A.dev=k=="all"?A.dev.filter(d=>d.id=="this"):A.dev.filter(d=>d.id!=k);persist();draw();toast("Logged out.")',
     'TVL.devOut(k).then(()=>{draw();toast("Logged out.")})'),
    # --- change number (code to the new one) / email (saved; verification comes with email sending)
    ("phone async", '$("#go",o).onclick=()=>{err("np","");', '$("#go",o).onclick=async()=>{err("np","");'),
    ("phone exists", 'loadAll();if(AC[p])return err("np","Another account already uses that number.");',
     'if(await TVL.exists(p))return err("np","Another account already uses that number.");'),
    ("phone verify", 'verify($("#pb",o),{label:mphone(p),back:"Change number",onBack:()=>{shut(o);setTimeout(phoneSheet,350)},onOk:()=>{delete AC[A.phone];const old=A.phone;A.phone=p;AC[p]=A;saveAll();',
     'verify($("#pb",o),{phone:p,purpose:"phone",label:mphone(p),back:"Change number",onBack:()=>{shut(o);setTimeout(phoneSheet,350)},onOk:async lid=>{const old=A.phone;if(!await TVL.phone(lid))return;'),
    ("email", 'loadAll();if(Object.values(AC).some(a=>a!==A&&a.email&&a.email.toLowerCase()==e.toLowerCase()))return err("em","Another account already uses that email.");\n'
              '  verify($("#pb",o),{label:e.replace(/^(.).*(@.*)$/,"$1••••$2"),ch:"email",back:"Change email",onBack:()=>{shut(o);setTimeout(emailSheet,350)},onOk:()=>{A.email=e;A.emailOk=true;persist();shut(o);all();toast("Email verified.")}})};',
     'TVL.email(e).then(x=>{if(x=="taken")return err("em","Another account already uses that email.");if(x!="ok")return err("em","Couldn\'t save it. Try again.");A.email=e;A.emailOk=false;shut(o);all();toast("Email saved.")})};'),
    # --- payout account: the real account name (Paystack), never the trader's own name pretending to be checked
    ("payout check", '$("#nm",o).textContent="Checking…";await sleep(900);if(!o.isConnected)return;$("#nm",o).innerHTML=`<b style="color:var(--pos);font-weight:500">✓ ${esc(A.name.toUpperCase())}</b><br>Is this you? If not, check the number.`;ok=true;',
     '$("#nm",o).textContent="Checking…";const nmv=await TVL.resolve($("#bk",o).value,n);if(!o.isConnected)return;o.an=nmv||"";$("#nm",o).innerHTML=nmv?`<b style="color:var(--pos);font-weight:500">✓ ${esc(nmv)}</b><br>Is this you? If not, check the number.`:"";ok=true;'),
    ("payout save", 'A.acctName=A.name.toUpperCase();persist();', 'A.acctName=o.an||"";persist();'),
    # --- money moves go to the book
    ("got", 'amtSheet("You got",v=>{const x=Math.min(v,c.b);c.b-=x;c.h.unshift(["Paid me",-x,"Today"]);inN+=x;if(!c.b)c.late=0;all();toast(`${f(x)} recorded. ${c.b?"Still owes "+f(c.b)+".":"Fully paid."}`)});',
     'amtSheet("You got",v=>TVL.got(c,v));'),
    ("gave", 'amtSheet("You gave",v=>{c.b+=v;c.h.unshift(["Sold on credit",v,"Today"]);all();toast(`${f(v)} added. ${first(c.n)} owes ${f(c.b)}.`)});',
     'amtSheet("You gave",v=>TVL.gave(c,v));'),
    # --- Ask: anything the quick answers don't cover goes to N-ATLaS
    # --- Home: Today / Week / Month / Year / 60 days (the design's own segmented switch; web/live.js keeps the choice
    #     and asks the server for that period's money in / money out)
    ("home period", '$("#home").innerHTML=`<h1 class="lt">${t("today")}<small>${gt()}, ${nm()}</small></h1><div class="hero"><p>Net today</p>',
     '$("#home").innerHTML=`<div class="ah perh"><h1 class="lt">${window.TVL?TVL.perTitle():t("today")}<small>${gt()}, ${nm()}</small></h1>${window.TVL?TVL.perPick():""}</div><div class="hero"><p>${window.TVL?TVL.netLabel():"Net today"}</p>'),
    # --- Ask chat: answers, photos and voice come from the server (web/live.js gives areply / aimg / AX.avoice
    #     their real versions); the design's own guesser and fake photo reader are not used
    ("ask answer", 'if(im)rep=await aimg();else{await sleep(650);rep=areply(text)}',
     'if(im)rep=await aimg(im,text);else rep=await areply(text,how)'),
    ("ask photo file", 'try{apend=await athumb(f0);arefresh();', 'try{apend=await athumb(f0);TVL.pick=f0;arefresh();'),
    ("ask check lines", '${m.act?`<button class="btn p" data-a="achk"', '${m.act?`<button class="btn p" data-a="achk" data-ts="${m.ts}"'),
    ("ask listen", '${m.t?`<p>${esc(m.t)}</p>`:""}', '${m.t?`<p>${esc(m.t)}</p>`:""}${m.r=="a"&&m.t?TVL.listenBtn(m):""}'),
    ("ask clear", '()=>{AH=[];asave();arefresh()}', '()=>{AH=[];asave();arefresh();TVL.askReset()}'),
    # --- a book refresh (after every answer) redraws every tab: the Ask box keeps what you are typing (and the cursor)
    ("ask keeps typing", 'function ask(){window.ask2&&ask2()}', 'function ask(){window.arefresh?arefresh():window.ask2&&ask2()}'),
    # --- the design's test tools (scenarios, empty book, design editor): only with ?demo=1
    ("demo tools", '<h2>Make it yours</h2>', '${TVL.demo?`<h2>Make it yours</h2>'),
    ("demo tools 2", '${R("Empty book","See the first-time screens",sw("empty",!C.length,"Empty book"))}',
     '${R("Empty book","See the first-time screens",sw("empty",!C.length,"Empty book"))}</ul>`:""}<ul hidden>'),
    # --- which ways in work today (the server puts window.TV_CH in the page, src/v2.py channels()): no WhatsApp yet
    #     -> sign up with number + password (no code), "log in with a code" only where a code can arrive (Telegram for
    #     numbers shared with the bot), nothing promises WhatsApp. Without TV_CH (a file opened by hand): as designed.
    ("channels", 'const $=(s,r=document)=>r.querySelector(s)',
     'const CH=window.TV_CH||{codes:"whatsapp",wa:true,sms:false,tg:"",nocode:false,team:""};const $=(s,r=document)=>r.querySelector(s)'),
    ("pin lockout", 'Too many tries. Wait ${s}s, or use WhatsApp.', 'Too many tries. Wait ${s}s.'),
    ("pin forgot", 'Forgot PIN? Get back in with WhatsApp', 'Forgot PIN?'),
    ("welcome line", 'A phone number and a 6-digit code. No long forms.',
     '${CH.nocode?"A phone number and a password. No long forms.":"A phone number and a 6-digit code. No long forms."}'),
    ("sign-up why", 'We use it to keep your book safe and to send your code on WhatsApp.',
     '${CH.nocode?"We use it to keep your book safe. It is how you log in.":CH.codes=="sms"?"We use it to keep your '
     'book safe and to send your code by text message.":"We use it to keep your book safe and to send your code on '
     'WhatsApp."}'),
    ("sign-up label", 'fld("ph","WhatsApp number",', 'fld("ph",CH.codes=="whatsapp"?"WhatsApp number":"Phone number",'),
    ("sign-up step 2", '<h1 class="sm">Check WhatsApp</h1>',
     '<h1 class="sm">${CH.nocode?"One moment":CH.codes=="sms"?"Check your phone":"Check WhatsApp"}</h1>'),
    ("code log in link", ' · <button data-g="otpin" style="text-decoration:underline">Log in with a WhatsApp code</button>',
     '${CH.codes||CH.tg?` · <button data-g="otpin" style="text-decoration:underline">Log in with a code</button>`:""}'),
    ("code log in where", "We'll send a code to your WhatsApp.",
     '${CH.codes=="whatsapp"?"We\'ll send a code to your WhatsApp.":CH.codes=="sms"?"We\'ll send a code to your phone.":'
     '"We\'ll send it to TradeVoice on Telegram, if you shared your number with the bot."}'),
    ("reset where", "Enter your phone number or email. We'll send a code.",
     '${CH.codes=="whatsapp"?"Enter your phone number or email. We\'ll send a code.":CH.codes=="sms"?"Enter your '
     'phone number. We\'ll send a code to it.":"Enter your phone number. If you shared it with TradeVoice on '
     'Telegram, the code comes there."}'),
    ("notifications where", 'We send these on WhatsApp. You can stop them any time.',
     '${CH.wa?"We send these on WhatsApp. You can stop them any time.":CH.tg?"We send these on Telegram once you '
     'share your number with the TradeVoice bot. You can stop them any time.":"These come on WhatsApp once the '
     'TradeVoice bot is live."}'),
    ("connect rows", 'B("Connect my WhatsApp","Keep one book on both","wac")',
     '(CH.wa?B("Connect my WhatsApp","Keep one book on both","wac"):"")}'
     '${CH.tg?B("Connect my Telegram","Use your book from Telegram too","tgc"):""'),
    ("log out text", "You'll need your password or a WhatsApp code to come back.", "You'll need your password to come back."),
]


def build():
    html = open(SRC, encoding="utf-8").read()
    missing = []
    for name, old, new in PATCHES:
        n = html.count(old)
        if n != 1:
            missing.append(f"{name} (found {n} times)")
            continue
        html = html.replace(old, new)
    if missing:
        sys.exit("The design changed; update these swaps in scripts/build_app.py:\n  " + "\n  ".join(missing))
    html = no_emoji_keep_layout(html)   # words only, no emojis (the owner's rule): the design's 🎉 💸 go
    html = html.replace("</body>", '<script src="/static/live.js"></script>\n</body>', 1)
    html = html.replace("<!doctype html>", "<!doctype html>\n<!-- BUILT from design/tradevoice-2.0/app.html by "
                        "scripts/build_app.py: edit the design or the script, not this file -->", 1)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"built {os.path.relpath(OUT, ROOT)} from the design ({len(PATCHES)} logic swaps)")
    page = open(LANDING_SRC, encoding="utf-8").read()
    for name, old, new, times in LANDING_PATCHES:
        if page.count(old) != times:
            sys.exit(f"The website design changed; update '{name}' in scripts/build_app.py")
        page = page.replace(old, new)
    page = no_emoji_keep_layout(page)
    with open(LANDING_OUT, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"built {os.path.relpath(LANDING_OUT, ROOT)} from the website design")


if __name__ == "__main__":
    build()
