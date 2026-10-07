"""Shared helpers: load the library, books, shared courses and language profiles; tokenize; validate.

library.json      site copy + which books/courses are on the shelf (planned books are inline objects)
courses/<id>/     course.json (borrows the lexicon of one book via "lexiconFrom") + lessons.json
Book folder layout:
  book.json        metadata, hero copy, fonts, theme
  text.json        sections -> sentences (de / zh / notes)
  lessons.json     primer lessons (HTML with [[examples]] and optional {{quiz}})
  lexicon/*.tsv    one line per word form: form|lemma|POS|grammar|meaning|note
"""
import json, re, pathlib, sys

KIT = pathlib.Path(__file__).resolve().parent.parent


def load_json(p):
    try:
        return json.loads(pathlib.Path(p).read_text(encoding="utf8"))
    except json.JSONDecodeError as e:
        sys.exit(f"JSON 格式错误：{p}：第 {e.lineno} 行第 {e.colno} 列：{e.msg}")


class Book:
    kind = "book"

    def __init__(self, folder):
        self.dir = pathlib.Path(folder).resolve()
        if not (self.dir / "book.json").exists():
            sys.exit(f"找不到 {self.dir / 'book.json'}。请传入书的文件夹，例如 books/kant-aufklaerung")
        self.meta = load_json(self.dir / "book.json")
        prof = self.meta.get("profile", "de-zh")
        self.profile = load_json(KIT / "profiles" / f"{prof}.json")
        # A long book is split into chapters: book.json "chapters" lists them in order, each chapter's text
        # lives in text/<chapter id>.json, and the lexicon and lessons are shared by the whole book.
        # Planned chapters ("planned": true) are listed in the table of contents but have no text yet.
        self.chapters = None
        if "chapters" in self.meta:
            self.chapters = []
            for ch in self.meta["chapters"]:
                cid = str(ch.get("id", ""))
                if not re.fullmatch(r"[a-z0-9]+", cid):
                    sys.exit(f"{self.dir.name}/book.json：章节 id 只能用小写字母和数字：{cid!r}")
                tp = self.dir / "text" / f"{cid}.json"
                if ch.get("planned"):
                    self.chapters.append((ch, []))
                elif not tp.exists():
                    sys.exit(f"找不到 {tp}（章节 {cid} 没有标 planned，就要有正文）")
                else:
                    self.chapters.append((ch, load_json(tp)))
            self.text = [sec for _, t in self.chapters for sec in t]
        else:
            self.text = load_json(self.dir / "text.json")
        lp = self.dir / "lessons.json"
        self.lessons = load_json(lp) if lp.exists() else []
        self.lex, self.lex_errors = self._load_lexicon()
        L = self.profile["letters"]
        self.tok = re.compile(r"(\(?)([" + L + r"]+)(?:\{([^}]*)\})?([.,;:!?)\-]*)")
        self.keyre = re.compile(self.profile["keyPattern"])

    def _load_lexicon(self):
        lex, errs = {}, []
        files = sorted((self.dir / "lexicon").glob("*.tsv"))
        if not files:
            errs.append("lexicon/ 里没有 .tsv 文件")
        for f in files:
            for n, line in enumerate(f.read_text(encoding="utf8").splitlines(), 1):
                if not line.strip() or line.startswith("#"):
                    continue
                parts = line.split("|")
                where = f"{f.name}:{n}"
                if len(parts) != 6:
                    errs.append(f"{where} 应有 6 个字段（form|lemma|POS|grammar|meaning|note），实际 {len(parts)} 个")
                    continue
                form = parts[0]
                if form != form.lower():
                    errs.append(f"{where} 词形应为小写：{form}")
                if parts[2] not in self.profile["pos"]:
                    errs.append(f"{where} 未知词性代码 {parts[2]}（可用：{' '.join(self.profile['pos'])}）")
                if not parts[4].strip():
                    errs.append(f"{where} 缺少释义：{form}")
                if form in lex:
                    errs.append(f"{where} 重复词条：{form}")
                lex[form] = parts[1:]
        return lex, errs

    def sections(self):
        """(location prefix, section index within its chapter, section) for every section of the text"""
        if self.chapters is None:
            for pi, sec in enumerate(self.text):
                yield "text ", pi, sec
        else:
            for ch, t in self.chapters:
                for pi, sec in enumerate(t):
                    yield f"text/{ch['id']} ", pi, sec

    def sentence(self, ref):
        """the sentence a demo reference points to: [part, sentence] or, in a chaptered book, [chapter, part, sentence]"""
        if self.chapters is not None:
            cid, pi, si = ref
            t = next(t for ch, t in self.chapters if str(ch["id"]) == str(cid))
            return t[pi]["s"][si]
        pi, si = ref
        return self.text[pi]["s"][si]

    # every German snippet in the book, with a human-readable location
    def snippets(self):
        for pre, pi, sec in self.sections():
            for si, s in enumerate(sec.get("s", [])):
                yield f"{pre}§{sec.get('k', pi)}.{si+1}", s.get("de", "")
        for li, l in enumerate(self.lessons):
            for m in re.finditer(r"\[\[(.*?)\]\]", l.get("html", "")):
                yield f"lesson {li+1}", m.group(1)
            for qi, q in enumerate(l.get("quiz", []) or []):
                yield f"lesson {li+1} quiz {qi+1}", q.get("de", "")

    def tokens(self, de):
        clean = re.sub(r"<<|>>", "", de).replace("*", "").replace("_", "")
        for m in self.tok.finditer(clean):
            yield m.group(2), m.group(3) or ""


