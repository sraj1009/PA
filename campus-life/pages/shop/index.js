const { store, locate } = require('../../adapters/local');
const api = require('../../core/shops');
const { ORIGIN, cats, shops } = require('../../data/shops');

const PRICE_WORDS = ['免费为主', '人均 10-20', '人均 20-40', '人均 40 以上'];

function hourLabel(h) {
  if (h === 24) return '24:00';
  const m = Math.floor(h);
  return (m < 10 ? '0' : '') + m + ':00';
}

function distText(d) {
  return d < 1 ? Math.round(d * 1000) + ' 米' : d.toFixed(2) + ' 公里';
}

function catTextOf(shop) {
  return shop.cats.map((c) => (cats.find((x) => x.id === c) || { label: c }).label).join(' · ');
}

Page({
  data: {
    shop: null,
    found: false,
    rows: [],
    near: [],
    fav: false,
    distSource: '示例坐标',
  },

  onLoad(query) {
    this.shopId = (query || {}).id || '';
    locate()
      .then((c) => { this.coords = c; this.setData({ distSource: '当前定位' }); })
      .catch(() => { this.coords = null; this.setData({ distSource: '示例坐标' }); })
      .then(() => this.refresh());
    this.refresh();
  },

  refresh() {
    const state = store().read();
    const favs = state.favourites.shops || [];
    const origin = this.coords || ORIGIN;
    const withDist = (s) =>
      Object.assign({}, s, {
        dist: Math.round(api.haversineKm(origin, s) * 100) / 100,
        catText: catTextOf(s),
      });

    const raw = shops.find((s) => s.id === this.shopId);
    if (!raw) {
      this.setData({ found: false, shop: null, rows: [], near: [] });
      return;
    }
    const s = withDist(raw);
    const hour = new Date().getHours();
    const dist = distText(s.dist);

    this.setData({
      found: true,
      fav: favs.indexOf(s.id) >= 0,
      shop: {
        id: s.id,
        name: s.name,
        desc: s.desc,
        tips: s.tips,
        tags: s.tags,
        catText: s.catText,
        ratingText: s.rating.toFixed(1),
        priceText: PRICE_WORDS[s.price] || '价格未填写',
        hours: hourLabel(s.open[0]) + ' - ' + hourLabel(s.open[1]),
        openNow: api.isOpen(s, hour),
        distText: dist,
      },
      rows: [
        { k: '类别', v: s.catText },
        { k: '营业时间', v: hourLabel(s.open[0]) + ' - ' + hourLabel(s.open[1]) },
        { k: '距离', v: dist },
        { k: '消费', v: PRICE_WORDS[s.price] || '未填写' },
        { k: '示例评分', v: s.rating.toFixed(1) + ' / 5.0' },
      ],
      near: api.sortBy(
        api
          .filter(shops.map(withDist), { cats: raw.cats })
          .filter((x) => x.id !== s.id),
        'distance',
      ).slice(0, 3).map((x) => ({
        id: x.id,
        name: x.name,
        catText: x.catText,
        distText: distText(x.dist),
      })),
    });
  },

  onFav() {
    const id = this.shopId;
    store().write((d) => { d.favourites.shops = api.toggleFav(d.favourites.shops, id); });
    this.refresh();
  },

  onNear(e) {
    wx.redirectTo({ url: '/pages/shop/index?id=' + e.currentTarget.dataset.id });
  },

  onBack() {
    wx.navigateBack();
  },
});
