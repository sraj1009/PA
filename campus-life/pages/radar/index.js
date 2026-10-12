const { store, tzOffsetMin } = require('../../adapters/local');
const moodscore = require('../../core/moodscore');
const mood = require('../../core/mood');
const fmt = require('../../core/format');

const WINDOWS = [7, 30];

// 雷达只吃用户自己记下的两类内容：心情打卡 + 树洞（已由 agent 分好类）。
// 打卡的 intensity 是用户没填过的字段，所以保持 null，让算法只按 mood 的极性算。
function events(state) {
  const manual = (state.moods || []).map((m) => ({
    ts: m.ts,
    mood: m.mood,
    text: m.text || '',
    from: '心情打卡',
  }));
  const holes = (state.posts || [])
    .filter((p) => !p.closed) // 收回的一条不再参与计算，页面上也不该再算它
    .map((p) => ({
      ts: p.ts,
      mood: p.mood,
      text: p.text || '',
      from: '树洞',
    }));
  return manual
    .concat(holes)
    .filter((e) => typeof e.ts === 'number')
    .sort((a, b) => a.ts - b.ts);
}

Page({
  data: {
    days: 7,
    windows: WINDOWS,
    axes: [],
    series: [],
    records: [],
    count: 0,
    hasData: false,
    moodPick: 'calm',
    moodOptions: mood.ORDER.map((k) => ({ value: k, label: mood.LABELS[k] })),
    note: '',
  },

  onLoad() { this.refresh(); },
  onShow() { this.refresh(); },

  refresh() {
    const tz = tzOffsetMin();
    const now = Date.now();
    const state = store().read();
    const ev = events(state);
    const inWindow = moodscore.within(ev, this.data.days, now);

    this.setData({
      axes: moodscore.axes(ev, { days: this.data.days, now: now, tz: tz }),
      series: moodscore.series(ev, { days: this.data.days, now: now, tz: tz }).map((p) => ({
        id: p.ts,
        value: p.value,
        count: p.n,
        day: fmt.day(p.ts, tz),
      })),
      records: ev
        .slice()
        .reverse()
        .slice(0, 8)
        .map((r) => ({
          id: r.ts + '-' + r.from,
          text: r.text || '只记了心情，没写为什么',
          moodText: mood.label(r.mood),
          when: fmt.ago(r.ts, now, tz),
          from: r.from,
        })),
      count: inWindow.length,
      hasData: inWindow.length > 0,
    });
  },

  onDays(e) {
    this.setData({ days: Number(e.currentTarget.dataset.days) });
    this.refresh();
  },

  onPickMood(e) {
    this.setData({ moodPick: e.currentTarget.dataset.v });
  },

  onNote(e) {
    this.setData({ note: e.detail.value });
  },

  onSave() {
    const text = this.data.note.trim();
    const ts = Date.now();
    store().write((d) => {
      d.moods.push({ id: 'm_' + ts, ts: ts, mood: this.data.moodPick, intensity: null, text: text });
    });
    this.setData({ note: '' });
    this.refresh();
    wx.showToast({ title: '已记下 ' + mood.label(this.data.moodPick), icon: 'success' });
  },
});