class Course:
    """Lessons shared by every book. Examples are drawn from one book, whose lexicon they use."""
    kind = "course"

    def __init__(self, folder):
        self.dir = pathlib.Path(folder).resolve()
        if not (self.dir / "course.json").exists():
            sys.exit(f"找不到 {self.dir / 'course.json'}")
        self.meta = load_json(self.dir / "course.json")
        self.lessons = load_json(self.dir / "lessons.json")
        src = KIT / "books" / self.meta["lexiconFrom"]
        self.source = Book(src)
        self.profile, self.lex, self.lex_errors = self.source.profile, self.source.lex, []
        self.text, self.tok, self.keyre = [], self.source.tok, self.source.keyre
        self.chapters = None
        if self.source.chapters is not None:
            sys.exit(f"共用课程 {self.dir.name} 的 lexiconFrom 不能是分章的书（{self.meta['lexiconFrom']}）")

    sections = Book.sections
    snippets = Book.snippets
    tokens = Book.tokens


class Library:
    def __init__(self, path=None):
        self.path = pathlib.Path(path or KIT / "library.json").resolve()
        self.site = load_json(self.path)
        self.books, self.planned, self.courses = [], [], []
        for b in self.site.get("books", []):
            if isinstance(b, dict):
                self.planned.append(b)
            else:
                self.books.append(Book(self.book_dir(b)))
        for c in self.site.get("courses", []):
            self.courses.append(Course(KIT / "courses" / c))

    def book_dir(self, entry):
        """a shelf entry is a folder name under books/, or a path relative to the library file (test fixtures)"""
        return (self.path.parent / entry) if "/" in entry else (KIT / "books" / entry)

    def items(self):
        return self.courses + self.books


