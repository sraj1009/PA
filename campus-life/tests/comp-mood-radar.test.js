// miniprogram-simulate 的 querySelector 不跨自定义组件边界，所以雷达的六个标签
// 要直接把组件挂载起来测，而不是从页面节点往里查。
const { loadComponent, allText, count, simulate } = require('./helpers/render');
const moodscore = require('../core/moodscore');

jest.setTimeout(60000);

const NOW = Date.parse('2026-10-11T02:00:00Z');

function axesOf(rows, days) {
  const events = rows.map((r) => ({ ts: NOW - r.d * 86400000, text: r.t, mood: r.m }));
  return moodscore.axes(events, { days: days || 30, now: NOW });
}

test('six axes become six labelled corners of the polygon', async () => {
  const comp = loadComponent('mood-radar', { axes: axesOf([{ d: 1, t: '在图书馆自习到闭馆', m: 'calm' }]), size: 520 });
  await simulate.sleep(20);

  expect(count(comp, '.axis')).toBe(6);
  expect(allText(comp, '.axis-n')).toBe('学业 | 社交 | 作息 | 运动 | 情绪稳定 | 兴趣');
  expect(allText(comp, '.axis-v')).toBe('50 | 0 | 0 | 0 | 68 | 0');
  expect(count(comp, '.ring')).toBe(4);
  expect(count(comp, '.spoke')).toBe(6);
  expect(count(comp, '.edge')).toBe(6);
  expect(count(comp, '.dot')).toBe(6); // 0 也照实画在圆心，不藏起来假装没这一维
});

test('a fuller record set pushes that corner outwards', async () => {
  const comp = loadComponent('mood-radar', {
    axes: axesOf([
      { d: 1, t: '跑步五公里', m: 'joy' },
      { d: 2, t: '晨跑六公里', m: 'joy' },
      { d: 3, t: '操场打球', m: 'joy' },
    ]),
    size: 520,
  });
  await simulate.sleep(20);

  const sport = comp.data.points.find((p) => p.axis === '运动');
  const study = comp.data.points.find((p) => p.axis === '学业');
  expect(sport.value).toBe(84); // 40*3/5 + 60*1
  expect(study.value).toBe(0);
  expect(sport.r).toBeGreaterThan(study.r);
  expect(sport.r).toBeCloseTo(comp.data.maxR * 0.84, 6);
  expect(study.x).toBeCloseTo(comp.data.center, 6); // 零值缩在圆心，不是编出来的小圆
});

test('an empty axes list draws nothing rather than a hexagon of zeroes', async () => {
  const comp = loadComponent('mood-radar', { axes: [], size: 520 });
  await simulate.sleep(20);
  expect(count(comp, '.axis')).toBe(0);
  expect(count(comp, '.edge')).toBe(0);
  expect(comp.data.points).toEqual([]);
});
