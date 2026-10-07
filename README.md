# Lesepult · 德语原典逐词精读

网站：**https://letsestel.github.io/lesepult/**

## 更新网站

```bash
python3 scripts/check.py                                   # 检查所有书 + 全站德语是否都查得到
python3 scripts/build.py --standalone -o docs/index.html   # 生成网站（index.html + data/*.json + 离线缓存）
python3 tests/e2e.py docs/index.html                       # 浏览器实测（需要 pip install playwright）
git add -A && git commit -m "更新" && git push             # 推送后一两分钟生效
```

GitHub Pages 从 `main` 分支的 `docs/` 文件夹发布。每次推送，GitHub Actions（`.github/workflows/ci.yml`）会重跑检查、确认 `docs/` 与源文件一致，并做浏览器测试。

## 架构（2026-10 起）

- **全站德语可点**：除了精读原文（逐词标注），书名、引语、章节德文标题、课程讲解、语法注释、词卡里的释义和例子、页脚里出现的每个德语词都是词典链接。页面渲染后由脚本自动加链接：先查当前书的词典（能显示这个词在原文里出现在哪些句子），再查全站词典。`Mün-dig-keit` 这样的拆分会先整体查，查不到再按前缀 `ver-` / 后缀 `-ung` / 词干查。词卡里的词也能点，词卡顶部有「← 上一个词」。
- **全站词典** = `shared/lexicon/*.tsv`（界面、语法术语、人名地名、缩写、构词成分、注释里的普通词）+ 各书词条 + 自动生成的词典形（书里只有 drohet，也能查 drohen）。格式与书的词典相同。`check.py` 会扫描所有会显示的文字，任何查不到的词都会报错并给出位置。
- **按需加载**：网站首页只有约 120 KB（书架 + 程序）；每本书的原文、词典（`data/<书>.json`）在第一次打开时才下载，全站词典（`data/dict.json`）在后台加载。文件名带内容哈希（`?v=`），更新后浏览器自动取新版。书再多，首页也不会变慢。
- **离线 / 可安装**：`sw.js` 缓存看过的书，没网也能读；`manifest.webmanifest` 让手机可以「添加到主屏幕」。
- **一致性检查**：`check.py` 用变格表核对每个 `{格性}` 标注（比如 `dem{nf}` 会报错），防止讲解自相矛盾。
- **两种构建**：`build.py`（默认）生成单文件，用于 Claude artifact；`--standalone` 生成上面的分文件网站；`--standalone --single` 生成单文件完整网页。下面是工具包（reader-kit）的完整说明。

---

# reader-kit：把外语原典做成「零基础逐词精读」书架网站

Lesepult 书架就是用这套工具做出来的：一个网页里放多本书，再加一门所有书共用的德语基础课。`books/kant-aufklaerung/`（短文，入门）和 `books/kant-krv-einleitung/`（纯理导言，长句）是两本完整的样板。加一本新书时，**模板和脚本都不用改**，只需要准备四份数据（书的信息、分好句的原文、词典、专题课），再在 `library.json` 里加一行。

网站包括：
- **书架首页**：基础课入口、每本书的封面和阅读进度、筹备中的书。
- **每本书**：导读、专题课（带练习）、逐句精读（每个词可点开看原形、词性、格以及「为什么是这个格」；每句有语法讲解、译文和学界页码；支持朗读）、词汇表、生词本翻卡。
- **共用的基础课**：发音、格、动词位置等，所有书通用。

适配手机和电脑，支持深色模式；可以生成单文件（Claude artifact），也可以生成按需加载的静态网站（GitHub Pages）。

---

## 目录

