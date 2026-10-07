#!/usr/bin/env python3
"""Make a small test library with a chaptered book, so the chapter UI is tested even before a real
chaptered book is on the shelf.

  python3 tests/make_fixture.py            # writes tests/fixtures/ (git-ignored)
  python3 scripts/build.py --standalone --library tests/fixtures/library.json -o /tmp/fx/index.html
  python3 tests/e2e.py /tmp/fx/index.html

The chaptered book is the Prolegomena preface cut into two chapters, plus a planned third one.
"""
import json, pathlib, shutil

KIT = pathlib.Path(__file__).resolve().parent.parent
FX = KIT / "tests" / "fixtures"
SRC = KIT / "books" / "kant-prolegomena"


def main():
    if FX.exists():
        shutil.rmtree(FX)
    book = FX / "chaptered-demo"
    (book / "text").mkdir(parents=True)
    shutil.copytree(SRC / "lexicon", book / "lexicon")
    text = json.loads((SRC / "text.json").read_text(encoding="utf8"))
    meta = json.loads((SRC / "book.json").read_text(encoding="utf8"))
    cut = len(text) // 2
    (book / "text" / "a.json").write_text(json.dumps(text[:cut], ensure_ascii=False, indent=1), encoding="utf8")
    (book / "text" / "b.json").write_text(json.dumps(text[cut:], ensure_ascii=False, indent=1), encoding="utf8")
    lessons = json.loads((SRC / "lessons.json").read_text(encoding="utf8"))
    if lessons:
        lessons[-1]["ch"] = "b"
    (book / "lessons.json").write_text(json.dumps(lessons, ensure_ascii=False, indent=1), encoding="utf8")
    d0, d1 = meta["demo"]
    meta.update({
        "id": "chaptered-demo", "short": "分章测试",
        "demo": ["a", d0, d1] if d0 < cut else ["b", d0 - cut, d1],
        "chapters": [
            {"id": "a", "h": "序言（上）", "t": "Vorrede", "blurb": text[0]["h"]},
            {"id": "b", "h": "序言（下）", "t": "Vorrede"},
            {"id": "c", "h": "总问题", "t": "Prolegomena", "planned": True},
        ],
    })
    (book / "book.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf8")
    lib = json.loads((KIT / "library.json").read_text(encoding="utf8"))
    lib["books"] = [b for b in lib["books"] if isinstance(b, str)] + ["./chaptered-demo"]
    lib["default"] = "kant-aufklaerung"
    (FX / "library.json").write_text(json.dumps(lib, ensure_ascii=False, indent=1), encoding="utf8")
    print(f"已生成 {FX}")


if __name__ == "__main__":
    main()
