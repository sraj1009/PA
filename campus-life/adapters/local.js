// Adapters bind the pure core to real device APIs. Keeping wx here is what
// lets every module under core/ stay wx-free and unit-testable.
const { createStore } = require('../core/store');
const { KEY } = require('../core/schema');

const storage = {
  get: (k) => wx.getStorageSync(k),
  set: (k, v) => wx.setStorageSync(k, v),
  remove: (k) => wx.removeStorageSync(k),
};

let singleton = null;
function store() {
  if (!singleton) singleton = createStore(storage, { key: KEY });
  return singleton;
}

// Tests clear device storage between cases; the cached snapshot must go too.
function resetStore() { singleton = null; }

/** Resolves to {lat,lng} or rejects; callers must handle denial. */
function locate() {
  // wx hands back latitude/longitude; the core only speaks {lat,lng} (haversine's shape),
  // so the conversion happens here rather than in every page.
  const toPoint = (res) => ({ lat: res.latitude, lng: res.longitude });
  const getLocation = (resolve, reject) =>
    wx.getLocation({ type: 'gcj02', success: (res) => resolve(toPoint(res)), fail: reject });

  return new Promise((resolve, reject) => {
    wx.getSetting({
      success: (res) => {
        if (res.authSetting['scope.userLocation']) {
          getLocation(resolve, reject);
        } else {
          wx.authorize({
            scope: 'scope.userLocation',
            success: () => getLocation(resolve, reject),
            fail: reject,
          });
        }
      },
      fail: reject,
    });
  });
}

/**
 * Promise wrapper over wx.request so the agent can await and time out.
 * A caller that brings its own success/fail (llm.js does — it needs a hard
 * timer of its own) is passed through untouched; overwriting those handlers
 * used to swallow every model response and leak an unhandled rejection.
 */
function request(options) {
  if (typeof options.success === 'function' || typeof options.fail === 'function') {
    return wx.request(options);
  }
  return new Promise((resolve, reject) => {
    wx.request(Object.assign({}, options, { success: resolve, fail: reject }));
  });
}

function tzOffsetMin() {
  return -new Date().getTimezoneOffset();
}

module.exports = { storage, store, resetStore, locate, request, tzOffsetMin };
