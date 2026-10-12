// Pre-seeds global.wx BEFORE miniprogram-simulate is required.
// definition.js:29 does Object.assign(api, global.wx), so these real
// implementations win over simulate's no-op mocks.
const state = {
  store: new Map(),
  nav: [],
  toasts: [],
  requests: [],
  quotaFailTimes: 0,
  location: { latitude: 30.5152, longitude: 114.4308 },
  denyLocation: false,
};

function write(key, value) {
  if (state.quotaFailTimes > 0) {
    state.quotaFailTimes -= 1;
    throw new Error('exceed storage quota');
  }
  state.store.set(key, JSON.parse(JSON.stringify(value)));
}

global.__wxState = state;
global.wx = {
  setStorageSync: write,
  getStorageSync: (k) => (state.store.has(k) ? state.store.get(k) : ''),
  removeStorageSync: (k) => state.store.delete(k),
  getStorageInfoSync: () => ({ keys: [...state.store.keys()], currentSize: 1, limitSize: 10240 }),

  navigateTo: (o) => state.nav.push({ type: 'navigateTo', url: o.url }),
  redirectTo: (o) => state.nav.push({ type: 'redirectTo', url: o.url }),
  switchTab: (o) => state.nav.push({ type: 'switchTab', url: o.url }),
  navigateBack: () => state.nav.push({ type: 'navigateBack', url: '' }),

  showToast: (o) => state.toasts.push(o.title),
  showModal: (o) => o.success && o.success({ confirm: true, cancel: false }),
  showLoading: () => {},
  hideLoading: () => {},

  request: (o) => {
    state.requests.push(o);
    // Default: transport failure, so unconfigured tests exercise the offline path.
    setTimeout(() => (o.fail ? o.fail({ errMsg: 'request:fail mock' }) : null), 0);
  },

  getSetting: (o) => o.success && o.success({ authSetting: state.denyLocation ? {} : { 'scope.userLocation': true } }),
  authorize: (o) => (state.denyLocation ? o.fail({ errMsg: 'authorize:fail' }) : o.success({})),
  getLocation: (o) =>
    state.denyLocation ? o.fail({ errMsg: 'getLocation:fail auth deny' }) : o.success({ ...state.location }),

  createSelectorQuery: () => ({
    in: () => ({ select: () => ({ boundingClientRect: (cb) => cb && cb({ left: 0, top: 0, width: 300, height: 300 }), scrollOffset: (cb) => cb && cb({ scrollTop: 0 }) }), selectAll: () => ({ fields: (f, cb) => cb && cb([]) }) }),
    select: () => ({ boundingClientRect: (cb) => cb && cb({ left: 0, top: 0, width: 300, height: 300 }) }),
    selectViewport: () => ({ scrollOffset: (cb) => cb && cb({ scrollTop: 0 }) }),
    exec: (cb) => cb && cb([]),
  }),
  canvasToTempFilePath: (o) => o.success && o.success({ tempFilePath: '' }),
  nextTick: (cb) => setTimeout(cb, 0),
  getSystemInfoSync: () => ({ windowWidth: 375, windowHeight: 667, pixelRatio: 2, platform: 'devtools', safeArea: { bottom: 667 } }),
  setNavigationBarTitle: () => {},
};
