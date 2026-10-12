const p = require('../core/planner');

const T = (id, o) => Object.assign({ id, title: id, priority: 2, durationMin: 60 }, o);
const W = [480, 1320]; // 08:00 - 22:00

test('earlier deadline wins when both fit', () => {
  const r = p.solve({
    tasks: [T('b', { deadline: 1100 }), T('a', { deadline: 900 })],
    now: 480, workWindow: W,
  });
  expect(r.slots.map((s) => s.taskId)).toEqual(['a', 'b']);
});

test('fixed commitments keep their exact slot and nothing overlaps them', () => {
  const r = p.solve({
    tasks: [T('class', { fixed: true, start: 600, end: 750 }), T('hw', { deadline: 1000, durationMin: 90 })],
    now: 480, workWindow: W,
  });
  const cls = r.slots.find((s) => s.taskId === 'class');
  expect([cls.start, cls.end]).toEqual([600, 750]);
  r.slots.filter((s) => s.taskId !== 'class').forEach((s) => {
    expect(s.start >= 750 || s.end <= 600).toBe(true);
  });
});

test('higher priority wins the window when only one task fits', () => {
  // Plan corrected during transcription: the original fixture asked a 240-min
  // task to beat a 100-min deadline, which is infeasible for any ordering.
  const r = p.solve({
    tasks: [T('low', { priority: 1, deadline: 1200, durationMin: 60 }), T('high', { priority: 3, deadline: 1300, durationMin: 700 })],
    now: 480, workWindow: W,
  });
  expect(r.slots.map((s) => s.taskId)).toEqual(['high']);
  expect(r.unscheduled).toEqual(['low']);
});

test('nothing is scheduled before now', () => {
  const r = p.solve({ tasks: [T('x', { durationMin: 60 })], now: 1000, workWindow: W });
  expect(r.slots[0].start).toBeGreaterThanOrEqual(1000);
});

test('a task whose deadline already passed is reported, never scheduled', () => {
  const r = p.solve({ tasks: [T('late', { deadline: 100 })], now: 500, workWindow: W });
  expect(r.slots).toEqual([]);
  expect(r.unscheduled).toEqual(['late']);
});

test('a task without a deadline is treated as due at the end of the window', () => {
  const r = p.solve({ tasks: [T('nodl')], now: 480, workWindow: W });
  expect(r.slots[0].end).toBeLessThanOrEqual(1320);
  expect(r.busyMin).toBe(60);
  expect(r.freeMin).toBe(840 - 60); // 08:00 - 22:00 is a 840-minute window
});

test('a task longer than the free window cannot be scheduled', () => {
  const r = p.solve({ tasks: [T('huge', { durationMin: 999 })], now: 480, workWindow: W });
  expect(r.unscheduled).toEqual(['huge']);
});

test('solve is deterministic for identical input', () => {
  const tasks = [T('a', { deadline: 900 }), T('b', { priority: 3, deadline: 1100 }), T('c', { fixed: true, start: 800, end: 900 })];
  const one = p.solve({ tasks, now: 480, workWindow: W });
  const two = p.solve({ tasks, now: 480, workWindow: W });
  expect(one.slots).toEqual(two.slots);
});
