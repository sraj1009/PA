// 匿名一对一聊天的纯逻辑层。对面永远只有一个本机的模拟同伴，
// 所以这里没有配对、没有网络、也没有"其他真人"——需求里那条
// 「5 分钟无操作自动关闭」在这里是硬编码的 300000 毫秒，
// 页面倒计时只是把它读给人看。
//
// 会话从头到尾都待在 state.chats 里：关闭只是打上 closed/closedAt/reason，
// 不删记录，也不另开一个归档数组——「归档」在纯本地小程序里就是同一份本机数据。

const IDLE_MS = 300000; // 无操作 5 分钟关闭
const WARN_AT = 270000; // 无操作到 4 分半开始提醒，还剩 30 秒
const MAX_LEN = 200;

function byId(state, id) {
  return (state.chats || []).find((c) => c.id === id) || null;
}

/** 模拟同伴能聊的共同话题只来自用户自己加入的示例社群；没加入就是空。 */
function topics(state, pool) {
  const joined = require('./groups').joined(state, pool);
  const out = [];
  joined.forEach((g) => {
    (g.tags || []).forEach((t) => {
      if (out.indexOf(t) < 0) out.push(t);
    });
  });
  return out.slice(0, 6);
}

function open(state, opts) {
  const o = opts || {};
  const ts = Number(o.ts) || 0;
  if (!Array.isArray(state.chats)) state.chats = [];
  const session = {
    id: 'c_' + ts + '_' + (state.chats.length + 1),
    startedAt: ts,
    lastAt: ts,
    closed: false,
    closedAt: null,
    reason: null,
    persona: o.persona || 'warm',
    topics: (o.topics || []).slice(),
    messages: [],
  };
  state.chats.push(session);
  return session;
}

/** 当前还开着的那一条；同时最多一条，多开也只认最新。 */
function current(state) {
  const list = (state.chats || []).filter((c) => !c.closed);
  return list.length ? list[list.length - 1] : null;
}

function push(state, id, from, text, ts) {
  const s = byId(state, id);
  if (!s) return { ok: false, reason: '会话不存在' };
  if (s.closed) return { ok: false, reason: '这个会话已经关闭了' };
  const clean = String(text == null ? '' : text).trim();
  if (from === 'me' && !clean) return { ok: false, reason: '先写点什么再发' };
  const message = { from, text: clean.slice(0, MAX_LEN), ts };
  s.messages.push(message);
  s.lastAt = ts; // 任何一侧开口都重新计时
  return { ok: true, message, session: s };
}

function send(state, id, text, ts) {
  return push(state, id, 'me', text, ts);
}

/** 模拟同伴的回复。迟到的回复不会把已关闭的会话救活，只会整条丢掉。 */
function peer(state, id, text, ts) {
  return push(state, id, 'peer', text, ts);
}

/** 只做一件事：按给定时刻判断这条会话还开着吗，超时就地关闭。 */
function expire(state, id, ts) {
  const s = byId(state, id);
  if (!s) return { closed: true, reason: 'missing', remaining: 0, warn: false };
  if (s.closed) return { closed: true, reason: s.reason, remaining: 0, warn: false };

  const idle = ts - s.lastAt;
  if (idle > IDLE_MS) {
    s.closed = true;
    s.closedAt = s.lastAt + IDLE_MS; // 关闭时刻是超时点，不是扫描时刻
    s.reason = 'timeout';
    return { closed: true, reason: 'timeout', remaining: 0, warn: false };
  }
  return {
    closed: false,
    reason: null,
    idle,
    remaining: IDLE_MS - idle,
    warn: idle >= WARN_AT,
  };
}

/** 扫一遍所有会话，把过期的关掉；重复调用不会改动已经关掉的那些。 */
function reap(state, ts) {
  (state.chats || []).forEach((c) => {
    if (!c.closed) expire(state, c.id, ts);
  });
  return state;
}

module.exports = {
  idleMs: IDLE_MS,
  warnAt: WARN_AT,
  maxLen: MAX_LEN,
  byId,
  current,
  open,
  send,
  peer,
  expire,
  reap,
  topics,
};
