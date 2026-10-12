const { loadPage, tap, tapN, input, text, allText, count, classAt, wxState, resetWxState, simulate } = require('./helpers/render');
const { freeze, unfreeze } = require('./helpers/clock');
const { store, resetStore, storage } = require('../adapters/local');
const { KEY } = require('../core/schema');
const { shops } = require('../data/shops');

jest.setTimeout(60000);

async function openList() {
  const page = await loadPage('shops');
  await simulate.sleep(20); // locate() settles across microtasks before the second refresh
  return page;
}

beforeEach(() => {
  resetWxState();
  resetStore();
  freeze(9, 0);
});

afterEach(() => {
  unfreeze();
});

test('the list renders every sample shop and labels the data as a sample', async () => {
  const page = await openList();
  expect(count(page, '.shop')).toBe(20);
  expect(count(page, '.empty')).toBe(0);
  expect(text(page, '.local-only')).toContain('示例数据');
  expect(text(page, '.local-only')).toContain('内容仅存于本机');
  expect(text(page, '.sumline')).toContain('共 20 / 20 家');
});

test('the default sort is by distance, so the nearest shop is on top', async () => {
  const page = await openList();
  expect(text(page, '.s-name')).toContain('咖啡馆（校内）');
  expect(text(page, '.dist')).toBe('140 米');
});

test('a category chip filters the list and stacks into a union', async () => {
  const page = await openList();
  await tapN(page, '.chip', 1); // 咖啡饮品
  expect(count(page, '.shop')).toBe(4);
  expect(classAt(page, '.chip', 1)).toContain('chip--on');

  await tapN(page, '.chip', 0); // 吃饭
  expect(count(page, '.shop')).toBe(9);

  await tapN(page, '.chip', 1); // 取消咖啡饮品
  expect(count(page, '.shop')).toBe(5);
});

test('search matches names and descriptions, not just categories', async () => {
  const page = await openList();
  await input(page, '.js-q', '面');
  expect(count(page, '.shop')).toBe(1);
  expect(text(page, '.s-name')).toContain('老门面馆');

  await input(page, '.js-q', '奶茶');
  expect(count(page, '.shop')).toBe(1);
  expect(text(page, '.s-name')).toContain('茶饮实验室');

  await input(page, '.js-q', '咖啡');
  expect(count(page, '.shop')).toBe(4);
});

test('营业中 keeps only shops open at the current hour', async () => {
  const page = await openList();
  expect(count(page, '.badge--off')).toBe(7);

  await tap(page, '.js-open');
  expect(count(page, '.shop')).toBe(13);
  expect(count(page, '.badge--on')).toBe(13);
  expect(count(page, '.badge--off')).toBe(0);
});

test('a 500 米 range drops the far end of the catalogue', async () => {
  const page = await openList();
  await tapN(page, '.js-range', 1);
  expect(count(page, '.shop')).toBe(16);
  expect(text(page, '.sumline')).toContain('距离按当前定位计算');
});

test('no matches offers a reset that restores the full list', async () => {
  const page = await openList();
  await input(page, '.js-q', '不存在的店名');
  expect(count(page, '.empty')).toBe(1);
  expect(count(page, '.shop')).toBe(0);

  await tap(page, '.js-reset');
  expect(count(page, '.shop')).toBe(20);
  expect(text(page, '.sumline')).toContain('共 20 / 20 家');
});

test('favouriting persists to favourites.shops, marks the star, and does not navigate', async () => {
  const page = await openList();
  await tap(page, '.js-fav');

  expect(storage.get(KEY).favourites.shops).toEqual(['s06']);
  expect(classAt(page, '.star', 0)).toContain('star--on');
  expect(text(page, '.star')).toContain('★');
  expect(wxState().nav.length).toBe(0);
  expect(text(page, '.sumline')).toContain('已收藏 1');
});

test('a favourite survives a remount', async () => {
  const page = await openList();
  await tap(page, '.js-fav');

  const again = await openList();
  expect(classAt(again, '.star', 0)).toContain('star--on');
  expect(count(again, '.star--on')).toBe(1);
});

test('tapping a card opens the detail page for that shop', async () => {
  const page = await openList();
  await tap(page, '.js-shop');

  expect(wxState().nav.length).toBe(1);
  const url = wxState().nav[0].url;
  expect(url.indexOf('/pages/shop/index?id=')).toBe(0);
  expect(shops.some((s) => s.id === url.split('=')[1])).toBe(true);
});

test('the detail page reads ?id=, shows the sample label, and lists nearby same-category shops', async () => {
  const page = await loadPage('shop', { id: 's01' });
  await simulate.sleep(20);

  expect(text(page, '.h-name')).toContain('老门面馆');
  expect(text(page, '.local-only')).toContain('示例数据');
  expect(count(page, '.mrow')).toBe(5);
  expect(allText(page, '.mrow')).toContain('营业时间');
  expect(allText(page, '.mrow')).toContain('类别');
  expect(allText(page, '.mrow')).toContain('440 米');
  expect(count(page, '.tip')).toBe(2);
  expect(count(page, '.js-near')).toBe(3);
  expect(text(page, '.near-n')).toContain('食堂三楼自选餐');
  expect(text(page, '.badge')).toContain('营业中');
});

test('收藏 on the detail page writes the same storage key as the list', async () => {
  const page = await loadPage('shop', { id: 's03' });
  await simulate.sleep(20);
  expect(text(page, '.js-fav')).toContain('☆');

  await tap(page, '.js-fav');
  expect(storage.get(KEY).favourites.shops).toEqual(['s03']);
  expect(text(page, '.js-fav')).toContain('★ 已收藏');
});

test('the detail page navigates to a nearby shop without stacking pages', async () => {
  const page = await loadPage('shop', { id: 's01' });
  await simulate.sleep(20);
  await tap(page, '.js-near');
  expect(wxState().nav[0].type).toBe('redirectTo');
  expect(wxState().nav[0].url).toContain('/pages/shop/index?id=s04');

  await tap(page, '.js-back');
  expect(wxState().nav[1].type).toBe('navigateBack');
});

test('an unknown id degrades to an empty state instead of a blank page', async () => {
  const page = await loadPage('shop', { id: 'nope' });
  await simulate.sleep(20);
  expect(count(page, '.empty')).toBe(1);
  expect(count(page, '.hero')).toBe(0);
  expect(text(page, '.empty-t')).toContain('没找到这家店');
});
