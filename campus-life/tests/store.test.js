const { createStore, QuotaError } = require('../core/store');
const { schema, KEY } = require('../core/schema');
const { memoryStorage } = require('./helpers/memory-storage');

test('read() fills missing keys from the empty schema', () => {
  const storage = memoryStorage({ [KEY]: { version: 1, posts: [{ id: 'p1' }] } });
  const s = createStore(storage);
  expect(s.read().posts).toEqual([{ id: 'p1' }]);
  expect(s.read().checkins).toEqual([]);
  expect(s.read().favourites).toEqual({ shops: [], groups: [] });
});

test('write() persists so a new store instance sees it (app restart)', () => {
  const st = memoryStorage();
  createStore(st).write((d) => { d.checkins.push({ id: 'c1' }); });
  const again = createStore(st).read();
  expect(again.checkins.map((c) => c.id)).toEqual(['c1']);
});

test('write() does not mutate the previously read object', () => {
  const s = createStore(memoryStorage());
  const before = s.read();
  s.write((d) => { d.posts.push({ id: 'p9' }); });
  expect(before.posts).toEqual([]);
});

test('corrupt storage is replaced by the empty schema rather than crashing', () => {
  const st = memoryStorage({ [KEY]: 'not-an-object' });
  const s = createStore(st);
  expect(s.read().version).toBe(schema().version);
});

test('quota errors prune oldest chat messages, then closed posts, then surface', () => {
  const seed = {
    ...schema(),
    chats: [{ id: 'a', closed: false, messages: Array.from({ length: 50 }, (_, i) => ({ id: i })) }],
    posts: [{ id: 'p1', closed: true, ts: 1 }, { id: 'p2', closed: false, ts: 9 }],
  };
  let calls = 0;
  const boom = memoryStorage({ [KEY]: seed });
  const realSet = boom.set;
  boom.set = (k, v) => {
    calls += 1;
    if (calls <= 2) throw new Error('exceed storage quota');
    realSet(k, v);
  };
  const s = createStore(boom);
  expect(() => s.write((d) => { d.checkins.push({ id: 'x' }); })).not.toThrow();
  const saved = boom.get(KEY);
  expect(saved.chats[0].messages.length).toBeLessThan(50);
  expect(calls).toBe(3);
});

test('quota failure that survives pruning raises QuotaError', () => {
  const always = memoryStorage();
  always.set = () => { throw new Error('exceed storage quota'); };
  const s = createStore(always);
  let err = null;
  try { s.write((d) => { d.posts.push({ id: 'z' }); }); } catch (e) { err = e; }
  expect(err).toBeInstanceOf(QuotaError);
});