def validate(book):
    errors, warnings = list(book.lex_errors), []
    P = book.profile
    required = ["id", "title", "mast", "demo", "fonts"] if book.kind == "book" else ["id", "title", "lexiconFrom"]
    for k in required:
        if k not in book.meta:
            errors.append(f"{book.kind}.json 缺少字段 {k}")
    for pre, pi, sec in book.sections():
        if "h" not in sec or "s" not in sec:
            errors.append(f"{pre}第 {pi} 部分缺少 h 或 s")
            continue
        for si, s in enumerate(sec["s"]):
            loc = f"{pre}§{sec.get('k', pi)}.{si+1}"
            for f in ("de", "zh", "n"):
                if f not in s:
                    errors.append(f"{loc} 缺少字段 {f}")
            if s.get("de", "").count("*") % 2 or s.get("de", "").count("_") % 2:
                errors.append(f"{loc} 的 * 或 _ 没有成对出现")
            if not s.get("n"):
                warnings.append(f"{loc} 没有语法讲解")
    if book.kind == "book":
        try:
            book.sentence(book.meta.get("demo"))
        except (IndexError, KeyError, TypeError, ValueError, StopIteration):
            errors.append("book.json 的 demo 指向不存在的句子" + ("（分章的书写成 [章节 id, 部分, 句子]）" if book.chapters is not None else ""))
        if book.chapters is not None:
            ids = [str(ch.get("id")) for ch, _ in book.chapters]
            if len(set(ids)) != len(ids):
                errors.append("book.json 的 chapters 里有重复的章节 id")
            for ch, t in book.chapters:
                if not ch.get("h"):
                    errors.append(f"章节 {ch.get('id')} 缺少中文标题 h")
                if not ch.get("planned") and not t:
                    errors.append(f"章节 {ch.get('id')} 的 text/{ch.get('id')}.json 是空的（还没做就标 planned）")
            if all(ch.get("planned") for ch, _ in book.chapters):
                errors.append("分章的书至少要有一章不是 planned")
            for li, l in enumerate(book.lessons):
                if l.get("ch") and l["ch"] not in ids:
                    errors.append(f"lesson {li+1} 的 ch={l['ch']} 不是本书的章节 id")
    for li, l in enumerate(book.lessons):
        q = l.get("quiz")
        html_ = l.get("html", "")
        secs = set(re.findall(r"\{\{quiz(?::([\w-]+))?\}\}", html_))
        if q and not secs:
            errors.append(f"lesson {li+1} 有 quiz 但 html 里没有 {{{{quiz}}}} 或 {{{{quiz:分组}}}} 占位符")
        ids = [it.get("id") for it in (q or [])]
        if q and (None in ids or len(set(ids)) != len(ids)):
            errors.append(f"lesson {li+1} 的每道题都需要唯一的 id")
        if q and "" not in secs:
            for it in q:
                if it.get("sec") not in secs:
                    errors.append(f"lesson {li+1} 题 {it.get('id')} 的分组 sec={it.get('sec')} 在 html 里没有对应的 {{{{quiz:{it.get('sec')}}}}}")
        for qi, it in enumerate(q or []):
            if not (0 <= it.get("ans", -1) < len(it.get("opts", []))):
                errors.append(f"lesson {li+1} quiz {qi+1} 的 ans 超出选项范围")
            if "<<" not in it.get("de", ""):
                warnings.append(f"lesson {li+1} quiz {qi+1} 没有用 <<…>> 标出考查的词")

    missing, badkeys, used = {}, [], set()
    for loc, de in book.snippets():
        for word, key in book.tokens(de):
            w = word.lower()
            if w in book.lex:
                used.add(w)
            else:
                missing.setdefault(w, []).append((loc, de))
            for k in filter(None, key.split(":")):
                if book.keyre.match(k):
                    continue
                if f"{w}#{k}" in book.lex:
                    used.add(f"{w}#{k}")
                else:
                    missing.setdefault(f"{w}#{k}", []).append((loc, de))
    unused = sorted(set(book.lex) - used) if book.kind == "book" else []
    if unused:
        warnings.append(f"{len(unused)} 个词条在文中没有用到（不影响构建）：{' '.join(unused[:12])}{' …' if len(unused) > 12 else ''}")
    return errors, warnings, missing


# ---------------------------------------------------------------- whole-site coverage
# Every Latin-script word the reader can SEE (outside the annotated sentences) is made
# clickable at runtime. These helpers list those strings so check.py can make sure each
# word has a dictionary entry somewhere (own book → shared lexicon → any other book).

WORD = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿẞ]+")
_PROFILE_SKIP = {"_about", "lang", "tts", "letters", "keyPattern", "css", "when", "verbPos", "verbLightPos",
                 "taggedPos", "contentPos", "posFilter", "caseOrder", "genderOrder", "plural", "governors"}


def visible_words(s):
    s = re.sub(r"\[\[.*?\]\]|\{\{[^}]*\}\}|<[^>]+>|&\w+;", " ", s)
    return WORD.findall(s)


def load_shared(profile):
    """shared/lexicon/*.tsv: words used on library/course/UI pages and in notes."""
    fake = Book.__new__(Book)
    fake.dir, fake.profile = KIT / "shared", profile
    return Book._load_lexicon(fake) if fake.dir.exists() else ({}, [])


