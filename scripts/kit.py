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

    # every German snippet in the book, with a human-readable location
    def snippets(self):
        for pi, sec in enumerate(self.text):
            for si, s in enumerate(sec.get("s", [])):
                yield f"text §{sec.get('k', pi)}.{si+1}", s.get("de", "")
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
                self.books.append(Book(KIT / "books" / b))
        for c in self.site.get("courses", []):
            self.courses.append(Course(KIT / "courses" / c))

    def items(self):
        return self.courses + self.books


def validate(book):
    errors, warnings = list(book.lex_errors), []
    P = book.profile
    required = ["id", "title", "mast", "demo", "fonts"] if book.kind == "book" else ["id", "title", "lexiconFrom"]
    for k in required:
        if k not in book.meta:
            errors.append(f"{book.kind}.json 缺少字段 {k}")
    for pi, sec in enumerate(book.text):
        if "h" not in sec or "s" not in sec:
            errors.append(f"text.json 第 {pi} 部分缺少 h 或 s")
            continue
        for si, s in enumerate(sec["s"]):
            loc = f"text §{sec.get('k', pi)}.{si+1}"
            for f in ("de", "zh", "n"):
                if f not in s:
                    errors.append(f"{loc} 缺少字段 {f}")
            if s.get("de", "").count("*") % 2 or s.get("de", "").count("_") % 2:
                errors.append(f"{loc} 的 * 或 _ 没有成对出现")
            if not s.get("n"):
                warnings.append(f"{loc} 没有语法讲解")
    if book.kind == "book":
        try:
            d0, d1 = book.meta.get("demo", [0, 0])
            book.text[d0]["s"][d1]
        except (IndexError, KeyError, TypeError, ValueError):
            errors.append("book.json 的 demo 指向不存在的句子")
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
