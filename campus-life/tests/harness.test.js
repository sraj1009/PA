// Validates the spec's one unproven assumption: a standard Page() file must
// compile, render and react through miniprogram-simulate. The probe page lives
// in tests/fixtures/pages so the product pages/ tree stays exactly the app.json set.
const { loadFixture, tap, text, count } = require('./helpers/render');

jest.setTimeout(60000);

test('a standard Page() file compiles, renders, and reacts to tap', async () => {
  const page = await loadFixture('__probe');

  expect(text(page, '.hd')).toContain('探针');
  expect(count(page, '.row')).toBe(3);

  await tap(page, '.hd');
  expect(text(page, '.hd')).toContain('已点击 1 次');

  await tap(page, '.hd');
  expect(text(page, '.hd')).toContain('已点击 2 次');
});

test('onLoad ran before the first paint', async () => {
  const page = await loadFixture('__probe');
  expect(page.data.title).toBe('探针');
  expect(page.data.clicks).toBe(0);
});