```
reader-kit/
  library.json              书架：网站标题文案、上架的书（按顺序）、筹备中的书、共用课程
  template/app.src.html     网页模板（一般不用改）
  profiles/de-zh.json       语言规则：德语原文 → 中文讲解（格、性、变格表、介词支配……）
  shared/lexicon/*.tsv      全站词典：书以外出现的德语（界面、术语、专名、缩写、构词成分、注释用词）
  tests/e2e.py              浏览器端到端测试（含「全站德语可点」审计）
  scripts/check.py          检查全部书和课程 + 生成某本书的「缺词清单」
  scripts/build.py          生成整个书架的单文件网页（dist/index.html）
  courses/de-basics/        共用的德语基础课
    course.json             课程信息；lexiconFrom 指定例句用哪本书的词典
    lessons.json            课程内容
  books/kant-aufklaerung/   样板书 1（短文）
  books/kant-krv-einleitung/ 样板书 2（长句、B 页码、术语表）
    book.json               书的信息、首页文案、字体、主题色、书架封面文案
    text.json               原文：部分 → 句子（原文 / 译文 / 语法讲解 / 页码）
    lessons.json            本书专题课（可含练习题）
    lexicon/*.tsv           词典：每个词形一行
```

运行环境只需要 Python 3。如果装了 Node，构建时会顺便检查网页脚本的语法。

---

## 流水线：九步做一本新书

| 步 | 做什么 | 产出 | 谁来做 |
|---|---|---|---|
| 0 | 选书 | 一段公有领域的原文 | 你 |
| 1 | 建文件夹，上书架 | `books/<id>/book.json`、`library.json` 加一行 | 你 / Claude |
| 2 | 取原文 | 原始文本 | Claude（网络检索） |
| 3 | 分段、分句、标注、翻译、讲解 | `text.json` | Claude，每次一到两段 |
| 4 | 查缺词 | `worklist.tsv` | `check.py --worklist` |
| 5 | 写词条 | `lexicon/NN-*.tsv` | Claude，按清单分批写 |
| 6 | 写本书专题课和练习 | `lessons.json` | Claude |
| 7 | 构建整个书架 | `dist/index.html` | `build.py` |
| 8 | 发布、复查 | Artifact 链接 | Claude + 你在手机上看一遍 |

第 4、5 步要反复做，直到 `check.py` 显示「通过 ✓」。

### 0　选书

- **版权**：必须是公有领域的作品。一般来说，作者去世超过 70 年即可（中国大陆为 50 年）。1900 年以前去世的作者都没有问题，比如康德、歌德、席勒、海涅、尼采、格林童话。也要留意现代译本或现代编校本本身可能有版权，所以尽量用 Projekt Gutenberg、Wikisource、zeno.org 上的旧版本。
- **篇幅**：一个网页适合 2,000–15,000 词。长书按章拆开，每章建一个 book 文件夹，例如 `books/faust-1-nacht/`。
- **难度**：第一次做最好选短篇散文。诗歌和戏剧也能做，每一行或每一句台词就是一个「句子」。

### 1　建文件夹

复制样板，然后清空数据：

```bash
cp -r books/kant-aufklaerung books/<新id>
cd books/<新id> && rm -f lexicon/*.tsv && echo '[]' > lessons.json && echo '[]' > text.json
```

改 `book.json`（字段说明见下文）。`id` 要改成新的，否则两本书会共用浏览器里的学习进度。另外删掉 `legacyStorage` 这一项，它只是康德那本用来迁移旧进度的。

然后在 `library.json` 的 `books` 里加上文件夹名，它就上架了；顺序就是书架上的顺序。还没开始做的书可以先写成一个对象占位，书架上会显示「筹备中」：

```json
{"id": "kant-prolegomena", "planned": true, "title": "Prolegomena", "zh": "未来形而上学导论",
 "author": "Immanuel Kant", "year": "1783", "mast": "Prolegomena", "blurb": "……", "level": "进阶 · 筹备中",
 "accent": "#5c5a2e", "accentDark": "#c9c48a"}
```

长书（比如整部《纯粹理性批判》）建议按章或按节建成几本「书」，每本几千词，书名里写清范围。

### 2　取原文

让 Claude 从可靠来源取全文，保留原拼写，并记下版本和出处（之后写进 `footer`）。

### 3　写 `text.json`：最费工夫的一步

每个「部分」相当于原文的一段，每个「句子」是一句话。超长的句子可以在冒号或分号处拆开，并在讲解里注明「原文是同一句」。

