// 心情雷达的算法层：只吃用户自己写下的记录（打卡 + 树洞分类结果），
// 输出六个固定维度的 0..100 数值和证据条数。没有数据就是 0，绝不补一个"看起来正常"的数。
const DAY_MS = 86400000;

const AXES = ['学业', '社交', '作息', '运动', '情绪稳定', '兴趣'];

const KEYWORDS = {
  学业: ['课', '作业', '考试', '论文', '图书馆', '自习', '答辩', '汇报', '展示', '实验', '复习', '签到', '学分', '导师', '小组', '成绩', '报名', '截止', 'ddl'],
  社交: ['朋友', '聊天', '聚餐', '社团', '室友', '约会', '聚会', '交流', '活动', '认识', '同学', '一起', '组队', '谈心', '吵架', '孤立'],
  作息: ['睡觉', '睡', '熬夜', '熬', '失眠', '早起', '午睡', '作息', '凌晨', '半夜', '起床', '困', '睡眠', '通宵', '晚睡'],
  运动: ['跑步', '晨跑', '健身', '打球', '篮球', '足球', '羽球', '乒乓球', '骑行', '瑜伽', '操场', '游泳', '散步', '运动', '锻炼', '拉伸', '步数'],
  兴趣: ['摄影', '相机', '拍照', '音乐', '听歌', '电影', '展览', '看展', '画画', '游戏', '吉他', '舞蹈', '看书', '读书', '小说', '动漫', '播客', '手工', '乐器', '编程', '模型'],
};

// 情绪极性：用来把"发生了什么"和"感觉怎么样"合成一个 0..100 的读数。
const POLARITY = { joy: 1, calm: 0.4, anxious: -0.4, angry: -0.6, low: -1 };

function clamp100(x) {
  return Math.max(0, Math.min(100, Math.round(x)));
}

function within(events, days, now) {
  const from = now - days * DAY_MS;
  return (events || []).filter((e) => e && typeof e.ts === 'number' && e.ts > from && e.ts <= now);
}

function mentions(text, list) {
  const t = String(text || '');
  return list.some((k) => t.indexOf(k) >= 0);
}

function valence01(rows) {
  const tagged = rows.filter((r) => POLARITY[r.mood] != null);
  if (!tagged.length) return 0.5; // 只记了事、没标情绪：按中性算，不猜
  const mean = tagged.reduce((n, r) => n + POLARITY[r.mood], 0) / tagged.length;
  return (mean + 1) / 2;
}

function localDay(ts, tz) {
  return Math.floor((ts + (tz || 0) * 60000) / DAY_MS);
}

/** 情绪稳定看的是相邻日子的极性有没有反复翻面，而不是关键词。 */
function stability(rows, tz) {
  if (!rows.length) return { value: 0, evidence: 0 };
  const byDay = new Map();
  rows.slice().sort((a, b) => a.ts - b.ts).forEach((r) => {
    const p = POLARITY[r.mood];
    if (p == null) return;
    byDay.set(localDay(r.ts, tz), Math.sign(p));
  });
  const signs = [...byDay.values()].filter((s) => s !== 0);

  let flips = 0;
  let intervals = 0;
  for (let i = 1; i < signs.length; i += 1) {
    intervals += 1;
    if (signs[i] !== signs[i - 1]) flips += 1;
  }
  const steady = intervals === 0 ? 1 : 1 - flips / intervals;
  return {
    value: clamp100(40 * (Math.min(rows.length, 5) / 5) + 60 * steady),
    evidence: rows.length,
  };
}

function axes(events, options) {
  const o = options || {};
  const rows = within(events, o.days == null ? 7 : o.days, o.now == null ? Date.now() : o.now);
  const tz = o.tz || 0;

  return AXES.map((axis) => {
    if (axis === '情绪稳定') {
      const s = stability(rows, tz);
      return { axis, value: s.value, evidence: s.evidence, label: '近 ' + (o.days == null ? 7 : o.days) + ' 天心情起伏' };
    }
    const hits = rows.filter((r) => mentions(r.text, KEYWORDS[axis]));
    if (!hits.length) return { axis, value: 0, evidence: 0, label: '还没有相关记录' };
    const value = clamp100(40 * (Math.min(hits.length, 5) / 5) + 60 * valence01(hits));
    return {
      axis,
      value,
      evidence: hits.length,
      label: hits.length + ' 条相关记录',
    };
  });
}

/** 趋势线只铺有数据的日子：空日子留在轴上会被读成"那天心情是 0"，那是编造。 */
function series(events, options) {
  const o = options || {};
  const rows = within(events, o.days == null ? 7 : o.days, o.now == null ? Date.now() : o.now);
  const tz = o.tz || 0;
  const buckets = new Map();

  rows
    .slice()
    .sort((a, b) => a.ts - b.ts)
    .forEach((r) => {
      const key = localDay(r.ts, tz);
      if (!buckets.has(key)) buckets.set(key, []);
      buckets.get(key).push(r);
    });

  return [...buckets.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([, list]) => ({
      ts: list[0].ts,
      n: list.length,
      value: clamp100(40 * (Math.min(list.length, 5) / 5) + 60 * valence01(list)),
    }));
}

const TAU = Math.PI * 2;

/** 六边形雷达的几何：纯计算，好让测试能验证，也让 WXML 只负责画。 */
function polygon(rows, options) {
  const o = options || {};
  const size = o.size || 480;
  const pad = o.pad == null ? 64 : o.pad;
  const center = size / 2;
  const maxR = Math.max(0, center - pad);
  const list = rows || [];

  const points = list.map((r, i) => {
    const angle = -Math.PI / 2 + (TAU * i) / (list.length || 1);
    const rad = (maxR * Math.max(0, Math.min(100, r.value || 0))) / 100;
    return {
      axis: r.axis,
      value: r.value || 0,
      angle,
      r: rad,
      x: center + rad * Math.cos(angle),
      y: center + rad * Math.sin(angle),
      labelX: center + (maxR + pad * 0.45) * Math.cos(angle),
      labelY: center + (maxR + pad * 0.45) * Math.sin(angle),
    };
  });

  const edges = points.map((p, i) => {
    const q = points[(i + 1) % points.length];
    return {
      x: p.x,
      y: p.y,
      len: Math.sqrt((q.x - p.x) ** 2 + (q.y - p.y) ** 2),
      angle: (Math.atan2(q.y - p.y, q.x - p.x) * 180) / Math.PI,
    };
  });

  const spokes = points.map((p) => ({
    x: center,
    y: center,
    len: maxR,
    angle: (p.angle * 180) / Math.PI,
  }));

  return { size, center, maxR, points, edges, spokes };
}

module.exports = { AXES, KEYWORDS, POLARITY, DAY_MS, axes, series, polygon, mentions, within };
