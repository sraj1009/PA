const posts = require('../core/posts');
const { schema } = require('../core/schema');

const DAY = 86400000;
const T = (daysAgo) => Date.parse('2026-10-11T02:00:00Z') - daysAgo * DAY;
const S = () => schema();

test('the feed is newest first', () => {
  const s = S();
  posts.add(s, { text: '旧的', ts: T(3) });
  posts.add(s, { text: '新的', ts: T(1) });
  posts.add(s, { text: '中间的', ts: T(2) });
  expect(posts.feed(s).map((p) => p.text)).toEqual(['新的', '中间的', '旧的']);
});

test('the feed filters by mood and "all" keeps everything', () => {
  const s = S();
  posts.add(s, { text: '论文交不上', ts: T(1), mood: 'anxious' });
  posts.add(s, { text: '操场跑了五公里', ts: T(2), mood: 'joy' });
  posts.add(s, { text: '随便坐一会儿', ts: T(3), mood: 'calm' });

  expect(posts.feed(s, { mood: 'joy' }).map((p) => p.text)).toEqual(['操场跑了五公里']);
  expect(posts.feed(s, { mood: 'all' }).length).toBe(3);
  expect(posts.feed(s).length).toBe(3);
  expect(s.posts.length).toBe(3); // 读一次不该改动存档
});

test('empty text is refused and nothing lands in storage', () => {
  const s = S();
  const r = posts.add(s, { text: '   ', ts: T(1) });
  expect(r.ok).toBe(false);
  expect(s.posts).toEqual([]);

  const missing = posts.add(s, { ts: T(1) });
  expect(missing.ok).toBe(false);
  expect(s.posts).toEqual([]);
});

test('the anonymous handle is stable for one day and changes the next day', () => {
  const same1 = posts.anonId(T(1) + 3600000, 0);
  const same2 = posts.anonId(T(1) + 7 * 3600000, 0);
  const nextDay = posts.anonId(T(0), 0);

  expect(same1).toBe(same2); // 同一天回来，代号不该变
  expect(nextDay).not.toBe(same1);
  expect(same1).toMatch(/同学\d{3}$/);

  const ids = [];
  for (let d = 0; d < 60; d += 1) ids.push(posts.anonId(T(d), 0));
  expect(new Set(ids).size).toBeGreaterThan(20); // 不是"匿名同学123"这种只有一个数的摆设
});

test('the handle never depends on the device or the author', () => {
  const evening = Date.parse('2026-10-10T20:00:00Z');
  expect(posts.anonId(evening, 0)).not.toBe(posts.anonId(evening, 480)); // 东八区已经是第二天
  expect(posts.anonId(evening, 0)).toBe(posts.anonId(evening + 3 * 3600000, 0));
  const a = posts.anonId(evening, 0);
  expect(a.indexOf('wx')).toBe(-1);
  expect(a).not.toMatch(/[0-9a-f]{8,}/); // 不是把设备号截了一段当昵称
});

test('a post keeps whatever the classifier said, or an honest null', () => {
  const s = S();
  const tagged = posts.add(s, { text: 'emo 了', ts: T(1), mood: 'low', intensity: 0.8, source: 'llm' });
  const plain = posts.add(s, { text: '今天天气不错', ts: T(2) });

  expect(tagged.post.mood).toBe('low');
  expect(tagged.post.intensity).toBe(0.8);
  expect(tagged.post.source).toBe('llm');
  expect(plain.post.mood).toBe(null);
  expect(plain.post.intensity).toBe(null);
  expect(plain.post.source).toBe('offline');
});

test('closing a post takes it out of the feed without inventing a delete', () => {
  const s = S();
  posts.add(s, { text: '想收回的一条', ts: T(1), mood: 'angry' });
  posts.add(s, { text: '留下的一条', ts: T(2), mood: 'joy' });

  const ok = posts.close(s, s.posts.find((p) => p.text === '想收回的一条').id);
  expect(ok).toBe(true);
  expect(posts.feed(s).map((p) => p.text)).toEqual(['留下的一条']);
  expect(s.posts.length).toBe(2); // 还在库里，等配额回收（core/store 的 dropClosedPosts）
  expect(posts.close(s, 'nope')).toBe(false);
});

test('two posts in the same millisecond still get different ids', () => {
  const s = S();
  const ts = T(1);
  posts.add(s, { text: '甲', ts });
  posts.add(s, { text: '乙', ts });
  expect(s.posts[0].id).not.toBe(s.posts[1].id);
  expect(posts.feed(s).length).toBe(2);
});
