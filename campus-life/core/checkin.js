const DAY_MS = 86400000;
const DEDUPE_MIN = 60;

const dayIndex = (ts, tzOffsetMin) => Math.floor((ts + tzOffsetMin * 60000) / DAY_MS);

function latestFor(checkins, spotId) {
  let best = null;
  (checkins || []).forEach((ci) => {
    if (ci.spotId === spotId && (!best || ci.ts > best.ts)) best = ci;
  });
  return best;
}

/** Consecutive local days ending today. A missed day resets to 0. */
function streak(checkins, tzOffsetMin, now) {
  if (!checkins || !checkins.length) return 0;
  const days = new Set(checkins.map((ci) => dayIndex(ci.ts, tzOffsetMin)));
  const today = dayIndex(now, tzOffsetMin);
  if (!days.has(today)) return 0;
  let n = 0;
  for (let d = today; days.has(d); d -= 1) n += 1;
  return n;
}

function coverage(checkins, spots) {
  if (!spots || !spots.length) return 0;
  const seen = new Set((checkins || []).map((ci) => ci.spotId));
  const visited = spots.filter((s) => seen.has(s.id)).length;
  return visited / spots.length;
}

function canCheck(spot, last, now, windowMin) {
  const limit = (windowMin || DEDUPE_MIN) * 60000;
  if (!last) return { ok: true, reason: '' };
  const elapsed = now - last.ts;
  if (elapsed < 0) return { ok: false, reason: '打卡时间异常，请检查设备时间' };
  if (elapsed < limit) {
    return { ok: false, reason: Math.ceil((limit - elapsed) / 60000) + ' 分钟后可再次打卡' };
  }
  return { ok: true, reason: '' };
}

function list(spots, checkins) {
  return (spots || []).map((s) => {
    const last = latestFor(checkins, s.id);
    return Object.assign({}, s, { visited: !!last, lastAt: last ? last.ts : 0 });
  });
}

function groupByZone(rows) {
  const order = ['teach', 'sport', 'life', 'food'];
  const label = { teach: '教学区', sport: '运动区', life: '生活区', food: '餐饮区' };
  const buckets = {};
  rows.forEach((r) => {
    const z = r.zone || 'life';
    if (!buckets[z]) buckets[z] = [];
    buckets[z].push(r);
  });
  return Object.keys(buckets)
    .sort((a, b) => order.indexOf(a) - order.indexOf(b))
    .map((z) => ({ zone: z, label: label[z] || z, spots: buckets[z] }));
}

/** Mutates the draft in place; returns {ok, reason} so the page can toast. */
function doCheckin(draft, opts) {
  const { spots, spotId, ts, note } = opts;
  const spot = (spots || []).find((s) => s.id === spotId);
  if (!spot) return { ok: false, reason: '地点不存在' };
  const last = latestFor(draft.checkins, spotId);
  const verdict = canCheck(spot, last, ts);
  if (!verdict.ok) return verdict;
  draft.checkins.push({ id: 'ci_' + ts + '_' + spotId, spotId, ts, note: note || '' });
  return { ok: true, reason: '', spot, count: draft.checkins.length };
}

module.exports = { DAY_MS, DEDUPE_MIN, streak, coverage, canCheck, list, groupByZone, doCheckin, latestFor, dayIndex };
