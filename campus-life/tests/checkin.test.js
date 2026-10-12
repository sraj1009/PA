const c = require('../core/checkin');

const D = (iso) => new Date(iso).getTime();
const spots = [
  { id: 'lib', name: '图书馆', zone: 'teach', lat: 30.51, lng: 114.42 },
  { id: 'gym', name: '体育馆', zone: 'sport', lat: 30.52, lng: 114.43 },
];

test('streak counts consecutive days', () => {
  const ci = [
    { spotId: 'lib', ts: D('2026-10-10T09:00:00Z') },
    { spotId: 'gym', ts: D('2026-10-11T09:00:00Z') },
  ];
  expect(c.streak(ci, 0, D('2026-10-11T12:00:00Z'))).toBe(2);
});

test('streak resets after a missed day', () => {
  const ci = [{ spotId: 'lib', ts: D('2026-10-08T09:00:00Z') }];
  expect(c.streak(ci, 0, D('2026-10-11T12:00:00Z'))).toBe(0);
});

test('streak buckets by local day, not UTC midnight', () => {
  // 16:30Z is 00:30 the next day in UTC+8: these are two consecutive LOCAL days,
  // but in UTC the newest one lands on "today" only for the +8 reader.
  const ci = [
    { spotId: 'lib', ts: D('2026-10-09T16:30:00Z') },
    { spotId: 'gym', ts: D('2026-10-10T16:30:00Z') },
  ];
  const now = D('2026-10-11T02:00:00Z');
  expect(c.streak(ci, 480, now)).toBe(2); // local Oct 10 + Oct 11
  expect(c.streak(ci, 0, now)).toBe(0);   // UTC days Oct 9 + Oct 10, none today
});

test('coverage is visited spots over total spots', () => {
  expect(c.coverage([{ spotId: 'lib', ts: 1 }], spots)).toBeCloseTo(0.5);
  expect(c.coverage([], spots)).toBe(0);
  expect(c.coverage([{ spotId: 'lib', ts: 1 }, { spotId: 'gym', ts: 1 }], spots)).toBeCloseTo(1);
});

test('a second check-in inside the dedupe window is refused with a reason', () => {
  const last = { spotId: 'lib', ts: D('2026-10-11T09:00:00Z') };
  const soon = c.canCheck(spots[0], last, D('2026-10-11T09:30:00Z'));
  expect(soon.ok).toBe(false);
  expect(soon.reason).toContain('30');
  expect(c.canCheck(spots[0], last, D('2026-10-11T11:00:00Z')).ok).toBe(true);
  expect(c.canCheck(spots[0], null, D('2026-10-11T09:00:00Z')).ok).toBe(true);
});

test('list marks visited spots and keeps the newest check-in', () => {
  const rows = c.list(spots, [
    { spotId: 'lib', ts: D('2026-10-01T09:00:00Z') },
    { spotId: 'lib', ts: D('2026-10-09T09:00:00Z') },
  ]);
  const lib = rows.find((r) => r.id === 'lib');
  expect(lib.visited).toBe(true);
  expect(lib.lastAt).toBe(D('2026-10-09T09:00:00Z'));
  expect(rows.find((r) => r.id === 'gym').visited).toBe(false);
});

test('doCheckin appends exactly one entry and is idempotent on refusal', () => {
  const draft = { checkins: [] };
  c.doCheckin(draft, { spots, spotId: 'lib', ts: D('2026-10-11T09:00:00Z') });
  const second = c.doCheckin(draft, { spots, spotId: 'lib', ts: D('2026-10-11T09:10:00Z') });
  expect(draft.checkins.length).toBe(1);
  expect(second.ok).toBe(false);
});
