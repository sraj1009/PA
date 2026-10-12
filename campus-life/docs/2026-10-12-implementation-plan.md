# Campus Life Mini Program (校园生活小程序) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a two-module, fully local WeChat Mini Program (3 local-life tools + 4 social features) that runs an AI agent over local Ollama with a deterministic offline fallback.

**Architecture:** Thin `Page()` files own lifecycle only; all domain logic lives in `core/` as pure CommonJS functions with zero `wx` references; all persistence flows through one injected storage adapter; an `agent/` adapter picks `LlmAgent` (local Ollama) or `OfflineAgent` (lexicon + keyword/IDF) at launch and degrades per-call.

**Tech Stack:** WeChat Mini Program (WXML/WXSS/JS, CommonJS), Node 24, jest 30 + jest-environment-jsdom + `miniprogram-simulate@1.6.2` (official WXML compiler), Ollama `qwen2.5:3b`.

**Spec:** `campus-life/docs/2026-10-12-design.md` — read it with this plan; the spec owns the why, this plan owns the how.

**Status:** Tasks 1–11 executed on 2026-10-12 (27 suites / 223 tests green, incl. a live Ollama run). Measured output and the DevTools-only gap list live in `campus-life/README.md`; where the shipped code differs from the wording below, the README's *Deviations from the design doc* is authoritative.

## Global Constraints

Every task implicitly includes these. Values are copied verbatim from the spec and from measured environment facts.

- **No cloud services.** Zero network calls except `http://localhost:11434` on the developer's own machine. No SDK, no analytics, no map provider.
- **No `git commit` steps.** The user explicitly chose not to commit this project; each task ends with a green suite instead.
- **Platform ceilings:** 2 MB main package, 10 concurrent `wx.request`, ~10 MB storage quota, 200 nodes per screen.
- **Honesty rules, enforced in copy:** chat partner is labelled `模拟/AI`; every screen holding local data states `内容仅存于本机`; the active engine is always visible via `mode-badge` (`本地模型` / `离线模式`); no fabricated campus-wide statistics anywhere.
- **Visual:** cool tones only — blue `#3B6EF6`, cyan `#22C7D6`, purple `#7A5AF8`, mint `#2ED3A7`, ink `#101B33`, surface `#FFFFFF`, canvas `#F2F5FB`, muted `#7B89A6`. 4/8-pt spacing scale, `rpx` units, radius 12/16/24.
- **Copy language:** Simplified Chinese for all user-facing strings.
- **`core/` purity:** no file under `core/` may reference `wx`, `getApp`, or `Page`. Tests import them directly with plain `require`.
- **Event timing:** simulate dispatches events as async microtasks — every interaction test must `await simulate.sleep(10)` before asserting.
- **Verify-before-claiming:** a feature is done only when its render test passes AND its pure-logic test passes. Never report green without pasted output.

---

## Task 1: Harness, tokens, and the page shim

Validates the one unproven assumption in the spec before any feature is built on top of it, and lands the scaffolding every later task needs.

**Files:**
- Create: `campus-life/project.config.json`
- Create: `campus-life/app.json`, `campus-life/app.js`, `campus-life/app.wxss`
- Create: `campus-life/sitemap.json`
- Create: `campus-life/theme/tokens.wxss`
- Create: `campus-life/package.json`, `campus-life/jest.config.js`
- Create: `campus-life/tests/helpers/shim.js`
- Create: `campus-life/tests/helpers/render.js`
- Create: `campus-life/tests/helpers/memory-storage.js`
- Create: `campus-life/tests/harness.test.js`
- Test: `campus-life/tests/harness.test.js`

**Interfaces:**
- Produces: `shim.install(globals)` — defines `Page`, `Component`, `getApp`, `wx` bridging for tests.
- Produces: `render.loadPage(name)` → mounted component instance; `render.tap(node, name)`, `render.text(node, selector)`.
- Produces: `memoryStorage()` → `{ get(k), set(k,v), remove(k), dump() }`, the test double for storage.

- [x] **Step 1: Write the failing harness test**

`campus-life/tests/harness.test.js` — this test both drives TDD and *is* the shim validation. It renders a real `Page()`-built page from disk through the official compiler.

```js
const path = require('path');
const { loadPage, tap, text } = require('./helpers/render');

jest.setTimeout(30000);

test('a standard Page() file compiles, renders, and reacts to tap', async () => {
  const page = await loadPage('__probe');            // pages/__probe/* exists only for this test
  expect(text(page, '.hd')).toContain('探针');       // proves {{}} binding rendered
  expect(page.querySelectorAll('.row').length).toBe(3); // proves wx:for expanded

  await tap(page, '.hd');                             // proves bindtap -> handler -> setData
  expect(text(page, '.hd')).toContain('已点击 1 次');
});
```

- [x] **Step 2: Run it to verify it fails**

Run: `cd campus-life && npx jest tests/harness.test.js`
Expected: FAIL — `Cannot find module './helpers/render'`.

- [x] **Step 3: Write the shim**

