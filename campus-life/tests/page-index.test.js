const {
  loadPage, tapInner, text, html, count, simulate, wxState, resetWxState,
} = require('./helpers/render');
const { store, resetStore, storage, tzOffsetMin } = require('../adapters/local');
const { KEY } = require('../core/schema');
const fmt = require('../core/format');
const agent = require('../agent/index');

jest.setTimeout(60000);

const DAY_MS = 86400000;
const REAL_DATE = Date;
const NOW = () => Date.now();

async function openHome() {
  const page = await loadPage('index');
  await simulate.sleep(30);
  return page;
}

/** 把时钟挪到「昨天」，用真 Date.now 做基准，免得和 helpers/clock 的冻结钟打架。 */
function yesterday(fn) {
  const real = Date;
  global.Date = class extends real {
    constructor(...a) { if (a.length) super(...a); else super(real.now() - DAY_MS); }
    static now() { return real.now() - DAY_MS; }
  };
  try { fn(); } finally { global.Date = real; }
}

function seedPlan(ts, slots, unscheduled) {
  store().write((d) => {
    d.plans.push({
      id: 'plan_' + ts,
      day: fmt.day(ts, tzOffsetMin()),
      ts,
      slots,
      unscheduled,
    });
  });
}

beforeEach(() => {
  resetWxState();
  resetStore();
  agent.reset();
});

afterEach(() => {
  global.Date = REAL_DATE;
});

test('a fresh device shows three honest blanks and never writes to storage', async () => {
  const page = await openHome();

  expect(count(page, '.stat')).toBe(3);
  expect(text(page, '.js-plan-empty')).toContain('今天还没排过日程');
  expect(text(page, '.js-plan-empty')).toContain('去规划');
  expect(count(page, '.js-plan')).toBe(0);
  expect(text(page, '.js-check')).toBe('今天还没打卡');
  expect(text(page, '.js-check-meta')).toBe('走过 0 / 12 个校内地点');
  expect(text(page, '.js-mood-empty')).toContain('还没有心情记录');
  expect(text(page, '.js-mood-meta')).toBe('本机共 0 条（心情 0 · 树洞 0）');
  expect(text(page, '.js-mode')).toContain('离线模式');
  expect(text(page, '.local-only')).toContain('内容仅存于本机');
  expect(storage.get(KEY)).toBe(''); // 仪表盘只读：光打开首页不该留下任何东西
});

test('both modules list every entry they have', async () => {
  const page = await openHome();
  const social = html(page, '.js-social');
  const tools = html(page, '.js-tools');

  expect(count(page, '.js-nav')).toBe(4);
  expect(count(page, '.js-tool')).toBe(3);
  expect(social).toContain('校园树洞');
  expect(social).toContain('匿名一对一聊天');
  expect(social).toContain('兴趣社群匹配');
  expect(social).toContain('心情雷达');
  expect(tools).toContain('本地探索打卡');
  expect(tools).toContain('时间管理智能规划');
  expect(tools).toContain('周边好店聚合');
  expect(social + tools).not.toMatch(/%/); // 首页不编百分比
  page.detach();
});

test('tapping an entry uses the navigation call that page actually answers to', async () => {
  const page = await openHome();

  await tapInner(page, '.js-nav', 'nav'); // 社交第一项：树洞在 tabBar 上
  expect(wxState().nav).toEqual([{ type: 'switchTab', url: '/pages/treehole/index' }]);

  wxState().nav.length = 0;
  await tapInner(page, '.js-chat', 'nav'); // 聊天不在 tabBar 上，只能 navigateTo
  expect(wxState().nav).toEqual([{ type: 'navigateTo', url: '/pages/chat/index' }]);
  page.detach();
});

test('an empty status sends the visitor where the record is made', async () => {
  const page = await openHome();

  await tapInner(page, '.js-plan-empty', 'js-action');
  expect(wxState().nav).toEqual([{ type: 'switchTab', url: '/pages/planner/index' }]);

  wxState().nav.length = 0;
  await tapInner(page, '.js-mood-empty', 'js-action');
  expect(wxState().nav).toEqual([{ type: 'navigateTo', url: '/pages/radar/index' }]);
  page.detach();
});

