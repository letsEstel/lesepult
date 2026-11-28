#!/usr/bin/env python3
"""Read the English entries of English Wiktionary (kaikki.org JSON lines) on stdin and write their German
translations as TSV on stdout:  english word, POS, sense (what the translation table is for), German word, tags.

  curl -sL …/kaikki.org-dictionary-English.jsonl | python3 extract_en.py > en-de.tsv

The full English dump is several GB, so it is streamed and never stored."""
import json, sys

out = sys.stdout
n = 0
for line in sys.stdin:
    if '"de"' not in line and '"German"' not in line:   # cheap pre-filter: most entries have no German translation
        continue
    try:
        d = json.loads(line)
    except ValueError:
        continue
    if d.get("lang_code", "en") != "en":
        continue
    word, pos = d.get("word", ""), d.get("pos", "")
    trs = list(d.get("translations") or [])
    for s in d.get("senses") or []:
        trs += s.get("translations") or []
    seen = set()
    for t in trs:
        if t.get("code") != "de" and t.get("lang") != "German":
            continue
        de = (t.get("word") or "").strip()
        if not de or len(de) > 60 or "\t" in de or (de, t.get("sense")) in seen:
            continue
        seen.add((de, t.get("sense")))
        sense = (t.get("sense") or "").replace("\t", " ").replace("\n", " ")[:120]
        out.write("\t".join([word, pos, sense, de, " ".join(t.get("tags") or [])]) + "\n")
        n += 1
print(f"英→德翻译：{n} 条", file=sys.stderr)
