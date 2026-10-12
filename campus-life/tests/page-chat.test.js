const fs = require('fs');
const path = require('path');
const {
  loadPage, tap, tapN, input, text, allText, count, classAt,
  wxState, resetWxState, simulate,
} = require('./helpers/render');
const { freeze, unfreeze, advance } = require('./helpers/clock');
const { store, resetStore, storage } = require('../adapters/local');
const { KEY } = require('../core/schema');
const chat = require('../core/chat');
const groups = require('../core/groups');
const offline = require('../agent/offline');
const agent = require('../agent/index');
const { groups: POOL } = require('../data/groups');

jest.setTimeout(60000);

async function settle() {
  await simulate.sleep(30);
  await simulate.sleep(30);
}

// 聊天页有个每秒跑一次的计时器：页面不 detach 的话，它会在后面的用例里继续活着，
// 用当前时钟把那条用例的会话关掉、把 toast 弹出来——到时候失败的就不是泄漏的用例了。
const mounted = [];

async function openChat() {
  const page = await loadPage('chat');
  mounted.push(page);
  await settle();
  return page;
}

/** 直接造一条还开着的会话，省掉等 5 分钟的用例时间。 */
function seedSession(ageMs, opts) {
  const o = opts || {};
  store().write((d) => {
    const ts = Date.now() - ageMs;
    const s = chat.open(d, { ts, persona: o.persona || 'warm', topics: o.topics || [] });
    if (o.text) chat.send(d, s.id, o.text, ts);
  });
}

/** 关闭由 setInterval 完成，用例轮询等它出现；这台机器上定时器会被压到 1 秒以后，赌固定 sleep 会时好时坏。 */
async function waitClosed(page) {
  for (let i = 0; i < 12; i += 1) {
    if (page.querySelector('.again')) return true;
    await simulate.sleep(250);
  }
  return false;
}

beforeEach(() => {
  resetWxState();
  resetStore();
  agent.reset(); // 每条用例重新探测，才能看见页面确实走的是适配层
  freeze(9, 0);
});

afterEach(() => {
  // detach 会触发 onUnload：每条用例都把自己留下的计时器清干净，失败才只可能是真的泄漏。
  while (mounted.length) mounted.pop().detach();
  unfreeze();
});

test('a fresh chat offers a persona, labels the peer as a simulation, and stores nothing', async () => {
  const page = await openChat();

  expect(count(page, '.start')).toBe(1);
  expect(count(page, '.js-persona')).toBe(3);
  expect(text(page, '.badge--ai')).toBe('模拟/AI');
  expect(text(page, '.mode-badge')).toBe('离线模式'); // 这台机器上模型不可达，标注就得说实话
  expect(text(page, '.local-only')).toContain('内容仅存于本机');
  expect(text(page, '.start')).toContain('也不会替你编一个');
  expect(count(page, '.b')).toBe(0);
  expect(storage.get(KEY)).toBe('');
});

test('开始聊天 opens one local session with the picked persona', async () => {
  const page = await openChat();
  await tapN(page, '.js-persona', 1); // 同好型
  expect(text(page, '.meta')).toContain('同好型');

  await tap(page, '.js-open');
  await settle();

  const saved = storage.get(KEY).chats;
  expect(saved.length).toBe(1);
  expect(saved[0].persona).toBe('curious');
  expect(saved[0].closed).toBe(false);
  expect(saved[0].messages).toEqual([]);
  expect(count(page, '.compose')).toBe(1);
  expect(count(page, '.empty')).toBe(1);
  expect(wxState().toasts).toContain('开始聊天 · 对面是本机模拟同伴');
});

test('发送 shows my bubble first, then a peer bubble that really came from the agent', async () => {
  const page = await openChat();
  await tap(page, '.js-open');

  const line = '明天小组展示，特别紧张';
  await input(page, '.js-draft', line);
  await tap(page, '.js-send');
  await settle();

  // 页面只经过 agent/index：先探测本机模型，不可达再由离线词库接住。
  expect(wxState().requests.length).toBeGreaterThan(0);
  expect(wxState().requests[0].url).toBe('http://localhost:11434/api/tags');

  const saved = storage.get(KEY).chats[0];
  expect(saved.messages.map((m) => m.from)).toEqual(['me', 'peer']);
  expect(saved.messages[0].text).toBe(line);
  expect(saved.messages[1].text).toBe(offline.chat([], line, 'warm').text);

  expect(count(page, '.b')).toBe(2);
  expect(text(page, '.b--me')).toContain(line);
  expect(allText(page, '.b--peer')).toContain('模拟同伴');
  expect(text(page, '.ai')).toBe('模拟/AI');
  expect(text(page, '.count')).toContain('离线词库回复');
  expect(text(page, '.js-send')).toBe('发送'); // 按钮从「思考中…」回来了
});

