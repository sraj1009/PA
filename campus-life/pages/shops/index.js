const { store, save, locate } = require('../../adapters/local');
const api = require('../../core/shops');
const { ORIGIN, cats, shops } = require('../../data/shops');

const SORTS = [
  { key: 'distance', label: '最近' },
  { key: 'rating', label: '评分高' },
  { key: 'price', label: '更便宜' },
];
const RANGES = [
  { value: -1, label: '不限' },
  { value: 0.5, label: '500 米内' },
  { value: 1, label: '1 公里内' },
];

function hourLabel(h) {
  if (h === 24) return '24:00';
  const m = Math.floor(h);
  return (m < 10 ? '0' : '') + m + ':00';
}

function priceLabel(p) {
  return '¥'.repeat((p || 0) + 1);
}

// WXML only gets plain data, so the selected state is folded into the chip list.
function catView(selected) {
  return cats.map((c) => ({ id: c.id, label: c.label, on: selected.indexOf(c.id) >= 0 }));
}

function catTextOf(shop) {
  return shop.cats.map((c) => (cats.find((x) => x.id === c) || { label: c }).label).join(' · ');
}

Page({
  data: {
    q: '',
    cats: catView([]),
    selected: [],
    openOnly: false,
    sort: 'distance',
    sorts: SORTS,
    ranges: RANGES,
    range: -1,
    rangeLabel: '不限',
    list: [],
    total: 0,
    empty: false,
    favCount: 0,
    gpsOn: false,
    distSource: '示例坐标',
  },

  onLoad() {
    // 定位只影响距离数字，拿不到就退回校内基准点，列表照常渲染。
    locate()
      .then((c) => { this.coords = c; this.setData({ gpsOn: true, distSource: '当前定位' }); })
      .catch(() => { this.coords = null; this.setData({ gpsOn: false, distSource: '示例坐标' }); })
      .then(() => this.refresh());
    this.refresh();
  },

  onShow() { this.refresh(); },

  view(s, favs) {
    return {
      id: s.id,
      name: s.name,
      desc: s.desc,
      catText: catTextOf(s),
      dist: s.dist,
      distText: s.dist < 1 ? Math.round(s.dist * 1000) + ' 米' : s.dist.toFixed(2) + ' 公里',
      ratingText: s.rating.toFixed(1),
      priceText: priceLabel(s.price),
      hours: hourLabel(s.open[0]) + ' - ' + hourLabel(s.open[1]),
      openNow: api.isOpen(s, new Date().getHours()),
      fav: favs.indexOf(s.id) >= 0,
    };
  },

  refresh() {
    const state = store().read();
    const favs = state.favourites.shops || [];
    const origin = this.coords || ORIGIN;
    const hour = new Date().getHours();

    const annotated = shops.map((s) =>
      Object.assign({}, s, {
        dist: Math.round(api.haversineKm(origin, s) * 100) / 100,
        catText: catTextOf(s),
      }),
    );
    const picked = api.filter(annotated, {
      q: this.data.q,
      cats: this.data.selected,
      openNow: this.data.openOnly,
      maxDist: this.data.range < 0 ? null : this.data.range,
      at: hour,
    });
    const sorted = api.sortBy(picked, this.data.sort);

    this.setData({
      cats: catView(this.data.selected),
      list: sorted.map((s) => this.view(s, favs)),
      total: shops.length,
      empty: sorted.length === 0,
      favCount: favs.length,
    });
  },

  onSearch(e) { this.setData({ q: e.detail.value }); this.refresh(); },
  onToggleCat(e) {
    const id = e.currentTarget.dataset.id;
    const selected = this.data.selected.indexOf(id) >= 0
      ? this.data.selected.filter((x) => x !== id)
      : this.data.selected.concat([id]);
    this.setData({ selected });
    this.refresh();
  },
  onToggleOpen() {
    this.setData({ openOnly: !this.data.openOnly });
    this.refresh();
  },
  onSort(e) { this.setData({ sort: e.currentTarget.dataset.k }); this.refresh(); },
  onRange(e) {
    const v = Number(e.currentTarget.dataset.v);
    const hit = RANGES.find((r) => r.value === v) || RANGES[0];
    this.setData({ range: v, rangeLabel: hit.label });
    this.refresh();
  },
  onReset() {
    this.setData({ q: '', selected: [], openOnly: false, range: -1, rangeLabel: '不限', sort: 'distance' });
    this.refresh();
  },

  onFav(e) {
    const id = e.currentTarget.dataset.id;
    if (!save((d) => { d.favourites.shops = api.toggleFav(d.favourites.shops, id); }).ok) return; // 没落进本机就不重画星标
    this.refresh();
  },

  onOpen(e) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({ url: '/pages/shop/index?id=' + id });
  },
});
