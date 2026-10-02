"""1,000 test sentences (200 per language) for the N-ATLaS benchmark: python eval/make_1000.py

Same traps and templates as make_hard_cases.py, drawn with many new seeds (new names, amounts, items, days and
combinations), keeping only sentences NOT already in cases_hard / cases_fresh. Template sentences are not real
traders: report them next to the team's own sentences (cases_team.jsonl) and the pilot's real voice notes.
"""
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(__file__))
import make_hard_cases as m  # noqa: E402

HERE = os.path.dirname(__file__)
PER_LANG = 200
seen = {json.loads(l)["text"] for f in ("cases_hard.jsonl", "cases_fresh.jsonl")
        for l in open(os.path.join(HERE, f), encoding="utf-8") if l.strip()}
picked = {lang: [] for lang in m.T}
seed = 1000
while any(len(v) < PER_LANG for v in picked.values()) and seed < 1400:
    m.rng = random.Random(seed)
    seed += 1
    for lang, cats in m.T.items():
        draws = [m.draw(lang, cat, typ, text, rule) for cat, ts in cats.items() for typ, text, rule in ts]
        typ, text, rule = m.rng.choice(cats["basic"][:2])
        draws.append(m.draw(lang, "amount_format", typ, text, rule, style=m.rng.choice(m.FORMATS + ["m"])))
        draws += [dict(c, category="asr_noise", text=m.noisy(c["text"], lang)) for c in draws[:2]]
        for c in draws:
            if c["text"] not in seen and len(picked[lang]) < PER_LANG:
                seen.add(c["text"])
                picked[lang].append(c)
out = os.path.join(HERE, "cases_1000.jsonl")
counters = {}
with open(out, "w", encoding="utf-8") as f:
    for lang, cases in picked.items():
        for c in cases:
            key = f"{lang[:2]}-{c['category']}"
            counters[key] = counters.get(key, 0) + 1
            f.write(json.dumps({"id": f"k-{key}-{counters[key]}", **c}, ensure_ascii=False) + "\n")
print(f"Wrote {sum(map(len, picked.values()))} cases to {out}: " + ", ".join(f"{k} {len(v)}" for k, v in picked.items()))
