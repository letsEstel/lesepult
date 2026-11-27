#!/usr/bin/env python3
"""Build Lesepult's German–English dictionary (docs/wb/) from open data.

  python3 scripts/dict/build_dict.py SRC_DIR [-o docs/wb]

SRC_DIR holds what scripts/dict/fetch.sh downloaded (any missing source is skipped):
  kaikki.jsonl            German entries of English Wiktionary, extracted by wiktextract (kaikki.org)   CC BY-SA 4.0
  deu_sentences.tsv       Tatoeba German sentences (id, lang, text)                                     CC BY 2.0 FR
  eng_sentences.tsv       Tatoeba English sentences
  deu-eng_links.tsv       Tatoeba German → English translation pairs
  leipzig-sentences.txt   Leipzig Corpora Collection, German (id, sentence)                             CC BY 4.0
  leipzig-words.txt       … word frequencies (id, word, count)

Output: docs/wb/meta.json (version, shard keys and sizes, counts) and docs/wb/<key>.json shards.
A shard holds every headword and word form whose folded spelling starts with its key:
  {"e": {headword: [entry, …]},          entries of one spelling (Essen the noun, essen the verb are different headwords)
   "f": {form: [[headword, how], …]},     lower-cased form → the headwords it belongs to ("how": Wiktionary tags)
   "x": {headword: {"t": [[de, en], …],   Tatoeba sentence pairs
                    "l": [de, …],         Leipzig corpus sentences
                    "b": [[de, zh, route, book], …]}}   sentences from Lesepult's own books
An entry: {"p": POS, "g": gender, "i": IPA, "a": audio URL, "r": corpus frequency,
           "s": [[gloss, [tags], [[example, translation], …]], …], "fm": [[form, tags], …], "et": etymology}
"""
import argparse, collections, gzip, heapq, json, pathlib, re, sys, time, unicodedata

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

LET = "A-Za-zÄÖÜäöüßẞÀ-ÖØ-öø-ÿ"
TOKRE = re.compile(f"[{LET}]+(?:-[{LET}]+)*")


def fold(w):
    w = w.lower().replace("ä", "a").replace("ö", "o").replace("ü", "u").replace("ß", "ss").replace("ẞ", "ss")
    w = unicodedata.normalize("NFKD", w)
    return re.sub(r"[^a-z]", "", w)


def key2(w):
    f = fold(w)
    return (f + "__")[:2] if f else "__"


def opener(p):
    p = pathlib.Path(p)
    if p.suffix == ".gz":
        return gzip.open(p, "rt", encoding="utf8", errors="replace")
    return open(p, encoding="utf8", errors="replace")


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


# ---------------------------------------------------------------- Wiktionary
SKIP_FORM_TAGS = {"table-tags", "inflection-template", "class", "romanization", "canonical", "error-unknown-tag"}
LEAD = {"der", "die", "das", "des", "dem", "den", "ein", "eine", "einer", "eines", "einem", "einen", "kein", "keine",
        "keiner", "keines", "keinem", "keinen", "ich", "du", "er", "sie", "es", "wir", "ihr", "man", "er/sie/es", "dass", "daß"}
GENDERS = {"masculine": "m", "feminine": "f", "neuter": "n"}
SENSE_TAGS = {"transitive", "intransitive", "reflexive", "colloquial", "informal", "formal", "dated", "obsolete", "archaic",
              "rare", "figuratively", "literary", "slang", "vulgar", "derogatory", "humorous", "regional", "Austria",
              "Switzerland", "Southern-Germany", "Northern-Germany", "uncountable", "countable", "plural-only",
              "singular-only", "impersonal", "auxiliary", "with-dative", "with-genitive", "with-accusative", "law",
              "philosophy", "physics", "mathematics", "theology", "historical", "poetic", "pejorative", "dialectal",
              "Christianity", "music", "military", "medicine", "biology", "chemistry", "grammar", "linguistics"}
DECL_TAGS = {"strong", "weak", "mixed"}  # adjective declension: regular, rebuilt in the browser
# compound tenses (hat gesehen, wurde gesehen, werde gesehen haben …) are predictable from the auxiliary and the
# participle; Wiktionary lists them for every verb, which would make the dictionary ten times bigger
COMPOUND_TAGS = {"perfect", "pluperfect", "future", "future-i", "future-ii", "passive", "future-perfect"}
AUX = set("""haben habe hast hat habt hatte hattest hatten hattet hätte hättest hätten hättet gehabt sein bin bist ist sind
seid war warst waren wart wäre wärst wären wärt sei seist seien gewesen werden werde wirst wird werdet wurde wurdest wurden
wurdet würde würdest würden würdet worden geworden""".split())


