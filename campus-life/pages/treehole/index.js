const { store, tzOffsetMin } = require('../../adapters/local');
const posts = require('../../core/posts');
const mood = require('../../core/mood');
const fmt = require('../../core/format');
const agent = require('../../agent/index');

const FILTERS = [{ value: 'all', label: '全部' }].concat(
  mood.ORDER.map((k) => ({ value: k, label: mood.LABELS[k] })),
);

function modeText(m) {
  return m === 'llm' ? '本地模型' : '离线模式';
}

Page({
  data: {
    draft: '',
    filter: 'all',
    filters: FILTERS,
    counts: {},
    total: 0,
    rows: [],
    empty: true,
    busy: false,
    modeText: '离线模式',
  },

  onLoad() {
    this.refresh();
    // 探测结果决定标注文字；没探完之前先按离线写，宁可少报也不虚报。
    agent.ready().then(() => this.setData({ modeText: modeText(agent.mode()) }));
  },

  onShow() { this.refresh(); },

  refresh() {
    const tz = tzOffsetMin();
    const now = Date.now();
    const state = store().read();
    const rows = posts.feed(state, { mood: this.data.filter });

    this.setData({
      rows: rows.map((p) => ({
        id: p.id,
        text: p.text,
        anon: p.anon,
        moodValue: p.mood || 'none',
        moodText: mood.label(p.mood),
        when: fmt.ago(p.ts, now, tz),
        taggedBy: p.source === 'llm' ? '本地模型标注' : '离线词库标注',
      })),
      counts: posts.counts(state),
      total: posts.feed(state).length,
      empty: rows.length === 0,
      modeText: modeText(agent.mode()),
    });
  },

  onDraft(e) { this.setData({ draft: e.detail.value }); },

  onFilter(e) {
    this.setData({ filter: e.currentTarget.dataset.v });
    this.refresh();
  },

  async onPublish() {
    const text = this.data.draft.trim();
    if (!text) {
      wx.showToast({ title: '先写点什么再发', icon: 'none' });
      return;
    }
    if (this.data.busy) return;
    this.setData({ busy: true });

    // 分类只经过 agent/index：模型不可达时它自己降级，树洞照样能发出去。
    const tag = await agent.classify(text);
    const ts = Date.now();
    store().write((d) => {
      posts.add(d, {
        text,
        ts,
        tz: tzOffsetMin(),
        mood: tag.mood,
        intensity: tag.intensity,
        source: tag.source,
      });
    });

    this.setData({ draft: '', busy: false });
    this.refresh();
    wx.showToast({ title: '已发出 · ' + modeText(tag.source) + '标注', icon: 'none' });
  },

  onClose(e) {
    const id = e.currentTarget.dataset.id;
    wx.showModal({
      title: '收回这条？',
      content: '信息流里不再显示，心情雷达也不再算它。记录只在你本机。',
      success: (res) => {
        if (!res.confirm) return;
        store().write((d) => { posts.close(d, id); });
        this.refresh();
        wx.showToast({ title: '已收回', icon: 'success' });
      },
    });
  },
});
