const {
  loadPage, tap, tapN, input, text, allText, html, count, classAt,
  wxState, resetWxState, simulate,
} = require('./helpers/render');
const { freeze, unfreeze } = require('./helpers/clock');
const { store, resetStore, storage } = require('../adapters/local');
const { KEY } = require('../core/schema');
const posts = require('../core/posts');

jest.setTimeout(60000);

const DAY = 86400000;
const now = () => Date.now();

async function openRadar() {
  const page = await loadPage('radar');
  await simulate.sleep(20);
  return page;
}

function seed(moods, posts) {
  store().write((d) => {
    d.moods = moods || [];
    d.posts = posts || [];
  });
}

const M = (daysAgo, text_, moodName) => ({
  id: 'm' + daysAgo,
  ts: now() - daysAgo * DAY,
  text: text_,
  mood: moodName,
  intensity: null,
});

beforeEach(() => {
  resetWxState();
  resetStore();
  freeze(9, 0);
});

afterEach(() => {
  unfreeze();
});

test('an empty store shows the zero state instead of an invented all-zero radar', async () => {
  const page = await openRadar();
  expect(count(page, '.radar-card')).toBe(0);
  expect(count(page, '.row')).toBe(0);
  expect(count(page, '.trend')).toBe(0);
  expect(text(page, '.zero-t')).toContain('还没有记录');
  expect(text(page, '.zero')).toContain('不会替你编');
  expect(text(page, '.local-only')).toContain('内容仅存于本机');
});

test('the page hands the store numbers to the radar component', async () => {
  seed([M(1, '在图书馆自习到闭馆', 'calm'), M(2, '跑步五公里', 'joy')]);
  const page = await openRadar();

  // simulate 的 querySelector 不进入自定义组件的 shadow 树（组件类名会被加
  // mood-radar-- 前缀，页面里查不到），所以这里直接读页面渲染出的组件标记，
  // 证明 store 算出的六个值真的画进了雷达；组件自身的行为在
  // tests/comp-mood-radar.test.js 里逐条验证。
  expect(count(page, '.radar-card')).toBe(1);
  const markup = html(page, '.radar-card');
  expect((markup.match(/mood-radar--axis"/g) || []).length).toBe(6);
  expect(markup).toContain('学业');
  expect(markup).toContain('情绪稳定');
  expect(markup).toContain('>50<'); // 学业 = 40*1/5 + 60*0.7
  expect(markup).toContain('>76<'); // 情绪稳定 = 40*2/5 + 60
  expect(markup).toContain('height:520px'); // size 传进了组件，不是写死的
});

test('axis values and evidence labels are the numbers the store implies', async () => {
  seed([M(1, '在图书馆自习到闭馆', 'calm'), M(2, '跑步五公里', 'joy')]);
  const page = await openRadar();

  expect(count(page, '.row')).toBe(6);
  expect(allText(page, '.row-n')).toBe('学业 | 社交 | 作息 | 运动 | 情绪稳定 | 兴趣');
  // 学业 1 条 calm: 40*1/5 + 60*0.7 = 50 · 运动 1 条 joy: 8 + 60 = 68
  // 情绪稳定 2 条、两天同号: 40*2/5 + 60*1 = 76
  expect(allText(page, '.row-v')).toBe('50 | 0 | 0 | 68 | 76 | 0');
  expect(allText(page, '.row-e')).toContain('还没有相关记录');
});

test('widening to 30 days re-renders every number on the page', async () => {
  seed([M(3, '和朋友聚餐', 'joy'), M(20, '通宵赶论文', 'low')]);
  const page = await openRadar();

  expect(text(page, '.head')).toContain('近 7 天读到你记了 1 条内容');
  expect(allText(page, '.row-v')).toBe('0 | 68 | 0 | 0 | 68 | 0');
  expect(classAt(page, '.js-days', 0)).toContain('chip--on');

  await tapN(page, '.js-days', 1);
  expect(text(page, '.head')).toContain('近 30 天读到你记了 2 条内容');
  expect(allText(page, '.row-v')).toBe('8 | 68 | 8 | 0 | 16 | 0');
  expect(classAt(page, '.js-days', 1)).toContain('chip--on');
  expect(count(page, '.tcol')).toBe(2); // 两个有日子，中间的空日子不补零
});

test('a manual 记一笔心情 writes state.moods and the radar reacts', async () => {
  const page = await openRadar();
  await tapN(page, '.js-mood', 0); // 开心
  await input(page, '.js-note', '和室友去操场走了三圈');
  await tap(page, '.js-save');

  const row = store().read().moods[0];
  expect(row.mood).toBe('joy');
  expect(row.text).toBe('和室友去操场走了三圈');
  expect(row.intensity).toBe(null); // 用户没填强度，就不替他编一个
  expect(wxState().toasts[wxState().toasts.length - 1]).toBe('已记下 开心');

  expect(count(page, '.radar-card')).toBe(1);
  expect(count(page, '.zero')).toBe(0);
  expect(allText(page, '.row-n')).toContain('社交');
  expect(allText(page, '.row-v')).toBe('0 | 68 | 0 | 68 | 68 | 0');
  expect(text(page, '.rec')).toContain('和室友去操场走了三圈');
});

test('树洞 records feed the same radar even though they were written elsewhere', async () => {
  seed([], [{ id: 'p1', ts: now() - DAY, text: '和室友看了场电影', mood: 'joy', closed: false }]);
  const page = await openRadar();

  expect(text(page, '.head')).toContain('读到你记了 1 条内容');
  expect(allText(page, '.rec')).toContain('来自树洞');
  expect(allText(page, '.row-v')).toBe('0 | 68 | 0 | 0 | 68 | 68'); // 室友→社交 · 电影→兴趣 · 情绪稳定 1 条
});

test('an empty note is still a valid check-in because the mood itself is the record', async () => {
  const page = await openRadar();
  await tapN(page, '.js-mood', 4); // 低落
  await tap(page, '.js-save');

  const row = store().read().moods[0];
  expect(row.mood).toBe('low');
  expect(row.text).toBe('');
  expect(allText(page, '.rec')).toContain('只记了心情，没写为什么');
  expect(allText(page, '.row-v')).toBe('0 | 0 | 0 | 0 | 68 | 0'); // 没有文字，就没有任何维度被关键词点亮
});

test('收回的一条树洞不再被雷达计算', async () => {
  store().write((d) => {
    posts.add(d, { text: '在图书馆自习到闭馆', ts: now() - DAY, mood: 'calm', tz: 0 });
    posts.close(d, d.posts[0].id);
  });
  const page = await openRadar();

  expect(text(page, '.head')).toContain('记了 0 条内容');
  expect(count(page, '.radar-card')).toBe(0);
  expect(count(page, '.rec')).toBe(0);
});