```json
[
  {"h": "一 · 启蒙的定义", "t": "Die Definition", "k": "1", "s": [
    {"de": "*Unmündigkeit* ist das{nn} Unvermögen, sich{refl} seines{gm} Verstandes … zu bedienen.",
     "zh": "不成年状态，就是没有他人的引导便无法运用自己的知性。",
     "n": ["结构：A ist B, + zu-不定式……", "sich + 属格 + bedienen：……"]}
  ]}
]
```

- `h`：中文小标题；`t`：原文语言的小标题（可省）；`k`：段落导航上显示的编号（数字、罗马数字，或「题」「注」这类字）；`pg`：这一部分的学界页码（可省，例如 `"B 1–3"`）。句子上也可以加 `pg`，显示在句号旁边。
- `de`：原文，带标注（见下）。`zh`：通顺的中文译文。`n`：语法讲解，**第一条讲句子骨架**（主干是什么、动词在哪），后面逐条讲难点。

**标注语法**（写在原文里，网页上不会显示）：

| 写法 | 含义 | 例子 |
|---|---|---|
| `*…*` | 原文的疏排（加宽）强调 | `*Aufklärung*` |
| `_…_` | 外文 / 拉丁文，显示为斜体 | `_Sapere aude!_` |
| `词{格性}` | 这个冠词或代词在此处的格与性：`n a d g` + `m f n p` | `der{gf}` = 阴性单数属格 |
| `词{义项}` | 选用词典里的某个义项 `词#义项` | `sie{they}`、`es{expl}`、`ab{sep}` |
| `词{义项:格性}` | 两者同时 | `der{rel:nm}` = 关系代词，阳性主格 |
| `<<…>>` | 只用在练习题里，标出被考查的词 | `ist <<der>> Aufklärung hinderlich` |

**要标格的词**：所有冠词、物主代词、指示代词和关系代词，也就是 der/die/das 类、ein 类、dieser 类，以及 sein/ihr。标了格，网页才能显示「此处：阴性 · 单数 · 属格」、语法着色、变格表和「为什么是这个格」。名词和形容词不用标。

**要选义项的词**：同一个拼写有不同身份时才需要，比如 `der`（冠词 / 关系代词 / 指示代词）、`sie`（她 / 他们 / 他们〔宾格〕）、`es`（它 / 形式主语）、句末的可分前缀（`ab{sep}`）。

### 4　查缺词

```bash
python3 scripts/check.py books/<id> --worklist
```

脚本会列出每个还没有词条的词形，以及带义项标注但词典里没有对应义项的写法，并写出 `worklist.tsv`。文件按出现次数排序，每行附一句上下文。

### 5　写词典 `lexicon/*.tsv`

每个**词形**一行（不是每个词一行：`Verstand`、`Verstandes`、`Verstande` 各一行），用 `|` 分隔，共 6 个字段：

```
词形(小写)|原形|词性|语法|释义|用法注释
verstandes|der Verstand|N|名词 · 阳性 · 单数 · 属格|知性的|sich seines Verstandes bedienen：运用自己的知性。全文出现最多的词组。
der#rel|der / die|R|关系代词|（……的）那个|关系代词形式和定冠词几乎一样……
```

- **释义**：用「；」分隔多个意思，第一个会作为行间释义显示在词下方，所以要短（2–6 个字）。
- **词性代码**（在 profile 里定义）：N 名词，V 变位动词，I 不定式 / 分词，A 形容词，D 副词，P 介词，K 连词，R 代词，T 冠词 / 限定词，Z 小品词 / 可分前缀，X 外文，M 缩写。
- **用法注释**写这些内容：固定搭配、这个词在本书里的特殊义（古义、术语）、与今天用法的不同、构词拆解。不需要每个都写，但难词、高频词、术语一定要写。
- 文件可以按字母拆成几个（`01-a-d.tsv`……），脚本会全部读入。以 `#` 开头的行是注释。

写完后回到第 4 步，直到通过检查。

### 6　写入门课 `lessons.json`

```json
[{"t": "四个格（下）：与格和属格怎么分", "de": "Dativ oder Genitiv?", "min": 20,
  "html": "<p>……第三步的讲解……</p>[[ist der{df} Aufklärung hinderlich]]{{quiz:s3}}",
  "quiz": [{"id": "b1", "sec": "s3", "de": "ist <<der>> Aufklärung hinderlich", "opts": ["与格","属格"], "ans": 0, "why": "hinderlich 要求与格……"}]}]
```

