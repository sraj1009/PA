App({
  // 引擎状态只以 agent/index 的 mode() 为准：这里再存一份一定会和 mode-badge 打架。
  globalData: {
    windowWidth: 375,
  },
  onLaunch() {
    const info = wx.getSystemInfoSync();
    this.globalData.windowWidth = info.windowWidth;
  },
});
