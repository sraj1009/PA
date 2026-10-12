// Registers a Page() options object as a simulate-renderable component.
// miniprogram-simulate only knows Component(); real pages must stay Page(),
// so tests bridge the two and keep page lifecycle semantics.
// miniprogram-simulate must be required after tests/setup.js seeds global.wx.
const simulate = require('miniprogram-simulate');

const PAGE_LIFECYCLE = [
  'onLoad', 'onShow', 'onReady', 'onHide', 'onUnload',
  'onPullDownRefresh', 'onReachBottom', 'onShareAppMessage', 'onPageScroll', 'onTabItemTap',
];

let installed = false;

function install() {
  if (installed) return;
  installed = true;

  global.Page = function Page(options) {
    if (typeof Component !== 'function') {
      throw new Error('Component is not a function - simulate did not inject it; the Page shim cannot be used');
    }
    const opts = options || {};
    const methods = {};
    Object.keys(opts).forEach((k) => {
      if (typeof opts[k] === 'function' && PAGE_LIFECYCLE.indexOf(k) < 0) methods[k] = opts[k];
    });

    Component({
      properties: { launchQuery: { type: Object, value: {} } },
      data: Object.assign({}, opts.data),
      methods,
      lifetimes: {
        attached() {
          // Page handlers may read this.route / this.options in real code.
          this.route = this.route || '';
          this.options = this.properties.launchQuery || {};
          if (opts.onLoad) opts.onLoad.call(this, this.options);
          if (opts.onReady) Promise.resolve().then(() => opts.onReady.call(this));
        },
        detached() {
          if (opts.onUnload) opts.onUnload.call(this);
        },
      },
      pageLifetimes: {
        show() { if (opts.onShow) opts.onShow.call(this); },
        hide() { if (opts.onHide) opts.onHide.call(this); },
      },
    });
  };

  if (!global.getApp) global.getApp = () => global.__app || { globalData: {} };
}

module.exports = { install, PAGE_LIFECYCLE, simulate };