test('today’s plan reports its segments, its minutes and what did not fit', async () => {
  seedPlan(NOW(), [
    { taskId: 't1', title: '写高数作业', start: 540, end: 600 },
    { taskId: 't2', title: '背五十个单词', start: 660, end: 690 },
  ], ['t9']);

  const page = await openHome();
  expect(count(page, '.js-plan-empty')).toBe(0);
  expect(text(page, '.js-plan')).toBe('2 段安排 · 占 90 分钟 · 还有 1 件没排下');
  expect(text(page, '.js-plan-meta')).toContain('生成');
  page.detach();
});

test('a plan made yesterday is not presented as today’s', async () => {
  yesterday(() => seedPlan(Date.now(), [{ taskId: 't1', title: '交实验报告', start: 600, end: 660 }], []));

  const page = await openHome();
  expect(count(page, '.js-plan')).toBe(0);
  expect(text(page, '.js-plan-empty')).toContain('今天还没排过日程');
  page.detach();
});

test('check-ins raise the streak and the places walked, and a gap cuts it off', async () => {
  store().write((d) => {
    d.checkins.push({ id: 'c1', spotId: 'lib', ts: NOW() });
    d.checkins.push({ id: 'c2', spotId: 'gym', ts: NOW() - DAY_MS });
    d.checkins.push({ id: 'c3', spotId: 'canteen2', ts: NOW() - DAY_MS });
  });
  let page = await openHome();
  expect(text(page, '.js-check')).toBe('连续打卡 2 天');
  expect(text(page, '.js-check-meta')).toBe('走过 3 / 12 个校内地点');
  page.detach();

  store().write((d) => { d.checkins = d.checkins.filter((c) => c.id !== 'c1'); }); // 今天没打
  page = await openHome();
  expect(text(page, '.js-check')).toBe('今天还没打卡');
  expect(text(page, '.js-check-meta')).toBe('走过 2 / 12 个校内地点');
  page.detach();
});

test('the mood line takes whichever of the two records is newer', async () => {
  store().write((d) => {
    d.moods.push({ id: 'm1', ts: NOW() - 3 * DAY_MS, mood: 'joy', intensity: null, text: '晨跑' });
  });
  let page = await openHome();
  expect(text(page, '.js-mood')).toContain('开心');
  expect(text(page, '.js-mood')).toContain('3天前');
  page.detach();

  store().write((d) => {
    d.posts.push({
      id: 'p1', ts: NOW() - 3600000, text: '答辩排在周一', mood: 'anxious', intensity: 0.7,
      source: 'offline', closed: false, anon: '晚风同学101',
    });
  });
  page = await openHome();
  expect(text(page, '.js-mood')).toContain('焦虑');
  expect(text(page, '.js-mood')).toContain('今天');
  expect(text(page, '.js-mood-meta')).toBe('本机共 2 条（心情 1 · 树洞 1）');
  page.detach();
});

test('a tree-hole post that was taken back is not counted as a mood record', async () => {
  store().write((d) => {
    d.posts.push({
      id: 'p1', ts: NOW(), text: '刚哭了一场', mood: 'low', intensity: 0.8,
      source: 'offline', closed: true, anon: '路灯同学202',
    });
  });
  const page = await openHome();
  expect(count(page, '.js-mood')).toBe(0);
  expect(text(page, '.js-mood-empty')).toContain('还没有心情记录');
  expect(text(page, '.js-mood-meta')).toBe('本机共 0 条（心情 0 · 树洞 0）');
  page.detach();
});

test('the badge only claims 本地模型 after the probe actually reached the model', async () => {
  const before = await openHome();
  expect(text(before, '.js-mode')).toContain('离线模式');
  expect(wxState().requests.length).toBe(1);
  expect(wxState().requests[0].url).toBe('http://localhost:11434/api/tags');
  before.detach();

  const real = global.wx.request;
  global.wx.request = (o) => {
    setTimeout(() => o.success({ statusCode: 200, data: { models: [{ name: 'qwen2.5:3b' }] } }), 0);
  };
  agent.reset();
  const page = await openHome();
  global.wx.request = real;

  expect(text(page, '.js-mode')).toContain('本地模型');
  expect(text(page, '.js-mode')).not.toContain('不联网也能用');
  page.detach();
});
