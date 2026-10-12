// 本机存储写满，是这个「不依赖云端」的小程序唯一会遇到的“服务器错误”。
// 所有页面的写盘都只走 adapters/local 的 save()，所以这里逐页证明同一件事：
// 写不进去 → 说一句人话、不宣布成功、不擦掉人刚写的字、按钮不卡在忙态。
// 证明方式是用例里的 wxState().quotaFailTimes：它让每一次 wx.setStorageSync 都抛，
// core/store 的三次自救（原样 → 裁聊天 → 丢已收回树洞）全部失败，最后抛 QuotaError。
const {
  loadPage, tap, tapN, input, text, count, classAt, wxState, resetWxState, simulate, waitFor,
} = require('./helpers/render');
const { freeze, unfreeze } = require('./helpers/clock');
const { store, resetStore, storage } = require('../adapters/local');
const { KEY } = require('../core/schema');
const chat = require('../core/chat');

jest.setTimeout(60000);

const FULL = 99;
const mounted = [];

async function open(name) {
  const page = await loadPage(name);
  mounted.push(page);
  await simulate.sleep(20);
  return page;
}

function full() { wxState().quotaFailTimes = FULL; }
function toasts() { return wxState().toasts.join(' | '); }

beforeEach(() => {
  while (mounted.length) mounted.pop().detach();
  resetWxState();
  resetStore();
  freeze(9, 0); // 好店的「营业中」和规划的「今天还剩多少」都要一个稳定的小时
});

afterEach(() => {
  unfreeze();
});

test('树洞：写不进本机就不说「已发出」，草稿原样留着，按钮也不卡住', async () => {
  const page = await open('treehole');
  await input(page, '.js-draft', '论文交不上');
  full();
  await tap(page, '.js-publish');
  await waitFor(() => expect(toasts()).toContain('本机空间已满'));

  expect(toasts()).not.toContain('已发出');
  expect(page.instance.data.busy).toBe(false); // 不许永远停在「标注中…」
  expect(page.instance.data.draft).toContain('论文交不上');
  expect(count(page, '.post')).toBe(0);
  expect(storage.get(KEY)).toBe(''); // 一条都没写成，就不该在本机留下东西
});

test('打卡：没落进本机就不报「打卡成功」，计数与覆盖率都不动', async () => {
  const page = await open('explore');
  full();
  await tap(page, '.js-check');

  expect(toasts()).toContain('本机空间已满');
  expect(toasts()).not.toContain('打卡成功');
  expect(text(page, '.hero-n')).toBe('0');
  expect(storage.get(KEY)).toBe('');
});

test('规划：待办没存下就不擦掉这行字，列表也不会长出它', async () => {
  const page = await open('planner');
  await input(page, '.tinput', '写完高数作业');
  full();
  await tap(page, '.js-add');

  expect(toasts()).toContain('本机空间已满');
  expect(page.instance.data.title).toBe('写完高数作业');
  expect(count(page, '.task')).toBe(0);
  expect(storage.get(KEY)).toBe('');
});

test('规划：排得出来但存不下时，不把安排摆上屏，也不说「已生成」', async () => {
  store().write((d) => {
    d.tasks = [{ id: 't1', title: '取快递', priority: 1, durationMin: 30, deadline: null }];
  });
  const page = await open('planner');
  full();
  await tap(page, '.js-gen');

  expect(toasts()).toContain('本机空间已满');
  expect(toasts()).not.toContain('已生成');
  expect(count(page, '.slot')).toBe(0);
  expect(storage.get(KEY).plans).toEqual([]);
});

test('聊天：我这条没存下就不清空输入框，也不进入「思考中」', async () => {
  store().write((d) => {
    chat.open(d, { ts: Date.now(), persona: 'warm', topics: ['摄影'] });
  });
  const page = await open('chat');
  await input(page, '.js-draft', '周末去拍点什么好呢');
  full();
  await tap(page, '.js-send');

  expect(toasts()).toContain('本机空间已满');
  expect(page.instance.data.busy).toBe(false);
  expect(page.instance.data.draft).toContain('周末去拍点什么好呢');
  expect(storage.get(KEY).chats[0].messages).toEqual([]);
});

test('好店：收藏没落进本机，星标就不许亮起来', async () => {
  const page = await open('shops');
  full();
  await tap(page, '.js-fav');

  expect(toasts()).toContain('本机空间已满');
  expect(classAt(page, '.js-fav', 0)).not.toContain('star--on');
  expect(storage.get(KEY)).toBe('');
});

test('心情雷达：这条没存下就不说「已记下」，写好的字留着', async () => {
  const page = await open('radar');
  await input(page, '.js-note', '熬到两点才睡着');
  full();
  await tap(page, '.js-save');

  expect(toasts()).toContain('本机空间已满');
  expect(toasts()).not.toContain('已记下');
  expect(page.instance.data.note).toContain('熬到两点才睡着');
  expect(storage.get(KEY)).toBe('');
});

test('社群：加入没写进本机就不报「已加入」，清单也不重画', async () => {
  const page = await open('groups');
  await tapN(page, '.js-interest', 0); // 摄影：这一步要真的写进本机，加入按钮才会出现
  expect(storage.get(KEY).profile.interests).toEqual(['摄影']);
  full();
  await tap(page, '.js-join');

  expect(toasts()).toContain('本机空间已满');
  expect(toasts()).not.toMatch(/已加入|已退出/);
  expect((storage.get(KEY).favourites || {}).groups || []).toEqual([]);
});

test('仪表盘：偏好写不进本机时芯片不亮，屏幕仍然说存储里那一句', async () => {
  const page = await open('index');
  full();
  await tapN(page, '.js-mode-chip', 1); // 只用离线
  await waitFor(() => expect(toasts()).toContain('本机空间已满'));

  expect(page.instance.data.agentMode).toBe('auto'); // 本机里根本没有偏好，那就是 auto
  expect(classAt(page, '.js-mode-chip', 1)).not.toContain('chip--on');
  // 徽标这里断言「页面绑进去的那个值」而不是徽标上的字：mode-badge 被规划页和本页
  // 同时声明，simulate 每个页面各自注册一次同名子组件，后注册的那份渲染不出内容
  // （innerHTML 恒为空）。写进屏幕的那句话由 page-index.test.js 证明，那里首页先挂载。
  expect(count(page, '.js-mode')).toBe(1);
  expect(page.instance.data.mode).toBe('offline'); // 降级到离线，不虚报「本地模型」
  expect(page.instance.data.agentNote).toContain('自动'); // 说的还是存储里那一句
  expect(storage.get(KEY)).toBe('');
});