def strip_lead(form):
    parts = form.split()
    while len(parts) > 1 and parts[0].lower() in LEAD:
        parts = parts[1:]
    return " ".join(parts)


def clean_gloss(g):
    return re.sub(r"\s+", " ", g).strip()


def read_kaikki(path, freq):
    E = collections.defaultdict(list)          # headword → entries
    F = collections.defaultdict(list)          # lower form → [[headword, how]]
    n = nf = 0
    with opener(path) as fh:
        for line in fh:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if d.get("lang_code", "de") != "de":
                continue
            word, pos = d.get("word"), d.get("pos", "")
            if not word or len(word) > 60:
                continue
            senses = d.get("senses") or []
            real = []
            for s in senses:
                ref = (s.get("form_of") or s.get("alt_of") or [None])[0]
                tags = [t for t in s.get("tags", []) if t not in ("form-of", "alt-of")]
                if ref and ref.get("word") and " " not in word:
                    how = ("alt " if s.get("alt_of") else "") + " ".join(tags)
                    F[word.lower()].append([ref["word"], how.strip()])
                    nf += 1
                    continue
                gl = s.get("glosses") or s.get("raw_glosses")
                if not gl:
                    continue
                g = clean_gloss(gl[-1])
                if len(gl) > 1 and len(gl[0]) < 60:
                    g = clean_gloss(gl[0]).rstrip(":") + ": " + g
                ex = []
                for e in s.get("examples", []) or []:
                    t, tr = e.get("text", ""), e.get("english") or e.get("translation") or ""
                    if t and len(t) < 220 and e.get("type", "example") in ("example", "quotation", "quote"):
                        ex.append([t, tr])
                    if len(ex) >= 2:
                        break
                real.append([g[:300], [t for t in tags if t in SENSE_TAGS], ex])
            if not real:
                continue
            ent = {"p": pos}
            gs = {GENDERS[t] for t in d.get("tags", []) if t in GENDERS}
            fms, seen = [], set()
            for f in d.get("forms", []) or []:
                tags = f.get("tags", []) or []
                if "canonical" in tags:
                    gs |= {GENDERS[t] for t in tags if t in GENDERS}
                form = (f.get("form") or "").strip()
                if not form or form in ("-", "—", "–") or SKIP_FORM_TAGS & set(tags) or len(form) > 50:
                    continue
                form = strip_lead(form)
                if COMPOUND_TAGS & set(tags) or (" " in form and AUX & set(form.lower().split())):
                    continue
                tg = " ".join(t for t in tags if t not in ("table-tags",))
                if (form, tg) in seen:
                    continue
                seen.add((form, tg))
                if form.lower() != word.lower() and " " not in form:
                    F[form.lower()].append([word, tg])
                if pos == "adj" and DECL_TAGS & set(tags):
                    continue
                fms.append([form, tg])
            if not gs:
                for s in senses[:2]:
                    gs |= {GENDERS[t] for t in s.get("tags", []) if t in GENDERS}
            if gs and pos == "noun":
                ent["g"] = "".join(sorted(gs, key="mfn".index))
            for snd in d.get("sounds", []) or []:
                if "ipa" in snd and "i" not in ent:
                    ent["i"] = snd["ipa"]
                if "a" not in ent and (snd.get("mp3_url") or snd.get("ogg_url")):
                    ent["a"] = snd.get("mp3_url") or snd.get("ogg_url")
            ent["s"] = real[:12]
            if fms:
                ent["fm"] = fms[:90]
            et = d.get("etymology_text")
            if et:
                ent["et"] = et[:260] + ("…" if len(et) > 260 else "")
            r = freq.get(word, 0)
            if r:
                ent["r"] = r
            E[word].append(ent)
            n += 1
    log(f"Wiktionary：{n} 个词条，{len(E)} 个词头，{nf} 个变形指向")
    return E, F


# ---------------------------------------------------------------- examples
def words_of(s):
    return TOKRE.findall(s)


def ex_score(s, lo, hi, best):
    """lower is better: closeness of the word count to `best`, penalties for noise"""
    w = len(words_of(s))
    if w < lo or w > hi:
        return None
    p = abs(w - best)
    if re.search(r"\d", s):
        p += 4
    if re.search(r"https?:|www\.|@|\||\[|\]|…|\.\.\.", s):
        return None
    if s.count('"') + s.count("„") + s.count("“") > 2:
        p += 3
    if not s[0].isupper() or s[-1] not in ".!?":
        p += 6
    caps = sum(1 for x in words_of(s) if x.isupper() and len(x) > 1)
    p += caps * 2
    return p