def zone_strings(lib):
    """yield (zone, location, text) for every displayed string outside annotated German."""
    S = lib.site
    for k in ("title", "subtitle", "eyebrow", "lede", "footer"):
        yield "site", f"library.json {k}", S.get(k, "")
    for p in lib.planned:
        for k in ("title", "mast", "blurb", "level", "zh", "author"):
            yield "site", f"planned {k}", str(p.get(k, ""))
    prof = lib.books[0].profile

    def walk(o, path):
        if isinstance(o, dict):
            for k, v in o.items():
                if k not in _PROFILE_SKIP:
                    yield from walk(v, path + "." + k)
        elif isinstance(o, list):
            for v in o:
                yield from walk(v, path)
        elif isinstance(o, str):
            yield "site", "profile" + path, o
    yield from walk(prof, "")
    t = (KIT / "template" / "app.src.html").read_text(encoding="utf8")
    body = t[t.index("<header"):t.index("<script>")]
    yield "site", "template", re.sub(r'\s(class|id|data-[\w-]+|href|aria-[\w-]+|role|type|title)="[^"]*"', " ", body)
    js = t[t.index("<script>"):]
    for m in re.findall(r"'([^'\n]*[一-鿿][^'\n]*)'", js):
        yield "site", "template js", m
    for it in lib.items():
        z = it.meta["id"]
        m = it.meta
        for k in ("title", "de", "lede", "mast", "blurb", "level", "zh", "author", "eyebrow", "subtitle",
                  "demoCaption", "slipEmpty", "footer", "short"):
            if k in m:
                yield ("site" if k in ("title", "de", "lede", "mast", "blurb", "level", "zh", "author") else z), f"{z} meta {k}", str(m[k])
        for h in m.get("howto", []):
            yield z, f"{z} howto", h.get("h", "") + " " + h.get("p", "")
        for k, v in m.get("intro", {}).items():
            yield z, f"{z} intro {k}", v
        for ch, _ in (it.chapters or []):
            yield z, f"{z} chapter {ch.get('id')}", " ".join(str(ch.get(k, "")) for k in ("h", "t", "blurb", "pg"))
        for pre, pi, sec in it.sections():
            yield z, f"{z} {pre}§{pi} title", f"{sec.get('t', '')} {sec.get('h', '')} {sec.get('pg', '')}"
            for si, s in enumerate(sec.get("s", [])):
                yield z, f"{z} {pre}§{pi}.{si+1} notes", " ".join(s.get("n", [])) + " " + s.get("pg", "")
                yield z, f"{z} {pre}§{pi}.{si+1} zh", s.get("zh", "")
        for li, l in enumerate(it.lessons):
            yield z, f"{z} lesson {li+1}", f"{l.get('t', '')} {l.get('de', '')} {l.get('html', '')}"
            for q in l.get("quiz", []) or []:
                yield z, f"{z} lesson {li+1} quiz {q.get('id')}", " ".join(q.get("opts", [])) + " " + q.get("why", "")
        if it.kind == "book":
            for k, v in it.lex.items():
                yield z, f"{z} lexicon {k}", " ".join(v)


def coverage(lib):
    """words visible somewhere on the site that no lexicon explains: {word: [location, …]}"""
    shared, _ = load_shared(lib.books[0].profile)
    known = set(shared)
    for b in lib.books:
        known.update(b.lex)
    miss = {}
    for zone, loc, text in zone_strings(lib):
        for w in visible_words(text):
            lw = w.lower()
            if lw not in known:
                miss.setdefault(lw, []).append(loc)
    return miss


_ART = {"der": "阳性", "die": "阴性", "das": "中性"}


def lemma_entries(books):
    """Dictionary-form entries derived from lemmas: 'drohen' for a text that only has 'drohet'."""
    out, forms = {}, {}
    for b in books:
        for k, v in b.lex.items():
            if "#" in k:
                continue
            lemma, pos = v[0], v[1]
            for alt in lemma.split(" / "):
                alt = re.sub(r"（[^）]*）|\([^)]*\)", "", alt).strip()
                gender = None
                parts = alt.split()
                if pos == "N" and len(parts) == 2 and parts[0] in _ART:
                    gender, parts = _ART[parts[0]], parts[1:]
                elif len(parts) == 2 and parts[0] == "sich":
                    parts = parts[1:]
                if len(parts) != 1 or not WORD.fullmatch(parts[0]):
                    continue
                key = parts[0].lower()
                forms.setdefault(key, []).append(k)
                if key in out:
                    continue
                if pos == "N":
                    gram = "名词 · " + (gender + " · " if gender else "") + "词典形（单数主格）"
                elif pos in ("V", "I", "Z"):
                    pos, gram = "I", "不定式（词典形）" + ("，可分动词" if v[1] == "Z" else "")
                else:
                    gram = "原形（词典形）"
                out[key] = [lemma if pos != "I" else alt, pos, gram, v[3], ""]
    for key, e in out.items():
        fs = [f for f in dict.fromkeys(forms[key]) if f != key][:8]
        if fs:
            e[4] = "书中出现的形式：" + "、".join(fs)
    return out


