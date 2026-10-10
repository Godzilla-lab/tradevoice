"""Live proof that TradeVoice runs on N-ATLaS, for the NAIC upload "Evidence artefacts demonstrating integration".
It calls N-ATLaS the way the app does, on the live server, and prints what happened:
  A. what our two Modal apps serve (the N-ATLaS language model, the four N-ATLaS speech models);
  B. five live record calls, one per language: a made-up sentence in, N-ATLaS's JSON out, time, and the record after
     the app's code checks;
  C. five live speech round trips: a made-up sentence made into audio by the app's voice (Intron), heard by the
     N-ATLaS speech model for that language (Yoruba, Hausa and Igbo also by the English model, merged by N-ATLaS);
  D. N-ATLaS in the pilot: counts from the live log (no words, names, numbers or amounts; the team left out).
Sentences are the first of each language in eval/cases_1000.jsonl (made-up names). Its own calls are not counted in
the pilot log. It never prints a key: hosts only, errors masked. Safe to paste to anyone.
On the live server: see deploy/server/natlas_evidence.sh.   Here: python scripts/natlas_evidence.py --out FILE
"""
import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time
from urllib.parse import urlparse

ROOT = os.getenv("TV_APP") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import settings  # noqa: E402,F401  (loads .env)

ATTRIBUTION = ("N-ATLaS is an initiative of the Federal Ministry of Communications, Innovation and Digital Economy, "
               "and powered by Awarri Technologies.")
SECRET_WORDS = ("KEY", "TOKEN", "SECRET", "PASSWORD")
# case-file language -> (voice language for tts.speak, hearing language for the N-ATLaS speech app, label)
LANGS = [("english", "English", "english", "English"), ("pidgin", "Pidgin", "english", "Pidgin"),
         ("yoruba", "Yoruba", "yoruba", "Yorùbá"), ("hausa", "Hausa", "hausa", "Hausa"), ("igbo", "Igbo", "igbo", "Igbo")]
OUT = []


def say(line=""):
    OUT.append(line)
    print(line, flush=True)


def scrub(text):
    text = str(text or "")
    for name, value in os.environ.items():
        if value and len(value) >= 6 and any(w in name.upper() for w in SECRET_WORDS):
            text = text.replace(value, "***")
    return text.replace("Bearer ", "Bearer ***")[:300]


def host(url):
    return urlparse(url or "").hostname or "(not set)"


def head():
    return {"Authorization": f"Bearer {os.getenv('NATLAS_KEY', '')}"}


def section(title):
    say()
    say("=" * 78)
    say(title)
    say("=" * 78)


def cases():
    rows = [json.loads(line) for line in open(os.path.join(ROOT, "eval", "cases_1000.jsonl"), encoding="utf-8")]
    first = {}
    for r in rows:
        first.setdefault(r["lang"], r)
    return first


def quiet_log():
    """This script's own calls stay out of the pilot's numbers."""
    import events
    events.log = lambda *a, **k: None


# ---------------------------------------------------------------- A. what is served
def served():
    import requests
    section("A. What our servers run (asked live)")
    url = os.getenv("NATLAS_URL", "").rstrip("/")
    say(f"N-ATLaS language model server: {host(url)} (Modal, vLLM, OpenAI-compatible API)")
    t0 = time.perf_counter()
    r = requests.get(url + "/models", headers=head(), timeout=300)
    r.raise_for_status()
    for m in r.json().get("data", []):
        say(f"  served model: {m.get('id')}  <- weights: {m.get('root') or m.get('id')}  "
            f"(max context {m.get('max_model_len', '?')} tokens)")
    say(f"  answered in {time.perf_counter() - t0:.1f} s")
    asr = os.getenv("NATLAS_ASR_URL", "").rstrip("/")
    say(f"N-ATLaS speech server: {host(asr)} (Modal)")
    t0 = time.perf_counter()
    r = requests.get(asr + "/health", headers=head(), timeout=300)
    r.raise_for_status()
    for lang, model in (r.json().get("models") or {}).items():
        say(f"  {lang:<8} -> {model}")
    say(f"  answered in {time.perf_counter() - t0:.1f} s")


# ---------------------------------------------------------------- B. live record calls
def records(first):
    import extract
    import llm
    section("B. Live record calls: the trader's words -> N-ATLaS -> JSON record -> code checks")
    say("Each call is pinned to N-ATLaS (no backup model), with the app's own prompt, worked examples and JSON schema")
    say("(src/extract.py _rec_call, vLLM guided decoding). 'Expected' is the answer key from eval/cases_1000.jsonl.")
    today = dt.date.today()
    right = 0
    for code, _, _, label in LANGS:
        c = first[code]
        say()
        say(f"[{label}] {c['text']}")
        try:
            messages, kw = extract._rec_call(c["text"], today, None)
            kw.update(models=["natlas"], timeout=300, deadline=330, long=True, early_ok=False)
            t0 = time.perf_counter()
            content, used = llm.chat(messages, **kw)
            ms = (time.perf_counter() - t0) * 1000
            if not llm.is_natlas(used):
                say(f"  N-ATLaS did not answer (got: {used or 'nothing'})")
                continue
            raw = extract._parse_json(content)
            rules = extract.rule_extract(c["text"], today)
            rec = extract._normalise(dict(raw), c["text"], today)
            for k in ("amount", "customer", "quantity", "unit", "item"):
                if rec.get(k) in (None, "") and rules.get(k) is not None:
                    rec[k] = rules[k]
            rec = extract._check_guard(extract._sell_guard(rec, rules, c["text"]), rules, c["text"], today)
            say(f"  answered by: {used} in {ms:,.0f} ms")
            say(f"  N-ATLaS JSON: {json.dumps(raw, ensure_ascii=False)}")
            keep = {k: rec.get(k) for k in ("type", "amount", "customer", "item", "quantity", "unit", "due_date")}
            say(f"  after code checks: {json.dumps(keep, ensure_ascii=False)}")
            ok = (rec.get("type") == c["type"] and float(rec.get("amount") or 0) == float(c["amount"] or 0)
                  and (rec.get("customer") or None) == (c.get("customer") or None))
            right += ok
            say(f"  expected: type {c['type']}, amount {c['amount']}, customer {c.get('customer')}  ->  "
                f"{'matches' if ok else 'DOES NOT match'}")
        except Exception as e:  # noqa: BLE001
            say(f"  could not run: {scrub(e)}")
    say()
    say(f"{right} of {len(LANGS)} records match the answer key.")


