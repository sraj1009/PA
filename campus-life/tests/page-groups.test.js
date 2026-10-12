const {
  loadPage, tap, tapN, text, allText, html, count, classAt,
  wxState, resetWxState, simulate,
} = require('./helpers/render');
const { store, resetStore, storage } = require('../adapters/local');
const { KEY } = require('../core/schema');

jest.setTimeout(60000);

async function openGroups(query) {
  const page = await loadPage('groups', query || {});
  await simulate.sleep(20);
  return page;
}

// 兴趣标签的顺序就是 data/groups.js 里的 INTERESTS：0 摄影、1 跑步、4 电影。
const I = { photo: 0, run: 1, film: 4 };

beforeEach(() => {
  resetWxState();
  resetStore();
});

test('before any interest is picked the page lists nothing and says why', async () => {
  const page = await openGroups();

  expect(count(page, '.js-interest')).toBe(12);
  expect(count(page, '.row')).toBe(0);
  expect(count(page, '.zero')).toBe(1);
  expect(text(page, '.zero')).toContain('还没勾兴趣');
  expect(text(page, '.zero')).toContain('编出来的排名不是推荐');
  expect(text(page, '.badge')).toBe('本地算法');
  expect(text(page, '.local-only')).toContain('内容仅存于本机');
  expect(text(page, '.local-only')).toContain('示例数据');
  expect(storage.get(KEY)).toBe(''); // 光打开页面不该写任何东西
});

test('picking an interest writes the profile and re-ranks with visible reasons', async () => {
  const page = await openGroups();
  await tapN(page, '.js-interest', I.photo);

  expect(storage.get(KEY).profile.interests).toEqual(['摄影']);
  expect(classAt(page, '.js-interest', I.photo)).toContain('chip--on');
  expect(count(page, '.row')).toBe(12);
  expect(count(page, '.row--hit')).toBe(3);
  expect(count(page, '.why-i')).toBe(3);
  expect(text(page, '.why-t')).toBe('对上 1 个兴趣标签');
  expect(text(page, '.why-i')).toContain('你要的「摄影」正好是它的标签');
  expect(allText(page, '.section-title')).toContain('已选 1 项');
  expect(allText(page, '.section-title')).toContain('对上了 3 个社群 · 已加入 0 个');
});

test('a second interest re-orders the ranking instead of just appending to it', async () => {
  const page = await openGroups();
  await tapN(page, '.js-interest', I.photo);
  expect(text(page, '.name')).toBe('光影摄影社'); // 同分按示例数据里的顺序排

  await tapN(page, '.js-interest', I.film);
  expect(storage.get(KEY).profile.interests).toEqual(['摄影', '电影']);
  expect(text(page, '.name')).toBe('胶片电影社');
  expect(count(page, '.why-i')).toBe(4); // g05 两个理由，g01、g11 各一个
  expect(allText(page, '.section-title')).toContain('对上了 3 个社群');

  await tapN(page, '.js-interest', I.photo); // 取消摄影，电影那条仍然排第一
  expect(storage.get(KEY).profile.interests).toEqual(['电影']);
  expect(text(page, '.name')).toBe('胶片电影社');
  expect(count(page, '.row--hit')).toBe(1);
});

test('groups that did not match are listed as not matching, not silently dropped', async () => {
  const page = await openGroups();
  await tapN(page, '.js-interest', I.run);

  expect(count(page, '.row')).toBe(12);
  expect(count(page, '.row--hit')).toBe(2); // 深夜跑团、骑行小队
  expect(count(page, '.why-t--hit')).toBe(2);
  expect(allText(page, '.name')).toContain('慢读会');
  expect(allText(page, '.why-t')).toContain('没对上你写的兴趣');
});

test('reasons stay in plain words — no percentages dressed up as social proof', async () => {
  const page = await openGroups();
  await tapN(page, '.js-interest', I.photo);
  await tapN(page, '.js-interest', I.film);

  const words = allText(page, '.row');
  expect(words).not.toMatch(/%/);
  expect(words).not.toMatch(/\d+\s*人/); // 没有人数，也没有"XX 人已加入"
  expect(allText(page, '.why-t')).toContain('对上 2 个兴趣标签');
});

test('加入 persists to favourites.groups, flips the button, and survives a remount', async () => {
  const page = await openGroups();
  await tapN(page, '.js-interest', I.photo);
  await tap(page, '.js-join');

  expect(storage.get(KEY).favourites.groups).toEqual(['g01']);
  expect(text(page, '.js-join')).toBe('已加入 · 退出');
  expect(classAt(page, '.js-join', 0)).toContain('state--on');
  expect(count(page, '.state--on')).toBe(1);
  expect(wxState().toasts[wxState().toasts.length - 1]).toBe('光影摄影社 已加入（本机记录）');
  expect(allText(page, '.section-title')).toContain('已加入 1 个');

  const again = await openGroups();
  expect(count(again, '.state--on')).toBe(1);
  expect(allText(again, '.section-title')).toContain('对上了 3 个社群 · 已加入 1 个');
});

test('the same control leaves again — no second handler to keep in sync', async () => {
  const page = await openGroups();
  await tapN(page, '.js-interest', I.photo);
  await tap(page, '.js-join');
  await tap(page, '.js-join');

  expect(storage.get(KEY).favourites.groups).toEqual([]);
  expect(count(page, '.state--on')).toBe(0);
  expect(text(page, '.js-join')).toBe('加入');
  expect(wxState().toasts).toContain('已退出');
});

test('a joined group keeps its place when the ranking re-orders underneath it', async () => {
  const page = await openGroups();
  await tapN(page, '.js-interest', I.photo);
  await tap(page, '.js-join'); // g01 光影摄影社
  await tapN(page, '.js-interest', I.film); // 胶片电影社 现在排到 g01 前面

  expect(allText(page, '.name')).toContain('胶片电影社');
  expect(count(page, '.state--on')).toBe(1);
  expect(allText(page, '.js-join')).toContain('已加入 · 退出');
  expect(storage.get(KEY).favourites.groups).toEqual(['g01']);
});

test('清空 drops the profile and the whole result list with it', async () => {
  const page = await openGroups();
  await tapN(page, '.js-interest', I.photo);
  await tapN(page, '.js-interest', I.run);
  expect(count(page, '.row')).toBe(12);

  await tap(page, '.js-clear');
  expect(storage.get(KEY).profile.interests).toEqual([]);
  expect(count(page, '.row')).toBe(0);
  expect(count(page, '.zero')).toBe(1);
  expect(count(page, '.chip--on')).toBe(0);
  expect(count(page, '.js-clear')).toBe(0); // 没有输入的时候连"清空"都不该出现
});

test('matching is local-only: the page never touches the model or the network', async () => {
  const page = await openGroups();
  await tapN(page, '.js-interest', I.photo);
  await tapN(page, '.js-interest', I.film);
  await tap(page, '.js-join');

  expect(wxState().requests.length).toBe(0);
  expect(wxState().nav.length).toBe(0);
  expect(html(page, '.pg')).toContain('光影摄影社');
});
