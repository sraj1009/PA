const { loadPage, tap, tapN, input, text, innerText, count, classes, classAt, wxState, resetWxState } = require('./helpers/render');
const { freeze, unfreeze } = require('./helpers/clock');
const { store, resetStore, storage } = require('../adapters/local');
const { KEY } = require('../core/schema');

jest.setTimeout(60000);

function seed(tasks) {
  store().write((d) => { d.tasks = tasks; });
}

beforeEach(() => {
  resetWxState();
  resetStore();
  freeze(9, 0);
});

afterEach(() => {
  unfreeze();
});

test('the planner starts with an empty list and the draft form ready', async () => {
  const page = await loadPage('planner');
  expect(count(page, '.task')).toBe(0);
  expect(count(page, '.empty')).toBe(1);
  expect(count(page, '.chip')).toBe(11);
  expect(classes(page, '.chip')).not.toContain('chip--on');
  expect(classAt(page, '.chip', 1)).toContain('chip--on');
});

test('an empty title is refused with a toast and nothing is written', async () => {
  const page = await loadPage('planner');
  await tap(page, '.js-add');
  expect(wxState().toasts.join('')).toContain('先写点要做的事');
  expect(storage.get(KEY)).toBe('');
});

test('typing a title and tapping 加入待办 persists the task', async () => {
  const page = await loadPage('planner');
  await input(page, '.tinput', '写完高数作业');
  await tap(page, '.js-add');

  expect(count(page, '.task')).toBe(1);
  expect(text(page, '.task-t')).toContain('写完高数作业');
  const saved = storage.get(KEY).tasks[0];
  expect(saved.title).toBe('写完高数作业');
  expect(saved.durationMin).toBe(60);
  expect(saved.priority).toBe(2);
  expect(saved.deadline).toBeNull();
});

test('the chips drive the draft task that gets stored', async () => {
  const page = await loadPage('planner');
  await input(page, '.tinput', '准备 presentation');
  await tapN(page, '.chip', 2); // 90 分
  await tapN(page, '.chip', 4); // 优先级 高
  await tapN(page, '.chip', 8); // 截止 12:00
  expect(classAt(page, '.chip', 2)).toContain('chip--on');
  expect(classAt(page, '.chip', 4)).toContain('chip--on');
  expect(classAt(page, '.chip', 8)).toContain('chip--on');
  expect(classAt(page, '.chip', 7)).not.toContain('chip--on');

  await tap(page, '.js-add');
  const saved = storage.get(KEY).tasks[0];
  expect(saved.durationMin).toBe(90);
  expect(saved.priority).toBe(3);
  expect(saved.deadline).toBe(720);
});

test('generating with no tasks warns instead of making an empty plan', async () => {
  const page = await loadPage('planner');
  await tap(page, '.js-gen');
  expect(wxState().toasts.join('')).toContain('还没有待办事项');
  expect(count(page, '.slot')).toBe(0);
});

test('生成今日安排 renders ordered slots with times and persists the plan', async () => {
  seed([
    { id: 't1', title: '复习高数', priority: 3, durationMin: 90, deadline: null },
    { id: 't2', title: '取快递', priority: 1, durationMin: 30, deadline: null },
    { id: 't3', title: '写实验报告', priority: 2, durationMin: 60, deadline: 720 },
  ]);
  const page = await loadPage('planner');
  expect(count(page, '.task')).toBe(3);

  await tap(page, '.js-gen');

  expect(count(page, '.slot')).toBe(3);
  expect(text(page, '.slot-r')).toBe('09:00 - 10:30');
  expect(text(page, '.slot-t')).toBe('复习高数');

  const plans = storage.get(KEY).plans;
  const busy = plans[0].slots.reduce((n, s) => n + (s.end - s.start), 0);
  expect(busy).toBe(180);
  expect(text(page, '.sum')).toContain('占用 ' + busy + ' 分钟');
  expect(text(page, '.sum')).toContain('600 分钟空闲');

  expect(plans.length).toBe(1);
  expect(plans[0].slots.length).toBe(3);
  expect(plans[0].unscheduled).toEqual([]);
});

