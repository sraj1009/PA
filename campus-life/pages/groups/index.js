const { store } = require('../../adapters/local');
const groups = require('../../core/groups');
const { INTERESTS, groups: pool } = require('../../data/groups');

Page({
  data: {
    chips: [],
    rows: [],
    picked: [],
    hits: 0,
    joinedCount: 0,
    hasProfile: false,
  },

  onLoad() { this.refresh(); },
  onShow() { this.refresh(); },

  refresh() {
    const state = store().read();
    const picked = state.profile.interests || [];
    const rows = groups.rank(state, pool);

    this.setData({
      chips: INTERESTS.map((t) => ({ t, on: picked.indexOf(t) >= 0 })),
      picked,
      rows: rows.map((r) => ({
        id: r.id,
        name: r.name,
        line: r.line,
        place: r.place || '',
        time: r.time || '',
        tagsText: (r.tags || []).join(' · '),
        reasons: r.reasons,
        matched: r.matched,
        matchText: r.matchText,
        joined: r.joined,
      })),
      hits: rows.filter((r) => r.matched).length,
      joinedCount: (state.favourites.groups || []).length,
      hasProfile: picked.length > 0,
    });
  },

  onToggle(e) {
    const t = e.currentTarget.dataset.t;
    store().write((d) => {
      const list = d.profile.interests || [];
      d.profile.interests = list.indexOf(t) >= 0 ? list.filter((x) => x !== t) : list.concat([t]);
    });
    this.refresh();
  },

  onClear() {
    store().write((d) => { d.profile.interests = []; });
    this.refresh();
  },

  onJoinToggle(e) {
    const id = e.currentTarget.dataset.id;
    const joined = (store().read().favourites.groups || []).indexOf(id) >= 0;
    store().write((d) => {
      if (joined) groups.leave(d, id);
      else groups.join(d, id, pool);
    });
    this.refresh();
    if (joined) {
      wx.showToast({ title: '已退出', icon: 'none' });
      return;
    }
    const hit = pool.find((g) => g.id === id);
    wx.showToast({ title: (hit ? hit.name : '社群') + ' 已加入（本机记录）', icon: 'none' });
  },
});
