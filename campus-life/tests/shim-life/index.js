// 测试夹具，不是应用页面：它只为 tests/shim-lifecycle.test.js 提供一份真实的 Page() 定义，
// 用来证明 helpers/shim.js 那座 Page→Component 的桥是通的。
Page({
  data: { marks: [] },

  onLoad(query) {
    this.setData({ marks: this.data.marks.concat('load:' + ((query && query.who) || '')) });
  },

  onShow() { this.setData({ marks: this.data.marks.concat('show') }); },

  onReady() { this.setData({ marks: this.data.marks.concat('ready') }); },

  onHide() { this.setData({ marks: this.data.marks.concat('hide') }); },

  onUnload() { this.setData({ marks: this.data.marks.concat('unload') }); },

  onTap() { this.setData({ marks: this.data.marks.concat('tap') }); },

  go() { wx.switchTab({ url: '/pages/planner/index' }); },
});