`tests/helpers/shim.js`. The critical detail, learned from the spike: `global.wx` must be pre-seeded *before* `miniprogram-simulate` is required, because `definition.js:29` does `Object.assign(api, global.wx)` — ours wins.

```js
const simulate = require('miniprogram-simulate'); // requires global.wx to be pre-seeded

const PAGE_LIFECYCLE = new Set([
  'onLoad', 'onShow', 'onReady', 'onHide', 'onUnload', 'onPullDownRefresh',
  'onReachBottom', 'onShareAppMessage', 'onPageScroll', 'onTabItemTap',
]);

function install() {
  global.Page = function Page(options = {}) {
    const methods = {};
    Object.keys(options).forEach((k) => {
      if (typeof options[k] === 'function' && !PAGE_LIFECYCLE.has(k)) methods[k] = options[k];
    });
    Component({
      properties: { launchQuery: { type: Object, value: {} } },
      data: options.data || {},
      methods,
      lifetimes: {
        attached() {
          if (options.onLoad) options.onLoad.call(this, this.properties.launchQuery || {});
          if (options.onReady) Promise.resolve().then(() => options.onReady.call(this));
        },
        detached() { if (options.onUnload) options.onUnload.call(this); },
      },
      pageLifetimes: {
        show() { if (options.onShow) options.onShow.call(this); },
        hide() { if (options.onHide) options.onHide.call(this); },
      },
    });
  };
  global.getApp = () => global.__app || { globalData: {} };
}

module.exports = { install, simulate };
```

- [x] **Step 4: Write the render helper and memory storage**

`tests/helpers/memory-storage.js` — a `wx`-shaped storage double plus a request recorder.

```js
function memoryStorage(initial = {}) {
  const data = new Map(Object.entries(initial));
  return {
    get(k) { return data.has(k) ? data.get(k) : ''; },
    set(k, v) { data.set(k, v); },
    remove(k) { data.delete(k); },
    dump() { return Object.fromEntries(data); },
  };
}
module.exports = { memoryStorage };
```

`tests/helpers/render.js` — one entry point so no test hand-rolls `global.wx`.

```js
const path = require('path');
const ROOT = path.join(__dirname, '..');

function makeWx(over = {}) {
  const nav = [];
  const wx = {
    setStorageSync: (k, v) => { storage.set(k, v); },
    getStorageSync: (k) => storage.get(k),
    removeStorageSync: (k) => storage.remove(k),
    navigateTo: (o) => nav.push(o.url),
    switchTab: (o) => nav.push(o.url),
    showToast: (o) => nav.push('toast:' + o.title),
    request: (o) => (requests.push(o), fail(o)),
    getSetting: (o) => o.success && o.success({ authSetting: {} }),
    getLocation: (o) => o.success && o.success({ latitude: 30.5, longitude: 114.4 }),
    createSelectorQuery: () => fakeQuery(),
    ...over,
  };
  return { wx, nav, requests };
}
// loadPage(name): pre-seed global.wx -> shim.install() -> simulate.load(ROOT/pages/name/index)
//   -> render -> attach to document.body -> await simulate.sleep(10)
// tap(page, sel): page.querySelector(sel).dispatchEvent('tap'); await simulate.sleep(10)
// text(page, sel): (page.querySelector(sel) || {dom:{innerHTML:''}}).dom.innerHTML
```

Implement `loadPage`, `tap`, `text`, `fakeQuery`, `fail` fully — no stubs. `loadPage` must throw a clear error if `Component is not a function`, which is the signal that the shim assumption is wrong and the documented fallback applies.

- [x] **Step 5: Create the probe page and run the harness test**

Create `campus-life/pages/__probe/{index.js,index.wxml,index.wxss,index.json}` using `Page({ data: {title:'探针', rows:[1,2,3], n:0}, onTap(){ this.setData({title:'探针 已点击 '+(++this.data.n)+' 次'}) } })`.

Run: `npx jest tests/harness.test.js`
Expected: PASS. **If it fails on `Component is not a function`, STOP and switch to the spec's documented fallback (thin pages + `Component()` view components) before continuing to Task 2.**

- [x] **Step 6: Land the app shell and tokens**

`app.json` lists `pages/index/index` first plus a `tabBar` of 5 tabs; `app.wxss` does `@import "theme/tokens.wxss";` and sets page background `var(--canvas)`. `theme/tokens.wxss` defines every colour and the spacing scale as `--var` custom properties exactly as listed in Global Constraints. `project.config.json` sets `"compileType": "miniProgram"` and `"appid": "touristappid"` so DevTools can open it without credentials. Delete `pages/__probe` only after Tasks 2+ prove the harness on real pages — keep it as the permanent harness test fixture.

- [x] **Step 7: Green check**

Run: `npx jest`
Expected: harness test PASS, suite otherwise empty.

---

## Task 2: Persistence core (`core/store.js`)

Every feature reads and writes through this. It is the only module that touches `wx.setStorageSync`, which is what makes quota handling and migration testable in one place.

