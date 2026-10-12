// 跨功能接线：一句话从树洞出发，改变的是雷达上的一个角；一次打卡改变的是首页的天数；
// 加入一个社群改变的是聊天里 TA 能聊的话题。全部用真页面驱动，不直接调 core。
const {
  loadPage, tap, tapN, input, text, allText, count, wxState, resetWxState, simulate,
} = require('./helpers/render');
const { store, resetStore, storage } = require('../adapters/local');
const { KEY } = require('../core/schema');
const agent = require('../agent/index');

jest.setTimeout(60000);

const mounted = [];

async function open(name) {
  const page = await loadPage(name);
  mounted.push(page);
  await settle();
  return page;
}

async function settle() {
  await simulate.sleep(30);
  await simulate.sleep(30);
}

beforeEach(() => {
  resetWxState();
  resetStore();
  agent.reset();
});

afterEach(() => {
  while (mounted.length) mounted.pop().detach();
});

test('a line published in the tree hole moves the matching corner of the radar', async () => {
  const hole = await open('treehole');
  expect(count(hole, '.post')).toBe(0);

  await input(hole, '.js-draft', '答辩排在周一，晚上睡不着');
  await tap(hole, '.js-publish');
  await settle();

  const saved = storage.get(KEY);
  expect(saved.posts.length).toBe(1);
  expect(saved.posts[0].mood).toBe('anxious'); // 分类由适配层给出，这条走的是离线词库
  expect(saved.posts[0].source).toBe('offline');

  const radar = await open('radar');
  expect(count(radar, '.zero')).toBe(0);
  expect(text(radar, '.head')).toContain('读到你记了 1 条内容');
  // 学业（答辩）与作息（睡）各 40*(1/5)+60*0.3=26；只有一条记录，情绪稳定按不翻面算 68。
  expect(allText(radar, '.row-n')).toBe('学业 | 社交 | 作息 | 运动 | 情绪稳定 | 兴趣');
  expect(allText(radar, '.row-v')).toBe('26 | 0 | 26 | 0 | 68 | 0');
  expect(text(radar, '.rec')).toContain('答辩排在周一');
  expect(text(radar, '.rec')).toContain('来自树洞');
});

test('taking a tree-hole line back takes it out of the radar again', async () => {
  const hole = await open('treehole');
  await input(hole, '.js-draft', '答辩排在周一，晚上睡不着');
  await tap(hole, '.js-publish');
  await settle();
  await tap(hole, '.js-close');
  await settle();
  expect(storage.get(KEY).posts[0].closed).toBe(true);

  const radar = await open('radar');
  expect(count(radar, '.zero')).toBe(1);
  expect(text(radar, '.zero')).toContain('还没有记录');
});

test('a check-in on the explore page is the streak the home page reports', async () => {
  const home = await open('index');
  expect(text(home, '.js-check')).toBe('今天还没打卡');
  home.detach();

  const ex = await open('explore');
  await tap(ex, '.js-check');
  expect(text(ex, '.hero-n')).toBe('1');

  const again = await open('index');
  expect(text(again, '.js-check')).toBe('连续打卡 1 天');
  expect(text(again, '.js-check-meta')).toBe('走过 1 / 12 个校内地点');
});

test('joining a interest group is what the chat peer is allowed to talk about', async () => {
  const cold = await open('chat');
  expect(text(cold, '.start')).toContain('还没加入社群');
  expect(count(cold, '.topic')).toBe(0);
  cold.detach();

  const groups = await open('groups');
  await tapN(groups, '.js-interest', 0); // 摄影
  await tap(groups, '.js-join');
  expect(storage.get(KEY).favourites.groups).toEqual(['g01']);
  groups.detach();

  const chat = await open('chat');
  expect(allText(chat, '.topic')).toBe('摄影 | 相机 | 后期');
  expect(text(chat, '.topics')).toContain('来自你加入的 1 个示例社群');

  await tap(chat, '.js-open');
  await settle();
  const saved = storage.get(KEY);
  expect(saved.chats.length).toBe(1);
  expect(saved.chats[0].topics).toEqual(['摄影', '相机', '后期']);

  await input(chat, '.js-draft', '周末去拍点什么好呢');
  await tap(chat, '.js-send');
  await settle();
  const after = storage.get(KEY).chats[0].messages;
  expect(after.length).toBe(2);
  expect(after[0].from).toBe('me');
  expect(after[1].from).toBe('peer');
});

test('a generated plan is what the home page counts as today’s schedule', async () => {
  const plan = await open('planner');
  await input(plan, '.tinput', '写完高数作业');
  await tap(plan, '.js-add');
  await tap(plan, '.js-gen');
  await settle();

  const saved = storage.get(KEY);
  expect(saved.tasks.length).toBe(1);
  expect(saved.plans.length).toBe(1);
  plan.detach();

  const home = await open('index');
  expect(count(home, '.js-plan-empty')).toBe(0);
  expect(text(home, '.js-plan')).toContain('1 段安排');
  expect(text(home, '.js-plan-meta')).toContain('生成');
});
