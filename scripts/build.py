#!/usr/bin/env python3
"""Build the whole library (every book + shared courses) into one self-contained HTML page.

  python3 scripts/build.py                     # -> dist/index.html
  python3 scripts/build.py -o page.html
  python3 scripts/build.py --force             # build even if a check fails (preview a book in progress)
  python3 scripts/build.py --standalone        # full <!doctype html> page for your own hosting (GitHub Pages, VPS)

Without --standalone the output is a page fragment for publishing as a Claude artifact.
"""
import sys, json, html, re, argparse, pathlib, subprocess, shutil
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from kit import Library, validate, KIT


def jdump(x):
    return json.dumps(x, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--standalone", action="store_true")
    a = ap.parse_args()
    lib = Library()
    bad = []
    for x in lib.items():
        errors, _, missing = validate(x)
        if errors or missing:
            bad.append(f"《{x.meta.get('title')}》：{len(errors)} 个错误，{len(missing)} 个词形缺词条")
    if bad and not a.force:
        print("检查未通过，先运行 python3 scripts/check.py 查看（或加 --force 预览）：\n  " + "\n  ".join(bad))
        sys.exit(1)

    site = lib.site
    profiles = {}
    for x in lib.items():
        profiles[x.meta.get("profile", "de-zh")] = x.profile
    data = {
        "site": {k: site.get(k, "") for k in ("title", "subtitle", "footer")},
        "default": site.get("default") or (lib.books[0].meta["id"] if lib.books else None),
        "profiles": profiles,
        "books": [],
        "courses": [{"id": c.meta["id"], "meta": c.meta, "lessons": c.lessons} for c in lib.courses],
    }
    by_id = {b.meta["id"]: b for b in lib.books}
    for entry in site.get("books", []):
        if isinstance(entry, dict):
            data["books"].append(dict(entry, planned=True))
        else:
            b = by_id[pathlib.Path(entry).name] if pathlib.Path(entry).name in by_id else next(x for x in lib.books if x.dir.name == entry)
            data["books"].append({"id": b.meta["id"], "meta": b.meta, "text": b.text, "lessons": b.lessons, "lex": b.lex})

    src = (KIT / "template" / "app.src.html").read_text(encoding="utf8")
    fonts = site.get("fonts") or (lib.books[0].meta.get("fonts", {}) if lib.books else {})
    root = ":root{" + ";".join(f"{k}:{v}" for k, v in (("--f-de", fonts.get("text")), ("--f-frak", fonts.get("mast")), ("--f-zh", fonts.get("trans"))) if v) + "}"
    src = src.replace("</style>", root + "\n</style>", 1)
    for k in ("title", "subtitle", "eyebrow", "lede", "footer", "fontsHref"):
        src = src.replace("{{" + k + "}}", html.escape(str(site.get(k, ""))))
    left = re.findall(r"\{\{\w+\}\}", src.split("<script>")[0])
    if left:
        print("警告：模板里还有未填的占位符", set(left))
    src = src.replace("/*@LIB@*/", jdump(data))
    if a.standalone:
        head_end = src.index("</style>") + len("</style>")
        src = ('<!doctype html>\n<html lang="zh-CN">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">\n'
               f'<meta name="description" content="{html.escape(site.get("description", ""))}">\n'
               + src[:head_end] + "\n</head>\n<body>\n" + src[head_end:] + "\n</body>\n</html>\n")

    out = pathlib.Path(a.out) if a.out else KIT / "dist" / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(src, encoding="utf8")
    n_live = len(lib.books)
    print(f"已生成 {out}（{out.stat().st_size/1024:.0f} KB，{n_live} 本书，{len(lib.planned)} 本筹备中，{len(lib.courses)} 门共用课程）")
    if shutil.which("node"):
        js = src[src.index("<script>") + 8: src.rindex("</script>")]
        tmp = out.with_suffix(".check.js")
        tmp.write_text(js, encoding="utf8")
        r = subprocess.run(["node", "--check", str(tmp)], capture_output=True, text=True)
        tmp.unlink()
        print("脚本语法检查：", "通过 ✓" if r.returncode == 0 else "失败\n" + r.stderr)
        if r.returncode:
            sys.exit(1)


if __name__ == "__main__":
    main()