**Files:**
- Create: `campus-life/core/store.js`
- Create: `campus-life/core/schema.js`
- Test: `campus-life/tests/store.test.js`

**Interfaces:**
- Consumes: a `storage` adapter shaped exactly like `memoryStorage()`.
- Produces:
  - `createStore(storage, { key = 'cl:v1', seed })` → `{ read(), write(mutator), reset(), raw() }`
  - `read()` → plain state object, always fully populated (missing keys filled from `schema.empty()`).
  - `write(fn)` → applies `fn(draft)` to a shallow clone, persists, returns the new state. Throws `QuotaError` only after the prune path fails.
  - `schema.empty()` → `{ version:1, profile:{nickname:'',interests:[]}, settings:{agentMode:'auto'}, moods:[], posts:[], chats:[], checkins:[], tasks:[], plans:[], favourites:{shops:[],groups:[]} }`

- [x] **Step 1: Write the failing test**

```js
const { createStore } = require('../core/store');
const { schema } = require('../core/schema');
const { memoryStorage } = require('./helpers/memory-storage');

test('read() fills missing keys from the empty schema', () => {
  const s = createStore(memoryStorage({ 'cl:v1': { version: 1, posts: [{ id: 'p1' }] } }), { seed: schema.empty() });
  expect(s.read().posts).toEqual([{ id: 'p1' }]);
  expect(s.read().checkins).toEqual([]);
});

test('write() persists so a new store instance sees it (app restart)', () => {
  const st = memoryStorage();
  createStore(st, { seed: schema.empty() }).write((d) => d.checkins.push({ id: 'c1' }));
  const again = createStore(st, { seed: schema.empty() }).read();
  expect(again.checkins.map((c) => c.id)).toEqual(['c1']);
});

test('write() does not mutate the previously read object', () => {
  const s = createStore(memoryStorage(), { seed: schema.empty() });
  const before = s.read();
  s.write((d) => d.posts.push({ id: 'p9' }));
  expect(before.posts).toEqual([]);
});

test('quota errors prune oldest chat messages, then closed posts, then surface', () => {
  let calls = 0;
  const boom = memoryStorage();
  boom.set = () => { calls++; if (calls <= 1) throw new Error('exceed storage quota'); };
  const s = createStore(boom, { seed: { ...schema.empty(), chats: [{ id: 'a', messages: Array.from({length: 50}, (_, i) => ({ id: i }))}], posts: [{ id: 'p1', closed: true }] } });
  expect(() => s.write((d) => d.checkins.push({ id: 'x' }))).not.toThrow();
  expect(boom.dump()['cl:v1'].chats[0].messages.length).toBeLessThan(50);
});
```

- [x] **Step 2: Run to verify failure**

Run: `npx jest tests/store.test.js`
Expected: FAIL — `Cannot find module '../core/store'`.

- [x] **Step 3: Implement**

`write` deep-clones via `JSON.parse(JSON.stringify(state))` (state is JSON-safe by contract), runs the mutator, then `try storage.set(key, next)`. On throw: strip oldest entries from `chats[*].messages` (keep newest 20), retry; still throwing → drop `posts` where `closed === true` oldest-first, retry; still throwing → rethrow wrapped as `QuotaError`. Every successful write bumps `state.version` and stamps `state.updatedAt`.

- [x] **Step 4: Run to verify pass**

Run: `npx jest tests/store.test.js` — Expected: 4 passed.

---

## Task 3: 本地探索打卡 (check-in)

**Files:**
- Create: `campus-life/core/checkin.js`
- Create: `campus-life/data/spots.js`
- Create: `campus-life/pages/explore/{index.js,index.wxml,index.wxss,index.json}`
- Test: `campus-life/tests/checkin.test.js`, `campus-life/tests/page-explore.test.js`

**Interfaces:**
- Consumes: `createStore`.
- Produces: `checkin.list(spots, checkins)` → spots with `{visited, lastAt, distanceKm}`; `checkin.doCheckin(state, {spotId, ts})`; `checkin.streak(checkins, tzOffsetMin)`; `checkin.coverage(checkins, spots)` → 0..1; `checkin.canCheck(spot, last)` → `{ok, reason}` (60-min dedupe window).

- [x] **Step 1: Failing pure-logic test**

```js
const c = require('../core/checkin');
const D = (iso) => new Date(iso).getTime();
const spots = [{ id: 'lib', name: '图书馆', zone: 'teach' }, { id: 'gym', name: '体育馆', zone: 'sport' }];

test('streak counts consecutive days and resets on a gap', () => {
  const ci = [{ spotId: 'lib', ts: D('2026-10-10T09:00:00Z') }, { spotId: 'gym', ts: D('2026-10-11T09:00:00Z') }];
  expect(c.streak(ci, 0, D('2026-10-11T12:00:00Z'))).toBe(2);
  expect(c.streak([{ spotId: 'lib', ts: D('2026-10-08T09:00:00Z') }], 0, D('2026-10-11T12:00:00Z'))).toBe(0);
});

test('coverage is visited over total', () => {
  expect(c.coverage([{ spotId: 'lib', ts: 1 }], spots)).toBeCloseTo(0.5);
});

test('duplicate check-in inside the dedupe window is refused with a reason', () => {
  const last = { spotId: 'lib', ts: D('2026-10-11T09:00:00Z') };
  expect(c.canCheck(spots[0], last, D('2026-10-11T09:30:00Z')).ok).toBe(false);
  expect(c.canCheck(spots[0], last, D('2026-10-11T11:00:00Z')).ok).toBe(true);
});
```