- `html` 里的 `[[…]]` 会变成可点、可朗读的例句，同样支持标注语法。
- 每道题要有唯一的 `id`。题目里用 `<<…>>` 标出被考查的词，**不要给它标格**，否则学生点开词卡就看到答案了。
- **练习紧跟讲解**：给题目加 `"sec": "s1"`，再在 html 里对应讲解的后面放 `{{quiz:s1}}`，这一组题就出现在那里。题目顺序要和讲解顺序一致，不要考还没讲过的东西。只想放一组题在末尾时，可以不写 `sec`，直接用 `{{quiz}}`。
- 可用的样式有：`<div class="tip">` 提示框、`<p class="formula">` 公式行、`<table class="tbl">` 表格（外面套 `<div class="scroll">`）、`<ol class="steps">` 步骤、`<div class="roles">` 句子成分图、`<div class="attach">` 依附关系图（写法参考康德那本的第 4、5 课）。

**写课的原则**：只教读这本书用得上的语法；例句全部取自原文（这样词典已经覆盖，例句里的词都能点开）；最难的点单独成课，并配练习题和答错时的解释。

### 7　构建

```bash
python3 scripts/check.py                       # 检查书架上所有的书和课程
python3 scripts/build.py                       # 生成 dist/index.html（发布成 Claude artifact 用）
python3 scripts/build.py --standalone          # 生成完整的独立网页（放到 GitHub Pages、自己的服务器用）
```

构建前会先自动检查，没通过就停下（加 `--force` 可以强制构建，用来预览半成品）。

### 8　发布与复查

把 `dist/index.html` 交给 Claude，说「发布成 artifact」。以后更新时说「发布到同一个链接」。

发布后用手机和电脑各看一遍：
- 首页示例句能点，词卡能弹出。
- 抽查 20 个冠词，看格标得对不对，「为什么是这个格」的解释是否合理。
- 做一遍练习题。
- 打开「语法着色」和「行间释义」，读一整段，看排版有没有挤在一起。

---

## 网页里的导航

网页是单文件的「单页应用」：五个栏目在同一个页面里切换，每次切换都记在导航记录里。
- 顶栏左边有「← 返回 xx」按钮，写明会回到哪里。在 Claude App 里看时没有浏览器的返回键，就靠这个按钮。
- 浏览器的返回键、安卓返回键、iPhone 的左滑返回也走同一条路径。手机上词卡打开时，按返回只会关闭词卡。
- 返回后会回到原来的滚动位置，词汇表的搜索词也会保留。切换栏目时，每个栏目都记得你上次看到哪里。
- 链接末尾可以加位置：`#lib`（书架）、`#<书id>~home|intro|read|vocab|saved`、`#<书id>~s-5-3`（第 5 部分第 4 句，从 0 开始数）、`#<书id>~intro-2`（本书第 2 节专题课）、`#de-basics~intro-3`（基础课第 3 课）。旧版的 `#read` 这类链接会自动打开默认的那本书。
- 每本书的进度、生词本、练习记录分开保存；行间释义、字号这些显示设置全站共用。

## 共用课程 `courses/<id>/`

所有书都需要的语法课放在这里，书架首页和每本书的课程页顶部都有入口。`course.json` 的 `lexiconFrom` 指定例句取自哪本书：例句里的词用那本书的词典，词卡里的「出处」会跳到那本书的原文。例句必须真的出自那本书，否则检查不通过。

## `library.json` 字段

| 字段 | 说明 |
|---|---|
| `title` / `subtitle` / `eyebrow` / `lede` | 书架首页的标题、副标题、上方小字、介绍段 |
| `description` | 发布时的一句话简介 |
| `fontsHref` / `fonts` | 全站字体（每本书还可以在自己的 book.json 里覆盖） |
| `footer` | 书架页脚 |
| `courses` | 共用课程的文件夹名 |
| `books` | 上架的书：文件夹名，或筹备中的占位对象 |
| `default` | 旧链接（如 `#read`）打开哪本书 |

## `book.json` 字段

