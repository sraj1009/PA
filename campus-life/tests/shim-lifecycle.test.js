// 这条用例测的是 tests/helpers/shim.js 那座桥，不是应用代码。
// tests/shim-life 是只存在于测试里的夹具；页面用例全靠「Page 的生命周期能被
// miniprogram-simulate 驱动」这一句，桥断了的话页面会静默地不刷新，而不是报错。
const path = require('path');
const shim = require('./helpers/shim');
const { text, simulate, wxState, resetWxState } = require('./helpers/render');

jest.setTimeout(60000);

shim.install();
// simulate 一个进程里只能 load 同一个文件一次，所以只建一次、反复 render。
const id = shim.simulate.load(path.join(__dirname, 'shim-life', 'index'), 'sl-shimlife', {
  rootPath: path.join(__dirname, '..'),
});

function mount(query) {
  const comp = shim.simulate.render(id, { launchQuery: query || {} });
  comp.attach(document.createElement('div'));
  return comp;
}

async function settle() {
  await simulate.sleep(20);
  await simulate.sleep(20);
}

beforeEach(() => resetWxState());

test('attach runs onLoad with the launch query, then onReady', async () => {
  const comp = mount({ who: '甲' });
  await settle();
  expect(comp.data.marks).toEqual(['load:甲', 'ready']);
  expect(text(comp, '.n')).toBe('2');
});

test('the page lifetimes a real page relies on are driven from the harness', async () => {
  const comp = mount();
  await settle();

  comp.triggerPageLifeTime('show');
  await settle();
  expect(comp.data.marks).toEqual(['load:', 'ready', 'show']);

  comp.triggerPageLifeTime('hide');
  await settle();
  expect(comp.data.marks[comp.data.marks.length - 1]).toBe('hide');
});

test('detach runs onUnload — this is what lets the chat page clear its timer', async () => {
  const comp = mount();
  await settle();
  comp.detach();
  await settle();
  expect(comp.data.marks[comp.data.marks.length - 1]).toBe('unload');
});

test('a tap in the page template calls the page method, and wx still answers', async () => {
  const comp = mount();
  await settle();

  comp.querySelector('.js-tap').dispatchEvent('tap');
  await settle();
  expect(comp.data.marks).toContain('tap');

  comp.querySelector('.js-go').dispatchEvent('tap');
  await settle();
  expect(wxState().nav).toEqual([{ type: 'switchTab', url: '/pages/planner/index' }]);
});
