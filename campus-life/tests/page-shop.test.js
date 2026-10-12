// 店详情页（pages/shop/）此前从来没有被挂载过：它在 app.json 里，好店列表也跳得过去，
// 但没人证明过它渲染得出来。这里的用例全部从「列表上点一家店」那条真链接出发。
const {
  loadPage, tap, text, allText, count, classAt, wxState, resetWxState, simulate,
} = require('./helpers/render');
const { freeze, unfreeze } = require('./helpers/clock');
const { store, resetStore, storage } = require('../adapters/local');
const { KEY } = require('../core/schema');
const api = require('../core/shops');
const { ORIGIN, shops, cats } = require('../data/shops');
const agent = require('../agent/index');

jest.setTimeout(60000);

async function settle() {
  await simulate.sleep(30);
  await simulate.sleep(30);
}

async function openShop(id) {
  const page = await loadPage('shop', { id });
  await settle(); // onLoad 里 locate() 是异步的：等它把「按什么算的距离」定下来
  return page;
}

const ONE = shops.find((s) => s.id === 's01'); // 老门面馆：吃饭 / 07:00-21:00 / 人均 10-20

function rowValues(page) {
  return Array.prototype.slice.call(page.querySelectorAll('.mval')).map((el) => el.dom.textContent);
}

beforeEach(() => {
  resetWxState();
  resetStore();
  agent.reset();
  freeze(9, 0); // 上午九点：s01 的 07:00-21:00 一定算「营业中」
});

afterEach(() => {
  unfreeze();
});

test('the link on the shop list opens this page with the id it just showed', async () => {
  const list = await loadPage('shops');
  await settle();
  await tap(list, '.js-shop');
  expect(wxState().nav.length).toBe(1);
  expect(wxState().nav[0].type).toBe('navigateTo');
  const url = wxState().nav[0].url;
  expect(url.indexOf('/pages/shop/index?id=')).toBe(0);

  const id = url.split('=')[1];
  expect(shops.some((s) => s.id === id)).toBe(true);
  const detail = await openShop(id);
  expect(text(detail, '.h-name')).toBe(shops.find((s) => s.id === id).name);
  detail.detach();
  list.detach();
});

test('a known id renders the shop it was opened with, and says the data is sample data', async () => {
  const page = await openShop('s01');

  expect(text(page, '.h-name')).toBe(ONE.name);
  expect(text(page, '.h-desc')).toBe(ONE.desc);
  expect(classAt(page, '.badge', 0)).toContain('badge--on'); // 09:00 落在 07:00-21:00 里
  expect(text(page, '.badge')).toBe('营业中');
  expect(allText(page, '.mkey')).toBe('类别 | 营业时间 | 距离 | 消费 | 示例评分');

  const vals = rowValues(page);
  expect(vals[0]).toBe(cats.find((c) => c.id === 'meal').label);
  expect(vals[1]).toBe('07:00 - 21:00');
  expect(vals[3]).toBe('人均 10-20');
  expect(vals[4]).toBe('4.5 / 5.0');

  expect(allText(page, '.tip')).toContain('加辣提前说');
  expect(allText(page, '.tip')).toContain('午高峰 12:00 后要等位');
  expect(allText(page, '.chip')).toBe('面食 | 性价比');
  expect(text(page, '.local-only')).toContain('示例数据');
  page.detach();
});

// 距离这个数字在列表页会说清是按定位还是按示例坐标算的，详情页过去只给数字：
// 同一个数字必须有同一个出处说明。
test('the distance row names where the number came from', async () => {
  const page = await openShop('s01');
  const dist = rowValues(page)[2];
  expect(dist).toMatch(/^\d+(\.\d+)? (米|公里) · 按(当前定位|示例坐标)$/);
  expect(dist.split('· 按')[1]).toBe('当前定位'); // 测试替身给了授权与坐标
  expect(text(page, '.js-dist-src')).toBe('距离按当前定位计算');
  page.detach();
});

// 定位被拒是真实分支（手机上第一次一定会问）：这时距离只能来自示例坐标，屏幕上得写清楚。
test('without location permission the distance admits it came from the sample origin', async () => {
  wxState().denyLocation = true;
  const page = await openShop('s01');
  expect(text(page, '.js-dist-src')).toBe('距离按示例坐标计算');
  expect(rowValues(page)[2]).toContain('· 按示例坐标');
  page.detach();
});

test('收藏 writes the id to local storage, and tapping it again takes it back out', async () => {
  const page = await openShop('s01');
  expect(text(page, '.js-fav')).toContain('收藏这家店');

  await tap(page, '.js-fav');
  expect(storage.get(KEY).favourites.shops).toEqual(['s01']);
  expect(text(page, '.js-fav')).toContain('已收藏');
  expect(classAt(page, '.js-fav', 0)).toContain('btn--on');

  await tap(page, '.js-fav');
  expect(storage.get(KEY).favourites.shops).toEqual([]);
  expect(text(page, '.js-fav')).toContain('收藏这家店');
  page.detach();
});

test('附近同类 shows at most three other shops of the same category, nearest first', async () => {
  const page = await openShop('s01');
  expect(count(page, '.js-near')).toBe(3);
  const ids = page.instance.data.near.map((n) => n.id);

  expect(ids).not.toContain('s01');
  ids.forEach((id) => expect(shops.find((s) => s.id === id).cats).toContain('meal'));

  const d = (id) => api.haversineKm(ORIGIN, shops.find((s) => s.id === id));
  expect(ids.map(d)).toEqual(ids.map(d).sort((a, b) => a - b));

  wxState().nav.length = 0;
  await tap(page, '.js-near');
  expect(wxState().nav).toEqual([{ type: 'redirectTo', url: '/pages/shop/index?id=' + ids[0] }]);
  page.detach();
});

test('an id that is not in the sample data gets an explained blank, not a crash', async () => {
  const page = await openShop('s99');
  expect(count(page, '.hero')).toBe(0);
  expect(count(page, '.empty')).toBe(1);
  expect(text(page, '.empty')).toContain('没找到这家店');
  expect(text(page, '.empty')).toContain('示例数据');
  expect(count(page, '.js-fav')).toBe(0);
  page.detach();
});

test('返回列表 uses the call the page stack actually answers to', async () => {
  const page = await openShop('s01');
  await tap(page, '.js-back');
  expect(wxState().nav).toEqual([{ type: 'navigateBack', url: '' }]);
  page.detach();
});
