const { loadPage, tap, text, count, classes, wxState, resetWxState } = require('./helpers/render');
const { resetStore, storage } = require('../adapters/local');
const { KEY } = require('../core/schema');

jest.setTimeout(60000);

beforeEach(() => {
  resetWxState();
  resetStore();
});

test('explore lists every spot and starts empty', async () => {
  const page = await loadPage('explore');
  await tap(page, '.hero');
  expect(count(page, '.spot')).toBe(12);
  expect(text(page, '.hero-n')).toBe('0');
  expect(text(page, '.coverage')).toContain('0%');
  expect(count(page, '.empty')).toBe(1);
  // 覆盖率只有 0 也要说明数据从哪来：这一行是诚实规则，不是装饰。
  expect(text(page, '.local-only')).toContain('内容仅存于本机');
});

test('tapping 打卡 writes storage, updates the streak, and toasts', async () => {
  const page = await loadPage('explore');
  await tap(page, '.js-check');

  const saved = storage.get(KEY);
  expect(saved.checkins.length).toBe(1);
  expect(text(page, '.hero-n')).toBe('1');
  expect(text(page, '.coverage')).toContain('8%');
  expect(count(page, '.badge')).toBe(1);
  expect(wxState().toasts.join('')).toContain('打卡成功');
});

test('a second tap inside the dedupe window is refused and writes nothing', async () => {
  const page = await loadPage('explore');
  await tap(page, '.js-check');
  await tap(page, '.js-check');

  expect(storage.get(KEY).checkins.length).toBe(1);
  expect(wxState().toasts.join('')).toContain('分钟后可再次打卡');
});

test('a visited spot renders the done style', async () => {
  const page = await loadPage('explore');
  await tap(page, '.js-check');
  expect(classes(page, '.js-check')).toContain('btn-check--done');
});
