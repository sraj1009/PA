const m = require('../core/moodscore');

const NOW = Date.parse('2026-10-11T12:00:00Z');
const E = (daysAgo, text, mood, intensity) => ({
  ts: NOW - daysAgo * 864e5,
  text,
  mood,
  intensity,
});

test('returns exactly the six fixed axes, each within 0..100', () => {
  const r = m.axes([E(1, '去图书馆写作业', 'low', 0.5)], { days: 7, now: NOW });
  expect(r.map((x) => x.axis)).toEqual(['学业', '社交', '作息', '运动', '情绪稳定', '兴趣']);
  r.forEach((x) => expect(x.value).toBeGreaterThanOrEqual(0));
  r.forEach((x) => expect(x.value).toBeLessThanOrEqual(100));
});

test('window excludes events older than days', () => {
  // 计划里这条写的是 40 天前，可它同时要求 30 天窗口里 evidence 为 2——那条本身自相矛盾，
  // 按规格（7/30 天窗口）应当排除，所以改成 20 天前，让两个窗口真的能区分开。
  const ev = [E(2, '跑步五公里', 'joy', 0.6), E(20, '跑步五公里', 'joy', 0.6)];
  const w7 = m.axes(ev, { days: 7, now: NOW });
  const w30 = m.axes(ev, { days: 30, now: NOW });
  expect(w7.find((x) => x.axis === '运动').evidence).toBe(1);
  expect(w30.find((x) => x.axis === '运动').evidence).toBe(2);
});

test('the window edge is exclusive: 7 days ago is already outside a 7-day window', () => {
  const ev = [E(6, '和朋友聚餐', 'joy', 0.6), E(7, '和朋友聚餐', 'joy', 0.6)];
  const r = m.axes(ev, { days: 7, now: NOW });
  expect(r.find((x) => x.axis === '社交').evidence).toBe(1);
});

test('no events yields all-zero axes rather than invented numbers', () => {
  m.axes([], { days: 7, now: 1 }).forEach((x) => expect(x.value).toBe(0));
  m.axes([], { days: 7, now: 1 }).forEach((x) => expect(x.evidence).toBe(0));
});

test('情绪稳定 drops when polarity flips between consecutive days', () => {
  const stable = m.axes([E(1, '平静地自习', 'calm', 0.2), E(2, '平静地看书', 'calm', 0.2)], { days: 7, now: NOW });
  const volatile = m.axes([E(1, '开心极了', 'joy', 0.9), E(2, '难过死了', 'low', 0.9)], { days: 7, now: NOW });
  expect(stable.find((x) => x.axis === '情绪稳定').value)
    .toBeGreaterThan(volatile.find((x) => x.axis === '情绪稳定').value);
});

test('keyword buckets only count events that actually mention them', () => {
  const ev = [E(1, '今晚熬夜赶论文', 'anxious', 0.8), E(2, '和朋友聊天到半夜才睡', 'calm', 0.3)];
  const r = m.axes(ev, { days: 7, now: NOW });
  expect(r.find((x) => x.axis === '学业').evidence).toBe(1);
  expect(r.find((x) => x.axis === '社交').evidence).toBe(1);
  expect(r.find((x) => x.axis === '运动').evidence).toBe(0);
  expect(r.find((x) => x.axis === '作息').evidence).toBe(2);
});

test('more evidence and a brighter mood both raise an axis', () => {
  const few = m.axes([E(1, '打了一次篮球', 'low', 0.6)], { days: 7, now: NOW });
  const many = m.axes(
    [E(1, '打篮球', 'joy', 0.7), E(2, '跑步', 'joy', 0.6), E(3, '健身', 'calm', 0.4)],
    { days: 7, now: NOW },
  );
  expect(many.find((x) => x.axis === '运动').value)
    .toBeGreaterThan(few.find((x) => x.axis === '运动').value);
});

test('an event with no mood tag still counts as evidence', () => {
  const r = m.axes([E(1, '去上晚自习', null, undefined)], { days: 7, now: NOW });
  const study = r.find((x) => x.axis === '学业');
  expect(study.evidence).toBe(1);
  expect(study.value).toBeGreaterThan(0);
});

test('series is one point per day, oldest first, and never longer than the window', () => {
  const ev = [E(0, '早操跑步', 'joy', 0.5), E(1, '熬夜写作业', 'anxious', 0.7), E(2, '和朋友吃饭', 'joy', 0.4)];
  const s = m.series(ev, { days: 7, now: NOW });
  expect(s.length).toBeLessThanOrEqual(7);
  expect(s.length).toBe(3);
  expect(s.map((p) => p.n)).toEqual([1, 1, 1]);
  for (let i = 1; i < s.length; i += 1) expect(s[i].ts).toBeGreaterThan(s[i - 1].ts);
  s.forEach((p) => {
    expect(p.value).toBeGreaterThanOrEqual(0);
    expect(p.value).toBeLessThanOrEqual(100);
  });
});

test('an empty window gives an empty series instead of a flat fake line', () => {
  expect(m.series([], { days: 7, now: NOW })).toEqual([]);
});

test('polygon places six points, scaled by value, and closes them into edges', () => {
  const ax = [
    { axis: '学业', value: 100 },
    { axis: '社交', value: 50 },
    { axis: '作息', value: 0 },
    { axis: '运动', value: 25 },
    { axis: '情绪稳定', value: 75 },
    { axis: '兴趣', value: 60 },
  ];
  const p = m.polygon(ax, { size: 400, pad: 60 });
  expect(p.points.length).toBe(6);
  expect(p.edges.length).toBe(6);
  expect(p.points[0].r).toBeCloseTo(200 - 60, 6);
  expect(p.points[2].r).toBe(0);
  expect(p.points[2].x).toBeCloseTo(200, 6);
  expect(p.points[2].y).toBeCloseTo(200, 6);
  p.points.forEach((pt) => {
    expect(pt.x).toBeGreaterThanOrEqual(0);
    expect(pt.x).toBeLessThanOrEqual(400);
    expect(pt.y).toBeGreaterThanOrEqual(0);
    expect(pt.y).toBeLessThanOrEqual(400);
  });
});

test('a zero polygon sits exactly on the centre rather than disappearing', () => {
  const p = m.polygon(m.axes([], { days: 7, now: NOW }), { size: 300, pad: 40 });
  p.points.forEach((pt) => {
    expect(pt.x).toBeCloseTo(150, 6);
    expect(pt.y).toBeCloseTo(150, 6);
  });
});
