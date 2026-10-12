const { loadComponent, tap, text, count, simulate, wxState, resetWxState } = require('./helpers/render');

jest.setTimeout(60000);

async function empty(props) {
  const comp = loadComponent('empty-state', props);
  await simulate.sleep(20);
  return comp;
}

test('an empty state explains the reason instead of shrugging', async () => {
  const comp = await empty({ title: '今天还没排过日程', desc: '规划只用本机记下的任务算。' });
  expect(text(comp, '.t')).toBe('今天还没排过日程');
  expect(text(comp, '.d')).toBe('规划只用本机记下的任务算。');
});

test('no action text means no button, so nothing looks tappable for nothing', async () => {
  const comp = await empty({ title: '还没有心情记录' });
  expect(count(comp, '.js-action')).toBe(0);
  expect(count(comp, '.d')).toBe(0);
});

test('the action emits an event for the page to handle rather than navigating itself', async () => {
  resetWxState();
  const comp = await empty({ title: 'T', action: '去规划' });
  // 组件自己没有导航权：点下去只许发出 action，跳转由宿主页面决定。
  const seen = [];
  const inst = comp.instance;
  const raw = inst.triggerEvent;
  inst.triggerEvent = (name, detail, opts) => { seen.push(name); return raw.call(inst, name, detail, opts); };

  await tap(comp, '.js-action');
  expect(seen).toEqual(['action']);
  expect(wxState().nav).toEqual([]);
});
