const groups = require('../core/groups');
const { schema } = require('../core/schema');

const POOL = [
  { id: 'g01', name: '摄影社', tags: ['摄影', '相机', '街拍'], line: '每周一次外拍，器材不限。' },
  { id: 'g02', name: '夜跑团', tags: ['跑步', '夜跑', '操场'], line: '晚上八点在集合。' },
  { id: 'g03', name: '读书会', tags: ['读书', '小说', '分享'], line: '一个月读完一本。' },
  { id: 'g04', name: '篮球队', tags: ['篮球', '训练', '比赛'], line: '系队招新人。' },
  { id: 'g05', name: '电影社', tags: ['电影', '剪辑', '摄影'], line: '放映加拆解。' },
];

const S = (interests) => {
  const s = schema();
  s.profile.interests = interests || [];
  return s;
};

test('ranking is deterministic for a fixed profile', () => {
  const a = groups.rank(S(['摄影']), POOL);
  const b = groups.rank(S(['摄影']), POOL);
  expect(a.map((g) => g.id)).toEqual(b.map((g) => g.id));
  expect(a[0].id).toBe('g01'); // 三个标签里有两个能对上，最先出现的那条赢
  expect(a[0].score).toBeGreaterThan(0);
});

test('hits carry a reason and zero-score rows carry none', () => {
  const rows = groups.rank(S(['跑步', '读书']), POOL);
  rows.forEach((g) => {
    if (g.score > 0) {
      expect(g.reasons.length).toBeGreaterThan(0);
      expect(typeof g.reasons[0]).toBe('string');
    } else {
      expect(g.reasons).toEqual([]);
    }
  });
  expect(rows.find((g) => g.id === 'g02').reasons.join('')).toContain('跑步');
  expect(rows.find((g) => g.id === 'g04').score).toBe(0);
  expect(rows.find((g) => g.id === 'g04').reasons).toEqual([]);
});

test('no interests means no invented matches', () => {
  const rows = groups.rank(S([]), POOL);
  expect(rows.length).toBe(POOL.length);
  rows.forEach((g) => {
    expect(g.score).toBe(0);
    expect(g.reasons).toEqual([]);
    expect(g.matched).toBe(false);
  });
});

test('every pool row survives ranking, best-matching first', () => {
  const rows = groups.rank(S(['摄影', '电影']), POOL);
  expect(rows.map((g) => g.id).sort()).toEqual(['g01', 'g02', 'g03', 'g04', 'g05']);
  expect(rows[0].id).toBe('g05'); // 两个兴趣都对上的，盖过只对上一个的
  expect(rows[0].matched).toBe(true);
  expect(rows[0].score).toBeGreaterThan(rows[1].score);
});

test('join records the group id and is idempotent', () => {
  const s = S(['跑步']);
  groups.join(s, 'g02');
  groups.join(s, 'g02');
  expect(s.favourites.groups).toEqual(['g02']);

  groups.join(s, 'g03');
  expect(s.favourites.groups).toEqual(['g02', 'g03']);
});

test('an unknown id cannot be joined', () => {
  const s = S([]);
  expect(groups.join(s, 'nope', POOL).ok).toBe(false);
  expect(s.favourites.groups).toEqual([]);
});

test('leave removes only the one group', () => {
  const s = S([]);
  groups.join(s, 'g01');
  groups.join(s, 'g02');
  groups.leave(s, 'g01');
  expect(s.favourites.groups).toEqual(['g02']);
  groups.leave(s, 'g99');
  expect(s.favourites.groups).toEqual(['g02']);
});

test('ranking marks the rows the user already joined', () => {
  const s = S(['跑步']);
  groups.join(s, 'g02');
  const rows = groups.rank(s, POOL);
  expect(rows.find((g) => g.id === 'g02').joined).toBe(true);
  expect(rows.find((g) => g.id === 'g01').joined).toBe(false);
});

test('ranking does not reorder or damage the pool', () => {
  const before = JSON.stringify(POOL);
  groups.rank(S(['读书']), POOL);
  expect(JSON.stringify(POOL)).toBe(before);
});

test('scores are not turned into a fake percentage of anything', () => {
  const rows = groups.rank(S(['摄影']), POOL);
  rows.forEach((g) => {
    expect(g.matchText).toBeTruthy();
    expect(String(g.matchText)).not.toMatch(/%/);
  });
  expect(rows[0].matchText).toContain('标签');
});