- [x] **Step 2: Verify failure** — `npx jest tests/checkin.test.js` → FAIL module not found.
- [x] **Step 3: Implement `core/checkin.js`** — pure functions, day boundary computed with the offset so `2026-10-11T01:00Z` on a UTC+8 device is still Oct 11.
- [x] **Step 4: Verify pass** — `npx jest tests/checkin.test.js` → 3 passed.
- [x] **Step 5: Failing render test**

```js
const { loadPage, tap, text } = require('./helpers/render');

test('explore page lists spots, checks in on tap, and shows the streak', async () => {
  const page = await loadPage('explore');
  expect(page.querySelectorAll('.spot').length).toBeGreaterThan(0);
  expect(text(page, '.streak')).toContain('连续 0 天');
  await tap(page, '.spot .btn-check');
  expect(text(page, '.streak')).toMatch(/连续 [1-9] 天/);
  expect(text(page, '.spot')).toContain('已打卡');
});
```

- [x] **Step 6: Verify failure**, then **Step 7: build the page** — `onShow` reads the store, renders zone-grouped spots with visited state and a coverage bar; the check-in button calls `core/checkin`, writes through the store, re-renders; empty state and `内容仅存于本机` label present. GPS is requested with a manual `附近/校内` fallback that never blocks check-in.
- [x] **Step 8: Green check** — `npx jest tests/checkin.test.js tests/page-explore.test.js`.

---

## Task 4: 时间管理智能规划 (planner)

The solver is pure JS so it is verifiable without any model; the agent only rewrites its output into prose.

**Files:**
- Create: `campus-life/core/planner.js`
- Create: `campus-life/pages/planner/{index.js,index.wxml,index.wxss,index.json}`
- Test: `campus-life/tests/planner.test.js`, `campus-life/tests/page-planner.test.js`

**Interfaces:**
- Consumes: store `tasks[]` `{id,title,priority(1-3),durationMin,deadline?,fixed?,start?,end?}`.
- Produces: `planner.solve({tasks, day, now, workWindow})` → `{slots:[{taskId,title,start,end}], unscheduled:[taskId], busyMin, freeMin}`; `planner.suggest(tasks, agent)` → prose string.

- [x] **Step 1: Failing solver test** — the assertions encode the spec's four constraints.

```js
const p = require('../core/planner');
const T = (id, o) => ({ id, title: id, priority: 2, durationMin: 60, ...o });

test('earlier deadline wins when both fit', () => {
  const { slots } = p.solve({ tasks: [T('b', { deadline: 600 }), T('a', { deadline: 300 })], day: '2026-10-12', now: 0, workWindow: [0, 1440] });
  expect(slots.map((s) => s.taskId)).toEqual(['a', 'b']);
});

test('fixed commitments are respected and never overlapped', () => {
  const { slots } = p.solve({ tasks: [T('class', { fixed: true, start: 120, end: 300 }), T('hw', { deadline: 400, durationMin: 90 })], day: '2026-10-12', now: 0, workWindow: [0, 1440] });
  const cls = slots.find((s) => s.taskId === 'class');
  expect([cls.start, cls.end]).toEqual([120, 300]);
  slots.filter((s) => s.taskId !== 'class').forEach((s) => expect(s.start >= 300 || s.end <= 120).toBe(true));
});

test('higher priority wins when only one fits', () => {
  const { slots, unscheduled } = p.solve({ tasks: [T('low', { priority: 1, deadline: 100 }), T('high', { priority: 3, deadline: 100, durationMin: 240 })], day: 'x', now: 0, workWindow: [0, 300] });
  expect(slots.map((s) => s.taskId)).toEqual(['high']);
  expect(unscheduled).toEqual(['low']);
});

test('nothing is scheduled before now, and past-deadline tasks are reported', () => {
  const r = p.solve({ tasks: [T('late', { deadline: 100 })], day: 'x', now: 500, workWindow: [0, 1440] });
  expect(r.slots).toEqual([]);
  expect(r.unscheduled).toEqual(['late']);
});
```

- [x] **Step 2: Verify failure** → `npx jest tests/planner.test.js`.
- [x] **Step 3: Implement** — greedy: partition fixed vs flexible; place fixed verbatim; sort flexible by `priority` desc then `deadline` asc (EDF with priority override); walk the work window inserting into the first gap ≥ `durationMin` that ends before `deadline` and after `now`. Return leftovers as `unscheduled`. No recursion, no randomness — deterministic for the test above.
- [x] **Step 4: Verify pass** → 4 passed.
- [x] **Step 5–8:** render test asserting task list → tap `生成今日安排` → `.slot` rows appear with times, `.unscheduled` shows the overflow task; page persists `plans[]`; agent prose is behind a `让 AI 说明` button that is inert (labelled) when no agent is available.

