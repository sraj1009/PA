// 计划里 Task 10 的示例把 chat.send 写成「返回 state」，实际契约和 core/posts.js
// 一致：state 就地修改，函数返回 {ok, reason} 结果对象，页面拿得到拒绝原因。
// 下面的用例按 shipped 契约写，chat.reap 仍旧返回 state。
const chat = require('../core/chat');
const groups = require('../core/groups');

const S = () => ({ chats: [], profile: { interests: [] }, favourites: { shops: [], groups: [] } });

test('open starts one anonymous local session with no messages', () => {
  const s = S();
  const c = chat.open(s, { ts: 1000, persona: 'curious' });
  expect(c.id).toBe('c_1000_1');
  expect(c.messages).toEqual([]);
  expect(c.closed).toBe(false);
  expect(c.persona).toBe('curious');
  expect(s.chats.length).toBe(1);
  expect(chat.current(s).id).toBe(c.id);
});

test('299s of silence keeps the session open with the countdown left', () => {
  const s = S();
  const { id } = chat.open(s, { ts: 0 });
  chat.send(s, id, '在吗', 0);
  const r = chat.expire(s, id, 299000);
  expect(r.closed).toBe(false);
  expect(r.remaining).toBe(1000);
  expect(r.warn).toBe(true); // 已经进了最后 30 秒
});

test('301s idle closes the session', () => {
  let s = S();
  const { id } = chat.open(s, { ts: 0, persona: 'warm' });
  chat.send(s, id, '在吗', 1000);
  expect(chat.expire(s, id, 1000 + 299000).closed).toBe(false);
  expect(chat.reap(s, 1000 + 301000).chats[0].closed).toBe(true);
  expect(s.chats[0].reason).toBe('timeout');
  expect(s.chats[0].closedAt).toBe(1000 + 300000); // 关闭时刻是超时点，不是扫描时刻
});

test('activity resets the countdown', () => {
  let s = S();
  const { id } = chat.open(s, { ts: 0 });
  chat.send(s, id, 'hi', 200000);
  expect(chat.expire(s, id, 400000).closed).toBe(false);
  expect(chat.reap(s, 400000).chats[0].closed).toBe(false);
  expect(s.chats[0].lastAt).toBe(200000);
});

test('the warning window is exactly the last 30 seconds', () => {
  expect(chat.warnAt).toBe(270000);
  expect(chat.idleMs).toBe(300000);
  const s = S();
  const { id } = chat.open(s, { ts: 0 });
  expect(chat.expire(s, id, 269999).warn).toBe(false);
  expect(chat.expire(s, id, 270000).warn).toBe(true);
  expect(chat.expire(s, id, 270000).remaining).toBe(30000);
});

test('a closed session rejects further messages from both sides', () => {
  const s = S();
  const { id } = chat.open(s, { ts: 0 });
  chat.send(s, id, '第一句', 0);
  chat.reap(s, 400000);

  const mine = chat.send(s, id, '还有人吗', 400001);
  expect(mine.ok).toBe(false);
  expect(mine.reason).toBe('这个会话已经关闭了');
  const late = chat.peer(s, id, '刚才在忙', 400002); // 迟到的回复不会把会话救活
  expect(late.ok).toBe(false);
  expect(s.chats[0].closed).toBe(true);
  expect(s.chats[0].messages.length).toBe(1);
});

test('reap is idempotent', () => {
  const s = S();
  const { id } = chat.open(s, { ts: 0 });
  chat.send(s, id, 'hi', 1000);
  const once = chat.reap(s, 1000 + 301000);
  const before = JSON.parse(JSON.stringify(once.chats));
  const twice = chat.reap(s, 1000 + 900000);
  expect(twice.chats).toEqual(before);
  expect(twice.chats.length).toBe(1);
});

test('empty and oversized messages are handled before they reach storage', () => {
  const s = S();
  const { id } = chat.open(s, { ts: 0 });
  expect(chat.send(s, id, '   ', 0).reason).toBe('先写点什么再发');
  expect(chat.send(s, id, null, 0).ok).toBe(false);
  const long = chat.send(s, id, '字'.repeat(300), 1000);
  expect(long.ok).toBe(true);
  expect(long.message.text.length).toBe(chat.maxLen);
  expect(s.chats[0].messages.length).toBe(1);
});

test('send to an unknown session says so instead of creating one', () => {
  const s = S();
  expect(chat.send(s, 'nope', 'hi', 0).reason).toBe('会话不存在');
  expect(s.chats).toEqual([]);
});

test('only the newest session counts as current and closing it leaves none', () => {
  const s = S();
  const a = chat.open(s, { ts: 0 });
  const b = chat.open(s, { ts: 1000 });
  expect(chat.current(s).id).toBe(b.id);
  chat.reap(s, a.lastAt + 301000);
  expect(chat.current(s).id).toBe(b.id); // b 刚开过，不该被 a 的时间牵连
  chat.reap(s, 1000 + 301000);
  expect(chat.current(s)).toBe(null);
});

test('two sessions opened in the same millisecond still get different ids', () => {
  const s = S();
  const a = chat.open(s, { ts: 5000 });
  const b = chat.open(s, { ts: 5000 });
  expect(a.id).not.toBe(b.id);
  expect(s.chats.map((c) => c.id)).toEqual(['c_5000_1', 'c_5000_2']);
});

test('peer turns are recorded as peer so the page can tell who said what', () => {
  const s = S();
  const { id } = chat.open(s, { ts: 0 });
  chat.send(s, id, '明天展示好紧张', 1000);
  chat.peer(s, id, '紧张很正常，是哪一段让你打鼓？', 2000);
  expect(s.chats[0].messages.map((m) => m.from)).toEqual(['me', 'peer']);
  expect(s.chats[0].messages[1].ts).toBe(2000);
});

test('the peer topic pool comes only from the groups joined on this device', () => {
  const pool = require('../data/groups').groups;
  const s = S();
  expect(chat.topics(s, pool)).toEqual([]); // 没加入就没有话题，不替用户编

  groups.join(s, 'g01', pool);
  groups.join(s, 'g05', pool);
  const list = chat.topics(s, pool);
  expect(list).toEqual(['摄影', '相机', '后期', '电影', '剪辑']); // 重叠的「摄影」只算一次
  expect(list.length).toBeLessThanOrEqual(6);
});

test('topics survive the session so an older chat keeps the pool it was opened with', () => {
  const pool = require('../data/groups').groups;
  const s = S();
  groups.join(s, 'g02', pool);
  const c = chat.open(s, { ts: 0, topics: chat.topics(s, pool) });
  expect(c.topics).toEqual(['跑步', '夜跑', '操场']);

  groups.leave(s, 'g02');
  expect(s.chats[0].topics).toEqual(['跑步', '夜跑', '操场']);
  expect(chat.topics(s, pool)).toEqual([]);
});
