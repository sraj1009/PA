const s = require('../core/shops');

const L = [
  { id: 'a', name: 'A', cats: ['coffee'], dist: 0.4, rating: 4.6, price: 2, open: [8, 22] },
  { id: 'b', name: 'B', cats: ['meal'], dist: 1.2, rating: 4.1, price: 1, open: [17, 23] },
  { id: 'c', name: 'C', cats: ['study'], dist: 2.5, rating: 4.9, price: 0, open: [9, 18] },
];

test('category filter, then distance sort', () => {
  expect(s.sortBy(s.filter(L, { cats: ['coffee', 'study'] }), 'distance').map((x) => x.id)).toEqual(['a', 'c']);
});

test('openNow uses the clock, not the array index', () => {
  expect(s.filter(L, { openNow: true, at: 20 }).map((x) => x.id)).toEqual(['a', 'b']);
});

test('text search matches name and category, case-insensitively', () => {
  expect(s.filter(L, { q: 'COFFEE' }).map((x) => x.id)).toEqual(['a']);
});

test('text search also matches the human category labels the page attaches', () => {
  const labelled = [
    Object.assign({}, L[0], { catText: '咖啡饮品' }),
    Object.assign({}, L[1], { catText: '吃饭' }),
  ];
  expect(s.filter(labelled, { q: '咖啡' }).map((x) => x.id)).toEqual(['a']);
});

test('all four criteria are conjunctive', () => {
  const got = s.filter(L, { q: 'b', cats: ['meal'], openNow: true, at: 18, maxDist: 2 });
  expect(got.map((x) => x.id)).toEqual(['b']);
  expect(s.filter(L, { q: 'b', maxDist: 1 }).map((x) => x.id)).toEqual([]);
  expect(s.filter(L, { cats: [], openNow: false }).map((x) => x.id)).toEqual(['a', 'b', 'c']);
});

test('a shop open across midnight is still open at 01:00', () => {
  const late = [{ id: 'n', name: '夜宵', cats: ['meal'], dist: 0.3, rating: 4.0, price: 1, open: [22, 3] }];
  expect(s.filter(late, { openNow: true, at: 1 }).map((x) => x.id)).toEqual(['n']);
  expect(s.filter(late, { openNow: true, at: 12 }).map((x) => x.id)).toEqual([]);
});

test('sorting by rating and price is in the direction the labels promise', () => {
  expect(s.sortBy(L, 'rating').map((x) => x.id)).toEqual(['c', 'a', 'b']);
  expect(s.sortBy(L, 'price').map((x) => x.id)).toEqual(['c', 'b', 'a']);
  expect(L.map((x) => x.id)).toEqual(['a', 'b', 'c']);
});

test('haversine is sane', () => {
  expect(s.haversineKm({ lat: 30.5, lng: 114.4 }, { lat: 30.51, lng: 114.4 })).toBeGreaterThan(0.8);
  expect(s.haversineKm({ lat: 30.5, lng: 114.4 }, { lat: 30.5, lng: 114.4 })).toBe(0);
});

test('toggleFav adds, removes, and never duplicates', () => {
  let favs = [];
  favs = s.toggleFav(favs, 'a');
  expect(favs).toEqual(['a']);
  favs = s.toggleFav(favs, 'a');
  expect(favs).toEqual([]);
  favs = s.toggleFav(s.toggleFav(favs, 'a'), 'b');
  expect(favs).toEqual(['a', 'b']);
  expect(s.toggleFav(['a'], 'a')).toEqual([]);
});
