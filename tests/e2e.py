#!/usr/bin/env python3
"""End-to-end smoke test in a real browser (Playwright + Chromium).

  python3 tests/e2e.py docs/index.html        # the website build (served over http so data/*.json can load)
  python3 tests/e2e.py dist/index.html        # a one-file build

Checks navigation, the word slip, quizzes, the shared course, and that every Latin-script word visible
on every page is a dictionary link (except navigation controls).
"""
import sys, pathlib, threading, http.server, functools
from playwright.sync_api import sync_playwright

page = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "docs/index.html").resolve()
class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass
handler = functools.partial(Quiet, directory=str(page.parent))
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{srv.server_port}/{page.name}"

AUDIT = r"""() => {
  const HARD='.de,.w,.lw,script,style,svg,input,textarea,select,option,title,#toast,.sl-word,[data-nolink]';
  const CTRL='button,a,[data-open],[data-route],[data-jump],[role="button"],.qopt,.tab';
  const bad={}; const tw=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
  while(tw.nextNode()){ const n=tw.currentNode, p=n.parentElement; if(!p||p.closest(HARD)) continue;
    if(p.closest(CTRL)&&!p.closest('[data-linkok]')) continue;
    for(const w of n.data.match(/[A-Za-zÀ-ÖØ-öø-ÿẞ]{2,}/g)||[]) bad[w]=(bad[w]||0)+1; }
  return Object.keys(bad); }"""

fails, log = 0, []
def ok(cond, msg):
    global fails
    fails += not cond
    print(("✓ " if cond else "✗ ") + msg)

with sync_playwright() as p:
    b = p.chromium.launch()
    for vp in ({"width": 390, "height": 844}, {"width": 1280, "height": 900}):
        tag = "手机" if vp["width"] < 600 else "桌面"
        ctx = b.new_context(viewport=vp, has_touch=vp["width"] < 600)
        ctx.route("**/fonts.g*/**", lambda r: r.abort())
        pg = ctx.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(URL); pg.wait_for_timeout(500)
        books = pg.evaluate("LIB.books.filter(b=>!b.planned).map(b=>b.id)")
        courses = pg.evaluate("LIB.courses.map(c=>c.id)")
        ok(pg.is_visible("#v-lib") and pg.locator("#shelf .book").count() >= len(books), f"[{tag}] 书架：{len(books)} 本书、{len(courses)} 门课")
        routes = ["lib"] + [f"{c}~intro" for c in courses] + [f"{x}~{v}" for x in books for v in ("home", "intro", "read", "vocab")]
        missing = set()
        for r in routes:
            pg.goto(URL + "#" + r); pg.wait_for_timeout(350)
            pg.evaluate("()=>document.querySelectorAll('.lesson-body,.notes,.zh').forEach(e=>e.hidden=false)")
            pg.wait_for_timeout(60)
            missing |= set(pg.evaluate(AUDIT))
        ok(not missing, f"[{tag}] {len(routes)} 个页面上所有德语都可点" + (f"；不可点：{sorted(missing)[:20]}" if missing else ""))
        bk = books[min(1, len(books) - 1)]
        pg.goto(URL + "#lib"); pg.wait_for_timeout(300)
        pg.locator(f'.book[data-route="{bk}~home"] .bk-cover').click(); pg.wait_for_timeout(400)
        ok(pg.is_visible("#v-home") and pg.inner_text("#backLbl") == "书架", f"[{tag}] 点书 → 导读页，返回按钮指向书架")
        pg.locator("#hSub .lw, #hEyebrow .lw").first.click(); pg.wait_for_timeout(250)
        slip = "#sheet" if pg.evaluate("document.querySelector('#sheet').classList.contains('open')") else "#slipDesk"
        w0 = pg.locator(f"{slip} .sl-word").first.inner_text()
        ok(bool(w0) and pg.locator(f"{slip} .sl-mean").count() == 1, f"[{tag}] 书名下方的德语可点：{w0}")
        inner = pg.locator(f"{slip} .sl-gram .lw, {slip} .sl-mean .lw, {slip} .sl-note .lw, {slip} .sl-lemma .lw")
        if inner.count():
            inner.first.click(); pg.wait_for_timeout(200)
            w1 = pg.locator(f"{slip} .sl-word").first.inner_text()
            pg.locator(f"{slip} [data-slipback]").click(); pg.wait_for_timeout(200)
            ok(pg.locator(f"{slip} .sl-word").first.inner_text() == w0, f"[{tag}] 词卡里的词也能点（{w0} → {w1} → 返回 {w0}）")
        pg.keyboard.press("Escape")
        pg.click('.tab[data-go="read"]'); pg.wait_for_timeout(300)
        pg.locator("#text .w").nth(3).click(); pg.wait_for_timeout(250)
        ok(pg.locator(".sl-word").first.inner_text() != "", f"[{tag}] 精读：点原文词出词卡")
        pg.keyboard.press("Escape"); pg.wait_for_timeout(100)
        pg.click("#backBtn"); pg.wait_for_timeout(400)
        ok(pg.is_visible("#v-home"), f"[{tag}] 返回 → 导读页")
        pg.goto(URL + f"#{courses[0]}~intro-4"); pg.wait_for_timeout(500)
        q = pg.locator("#lessons .lesson:nth-child(4) .qopt").first
        q.click(); pg.wait_for_timeout(150)
        ok(pg.locator("#lessons .lesson:nth-child(4) .qwhy").count() >= 1, f"[{tag}] 基础课练习可作答")
        pg.goto(URL + f"#{bk}~s-0-0"); pg.wait_for_timeout(600)
        ok(pg.is_visible("#v-read") and pg.evaluate("document.querySelector('#s-0-0').getBoundingClientRect().top") < 300, f"[{tag}] 深链接 #{bk}~s-0-0 直达句子")
        ok(not errs, f"[{tag}] 无脚本错误" + (f"：{errs[:3]}" if errs else ""))
        ctx.close()
    b.close()
srv.shutdown()
print("全部通过" if not fails else f"{fails} 项未通过")
sys.exit(1 if fails else 0)