test('a fixed commitment keeps its own time and flexible tasks go around it', async () => {
  seed([
    { id: 'f1', title: '下午两点专业课', priority: 2, durationMin: 120, fixed: true, start: 840, end: 960 },
    { id: 't1', title: '背单词', priority: 2, durationMin: 60, deadline: null },
  ]);
  const page = await loadPage('planner');
  await tap(page, '.js-gen');

  expect(count(page, '.slot')).toBe(2);
  expect(text(page, '.slot-r')).toBe('09:00 - 10:00');
  const saved = storage.get(KEY).plans[0].slots;
  expect(saved.map((s) => s.range || s.title)).toEqual(['背单词', '下午两点专业课']);
});

test('work that cannot fit today is listed as overflow instead of dropped', async () => {
  seed([
    { id: 't1', title: '写完课程大作业', priority: 3, durationMin: 900, deadline: null },
    { id: 't2', title: '取快递', priority: 1, durationMin: 30, deadline: null },
  ]);
  const page = await loadPage('planner');
  await tap(page, '.js-gen');

  expect(count(page, '.slot')).toBe(1);
  expect(count(page, '.over')).toBe(1);
  expect(text(page, '.over-i')).toBe('写完课程大作业');
  expect(storage.get(KEY).plans[0].unscheduled).toEqual(['t1']);
});

test('regenerating the same day replaces that day plan rather than stacking', async () => {
  seed([{ id: 't1', title: '取快递', priority: 1, durationMin: 30, deadline: null }]);
  const page = await loadPage('planner');
  await tap(page, '.js-gen');
  await tap(page, '.js-gen');
  expect(storage.get(KEY).plans.length).toBe(1);
  expect(count(page, '.slot')).toBe(1);
});

test('删除 removes the task from storage and the list', async () => {
  seed([{ id: 't1', title: '取快递', priority: 1, durationMin: 30, deadline: null }]);
  const page = await loadPage('planner');
  expect(count(page, '.task')).toBe(1);
  await tap(page, '.del');
  expect(count(page, '.task')).toBe(0);
  expect(count(page, '.empty')).toBe(1);
  expect(storage.get(KEY).tasks.length).toBe(0);
});

// 规划页的「让 AI 说明」是 agent.explain 唯一的使用者：没有它，改写能力就只是测试里的死代码。
test('the explain button only appears once a plan is on screen', async () => {
  seed([{ id: 't1', title: '取快递', priority: 1, durationMin: 30, deadline: null }]);
  const page = await loadPage('planner');
  expect(count(page, '.js-explain')).toBe(0);
  expect(count(page, '.advice')).toBe(0);

  await tap(page, '.js-gen');
  expect(count(page, '.js-explain')).toBe(1);
  expect(count(page, '.advice')).toBe(0);
});

test('让 AI 说明 rewrites the solver output into sentences and labels the engine', async () => {
  seed([
    { id: 't1', title: '复习高数', priority: 3, durationMin: 90, deadline: null },
    { id: 't2', title: '取快递', priority: 1, durationMin: 30, deadline: null },
    { id: 't3', title: '写实验报告', priority: 2, durationMin: 60, deadline: 720 },
  ]);
  const page = await loadPage('planner');
  await tap(page, '.js-gen');
  await tap(page, '.js-explain');

  expect(text(page, '.advice-t')).toContain('今天安排 3 段');
  expect(text(page, '.advice-t')).toContain('09:00 - 10:30 复习高数');
  // 请求 mock 默认失败，所以这里必须是离线词库那条路，而且要把这件事写在屏幕上。
  expect(innerText(page, '.js-advice-mode', 'badge')).toContain('离线模式');
  expect(wxState().requests.length).toBeGreaterThan(0);
});

test('the prose names the work that did not fit instead of hiding it', async () => {
  seed([
    { id: 't1', title: '写完课程大作业', priority: 3, durationMin: 900, deadline: null },
    { id: 't2', title: '取快递', priority: 1, durationMin: 30, deadline: null },
  ]);
  const page = await loadPage('planner');
  await tap(page, '.js-gen');
  await tap(page, '.js-explain');

  expect(text(page, '.advice-t')).toContain('今天放不下：写完课程大作业');
  expect(text(page, '.advice-t')).not.toContain('t1'); // solver 的 id 不许念给人听
  expect(text(page, '.advice-t')).not.toContain('%');
});

test('re-generating drops the prose written about the previous plan', async () => {
  seed([{ id: 't1', title: '取快递', priority: 1, durationMin: 30, deadline: null }]);
  const page = await loadPage('planner');
  await tap(page, '.js-gen');
  await tap(page, '.js-explain');
  expect(count(page, '.advice')).toBe(1);

  await tap(page, '.js-gen');
  expect(count(page, '.advice')).toBe(0);
});


