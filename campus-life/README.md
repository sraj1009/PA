# 校园生活 (Campus Life) — WeChat Mini Program

A two-module, **fully local** WeChat Mini Program: three 本地生活工具 plus four 社交互动 features, with an AI agent that runs on the developer's own machine (Ollama) and degrades to a deterministic offline engine when it is not there.

- Spec: `docs/2026-10-12-design.md` (owns the *why*)
- Plan: `docs/2026-10-12-implementation-plan.md` (owns the *how*, task by task)
- Nothing here is committed to git — the user asked for the source only.

**Status:** built and verified on 2026-10-12 by jest + `miniprogram-simulate` (real WXML/WXSS compiled and mounted, real taps driven, real DOM asserted) plus a live run against the machine's own Ollama. **It has never been opened in WeChat DevTools**, so the list in *What this machine cannot prove* is genuinely unverified — not "done, assume so".

---

## Verified run

Full suite, pasted from the terminal (one complete run; the timings and the model's wording change run to run):

```
$ cd campus-life && npx jest

Test Suites: 27 passed, 27 total
Tests:       223 passed, 223 total
Snapshots:   0 total
Time:        11.13 s
Ran all test suites.
```

The 27 suites break down as **11 pure-logic** (`core/*` + `agent/*`, 115 tests), **8 page-render** (every screen mounted from real WXML, 77 tests), **4 component**, plus `harness`, `shim-lifecycle`, `integration`, and `live-ollama`. No screen ships without a test that taps it.

Live agent run inside that suite (`tests/live-ollama.test.js` talks to the real model, and prints what came back):

```
[live classify] 探测 736 ms · 分类 1190 ms · 原文输入「明天要交论文，紧张得一点也睡不着」→ {"mood":"anxious","intensity":0.7}
[live chat] 1140 ms → 那感觉确实不怎么好，有事儿和朋友说说看。
[live mode] agent.mode() = llm
[live mode] classify source=llm mood=joy intensity=0.8
[live degrade] llm 不可达 → source=offline degraded=true mood=anxious
```

Those five lines are the spec's §8 requirement "live LLM run, with measured latency and the actual returned text quoted". The chat reply is not deterministic (temperature 0.85) — every run prints whatever the model actually said, and this README quotes one real run rather than a best-of. Classification latency for the same sentence varied between **1.2 s and 14.9 s** across the runs made while building this (cold vs. warm model), which is why the call timeout is a per-call degrade rather than an error screen.

Cross-feature wiring, measured in `tests/integration.test.js` (real pages, real storage, no mocks):
| Action | Observed result |
|---|---|
| 树洞 publish 「答辩排在周一，晚上睡不着」 | post tagged `mood=anxious, source=offline`; 心情雷达 six axes read `26 \| 0 \| 26 \| 0 \| 68 \| 0`; the record card says `来自树洞` |
| retract that post | radar returns to the zero state (nothing left behind) |
| 探索 tap one 打卡 | 首页 reads `连续打卡 1 天` and `走过 1 / 12 个校内地点` |
| 社群 join `g01` | 聊天 topic row reads `摄影 \| 相机 \| 后期`, session stores `topics` |
| 规划 add a task + 生成今日安排 | 首页 reads `1 段安排` |

---

## Run it yourself

```bash
cd campus-life
npm install          # jest, jest-environment-jsdom, miniprogram-simulate
npx jest             # 27 suites, 223 tests, no network required
npx jest tests/page-index.test.js        # one screen
npx jest tests/integration.test.js       # cross-feature wiring
```

The live model suite is self-skipping: without Ollama it prints
`[live-ollama] SKIPPED：本机 http://localhost:11434 没有响应…` and the rest of the suite still passes.

```bash
ollama serve                              # terminal 1
ollama pull qwen2.5:3b                    # default model, agent/llm.js DEFAULT_MODEL
npx jest tests/live-ollama.test.js        # terminal 2 — prints latency + raw replies
```

Opening it in DevTools: 导入项目 → select `campus-life/`; `project.config.json` sets `compileType: miniProgram` and `appid: touristappid`, so no credentials are needed. **Turn on 不校验合法域名** or the `http://localhost:11434` probe will be blocked (see the gap list).

---

## The seven features

| 模块 | 功能 | 页面 | 逻辑 | 屏幕上说真话的地方 |
|---|---|---|---|---|
| 本地生活工具 | 本地探索打卡 | `pages/explore/` | `core/checkin.js` + `data/spots.js` (12 spots) | 没打卡就写 `今天还没打卡`；页面上唯一的百分比是「你自己的 12 个示例地点走过几个」（`8%` 这类），首页则写成 `走过 1 / 12 个校内地点`；地点列表标注 `地点为示例数据` |
| 本地生活工具 | 时间管理智能规划 | `pages/planner/` | `core/planner.js` 纯约束求解（优先级/截止/时长/固定日程） | 页脚 `安排由本地算法生成`；`让 AI 说明` 只是把求解结果改写成句子，句子旁边挂着 `mode-badge` |
| 本地生活工具 | 周边好店聚合 | `pages/shops/`, `pages/shop/` | `core/shops.js` + `data/shops.js` (20 家) | 示例数据标注在列表和详情上；距离由 `haversineKm` 现算 |
| 社交互动 | 校园树洞 | `pages/treehole/` | `core/posts.js` + `core/mood.js` | 每条带 `离线词库标注` / `本地模型标注`；`内容仅存于本机`；匿名代号由「哪一天」派生（同一天稳定），词表固定、不来自设备号 |
| 社交互动 | 匿名一对一聊天 | `pages/chat/` | `core/chat.js` (空闲 300000 ms 关闭, 270000 ms 预警) | 同伴全程标 `模拟/AI`；剩余时间到 30 s 出现警告行；`onUnload` 清定时器 |
| 社交互动 | 兴趣社群匹配 | `pages/groups/` | `core/groups.js` → `agent.match`（关键词 + IDF + 共现） | 每条匹配给 `reasons[]` 文字，不给假百分比；排名不用 LLM，保证可复现 |
| 社交互动 | 心情雷达 | `pages/radar/` + `components/mood-radar/` | `core/moodscore.js` 六轴 0..100 | 窗口里没有记录时画的是 zero state（`近 N 天还没有记录`），不画雷达；每个角都能追到用户自己写过的记录（`来自树洞` / 手动记一笔），走势条只画有记录的日子，空日子不补零 |
| 外壳 | 首页仪表盘 | `pages/index/` | 只读 store，不写 | 三张状态卡 + `mode-badge` + 两个模块入口；`本机共 n 条（心情 x · 树洞 y）` |

`pages/__probe/` is the harness's own fixture page (Task 1). It is **not** in `app.json`'s page list, so it is unreachable in the app.

---

## Layering (enforced, not aspirational)

```
pages/      Page() — lifecycle, setData, navigation. No domain maths.
components/ mode-badge, nav-card, empty-state, mood-radar (Component())
adapters/   local.js — the ONLY production file that touches wx storage/location/request
core/       pure CommonJS: store, schema, checkin, planner, shops, posts, mood,
            moodscore, groups, chat, format  ← grep for `wx` here returns nothing
agent/      index.js (probe + per-call degrade), llm.js, offline.js, lexicon.js, prompts.js
data/       spots (12) / shops (20) / groups (12) — seeded sample data, labelled 示例数据
theme/      tokens.wxss — single source for colour/spacing/type
tests/      jest + miniprogram-simulate (27 suites)
```

Nothing above `agent/` knows whether a reply came from the model or the lexicon.

**Storage:** one versioned key `cl:v1`, owned by `core/store.js` (`read()` / `write(mutator)` / `reset()` / `raw()`); `core/schema.js` exports `schema()` (the plan's draft called it `schema.empty()`; `schema()` is what shipped) and `migrate(raw)`, which re-fills any missing key so a half-written storage value can never white-screen a page. On a quota error, `write` prunes oldest chat messages (keeps newest 20), then oldest `closed: true` posts, and only then raises `QuotaError`.

**Agent adapter:** `auto` probes `GET http://localhost:11434/api/tags` once (1500 ms budget). `classify` uses `POST /api/chat` with a JSON schema at `temperature 0` (one retry if the reply is not parseable), `chat` runs at `0.85`, `explain` at `0.4`. After the probe, **every** call independently degrades: if the model dies mid-session the page gets an extra `离线模式` note instead of an error screen, and the result carries `source` + `degraded`. `match` is never sent to the model — the spec's ranking has to stay reproducible.

---

## Honesty rules and the test that holds each one

| Rule | Held by |
|---|---|
| Chat partner is 模拟/AI, never presented as a person | `tests/page-chat.test.js` asserts the label in the mounted DOM |
| Local-data screens say `内容仅存于本机` | asserted in the mounted DOM by `page-chat`, `page-explore`, `page-groups`, `page-index`, `page-radar`, `page-shops`, `page-treehole` — one test per screen, so deleting a label turns a suite red |
| The active engine is always visible | `tests/comp-mode-badge.test.js`, `tests/page-index.test.js` — the badge reads `离线模式` on first mount and only becomes `本地模型` after a `/api/tags` request actually succeeds |
| No fabricated campus-wide statistics | `page-index` asserts the dashboard markup `not.toMatch(/%/)`; `page-planner` asserts the AI prose names tasks, not ids |
| No data → no number | `moodscore` unit test: empty events give six zeros, never a "looks normal" 50 |
| Empty list = explained empty state, not a blank card | `tests/comp-empty-state.test.js`, `page-index` |
| No cloud | the only URL in `agent/llm.js` is `localhost:11434`; `wx.request` is stubbed to fail by default in tests, and every screen still renders |

Shipable source (excluding `tests/`, `docs/`, `node_modules/`, and the harness probe page) is **149,578 bytes ≈ 146 KB**, ~7 % of the 2 MB main-package ceiling.

---

## Maintaining the tests (things this harness does not do the way you expect)

Found empirically; each cost a debugging pass, so they are written down.

- `miniprogram-simulate` only knows `Component()`. Real pages stay `Page()`; `tests/helpers/shim.js` registers a `Page(options)` as a component with `launchQuery` and maps `onLoad/onShow/onReady/onHide/onUnload` onto lifetimes/`pageLifetimes`. `tests/shim-lifecycle.test.js` mounts a fixture page and pins that mapping, so a silent break in the shim fails loudly instead of quietly skipping assertions.
- `global.wx` must be seeded **before** `miniprogram-simulate` is required (`definition.js:29` does `Object.assign(api, global.wx)`, so ours wins). That is `tests/setup.js`.
- `simulate.render()` gives you `dom/data/setData/querySelector/attach/dispatchEvent/triggerLifeTime/triggerPageLifeTime/instance`. `page.selectComponent` is **undefined on the wrapper** — `page.instance` is the component caller that actually has `selectComponent`/`selectAllComponents` and the page's methods.
- Component internals are materialised in the real jsdom tree with class prefix `<tagName>--<class>`. To assert inside a component from a page test, use `helpers/render.js` → `innerText(page, '.js-advice-mode', 'badge')`.
- Neither raw exparser `node.dispatchEvent('tap')` on a child node nor `domElement.click()` fires a WeChat handler across the component boundary. `tapInner()` works because it uses the same mechanism j-component itself uses: `exparser.Event.dispatchEvent(el.__wxElement, exparser.Event.create('tap', {}, {bubbles, capturePhase, composed}))`.
- A property observer does **not** run when the property equals its default. `mode-badge` therefore carries the offline copy in `data`, not only in `sync()`.
- `simulate.load` throws `invalid componentPath` if the sibling `.json` is missing, and a file can only be loaded **once per process** (`compile()` caches by path). Loading a page also registers its `usingComponents`, so a component test must live in its own file.
- `setInterval` outlives the test unless the page is detached. `page-chat.test.js` tracks every mount and detaches in `afterEach`; auto-close cases poll for the banner rather than betting on a fixed `sleep`.
- Every interaction needs `await simulate.sleep(10)` — events are async microtasks.

---

## Deviations from the design doc

Stated plainly so nobody has to rediscover them:

1. **Components.** §4 listed eleven (`mode-badge, nav-card, tag, progress-ring, empty-state, tab-bar, chat-bubble, mood-axis, shop-card, checkin-item, task-row`). Four shipped as real components: `mode-badge`, `nav-card`, `empty-state`, `mood-radar`. The rest exist as classes in `app.wxss` / page WXSS (`.tag`, `.btn`, `.slot`, `.row-*`) because the pages already had to own that markup and a component per row would only add a boundary to cross.
2. **`empty-state` is used on the dashboard only.** The older screens keep their own inline `.empty` / `.zero` blocks, which their page tests already assert (`count(page, '.empty')`, `text(page, '.zero')`), and each one carries screen-specific copy. Swapping them for the component would churn tested markup for no behaviour change, so it was left alone rather than done as decoration.
3. **`schema.empty()` → `schema()`**, and §4's `core/matcher.js` + `core/shopfilter.js` shipped as `agent/offline.js` (`match`) and `core/shops.js`. `data/seed.js` shipped as three files (`spots`, `shops`, `groups`).
4. **`app.js` globalData no longer carries `agentMode`.** Engine state has one source of truth (`agent.mode()`, read by `mode-badge`); a second copy in `globalData` was guaranteed to disagree with it. Nothing reads `globalData` today except the shell's `windowWidth`.
5. **Radar is DOM, not canvas.** `components/mood-radar` draws the hexagon from `moodscore.polygon()` geometry as positioned views/edges so tests can assert coordinates and labels. A `wx.createCanvasContext` version would look smoother on device — it is an upgrade, not a requirement, and no test here depends on it.

---

## What this machine cannot prove (open, not "done")

There is **no WeChat DevTools** on this box, so the following are unverified. Do not report them as working until a device or simulator pass confirms each one.

- [ ] **On-device navigation.** `wx.switchTab` / `navigateTo` / `navigateBack` are recorded by a test double. The real page stack, tab-bar switching, and `getCurrentPages()` behaviour have never run.
- [ ] **tabBar icon images.** `app.json`'s tabBar has five text-only entries (no `iconPath`). WeChat accepts a text-only bar, but the visual result on a phone has never been seen, and no icons were generated here.
- [ ] **Real GPS permission flow.** `adapters/local.js#locate()` chains `getSetting → authorize → getLocation(gcj02)`; tests only ever see the stubbed success (and a `denyLocation` branch). The system dialog, a denied scope, and the 校内/附近 manual fallback under real denial are unconfirmed.
- [ ] **`wx.request` domain whitelisting.** On a phone `http://localhost:11434` is unreachable **by design** — the agent will therefore be 离线模式 on device, always. In DevTools it works only with 不校验合法域名 enabled. Neither case has been observed here.
- [ ] **`rpx` rendering on physical screens.** All layout uses the token scale, but nothing has been measured on a 375 pt / 414 pt / tablet viewport. Long Chinese strings wrapping out of a `.chip` or a `.slot-r` column is a real possibility.
- [ ] **Share cards / `onShareAppMessage`.** Not implemented. The shim maps the lifecycle, but no page produces a share title or image.
- [ ] **Visual polish.** Colours, shadows, and spacing are code-verified against `theme/tokens.wxss`, never eye-verified.
- [ ] **Real-device storage quota.** The prune path is driven by an injected throw (`tests/store.test.js`), not by WeChat actually refusing a >10 MB write.
- [ ] **Model availability on another machine.** Live numbers above come from this machine's `qwen2.5:3b`. A slower GPU or a cold model may exceed the 6 s call timeout, in which case every call degrades to offline — correct behaviour, but visually a permanently 离线模式 badge.

Known small gap worth fixing next, not blocking the current suite:
- `agent.setPreference` (force `local` / `llm`) is implemented and unit-tested but has **no UI**; the preference is read from `settings.agentMode` in storage and nothing writes it. Today the engine is chosen purely by the launch probe, which is what the spec asked for — a manual switch would need a settings screen plus its own render test.