---

## Task 5: 周边好店聚合 (shops)

**Files:**
- Create: `campus-life/core/shops.js`
- Create: `campus-life/data/shops.js` (≥18 seeded sample shops, explicitly labelled 示例数据)
- Create: `campus-life/pages/shops/{index.js,...}`, `campus-life/pages/shop/{index.js,...}`
- Test: `campus-life/tests/shops.test.js`, `campus-life/tests/page-shops.test.js`

**Interfaces:**
- Produces: `shops.filter(list, {q, cats, openNow, maxDist})`; `shops.sortBy(list, 'distance'|'rating'|'price')`; `shops.haversineKm(a, b)`; `shops.toggleFav(favs, id)`.

- [x] **Step 1: Failing test**

```js
const s = require('../core/shops');
const L = [
  { id: 'a', name: 'A', cats: ['coffee'], dist: 0.4, rating: 4.6, price: 2, open: [8, 22] },
  { id: 'b', name: 'B', cats: ['meal'], dist: 1.2, rating: 4.1, price: 1, open: [17, 23] },
  { id: 'c', name: 'C', cats: ['study'], dist: 2.5, rating: 4.9, price: 0, open: [9, 18] },
];
test('category filter, then distance sort', () => {
  expect(s.sortBy(s.filter(L, { cats: ['coffee', 'study'] }), 'distance').map((x) => x.id)).toEqual(['a', 'c']);
});
test('openNow uses the clock, not the array index', () => {
  expect(s.filter(L, { openNow: true, at: 20 }).map((x) => x.id)).toEqual(['a', 'b']);
});
test('text search matches name and category, case-insensitively', () => {
  expect(s.filter(L, { q: 'COFFEE' }).map((x) => x.id)).toEqual(['a']);
});
test('haversine is sane', () => {
  expect(s.haversineKm({ lat: 30.5, lng: 114.4 }, { lat: 30.51, lng: 114.4 })).toBeGreaterThan(0.8);
  expect(s.haversineKm({ lat: 30.5, lng: 114.4 }, { lat: 30.5, lng: 114.4 })).toBe(0);
});
```

- [x] **Step 2: Verify failure**, **Step 3: Implement** (filter is conjunctive across all four criteria; `openNow` compares `at` against `open[0]..open[1]`), **Step 4: Verify pass**.
- [x] **Step 5–8:** render test — list renders, tapping a category chip reduces the count, favourite star persists to `favourites.shops` and survives a remount, detail page receives `?id=` and shows the 示例数据 label.

---

## Task 6: Agent adapter (`agent/`)

The spec's central decision. Nothing above this line may know which backend answered.

**Files:**
- Create: `campus-life/agent/index.js`, `campus-life/agent/offline.js`, `campus-life/agent/llm.js`, `campus-life/agent/lexicon.js`, `campus-life/agent/prompts.js`
- Test: `campus-life/tests/agent-offline.test.js`, `campus-life/tests/agent-llm.test.js`, `campus-life/tests/agent-probe.test.js`, `campus-life/tests/live-ollama.test.js`

**Interfaces:**
- Consumes: an injectable `{ request }` (the `wx.request` shape) so llm.js is testable without network.
- Produces:
  - `agent.classify(text)` → `{mood: 'joy'|'low'|'anxious'|'calm'|'angry', intensity: 0..1}`
  - `agent.chat(turns, userText, persona)` → `{text}`
  - `agent.match(profile, pool)` → `[{id, score, reasons:[]}]`
  - `agent.mode()` → `'llm' | 'offline'`, `agent.probe({timeoutMs=1500})` → `Promise<'llm'|'offline'>`
  - `agent.explain(plan)` → prose string

- [x] **Step 1: Failing offline test** — the offline engine must be genuinely useful, not a placeholder.

```js
const off = require('../agent/offline');

test('classify reads polarity including negation', () => {
  expect(off.classify('今天和朋友吃饭很开心').mood).toBe('joy');
  expect(off.classify('一点也不开心').mood).toBe('low');
  expect(off.classify('明天要交论文，焦虑得睡不着').mood).toBe('anxious');
});
test('intensity is 0..1 and grows with markers', () => {
  const weak = off.classify('还行');
  const strong = off.classify('太开心了！！！');
  expect(strong.intensity).toBeGreaterThan(weak.intensity);
  [weak, strong].forEach((r) => expect(r.intensity).toBeGreaterThanOrEqual(0));
});
test('match ranks by shared keywords and returns reasons', () => {
  const pool = [{ id: 'photo', name: '摄影社', tags: ['摄影', '相机'] }, { id: 'ball', name: '篮球队', tags: ['篮球'] }];
  const r = off.match({ interests: ['摄影', '拍照'] }, pool);
  expect(r[0].id).toBe('photo');
  expect(r[0].reasons.length).toBeGreaterThan(0);
  expect(r.find((x) => x.id === 'ball').score).toBe(0);
});
```