| 字段 | 说明 |
|---|---|
| `id` | 英文短名，也用作浏览器里存进度的命名空间 |
| `profile` | 用哪个语言规则，对应 `profiles/<名>.json` |
| `title` | 书的原文标题（书架封面下方、词卡等处） |
| `short` / `zh` / `author` / `year` / `level` / `blurb` | 顶栏的短名、中文书名、作者、年份、难度标签、书架上的简介 |
| `brandMark` | 顶栏的一个字母或字 |
| `mast` / `eyebrow` / `subtitle` / `lede` | 首页大字标题、上方小字、副标题、介绍段 |
| `demo` / `demoCaption` | 首页互动示例用哪一句：`[部分序号, 句子序号]` |
| `howto` | 首页三步说明 |
| `intro` / `vocab` / `saved` | 各栏目标题文案 |
| `slipEmpty` | 词卡空白时的提示（可以用 `<br>`） |
| `footer` | 出处与版权说明 |
| `fontsHref` / `fonts` | Google Fonts 链接，以及正文、大标题、译文三种字体 |
| `theme` | 主色（浅色 / 深色各一套） |
| `description` | 发布 artifact 时的一句话简介 |

**字体建议**：德语用 Literata，大标题可以用 UnifrakturMaguntia（哥特体，适合 18–19 世纪德语书）；法语可以用 EB Garamond；拉丁文可以用 Cormorant；俄语可以用 PT Serif。中文译文用 Noto Serif SC。

---

## 换一种语言

复制 `profiles/de-zh.json`，改成例如 `fr-zh.json`、`la-zh.json`、`ru-zh.json`：

- `letters`：这门语言的字母（正则字符类），比如法语 `A-Za-zÀ-ÿŒœ'’`，俄语 `А-Яа-яЁё`。
- `tts`：朗读语言代码，比如 `fr-FR`、`ru-RU`。拉丁文没有语音，可以用 `it-IT` 代替。
- `cases` / `caseOrder` / `genders` / `genderOrder` / `keyPattern`：格和性的代码与名称。拉丁文和俄语有六个格，加上去就行。**没有格的语言**（法语、英语）把 `keyPattern` 设为 `"^$"`，`tables` 和 `governors` 设为空，`legend` 只留动词。
- `tables`：词卡里显示的变格表。
- `governors`：介词支配哪个格，用于自动解释「为什么是这个格」。
- `reasons`：上面这些解释的中文措辞。
- `pos`：词性代码和名称。

模板会自动读取这些规则，不需要改代码。

---

## 让 Claude 做每一步时的提示词

在新对话里先把 `reader-kit` 交给 Claude（上传 zip，或者让它读工具包所在的位置），再按步骤说：

**第 2–3 步（每次一到两段）**
> 用 reader-kit 做〈书名〉。读 README 和 books/kant-aufklaerung 的 text.json 作为样板。现在请把原文第 N–M 段写进 books/<id>/text.json：分句；按 README 的标注语法给所有冠词、物主代词、指示代词和关系代词标格与性，给有歧义的 der/sie/es 和句末的可分前缀标义项；每句写通顺的中文译文；语法讲解第一条讲句子骨架，后面逐条讲难点。我是零基础，讲解要细。

**第 5 步**
> 运行 check.py --worklist，然后按 worklist.tsv 的顺序写词条，每批 250 个，存成 lexicon/NN-*.tsv。格式和详细程度照 kant-aufklaerung 的词典。写完再跑一次 check，直到通过。

**第 6 步**
> 根据这本书写专题课 lessons.json：这本书在讲什么（结构图）、术语表（带练习）、这本书特有的句型。通用语法已经在共用基础课里，不要重复。例句全部取自本书原文。

**第 7–8 步**
> 在 library.json 里把这本书加上书架，运行 check.py 和 build.py，把 dist/index.html 发布到原来的 artifact 链接。

---

## 检查清单

- [ ] `check.py` 通过，0 个缺词
- [ ] 每句都有译文；讲解第一条是句子骨架
- [ ] 所有冠词和代词都标了格（可以开「语法着色」，看有没有漏掉下划线的冠词）
- [ ] 练习题的考查词没有标格
- [ ] `footer` 写清出处与版权状态
- [ ] 手机上读完一整段
