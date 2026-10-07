#!/usr/bin/env python3
"""Build the library.

  python3 scripts/build.py                          # one self-contained page fragment (Claude artifact) -> dist/index.html
  python3 scripts/build.py --standalone -o docs/index.html
        # website: index.html (shelf + app) + data/<book>.json + data/dict.json, loaded on demand,
        # plus sw.js (offline cache) and manifest.webmanifest (installable). For GitHub Pages / any static host.
  python3 scripts/build.py --standalone --single    # website as one file (no data/ folder)
  python3 scripts/build.py --force                  # build even if a check fails (preview a book in progress)
"""
import sys, json, html, re, argparse, pathlib, subprocess, shutil
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from kit import Library, validate, KIT, build_dict, case_issues, coverage2
import hashlib


def jdump(x):
    return json.dumps(x, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--standalone", action="store_true")
    ap.add_argument("--single", action="store_true", help="inline all data even with --standalone")
    a = ap.parse_args()
    lib = Library()
    bad = []
    for x in lib.items():
        errors, _, missing = validate(x)
        errors += case_issues(x)
        if errors or missing:
            bad.append(f"《{x.meta.get('title')}》：{len(errors)} 个错误，{len(missing)} 个词形缺词条")
    if bad and not a.force:
        print("检查未通过，先运行 python3 scripts/check.py 查看（或加 --force 预览）：\n  " + "\n  ".join(bad))
        sys.exit(1)

    dic, derr = build_dict(lib)
    cov = coverage2(lib, dic)
    if (cov or derr) and not a.force:
        print(f"检查未通过：{len(cov)} 个页面上的词查不到，共用词典 {len(derr)} 个错误。运行 python3 scripts/check.py 查看。")
        sys.exit(1)
    split = a.standalone and not a.single
    site = lib.site
    profiles = {}
    for x in lib.items():
        profiles[x.meta.get("profile", "de-zh")] = x.profile
    data = {
        "site": {k: site.get(k, "") for k in ("title", "subtitle", "footer", "repo", "siteUrl", "feedbackContact")},
        "default": site.get("default") or (lib.books[0].meta["id"] if lib.books else None),
        "profiles": profiles,
        "books": [],
        "courses": [{"id": c.meta["id"], "meta": c.meta, "lessons": c.lessons} for c in lib.courses],
    }
    by_id = {b.meta["id"]: b for b in lib.books}
    payloads = {}
    for entry in site.get("books", []):
        if isinstance(entry, dict):
            data["books"].append(dict(entry, planned=True))
        else:
            b = by_id[pathlib.Path(entry).name] if pathlib.Path(entry).name in by_id else next(x for x in lib.books if x.dir.name == entry)
            toc = [[str(p.get("k", i)), len(p["s"])] for i, p in enumerate(b.text)]
            data["books"].append({"id": b.meta["id"], "meta": b.meta, "toc": toc, "nLex": len(b.lex), "nLessons": len(b.lessons)})
            payloads[b.meta["id"]] = {"text": b.text, "lessons": b.lessons, "lex": b.lex}
    payloads["dict"] = dic
    blob = {k: jdump(v) for k, v in payloads.items()}
    data["v"] = hashlib.sha1("".join(blob[k] for k in sorted(blob)).encode()).hexdigest()[:10]
    data["sw"] = split
    if not split:
        data["data"] = payloads

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
               '<meta name="theme-color" content="#1e3c6a">\n'
               + ('<link rel="manifest" href="manifest.webmanifest">\n<link rel="icon" href="icon.svg" type="image/svg+xml">\n' if split else '')
               + src[:head_end] + "\n</head>\n<body>\n" + src[head_end:] + "\n</body>\n</html>\n")

    out = pathlib.Path(a.out) if a.out else KIT / "dist" / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(src, encoding="utf8")
    if split:
        dd = out.parent / "data"
        dd.mkdir(exist_ok=True)
        for old in dd.glob("*.json"):
            old.unlink()
        for k, v in blob.items():
            (dd / f"{k}.json").write_text(v, encoding="utf8")
        for f in ("sw.js", "manifest.webmanifest", "icon.svg"):
            shutil.copy(KIT / "template" / f, out.parent / f)
        sizes = ", ".join(f"{k} {len(v.encode())/1024:.0f} KB" for k, v in blob.items())
        print(f"数据文件 {dd}：{sizes}")
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