test('an empty message is refused and stores nothing', async () => {
  const page = await openChat();
  await tap(page, '.js-open');
  await tap(page, '.js-send');

  expect(wxState().toasts).toContain('先写点什么再发');
  expect(storage.get(KEY).chats[0].messages).toEqual([]);
  expect(count(page, '.b')).toBe(0);
});

test('the last 30 seconds get a warning line instead of a silent cutoff', async () => {
  seedSession(chat.warnAt + 5000); // 已经沉默 4 分 35 秒
  const page = await openChat();

  expect(classAt(page, '.count', 0)).toContain('count--warn');
  expect(text(page, '.count')).toContain('还有 0:25 没有消息就自动关闭');
  expect(count(page, '.warn')).toBe(1);
});

test('5:01 of silence closes the session on the next tick and says why', async () => {
  seedSession(chat.idleMs + 1000, { text: '刚那句' });
  const page = await openChat();

  expect(await waitClosed(page)).toBe(true); // 关闭由页面自己的计时器完成

  expect(text(page, '.count')).toContain('会话已自动关闭');
  expect(wxState().toasts).toContain('5 分钟没有新消息，会话已自动关闭');

  const saved = storage.get(KEY).chats[0];
  expect(saved.closed).toBe(true);
  expect(saved.reason).toBe('timeout');
  expect(saved.messages.length).toBe(1); // 关闭不删记录

  expect(count(page, '.js-send')).toBe(0); // 关掉了就不该还能往里发
  expect(count(page, '.again')).toBe(1);
});

test('onUnload clears the timer — no toast fires after the page is gone', async () => {
  const page = await openChat();
  await tap(page, '.js-open');
  await settle();
  const seen = wxState().toasts.length;

  advance(chat.idleMs + 5000); // 时钟越过超时点，但页面已经被卸载
  page.detach();
  mounted.splice(mounted.indexOf(page), 1); // 手动卸过的就不再交给 afterEach
  await simulate.sleep(2500); // 定时器要是漏了，这一段时间足够它响一次

  expect(wxState().toasts.length).toBe(seen);
  expect(storage.get(KEY).chats[0].closed).toBe(false); // 没有泄漏的定时器替用户做决定
});

test('the peer topic pool comes from the groups joined on this device', async () => {
  store().write((d) => { groups.join(d, 'g01', POOL); });
  const page = await openChat();

  expect(count(page, '.topic')).toBe(3);
  expect(text(page, '.topics')).toContain('来自你加入的 1 个示例社群');
  expect(allText(page, '.topic')).toBe('摄影 | 相机 | 后期');

  await tap(page, '.js-open');
  expect(storage.get(KEY).chats[0].topics).toEqual(['摄影', '相机', '后期']);
});

test('重新开始 keeps the closed session and opens a second one', async () => {
  seedSession(chat.idleMs + 2000, { text: '上一段的话' });
  const page = await openChat();
  expect(await waitClosed(page)).toBe(true);

  await tap(page, '.js-open');
  await settle();

  const saved = storage.get(KEY).chats;
  expect(saved.length).toBe(2);
  expect(saved[0].closed).toBe(true);
  expect(saved[1].closed).toBe(false);
  expect(count(page, '.compose')).toBe(1);
  expect(text(page, '.count')).toContain('本次会话剩余 5:00');
});

test('an old session stays visible with its own closed banner until a new one opens', async () => {
  seedSession(chat.idleMs + 3000, { text: '那条没回完的' });
  const page = await openChat();
  expect(await waitClosed(page)).toBe(true);

  expect(allText(page, '.b')).toContain('那条没回完的');
  expect(count(page, '.b--me')).toBe(1);
  expect(text(page, '.again')).toContain('上一条记录还留在本机');
});

// maxlength 在这套框架里进不了 DOM（built-in 只留下 class），所以模板契约单独钉一次；
// 真正能被观察的是屏幕上那行字数，和 core 切断消息的那个长度。
test('the compose box shows the same limit core cuts messages at', async () => {
  const page = await openChat();
  await tap(page, '.js-open');
  await settle();

  expect(page.instance.data.maxLen).toBe(chat.maxLen);
  const wxml = fs.readFileSync(path.join(__dirname, '..', 'pages', 'chat', 'index.wxml'), 'utf8');
  expect(wxml).toContain('maxlength="{{maxLen}}"');
  expect(wxml).not.toMatch(/maxlength="\d/);

  await input(page, '.js-draft', '哈'.repeat(chat.maxLen + 50));
  expect(text(page, '.cnt')).toBe((chat.maxLen + 50) + '/' + chat.maxLen);

  await tap(page, '.js-send');
  await settle();

  const saved = storage.get(KEY).chats[0].messages;
  expect(saved[0].from).toBe('me');
  expect(saved[0].text.length).toBe(chat.maxLen); // 截到线上，不整条吞掉
});