- [x] **Step 2: Verify failure** → `npx jest tests/agent-offline.test.js`.
- [x] **Step 3: Implement `lexicon.js` + `offline.js`** — mood word lists per the five classes; negation particles `不/没/别/无` flip the next lexicon hit; intensifiers `太/很/超/特别/死了` multiply; `！` count adds weight; score is normalised to 0..1. `match` uses the exact keyword+IDF+co-occurrence algorithm validated in the spike (embeddings were measured broken — do not reintroduce them).
- [x] **Step 4: Verify pass.**
- [x] **Step 5: Failing LLM transport test** — fake `request`, asserting the contract, timeout, and the fallback path.

```js
const { createLlm } = require('../agent/llm');
const off = require('../agent/offline');

test('classify sends a JSON schema and parses the reply', async () => {
  let sent;
  const llm = createLlm({ request: (o) => { sent = o; o.success({ statusCode: 200, data: { message: { content: '{"mood":"anxious","intensity":0.7}' } } }); } });
  const r = await llm.classify('明天要交论文');
  expect(sent.url).toBe('http://localhost:11434/api/chat');
  expect(sent.method).toBe('POST');
  expect(JSON.parse(sent.data).format).toBeTruthy();
  expect(r).toEqual({ mood: 'anxious', intensity: 0.7 });
});

test('malformed JSON retries once then falls back to offline', async () => {
  let n = 0;
  const llm = createLlm({ request: (o) => { n++; o.success({ statusCode: 200, data: { message: { content: n === 1 ? 'not json' : '{"mood":"low","intensity":0.4}' } } }); } });
  expect((await llm.classify('有点难过')).mood).toBe('low');
  expect(n).toBe(2);
});

test('request failure rejects so the caller can use offline', async () => {
  const llm = createLlm({ request: (o) => o.fail({ errMsg: 'request:fail' }) });
  await expect(llm.classify('x')).rejects.toBeTruthy();
});
```

- [x] **Step 6: Implement `llm.js`** — `wx.request` wrapped in a Promise, `model: qwen2.5:3b`, `stream:false`, `options:{temperature:0}` for classify, `0.85` for chat, 6 s timeout, one retry on JSON-parse failure, reject on transport failure. Never throw synchronously.
- [x] **Step 7: Failing probe test** — `agent/index.js` picks llm when probe resolves, offline on timeout/failure, and `agent.classify` transparently degrades per-call when llm rejects while `mode()` is `'llm'`.
- [x] **Step 8: Implement `agent/index.js`.**
- [x] **Step 9: Live Ollama test** — `tests/live-ollama.test.js` skips itself unless `http://localhost:11434/api/tags` answers, then does one real `classify` and one real `chat`, asserts `mood` is a valid enum and the reply is non-empty Chinese, and `console.log`s latency + the raw reply so the report can quote it. This is the spec's live run; it must pass, not just exist.

Run: `npx jest` → all green including live suite.

---

## Task 7: 心情雷达 (mood radar)

**Files:**
- Create: `campus-life/core/moodscore.js`
- Create: `campus-life/components/mood-radar/{index.js,index.wxml,index.wxss,index.json}`
- Create: `campus-life/pages/radar/{index.js,...}`
- Test: `campus-life/tests/moodscore.test.js`, `campus-life/tests/page-radar.test.js`

**Interfaces:**
- Produces: `moodscore.AXES` = `['学业','社交','作息','运动','情绪稳定','兴趣']`; `moodscore.axes(events, {days, now})` → `[{axis, value:0..100, evidence:n}]`; `moodscore.series(events, {days, now})` for the trend line.
- Consumes: events shaped `{ts, mood, intensity, text}` from posts + manual check-ins.

- [x] **Step 1: Failing test**

```js
const m = require('../core/moodscore');
const E = (daysAgo, text, mood, intensity) => ({ ts: Date.parse('2026-10-11') - daysAgo * 864e5, text, mood, intensity });

test('returns exactly the six fixed axes, each within 0..100', () => {
  const r = m.axes([E(1, '去图书馆写作业', 'low', 0.5)], { days: 7, now: Date.parse('2026-10-11') });
  expect(r.map((x) => x.axis)).toEqual(['学业', '社交', '作息', '运动', '情绪稳定', '兴趣']);
  r.forEach((x) => expect(x.value).toBeGreaterThanOrEqual(0));
  r.forEach((x) => expect(x.value).toBeLessThanOrEqual(100));
});

test('window excludes events older than days', () => {
  const ev = [E(2, '跑步五公里', 'joy', 0.6), E(40, '跑步五公里', 'joy', 0.6)];
  const w7 = m.axes(ev, { days: 7, now: Date.parse('2026-10-11') });
  const w30 = m.axes(ev, { days: 30, now: Date.parse('2026-10-11') });
  expect(w7.find((x) => x.axis === '运动').evidence).toBe(1);
  expect(w30.find((x) => x.axis === '运动').evidence).toBe(2);
});

test('no events yields all-zero axes rather than invented numbers', () => {
  m.axes([], { days: 7, now: 1 }).forEach((x) => expect(x.value).toBe(0));
});

test('情绪稳定 drops when polarity flips between consecutive days', () => {
  const stable = m.axes([E(1, '平静地自习', 'calm', 0.2), E(2, '平静地看书', 'calm', 0.2)], { days: 7, now: Date.parse('2026-10-11') });
  const volatile = m.axes([E(1, '开心极了', 'joy', 0.9), E(2, '难过死了', 'low', 0.9)], { days: 7, now: Date.parse('2026-10-11') });
  expect(stable.find((x) => x.axis === '情绪稳定').value)
    .toBeGreaterThan(volatile.find((x) => x.axis === '情绪稳定').value);
});
```

