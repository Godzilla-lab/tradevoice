"""Makes the film's voice clips with Spitch text-to-speech. Runs ON THE SERVER (the Spitch key stays there), started
by film/voices.sh. Standard library only.

    SPITCH_API_KEY=... python voices.py lines.json OUT_DIR

For every line in lines.json, every listed voice and speed: POST https://api.spitch.app/v1/speech
{text, voice, language, speed, format: "wav"} -> 24 kHz mono WAV, saved as OUT_DIR/<line>__<voice>__<speed>.wav.
OUT_DIR/index.json lists them with their length. Two requests at a time (Spitch's first tier allows 3), retries
after Retry-After on 429/503. The key is never printed.
"""
import concurrent.futures as cf
import json
import os
import sys
import time
import urllib.error
import urllib.request
import wave

URL = os.getenv("SPITCH_BASE_URL", "https://api.spitch.app").rstrip("/") + "/v1/speech"


def speak(text, voice, language, speed):
    body = json.dumps({"text": text, "voice": voice, "language": language, "speed": speed,
                       "format": "wav"}).encode()
    head = {"Authorization": "Bearer " + os.environ["SPITCH_API_KEY"], "Content-Type": "application/json",
            "Accept": "audio/wav", "X-Data-Retention": "false", "User-Agent": "tradevoice-film/1"}
    for attempt in range(4):
        req = urllib.request.Request(URL, data=body, headers=head, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            said = e.read()[:300].decode("utf-8", "replace")
            if e.code in (429, 503) and attempt < 3:
                time.sleep(min(float(e.headers.get("Retry-After") or 3), 30))
                continue
            why = {401: "the Spitch key was refused", 402: "the Spitch account is out of credit",
                   422: "Spitch did not accept the request"}.get(e.code, f"Spitch said {e.code}")
            raise RuntimeError(f"{why}: {said}") from None


def main(lines_path, out):
    os.makedirs(out, exist_ok=True)
    os.chmod(out, 0o755)
    lines = json.load(open(lines_path, encoding="utf-8"))["lines"]
    jobs = [(ln, v, s) for ln in lines for v in ln["voices"] for s in ln["speeds"]]
    index, failed = [], []

    def one(job):
        ln, voice, speed = job
        name = f"{ln['id']}__{voice}__{speed:g}.wav"
        audio = speak(ln["text"], voice, ln["spitch_language"], speed)
        path = os.path.join(out, name)
        with open(path, "wb") as f:
            f.write(audio)
        os.chmod(path, 0o644)
        try:
            with wave.open(path) as w:
                secs = round(w.getnframes() / w.getframerate(), 3)
        except wave.Error:
            secs = None
        return {"file": name, "line": ln["id"], "voice": voice, "speed": speed, "seconds": secs}

    with cf.ThreadPoolExecutor(2) as pool:
        futs = {pool.submit(one, j): j for j in jobs}
        for fut in cf.as_completed(futs):
            ln, voice, speed = futs[fut]
            try:
                row = fut.result()
                index.append(row)
                print(f"  ok   {row['file']}  ({row['seconds']} s)")
            except Exception as e:  # noqa: BLE001
                failed.append(f"{ln['id']} {voice} {speed:g}: {e}")
                print(f"  FAIL {ln['id']} {voice} {speed:g}: {e}")
    index.sort(key=lambda r: r["file"])
    path = os.path.join(out, "index.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"made": time.strftime("%Y-%m-%d %H:%M:%S"), "clips": index, "failed": failed}, f, indent=1)
    os.chmod(path, 0o644)
    print(f"\n{len(index)} clips made, {len(failed)} failed.")
    return 0 if index else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