class Picker:
    """the n best examples per headword"""
    def __init__(self, n):
        self.n, self.h, self.c = n, collections.defaultdict(list), 0

    def add(self, head, score, item):
        self.c += 1
        h = self.h[head]
        e = (-score, self.c, item)
        if len(h) < self.n:
            heapq.heappush(h, e)
        elif e > h[0]:
            heapq.heapreplace(h, e)

    def get(self, head):
        return [x[2] for x in sorted(self.h.get(head, []), key=lambda e: (-e[0], e[1]))]


def heads_for(tok, E, F):
    out = []
    for cand in (tok, tok.lower(), tok[:1].upper() + tok[1:].lower()):
        if cand in E and cand not in out:
            out.append(cand)
    for w, how in F.get(tok.lower(), []):
        if w in E and w not in out and not how.startswith("alt"):
            out.append(w)
    return out[:3]


def tatoeba(src, E, F, n):
    links_p, de_p, en_p = src / "deu-eng_links.tsv", src / "deu_sentences.tsv", src / "eng_sentences.tsv"
    if not (links_p.exists() and de_p.exists() and en_p.exists()):
        log("Tatoeba：缺文件，跳过"); return None
    pairs = collections.defaultdict(list)
    with opener(links_p) as fh:
        for line in fh:
            a = line.rstrip("\n").split("\t")
            if len(a) >= 2:
                pairs[a[0]].append(a[1])
    need = {e for v in pairs.values() for e in v}
    en = {}
    with opener(en_p) as fh:
        for line in fh:
            a = line.rstrip("\n").split("\t")
            if len(a) >= 3 and a[0] in need:
                en[a[0]] = a[2]
    P = Picker(n)
    k = 0
    with opener(de_p) as fh:
        for line in fh:
            a = line.rstrip("\n").split("\t")
            if len(a) < 3 or a[0] not in pairs:
                continue
            tr = next((en[x] for x in pairs[a[0]] if x in en), None)
            if not tr:
                continue
            de = a[2]
            sc = ex_score(de, 3, 18, 7)
            if sc is None:
                continue
            k += 1
            for tok in set(words_of(de)):
                for h in heads_for(tok, E, F):
                    P.add(h, sc, [de, tr])
    log(f"Tatoeba：{k} 个带英译的德语句子")
    return P


def leipzig(src, E, F, n):
    p = src / "leipzig-sentences.txt"
    if not p.exists():
        log("Leipzig：缺文件，跳过"); return None
    P = Picker(n)
    k = 0
    with opener(p) as fh:
        for line in fh:
            a = line.rstrip("\n").split("\t")
            if len(a) < 2:
                continue
            s = a[-1].strip()
            sc = ex_score(s, 6, 24, 12)
            if sc is None:
                continue
            k += 1
            for tok in set(words_of(s)):
                for h in heads_for(tok, E, F):
                    P.add(h, sc, s)
    log(f"Leipzig：{k} 个可用句子")
    return P


def read_freq(src):
    p, f = src / "leipzig-words.txt", {}
    if p.exists():
        with opener(p) as fh:
            for line in fh:
                a = line.rstrip("\n").split("\t")
                if len(a) >= 3 and a[2].isdigit():
                    f[a[1]] = f.get(a[1], 0) + int(a[2])
    log(f"词频：{len(f)} 个词形")
    return f


def books(E, F, n):
    """sentences of Lesepult's own books, with their Chinese translation and a link back"""
    try:
        import kit
    except Exception as e:
        log("读不到书：", e); return None
    lib = kit.Library()
    P = Picker(n)
    k = 0
    for b in lib.books:
        title = b.meta.get("zh") or b.meta.get("title")
        for pre, pi, sec in b.sections():
            cid = pre.split("/")[1].strip() if "/" in pre else None
            for si, s in enumerate(sec.get("s", [])):
                de = s.get("de", "")
                plain = re.sub(r"\{[^}]*\}", "", de).replace("<<", "").replace(">>", "").replace("*", "").replace("_", "")
                zh = re.sub(r"\{[^}]*\}", "", s.get("zh", ""))
                if not plain or not zh:
                    continue
                route = f"{b.dir.name}~s-" + (f"{cid}-" if cid else "") + f"{pi}-{si}"
                sc = ex_score(plain, 3, 40, 14) or 30
                k += 1
                heads = set()
                for w, _ in b.tokens(de):
                    row = b.lex.get(w.lower())
                    lem = strip_lead(row[0]) if row else w
                    lem = re.sub(r"^sich\s+", "", lem)
                    heads.update(heads_for(lem, E, F) or heads_for(w, E, F))
                for h in heads:
                    P.add(h, sc, [plain, zh, route, title])
    log(f"书：{k} 个句子")
    return P


