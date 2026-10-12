// 树洞的纯逻辑层：落一条、读一列、给一个"同一天稳定"的匿名代号。
// 分类（agent.classify）发生在页面里，core 不碰 wx，也不碰网络。
const DAY_MS = 86400000;

// 屏幕上那个「/200」写的就是这个数：规则放在 core，页面只读它，不另抄一遍。
const MAX_LEN = 200;

// 代号取自固定词表，只由"哪一天"决定：既不需要设备号，也不需要在服务端存作者表。
const WORDS = ['梧桐', '晚风', '路灯', '书架', '操场', '银杏', '萤火', '潮汐', '白昼', '云梯', '钟楼', '喷泉'];

function hash(str) {
  let h = 2166136261;
  for (let i = 0; i < str.length; i += 1) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

function dayKey(ts, tz) {
  return Math.floor((ts + (tz || 0) * 60000) / DAY_MS);
}

/** 同一天的同一位本机作者拿到同一个代号；换一天就换一个，读的人不会以为是小号刷屏。 */
function anonId(ts, tz) {
  const h = hash('treehole:' + dayKey(ts, tz));
  return WORDS[h % WORDS.length] + '同学' + (100 + (h % 900));
}

/**
 * 一条树洞能不能发，规则只写在这里这一处。
 * 页面上的「/200」、发送前的拒绝、add 内部的拒绝读的都是它——抄第二份一定会漂。
 * 页面在花钱问模型之前先问一次 validate，是因为超线的内容发不出去，没必要为此调一次本地模型。
 */
function validate(raw) {
  const text = String(raw || '').trim();
  if (!text) return { ok: false, reason: '先写点什么再发' };
  // 发出去的东西不能悄悄被剪掉尾巴：超线就整条拒收，让页面把原因说给人听。
  if (text.length > MAX_LEN) return { ok: false, reason: '最长 ' + MAX_LEN + ' 字，现在 ' + text.length + ' 字' };
  return { ok: true, text };
}

/**
 * opts.mood / opts.intensity 是调用方从 agent.classify 拿到的结果；
 * 分类没跑成（比如还没探完）就留 null，页面上显示"未标注"，不猜一个情绪。
 */
function add(state, opts) {
  const o = opts || {};
  const v = validate(o.text);
  if (!v.ok) return v;
  const text = v.text;

  const ts = typeof o.ts === 'number' ? o.ts : Date.now();
  const post = {
    id: 'p_' + ts + '_' + hash(text),
    ts,
    text,
    mood: o.mood || null,
    intensity: typeof o.intensity === 'number' ? o.intensity : null,
    source: o.source || 'offline',
    closed: false,
    anon: anonId(ts, o.tz),
  };
  state.posts.push(post);
  return { ok: true, post };
}

/** 最新的在前；已收回的不进信息流，但留在库里等配额回收（core/store 的 dropClosedPosts）。 */
function feed(state, opts) {
  const o = opts || {};
  const rows = (state.posts || []).filter((p) => p && !p.closed);
  const list = o.mood && o.mood !== 'all' ? rows.filter((p) => p.mood === o.mood) : rows;
  return list.sort((a, b) => b.ts - a.ts);
}

function close(state, id) {
  const hit = (state.posts || []).find((p) => p.id === id);
  if (!hit) return false;
  hit.closed = true;
  return true;
}

/** 筛选条上的计数：只数没收回的，免得出现"焦虑 3"却只点得开 2 条。 */
function counts(state) {
  const out = {};
  (state.posts || []).forEach((p) => {
    if (!p || p.closed) return;
    const key = p.mood || 'none';
    out[key] = (out[key] || 0) + 1;
  });
  return out;
}

module.exports = { WORDS, maxLen: MAX_LEN, validate, anonId, add, feed, close, counts, dayKey };
