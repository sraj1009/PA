const { store, locate, tzOffsetMin } = require('../../adapters/local');
const checkin = require('../../core/checkin');
const fmt = require('../../core/format');
const { spots } = require('../../data/spots');

Page({
  data: {
    zones: [],
    streak: 0,
    coveragePct: '0%',
    coverageRatio: 0,
    total: 0,
    visited: 0,
    gpsOn: false,
    lastLabel: '',
    empty: true,
  },

  onLoad() {
    this.refresh();
    // GPS is an enhancement only: denial or failure must never block a check-in.
    locate()
      .then((c) => { this.coords = c; this.setData({ gpsOn: true }); })
      .catch(() => { this.coords = null; this.setData({ gpsOn: false }); });
  },

  onShow() { this.refresh(); },

  refresh() {
    const tz = tzOffsetMin();
    const now = Date.now();
    const state = store().read();
    const rows = checkin.list(spots, state.checkins);
    const ratio = checkin.coverage(state.checkins, spots);

    this.setData({
      zones: checkin.groupByZone(rows).map((g) => ({
        zone: g.zone,
        label: g.label,
        spots: g.spots.map((s) => ({
          id: s.id,
          name: s.name,
          tip: s.tip,
          visited: s.visited,
          when: s.visited ? fmt.ago(s.lastAt, now, tz) : '',
        })),
      })),
      streak: checkin.streak(state.checkins, tz, now),
      coverageRatio: ratio,
      coveragePct: fmt.pct(ratio),
      total: spots.length,
      visited: rows.filter((r) => r.visited).length,
      empty: state.checkins.length === 0,
      lastLabel: state.checkins.length ? fmt.stamp(state.checkins[state.checkins.length - 1].ts, tz) : '',
    });
  },

  onCheck(e) {
    const id = e.currentTarget.dataset.id;
    const ts = Date.now();
    let result = null;
    store().write((draft) => {
      result = checkin.doCheckin(draft, { spots, spotId: id, ts, coords: this.coords || null });
    });
    this.refresh();
    if (!result.ok) {
      wx.showToast({ title: result.reason, icon: 'none' });
      return;
    }
    const spot = spots.find((s) => s.id === id);
    wx.showToast({ title: (spot ? spot.name : '已打卡') + ' 打卡成功', icon: 'success' });
  },
});
