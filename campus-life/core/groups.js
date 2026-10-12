// 社群匹配纯逻辑层。排序沿用 agent/offline 的关键词 + IDF + 共现算法：
// 匹配从不走大模型，排名和理由必须可复现，所以 core 直接依赖那个纯函数，
// 而不是绕经 agent/index（那层会碰 wx）。
const { match } = require('../agent/offline');

function byId(pool, id) {
  return (pool || []).find((g) => g.id === id) || null;
}

/** 命中就写清对上几个标签；没命中就直说没对上，绝不编一个百分比当社交证明。 */
function matchText(reasons) {
  if (!reasons.length) return '没对上你写的兴趣';
  return '对上 ' + reasons.length + ' 个兴趣标签';
}

function rank(state, pool) {
  const profile = (state && state.profile) || { interests: [] };
  const joined = ((state && state.favourites) || {}).groups || [];
  const docs = pool || [];

  return match(profile, docs).map((r) => {
    const src = byId(docs, r.id) || {};
    const reasons = r.reasons || [];
    return {
      id: r.id,
      name: r.name,
      line: src.line || '',
      tags: (r.tags || []).slice(),
      score: r.score,
      reasons: reasons.slice(),
      matched: reasons.length > 0,
      matchText: matchText(reasons),
      joined: joined.indexOf(r.id) >= 0,
    };
  });
}

function join(state, id, pool) {
  if (pool && !byId(pool, id)) return { ok: false, reason: '这个社群不在本机样本里' };
  const favs = state.favourites.groups || [];
  if (favs.indexOf(id) < 0) favs.push(id);
  state.favourites.groups = favs;
  return { ok: true, id };
}

function leave(state, id) {
  state.favourites.groups = (state.favourites.groups || []).filter((x) => x !== id);
  return { ok: true, id };
}

/** 加入的社群决定模拟同伴聊天的话题池；没加入就是空，聊天层据此说明它不了解你。 */
function joined(state, pool) {
  const ids = ((state && state.favourites) || {}).groups || [];
  return (pool || []).filter((g) => ids.indexOf(g.id) >= 0);
}

module.exports = { rank, join, leave, joined };
