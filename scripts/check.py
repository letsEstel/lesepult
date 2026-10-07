#!/usr/bin/env python3
"""Validate the library (every book and shared course), or one book, and list words that still need lexicon entries.

  python3 scripts/check.py                            # whole library
  python3 scripts/check.py books/<book>               # one book
  python3 scripts/check.py books/<book> --worklist    # also write books/<book>/worklist.tsv

worklist.tsv has one missing form per line, with how often it occurs and one sentence of
context, sorted by frequency. Hand it to Claude in batches to get lexicon lines back.
"""
import sys, re, argparse, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from kit import Book, Course, Library, validate


def report(b, worklist=False):
    errors, warnings, missing = validate(b)
    n_sent = sum(len(s["s"]) for s in b.text)
    n_tok = sum(1 for _, de in b.snippets() for _ in b.tokens(de))
    name = b.meta.get("title")
    print(f"[{b.kind}] 《{name}》 {len(b.text)} 个部分 · {n_sent} 句 · {len(b.lessons)} 节课 · {len(b.lex)} 个词条 · 扫描 {n_tok} 个词")
    for w in warnings:
        print("  提示：", w)
    for e in errors:
        print("  错误：", e)
    if missing:
        print(f"  缺少词条：{len(missing)} 个词形")
        top = sorted(missing.items(), key=lambda kv: -len(kv[1]))
        print("   ", " ".join(f"{k}×{len(v)}" for k, v in top[:30]), "…" if len(top) > 30 else "")
    if worklist and b.kind == "book":
        out = b.dir / "worklist.tsv"
        lines = ["form\tcount\tcontext"]
        for k, v in sorted(missing.items(), key=lambda kv: (-len(kv[1]), kv[0])):
            loc, de = v[0]
            ctx = re.sub(r"\{[^}]*\}", "", de).replace("*", "").replace("_", "").replace("<<", "").replace(">>", "")
            lines.append(f"{k}\t{len(v)}\t{loc}: {ctx}")
        out.write_text("\n".join(lines) + "\n", encoding="utf8")
        print(f"  已写出 {out}（{len(missing)} 行）")
    ok = not errors and not missing
    print("  结果：", "通过 ✓" if ok else "未通过")
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("book", nargs="?")
    ap.add_argument("--worklist", action="store_true")
    a = ap.parse_args()
    if a.book:
        p = pathlib.Path(a.book)
        ok = report(Course(p) if (p / "course.json").exists() else Book(p), a.worklist)
    else:
        lib = Library()
        ok = all([report(x, a.worklist) for x in lib.items()])
        if lib.planned:
            print("筹备中：", "、".join(b.get("zh") or b.get("title") for b in lib.planned))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