# ---------------------------------------------------------------- output
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("-o", "--out", default=str(HERE.parent.parent / "docs" / "wb"))
    ap.add_argument("--tatoeba", type=int, default=4)
    ap.add_argument("--leipzig", type=int, default=3)
    ap.add_argument("--book", type=int, default=3)
    ap.add_argument("--max-shard", type=int, default=400_000)
    a = ap.parse_args()
    src, out = pathlib.Path(a.src), pathlib.Path(a.out)
    kk = next((p for p in (src / "kaikki.jsonl", src / "kaikki.jsonl.gz") if p.exists()), None)
    if not kk:
        sys.exit("缺少 kaikki.jsonl")
    freq = read_freq(src)
    E, F = read_kaikki(kk, freq)
    for k in list(F):
        seen, v = set(), []
        for w, how in F[k]:
            if (w, how) not in seen:
                seen.add((w, how)); v.append([w, how])
        F[k] = v[:8]
    T = tatoeba(src, E, F, a.tatoeba)
    L = leipzig(src, E, F, a.leipzig)
    B = books(E, F, a.book)

    shards = collections.defaultdict(lambda: {"e": {}, "f": {}, "x": {}})
    for w, ents in E.items():
        sh = shards[key2(w)]
        sh["e"][w] = ents
        x = {}
        for name, P in (("t", T), ("l", L), ("b", B)):
            if P:
                v = P.get(w)
                if v:
                    x[name] = v
        if x:
            sh["x"][w] = x
    for f, v in F.items():
        v = [p for p in v if p[0] in E]
        if v:
            shards[key2(f)]["f"][f] = v

    # split shards that came out too big: words longer than the key move to a key one letter longer, recursively;
    # the browser loads every key that is a prefix of the (folded) word it looks for
    def dump(sh):
        return json.dumps(sh, ensure_ascii=False, separators=(",", ":"))

    final = {}

    def place(k, sh):
        blob = dump(sh)
        if len(blob.encode()) <= a.max_shard or len(k) >= 7:
            final[k] = blob
            return
        keep = {"e": {}, "f": {}, "x": {}}
        sub = collections.defaultdict(lambda: {"e": {}, "f": {}, "x": {}})
        for part in ("e", "f", "x"):
            for w, v in sh[part].items():
                f = fold(w)
                (keep if len(f) <= len(k) else sub[f[:len(k) + 1]])[part][w] = v
        if any(keep[p] for p in keep):
            final[k] = dump(keep)
        for k2, s2 in sub.items():
            place(k2, s2)

    for k, sh in shards.items():
        place(k, sh)
    sizes_by = sorted(((len(b.encode()), k) for k, b in final.items()), reverse=True)[:8]
    log("最大的分片：", ", ".join(f"{k} {n/1e3:.0f} KB" for n, k in sizes_by))
    big = shards.get("ha") or {}
    for part in ("e", "f", "x"):
        log(f"  ha 分片里 {part}：{len(dump({part: big.get(part, {})}))/1e3:.0f} KB")

    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.json"):
        old.unlink()
    sizes = {}
    for k, blob in sorted(final.items()):
        (out / f"{k}.json").write_text(blob, encoding="utf8")
        sizes[k] = len(blob.encode())
    import hashlib
    h = hashlib.sha1("".join(final[k] for k in sorted(final)).encode()).hexdigest()[:10]
    meta = {"v": h, "built": time.strftime("%Y-%m-%d"), "keys": sizes,
            "n": {"heads": len(E), "entries": sum(len(v) for v in E.values()), "forms": len(F),
                  "tatoeba": sum(1 for w in E if T and T.get(w)), "leipzig": sum(1 for w in E if L and L.get(w)),
                  "book": sum(1 for w in E if B and B.get(w))},
            "src": json.loads((src / "sources.json").read_text()) if (src / "sources.json").exists() else {}}
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, separators=(",", ":")), encoding="utf8")
    tot = sum(sizes.values())
    gz = sum(len(gzip.compress(final[k].encode(), 6)) for k in final)
    log(f"写出 {len(final)} 个分片，共 {tot/1e6:.1f} MB（gzip 后约 {gz/1e6:.1f} MB），最大 {max(sizes.values())/1e3:.0f} KB")
    log("统计：", json.dumps(meta["n"], ensure_ascii=False))


if __name__ == "__main__":
    main()
