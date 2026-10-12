const { loadComponent, tap, text, allText, count, simulate, wxState, resetWxState } = require('./helpers/render');

jest.setTimeout(60000);

async function card(props) {
  const comp = loadComponent('nav-card', props);
  await simulate.sleep(20);
  return comp;
}

beforeEach(() => {
  resetWxState();
});

test('the card shows what it is, what it does and the live state line', async () => {
  const comp = await card({ glyph: '洞', title: '校园树洞', desc: '写下这一刻', meta: '本机共 3 条' });
  expect(text(comp, '.glyph')).toBe('洞');
  expect(text(comp, '.t')).toBe('校园树洞');
  expect(text(comp, '.d')).toBe('写下这一刻');
  expect(text(comp, '.m')).toBe('本机共 3 条');
});

test('an entry with nothing to say leaves the optional lines out', async () => {
  const comp = await card({ title: '只有标题' });
  expect(count(comp, '.d')).toBe(0);
  expect(count(comp, '.m')).toBe(0);
});

test('a tabBar page is entered with switchTab', async () => {
  const comp = await card({ title: '校园树洞', url: '/pages/treehole/index', tab: true });
  await tap(comp, '.nav');
  expect(wxState().nav).toEqual([{ type: 'switchTab', url: '/pages/treehole/index' }]);
});

test('a page outside the tabBar is entered with navigateTo', async () => {
  const comp = await card({ title: '匿名一对一聊天', url: '/pages/chat/index' });
  await tap(comp, '.nav');
  expect(wxState().nav).toEqual([{ type: 'navigateTo', url: '/pages/chat/index' }]);
});

test('an entry with no url is inert instead of jumping somewhere wrong', async () => {
  const comp = await card({ title: '还没做好的入口' });
  await tap(comp, '.nav');
  expect(wxState().nav).toEqual([]);
});

test('two mounted cards navigate independently', async () => {
  const a = await card({ title: '甲', url: '/pages/treehole/index', tab: true });
  const b = await card({ title: '乙', url: '/pages/chat/index' });
  await tap(b, '.nav');
  expect(wxState().nav).toEqual([{ type: 'navigateTo', url: '/pages/chat/index' }]);
  await tap(a, '.nav');
  expect(wxState().nav.length).toBe(2);
  expect(wxState().nav[1]).toEqual({ type: 'switchTab', url: '/pages/treehole/index' });
});
