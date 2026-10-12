// Deterministic day planner. Pure minutes-of-day (0..1440), no clock, no model,
// no randomness: the same input always yields the same schedule, which is what
// makes this testable and what keeps the LLM out of the scheduling decision.

function overlaps(a, b) {
  return a.start < b.end && b.start < a.end;
}

function gapsFrom(blocks, from, to) {
  const sorted = blocks.slice().sort((x, y) => x.start - y.start);
  const out = [];
  let cursor = from;
  sorted.forEach((b) => {
    const s = Math.max(b.start, from);
    const e = Math.min(b.end, to);
    if (s > cursor) out.push({ start: cursor, end: s });
    cursor = Math.max(cursor, e);
  });
  if (cursor < to) out.push({ start: cursor, end: to });
  return out;
}

function solve(input) {
  const tasks = input.tasks || [];
  const win = input.workWindow || [0, 1440];
  const wStart = win[0];
  const wEnd = win[1];
  const from = Math.max(input.now == null ? wStart : input.now, wStart);

  const fixed = tasks
    .filter((t) => t.fixed && t.start != null && t.end != null)
    .map((t) => ({ taskId: t.id, title: t.title, start: Math.max(t.start, from), end: Math.min(t.end, wEnd) }))
    .filter((b) => b.end > b.start)
    .sort((a, b) => a.start - b.start);

  const blocks = fixed.map((b) => ({ start: b.start, end: b.end }));
  const slots = fixed.slice();

  const order = tasks
    .map((t, i) => ({ t, i }))
    .filter((x) => !x.t.fixed)
    .sort((a, b) => {
      const pr = (b.t.priority || 2) - (a.t.priority || 2);
      if (pr !== 0) return pr;
      const dl = (a.t.deadline == null ? wEnd : a.t.deadline) - (b.t.deadline == null ? wEnd : b.t.deadline);
      if (dl !== 0) return dl;
      return a.i - b.i;
    });

  const unscheduled = [];

  order.forEach(({ t }) => {
    const dur = t.durationMin || 30;
    const due = t.deadline == null ? wEnd : t.deadline;
    let placed = false;

    const gaps = gapsFrom(blocks, from, wEnd);
    for (let g = 0; g < gaps.length && !placed; g += 1) {
      const gap = gaps[g];
      const start = Math.max(gap.start, from);
      const latestEnd = Math.min(gap.end, due);
      if (latestEnd - start >= dur) {
        const slot = { taskId: t.id, title: t.title, start, end: start + dur };
        // A lower-priority task may already own this gap; keep the earlier start.
        if (blocks.some((b) => overlaps({ start, end: start + dur }, b))) continue;
        blocks.push({ start, end: start + dur });
        slots.push(slot);
        placed = true;
      }
    }
    if (!placed) unscheduled.push(t.id);
  });

  slots.sort((a, b) => a.start - b.start || a.end - b.end);
  const busyMin = blocks.reduce((n, b) => n + (b.end - b.start), 0);

  return {
    slots,
    unscheduled,
    busyMin,
    freeMin: Math.max(0, wEnd - from - busyMin),
  };
}

/** Minutes-of-day -> "09:30". Planner works in minutes, so it formats its own. */
function mmhh(min) {
  const m = ((min % 1440) + 1440) % 1440;
  const h = Math.floor(m / 60);
  const r = m % 60;
  return (h < 10 ? '0' : '') + h + ':' + (r < 10 ? '0' : '') + r;
}

function label(slots) {
  return slots.map((s) => mmhh(s.start) + ' - ' + mmhh(s.end) + ' ' + s.title);
}

module.exports = { solve, mmhh, label, gapsFrom };
