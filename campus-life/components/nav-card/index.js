// 首页与内页之间的入口卡片。tabBar 里的页面必须走 switchTab，
// 用 navigateTo 打不开，所以入口类型由调用方标出来，而不是靠猜 url。
Component({
  properties: {
    title: { type: String, value: '' },
    desc: { type: String, value: '' },
    meta: { type: String, value: '' },
    url: { type: String, value: '' },
    tab: { type: Boolean, value: false },
    glyph: { type: String, value: '›' },
  },

  methods: {
    onGo() {
      const url = this.properties.url;
      if (!url) return;
      if (this.properties.tab) wx.switchTab({ url });
      else wx.navigateTo({ url });
    },
  },
});