- [x] **Step 2: Verify failure.**
- [x] **Step 3: Implement** — per-axis keyword buckets (`学业` 课/作业/考试/论文/图书馆…, `运动` 跑/健身/球/骑…, `作息` 睡/熬/失眠/早起…, `社交` 朋友/聊天/聚餐/社团…, `兴趣` 摄影/书/音乐/电影/展…); `value = clamp(round(40*min(evidence,5)/5 + 60*valence), 0, 100)`; `情绪稳定` uses sign flips instead of keywords. Pure and deterministic.
- [x] **Step 4: Verify pass.**
- [x] **Step 5–8:** render test — radar draws six `.axis` labels, values come from the store, the 7/30 toggle re-renders, an empty store shows the zero-state with `内容仅存于本机` and no fabricated aggregate.

---

## Task 8: 校园树洞 (tree hole)

**Files:** `campus-life/pages/treehole/*`, `campus-life/core/posts.js`, tests `posts.test.js` + `page-treehole.test.js`
**Produces:** `posts.add(state, {text, ts})` (runs `agent.classify`, tags `mood`), `posts.feed(state, {mood})` newest-first, `posts.anonId(state, ts)` stable per day so returning readers see consistent nicknames without device-derived ids.
- [x] **Steps 1–4:** pure tests for newest-first ordering, mood filter, empty-text rejection, and daily anon-id stability.
- [x] **Steps 5–8:** render test — typing + `发布` appends a card showing its mood tag; the feed filters by tag; `内容仅存于本机` present; agent is invoked through `agent/index` so offline mode still tags posts.

## Task 9: 兴趣社群匹配 (groups)

**Files:** `campus-life/pages/groups/*`, `campus-life/core/groups.js`, tests.
**Produces:** `groups.rank(state, pool)` delegating to `agent.match`, `groups.join(state, id)`, `groups.leave(state, id)`; each result carries `reasons[]`.
- [x] **Steps 1–4:** pure tests — ranking is deterministic for a fixed profile, `reasons` are non-empty for hits and absent for score 0, joining persists and survives remount.
- [x] **Steps 5–8:** render test — interest chips set the profile, ranking re-renders, reason text is visible (no bare percentages pretending to be social proof).

## Task 10: 匿名一对一聊天 (anonymous chat)

**Files:** `campus-life/pages/chat/*`, `campus-life/core/chat.js`, tests `chat.test.js` + `page-chat.test.js`.
**Produces (as shipped):** `chat.open(state, {ts, persona, topics})` → session `{id, startedAt, lastAt, closed:false, closedAt:null, reason:null, persona, topics, messages:[]}` pushed into `state.chats`; `chat.send(state, id, text, ts)` and `chat.peer(state, id, text, ts)` mutate `state` in place and return `{ok, reason}` / `{ok, message, session}` — the same result-object shape `core/posts.js` uses, so the page can show *why* a send was refused (an earlier draft of this plan had `send` returning `state`, which gave the caller nothing to report); `chat.expire(state, id, ts)` → `{closed, reason, remaining, warn}`, closing in place when `ts - lastAt > 300000`; `chat.warnAt = 270000`, `chat.idleMs = 300000`; `chat.reap(state, ts)` still returns `state` and closes every overdue session — "archive" means the closed flag + `closedAt` + `reason` on the row that already lives in `chats[]`, not a second array. `chat.current(state)` is the one open session; `chat.topics(state, pool)` derives the peer's topic pool from `core/groups.joined`.
- [x] **Steps 1–4:** pure tests on a fake clock — 299 s idle stays open, 301 s closes with `reason:'timeout'`, activity resets the timer, a closed session rejects further `send`, `reap` is idempotent.