# ---------------------------------------------------------------- C. live speech round trips
def speech(first):
    import requests
    import hearing
    import tts
    section("C. Live speech: audio -> N-ATLaS speech model -> words")
    say("The test audio is made by the app's voice (Intron text-to-speech) from the same made-up sentences: no trader's")
    say("voice is used. Yoruba, Hausa and Igbo audio is also heard by NigerianAccentedEnglish, and the N-ATLaS language")
    say("model merges the two hearings, as the app does (src/asr.py _natlas_transcribe, src/hearing.py merge).")
    base = os.getenv("NATLAS_ASR_URL", "").rstrip("/")
    for code, voice_lang, hear_lang, label in LANGS:
        c = first[code]
        say()
        say(f"[{label}] said: {c['text']}")
        try:
            out = tts.speak(c["text"], voice_lang)
            if not out:
                say(f"  skipped: no test audio ({scrub(tts.why_not_intron() or 'the voice is off')})")
                continue
            also = "english" if hear_lang != "english" else ""
            t0 = time.perf_counter()
            with open(out["path"], "rb") as f:
                r = requests.post(base + "/transcribe", files={"file": ("test.wav", f)}, headers=head(), timeout=300,
                                  data={"lang": hear_lang, "prompt": "", "prep": "1", "also": also})
            r.raise_for_status()
            j = r.json()
            ms = (time.perf_counter() - t0) * 1000
            say(f"  heard by {j.get('model')} in {ms:,.0f} ms ({j.get('seconds', '?')} s of audio): {j.get('text', '').strip()}")
            second = j.get("also") if isinstance(j.get("also"), dict) else None
            if second:
                say(f"  also heard by {second.get('model', 'NCAIR1/NigerianAccentedEnglish')}: {(second.get('text') or '').strip()}")
                merged, how = hearing.merge(j.get("text"), second.get("text"), hear_lang.title())
                say(f"  merged by N-ATLaS ({how}): {merged}")
            try:
                os.remove(out["path"])
            except OSError:
                pass
        except Exception as e:  # noqa: BLE001
            say(f"  could not run: {scrub(e)}")


# ---------------------------------------------------------------- D. the pilot's own log
def pilot(start, end):
    import validation_report as vr
    section(f"D. N-ATLaS in real use: the live app's log, {start} to {end} (counts only; the team left out)")
    a = dt.datetime.combine(dt.date.fromisoformat(start), dt.time(), vr.WAT)
    b = dt.datetime.combine(dt.date.fromisoformat(end) + dt.timedelta(days=1), dt.time(), vr.WAT)
    d = vr.collect(a, b)
    say(f"traders: {d['traders']}   sign-ups: {d['signups']}   conversations: {d['conversations']}   "
        f"records saved: {d['records']}")
    share = f"{d['natlas_share']}%" if d["natlas_share"] is not None else "n/a"
    say(f"AI answers: {d['ai_answers']}, of which N-ATLaS: {share}   (N-ATLaS failed to answer {d['natlas_failed']} time(s))")
    for k, v in d["models"].items():
        say(f"  {k:<40} {v}")
    say(f"voice notes heard: {d['voice_heard']}")
    for k, v in d["hearing"].items():
        say(f"  {k:<40} {v}")
    if d["reply_s"] is not None:
        say(f"median time from the trader's words to the reply: {d['reply_s']} s")
    say(f"phones left out as the team's own: {d['team_left_out']}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--start", default="2026-10-06", help="pilot log from (Lagos day), YYYY-MM-DD")
    ap.add_argument("--end", default=dt.date.today().isoformat(), help="to (included)")
    ap.add_argument("--out", default="")
    a = ap.parse_args(argv)
    say("TradeVoice: live evidence of the N-ATLaS integration")
    say(f"Made {dt.datetime.now(dt.timezone(dt.timedelta(hours=1))):%Y-%m-%d %H:%M} (Lagos) on the live server, "
        f"code {os.getenv('TV_COMMIT', '?')}. Live app: https://tradevoice.duckdns.org")
    first = cases()
    for step in (lambda: pilot(a.start, a.end), quiet_log, served, lambda: records(first), lambda: speech(first)):
        try:
            step()
        except Exception as e:  # noqa: BLE001  (one part failing never stops the others)
            say(f"  could not run this part: {scrub(e)}")
    say()
    say(ATTRIBUTION)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write("\n".join(OUT) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
