const {
  loadPage, tap, tapN, input, text, allText, html, count, classAt,
  wxState, resetWxState, simulate,
} = require('./helpers/render');
const { freeze, unfreeze } = require('./helpers/clock');
const { store, resetStore, storage } = require('../adapters/local');
const { KEY } = require('../core/schema');
const posts = require('../core/posts');
const agent = require('../agent/index');

jest.setTimeout(60000);

async function settle() {
  await simulate.sleep(30);
  await simulate.sleep(30);
}

async function openHole() {
  const page = await loadPage('treehole');
  await settle();
  return page;
}

function seedPosts(rows) {
  store().write((d) => {
    rows.forEach((r) => posts.add(d, { text: r.text, ts: r.ts, mood: r.mood, intensity: r.intensity, tz: 0 }));
  });
}

beforeEach(() => {
  resetWxState();
  resetStore();
  agent.reset(); // 每条用例都重新探测一次，才能看见页面确实走的是适配层
  freeze(9, 0);
});

afterEach(() => {
  unfreeze();
});

test('an empty tree hole says so and labels itself local-only', async () => {
  const page = await openHole();
  expect(count(page, '.post')).toBe(0);
  expect(count(page, '.empty')).toBe(1);
  expect(text(page, '.local-only')).toContain('内容仅存于本机');
  expect(text(page, '.badge')).toBe('离线模式');
});

test('发布 runs the agent through the adapter and appends a card with its mood tag', async () => {
  const page = await openHole();
  await input(page, '.js-draft', '明天要交论文，紧张得一点也睡不着');
  await tap(page, '.js-publish');
  await settle();

  expect(wxState().requests.length).toBeGreaterThan(0);
  expect(wxState().requests[0].url).toBe('http://localhost:11434/api/tags');

  const saved = storage.get(KEY).posts;
  expect(saved.length).toBe(1);
  expect(saved[0].mood).toBe('anxious');
  expect(saved[0].source).toBe('offline'); // 这台机器上模型不可达，标注就得说实话
  expect(saved[0].closed).toBe(false);

  expect(count(page, '.post')).toBe(1);
  expect(text(page, '.body')).toContain('明天要交论文');
  expect(text(page, '.tag')).toBe('焦虑');
  expect(text(page, '.foot')).toContain('离线词库标注');
  expect(text(page, '.js-publish')).toBe('发布'); // 输入框清空、按钮从"标注中…"回来
  expect(wxState().toasts[wxState().toasts.length - 1]).toContain('已发出 · 离线模式标注');
});

test('the mood chips filter the feed and their counts match the store', async () => {
  seedPosts([
    { text: '论文交不上', mood: 'anxious', ts: Date.now() - 86400000 },
    { text: '赢了院系赛', mood: 'joy', ts: Date.now() - 2 * 86400000 },
    { text: '在图书馆坐了一下午', mood: 'calm', ts: Date.now() - 3 * 86400000 },
  ]);
  const page = await openHole();

  expect(count(page, '.post')).toBe(3);
  expect(text(page, '.chip')).toContain('全部 3');
  expect(allText(page, '.chip')).toContain('开心 1');

  await tapN(page, '.js-filter', 1); // 开心
  expect(count(page, '.post')).toBe(1);
  expect(text(page, '.body')).toContain('赢了院系赛');
  expect(classAt(page, '.js-filter', 1)).toContain('chip--on');

  await tapN(page, '.js-filter', 4); // 生气
  expect(count(page, '.post')).toBe(0);
  expect(count(page, '.empty')).toBe(1);
  expect(text(page, '.empty')).toContain('还没有内容');
});

test('the feed is newest first', async () => {
  seedPosts([
    { text: '早上的事', mood: 'calm', ts: Date.now() - 3 * 86400000 },
    { text: '刚才的事', mood: 'joy', ts: Date.now() - 3600000 },
  ]);
  const page = await openHole();
  expect(allText(page, '.body')).toBe('刚才的事 | 早上的事');
});

test('收回 takes the post out of the feed but keeps the local record', async () => {
  seedPosts([{ text: '刚跟人吵了一架', mood: 'angry', ts: Date.now() - 3600000 }]);
  const page = await openHole();
  expect(count(page, '.post')).toBe(1);

  await tap(page, '.js-close');
  await settle();
  expect(count(page, '.post')).toBe(0);
  expect(wxState().toasts).toContain('已收回');

  const saved = storage.get(KEY).posts;
  expect(saved.length).toBe(1);
  expect(saved[0].closed).toBe(true);
});

test('two posts from the same day share one anonymous handle that is not a device id', async () => {
  seedPosts([
    { text: '早上没赶上第一节课', mood: 'calm', ts: Date.now() - 3600000 },
    { text: '晚上在自习室发呆', mood: 'calm', ts: Date.now() - 7200000 },
  ]);
  const page = await openHole();
  const handles = Array.prototype.slice.call(page.querySelectorAll('.anon')).map((el) => el.dom.textContent);

  expect(handles.length).toBe(2);
  expect(handles[0]).toBe(handles[1]);
  expect(handles[0]).toMatch(/同学\d{3}$/);
});

test('发布 with nothing typed says so and stores nothing', async () => {
  const page = await openHole();
  await tap(page, '.js-publish');
  await settle();

  expect(wxState().toasts).toContain('先写点什么再发');
  expect(storage.get(KEY)).toBe(''); // 连库都没开过：空内容不该留下任何记录
  expect(count(page, '.post')).toBe(0);
});