```js
const chat = require('../core/chat');
const S = () => ({ chats: [], profile: { interests: [] }, favourites: { shops: [], groups: [] } });
test('301s idle closes the session', () => {
  const s = S(); const { id } = chat.open(s, { ts: 0, persona: 'warm' });
  chat.send(s, id, '在吗', 1000);                       // 就地改 s，返回 {ok, message}
  expect(chat.reap(s, 1000 + 301000).chats[0].closed).toBe(true);
});
test('activity resets the countdown', () => {
  const s = S(); const { id } = chat.open(s, { ts: 0 });
  chat.send(s, id, 'hi', 200000);
  expect(chat.reap(s, 400000).chats[0].closed).toBe(false);
});
```

- [x] **Steps 5–8:** render test — sending appends my bubble then a peer bubble from `agent.chat`; the 30 s warning line renders when `remaining < 30000`; the partner is labelled `模拟/AI` on screen; timers are cleared in `onUnload` (assert `nav`/toast side effects do not fire after unload — this is where a leaked timer would show up).
  **Harness note found while executing:** `setInterval` keeps running after a test ends unless the page is detached, and the pinned clock is global — a leftover timer from an earlier case will close a later case's session and toast. `tests/page-chat.test.js` therefore tracks every mounted page and detaches in `afterEach`, and the auto-close cases poll for the closed banner instead of betting on a fixed `sleep`.

## Task 11: Home dashboard, integration, honest gap report

**Files:** `campus-life/pages/index/*`, `components/{mode-badge,empty-state,nav-card}/*`, `campus-life/README.md`, `campus-life/tests/page-index.test.js`, `campus-life/tests/integration.test.js`
- [x] **Steps 1–4:** index shows today's plan status, check-in streak, mood summary, both module entries, and the live `mode-badge`.
- [x] **Steps 5–6:** integration test — publish a post → radar axis moves; check in → index streak updates; join a group → chat persona interest changes. Cross-feature wiring is asserted, not assumed.
- [x] **Step 7: Run the whole suite and the live agent run**, paste real output into `README.md` with counts and latencies.
- [x] **Step 8: Write the gap section** listing exactly what only DevTools can confirm: on-device navigation, real GPS permissions, share cards, `wx.request` domain whitelisting, `rpx` rendering on physical screens, and tabBar icon images (none generated here). Do not call these done.

---

## Self-review notes

- **Spec coverage:** §4 layout → Tasks 1/11; §5 storage → Task 2; §6 features → Tasks 3,4,5 (local tools) and 7,8,9,10 (social); §3 agent adapter → Task 6; §7 error handling → Tasks 2 (quota), 6 (fallback), 3/5 (empty states); §8 verification → every task's render + pure test pair, plus Task 6 step 9 and Task 11 step 8. No spec requirement is untasked.
- **Placeholders:** Tasks 8-10 compress duplicated step wording (`Steps 1-4 pure tests, 5-8 render`) because the step *shape* is fixed by Tasks 3-5 and repeated verbatim there; their assertions are named concretely rather than left as "add tests".
- **Type consistency:** `store.read()/write()`, `agent.classify/chat/match/mode/probe`, `moodscore.AXES/axes`, and `chat.open/send/reap` are used with identical signatures in every later task. `memoryStorage()`'s shape is the one storage contract shared by Tasks 1-2 and all page tests.

---

## Execution notes (what changed while the plan was being carried out)

Recorded here so a later reader does not trust the plan over the code.

- **Task 2:** `schema.empty()` shipped as `schema()`; `migrate(raw)` is the read-side guard. Everything else matches the interface block.
- **Task 1:** the shim survives, and `pages/__probe/` is kept as its fixture (not in `app.json`'s page list). Added later, because the shim alone was not enough: `tests/shim-life/` + `tests/shim-lifecycle.test.js` pin `onLoad/onReady/onShow/onHide/onUnload` and the cross-boundary tap, so a silent shim break fails loudly.
- **Tasks 4 → 11:** the `让 AI 说明` button was specified in Task 4 steps 5–8 but only got wired while finishing Task 11. Doing it surfaced a real contract bug: `planner.solve()` returns `unscheduled` as **task ids**, and `agent.explain()` had been reading them verbatim, so the prose said `今天放不下：t1`. The page now hands the explain layer its own display view (`{slots, unscheduled: titles}`), and `tests/page-planner.test.js` asserts a raw id never reaches the screen.
- **Task 11:** components shipped are `mode-badge`, `nav-card`, `empty-state`, `mood-radar`. `empty-state` is used on the dashboard only — older screens keep their inline `.empty`/`.zero` blocks and were left alone rather than refactored without a way to test the change.
- **Harness knowledge this plan did not predict** (cross-boundary `exparser` tap, `page.instance` vs. the render wrapper, property observers not firing on default values, one-load-per-process, `setInterval` leaking across tests) is written up in `README.md` § *Maintaining the tests*.
- **No commits were made**, per the Global Constraints. Each task ended on a green `npx jest` instead. Final measured state: **27 suites / 223 tests passing, 11.13 s**, with the live Ollama suite reporting `探测 736 ms · 分类 1190 ms` and `chat 1140 ms` on the last run.
- **Still unverified** — the DevTools-only list lives in `README.md` § *What this machine cannot prove* and is deliberately not marked done anywhere.