def build_dict(lib):
    """One general-purpose dictionary for every page: shared lexicon > book entries > derived lemmas."""
    shared, errs = load_shared(lib.books[0].profile)
    d = dict(shared)
    for b in lib.books:
        for k, v in b.lex.items():
            if "#" not in k and k not in d:
                d[k] = v
    for k, v in lemma_entries(lib.books).items():
        d.setdefault(k, v)
    return d, errs


def chains(text):
    """tokenise like the browser does: hyphen/·-joined chains, tried whole first, then part by part"""
    text = re.sub(r"\[\[.*?\]\]|\{\{[^}]*\}\}|\{\w+\}|<[^>]+>|&\w+;", " ", text)
    for m in re.finditer(r"(-?)([A-Za-zÀ-ÖØ-öø-ÿẞ]+(?:[-·][A-Za-zÀ-ÖØ-öø-ÿẞ]+)*)(-?)", text):
        yield m.group(1), m.group(2), m.group(3)


def lookup_keys(lead, chain, trail):
    """candidate dictionary keys for one chain → list of (surface, [keys…]) units"""
    parts = re.split(r"[-·]", chain)
    if len(parts) > 1:
        whole = "".join(parts).lower()
        return [(chain, [whole])], [(p, ([("-" + p.lower())] if i or lead else []) + ([p.lower() + "-"] if i < len(parts) - 1 or trail else []) + [p.lower()]) for i, p in enumerate(parts)]
    p = parts[0]
    return [(p, ([("-" + p.lower())] if lead else []) + ([p.lower() + "-"] if trail else []) + [p.lower()])], None


def coverage2(lib, dic):
    miss = {}
    for zone, loc, text in zone_strings(lib):
        if loc == "template js" or ".tables" in loc:
            continue
        for lead, chain, trail in chains(text):
            first, alt = lookup_keys(lead, chain, trail)
            if alt and first[0][1][0] in dic:
                continue
            for surf, keys in (alt or first):
                if len(surf) < 2 or any(k in dic for k in keys):
                    continue
                miss.setdefault(keys[-1] if not (lead or trail) or len(keys) == 1 else keys[0], []).append(loc)
    return miss


def table_for(P, lemma, surface, named):
    for t in P["tables"]:
        w, stem = t["when"], ""
        if "named" in w and named not in w["named"]:
            continue
        if "lemma" in w and lemma not in w["lemma"]:
            continue
        if "lemmaStem" in w:
            if lemma not in w["lemmaStem"]:
                continue
            stem = w["lemmaStem"][lemma]
        if "surface" in w and (surface not in w["surface"] or named):
            continue
        ov = (t.get("override") or {}).get(lemma, {})
        return lambda c, g, t=t, stem=stem, ov=ov: ov.get(f"{c}.{g}") or (t["full"][c][g] if "full" in t else stem + t["endings"][c][g])
    return None


def case_issues(book):
    """a case/gender tag that contradicts the declension table: e.g. dem{nf} or diese{dm}"""
    P, out = book.profile, []
    for loc, de in book.snippets():
        for word, key in book.tokens(de):
            w = word.lower()
            cs = next((k for k in key.split(":") if book.keyre.match(k)), None)
            if not cs:
                continue
            named = next((k for k in key.split(":") if k and not book.keyre.match(k) and f"{w}#{k}" in book.lex), None)
            d = book.lex.get(f"{w}#{named}" if named else w)
            if not d or d[1] not in P["taggedPos"]:
                continue
            cell = table_for(P, d[0], w, named)
            if not cell:
                continue
            exp = cell(cs[0], cs[1]).lower()
            if exp != w and exp not in ("—",) and w.rstrip("e") != exp.rstrip("e"):
                out.append(f"{loc}：{word}{{{key}}} 按变格表 {cs} 应为 {exp}")
    return out
