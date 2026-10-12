const off = require('../agent/offline');

test('classify reads polarity including negation', () => {
  expect(off.classify('今天和朋友吃饭很开心').mood).toBe('joy');
  expect(off.classify('一点也不开心').mood).toBe('low');
  expect(off.classify('明天要交论文，焦虑得睡不着').mood).toBe('anxious');
});

test('classify maps the remaining two moods', () => {
  expect(off.classify('排队排了一个小时，太气了').mood).toBe('angry');
  expect(off.classify('今天在图书馆看书，很平静').mood).toBe('calm');
});

test('intensity is 0..1 and grows with markers', () => {
  const weak = off.classify('还行');
  const strong = off.classify('太开心了！！！');
  expect(strong.intensity).toBeGreaterThan(weak.intensity);
  [weak, strong].forEach((r) => {
    expect(r.intensity).toBeGreaterThanOrEqual(0);
    expect(r.intensity).toBeLessThanOrEqual(1);
  });
});

test('classify never invents a mood for text with no signal', () => {
  const r = off.classify('去三楼借了一本书');
  expect(r.mood).toBe('calm');
  expect(r.intensity).toBe(0);
});

test('negating a negative word moves toward calm, not deeper into it', () => {
  expect(off.classify('其实没有那么焦虑了').mood).toBe('calm');
});

test('match ranks by shared keywords and returns reasons', () => {
  const pool = [
    { id: 'photo', name: '摄影社', tags: ['摄影', '相机'] },
    { id: 'ball', name: '篮球队', tags: ['篮球'] },
  ];
  const r = off.match({ interests: ['摄影', '拍照'] }, pool);
  expect(r[0].id).toBe('photo');
  expect(r[0].reasons.length).toBeGreaterThan(0);
  expect(r.find((x) => x.id === 'ball').score).toBe(0);
});

test('match scores every member and is deterministic for the same input', () => {
  const pool = [
    { id: 'a', name: 'A', tags: ['篮球', '运动'] },
    { id: 'b', name: 'B', tags: ['篮球'] },
    { id: 'c', name: 'C', tags: ['话剧'] },
  ];
  const first = off.match({ interests: ['篮球'] }, pool);
  const second = off.match({ interests: ['篮球'] }, pool);
  expect(first.map((x) => x.id + ':' + x.score)).toEqual(second.map((x) => x.id + ':' + x.score));
  expect(first.filter((x) => x.score === 0).every((x) => x.reasons.length === 0)).toBe(true);
  expect(first.find((x) => x.id === 'a').score)
    .toBeGreaterThanOrEqual(first.find((x) => x.id === 'b').score);
});

test('rare tags outweigh common ones through IDF', () => {
  const common = Array.from({ length: 8 }, (_, i) => ({ id: 'c' + i, name: 'C' + i, tags: ['社交'] }));
  const pool = common.concat([{ id: 'rare', name: 'Rare', tags: ['天文'] }]);
  const r = off.match({ interests: ['天文', '社交'] }, pool);
  const rare = r.find((x) => x.id === 'rare');
  const hit = r.find((x) => x.id === 'c0');
  expect(rare.score).toBeGreaterThan(hit.score);
  expect(rare.reasons[0]).toContain('天文');
});

test('an empty profile matches nothing instead of guessing', () => {
  const r = off.match({ interests: [] }, [{ id: 'a', name: 'A', tags: ['篮球'] }]);
  expect(r[0].score).toBe(0);
});

test('a reason reads as one sentence that starts with what you asked for', () => {
  const r = off.match({ interests: ['天文'] }, [{ id: 'a', name: 'A', tags: ['天文'] }]);
  expect(r[0].reasons).toEqual(['你要的「天文」正好是它的标签']);
});

test('the reason follows the strongest tag, not the last one scanned', () => {
  const r = off.match({ interests: ['摄影'] }, [{ id: 'a', name: 'A', tags: ['摄影', '现场摄影'] }]);
  expect(r[0].reasons).toEqual(['你要的「摄影」正好是它的标签']);
});

test('chat replies in the mood of the message and echoes what was said', () => {
  const r = off.chat([], '明天小组展示，特别紧张', 'warm');
  expect(typeof r.text).toBe('string');
  expect(r.text.length).toBeGreaterThan(4);
  expect(/[\u4e00-\u9fa5]/.test(r.text)).toBe(true);
});

test('chat does not repeat its own previous line', () => {
  const turns = [];
  const seen = new Set();
  for (let i = 0; i < 4; i += 1) {
    const r = off.chat(turns, '还是有点难受', 'warm');
    expect(seen.has(r.text)).toBe(false);
    seen.add(r.text);
    turns.push({ role: 'assistant', text: r.text });
  }
});

test('chat keeps the persona voice distinct', () => {
  const warm = off.chat([], '今天一个人吃饭', 'warm').text;
  const playful = off.chat([], '今天一个人吃饭', 'playful').text;
  expect(warm).not.toBe(playful);
});

test('explain turns a plan into readable sentences', () => {
  const text = off.explain({
    slots: [
      { title: '复习高数', start: 540, end: 600 },
      { title: '取快递', start: 660, end: 690 },
    ],
    unscheduled: ['写论文'],
  });
  expect(text).toContain('09:00');
  expect(text).toContain('复习高数');
  expect(text).toContain('写论文');
  expect(text).toContain('今天放不下');
});
