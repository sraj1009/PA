const { loadComponent, text, classes, count, simulate } = require('./helpers/render');

jest.setTimeout(60000);

async function badge(props) {
  const comp = loadComponent('mode-badge', props || {});
  await simulate.sleep(20);
  return comp;
}

test('an unprobed badge says 离线模式 and promises nothing about a model', async () => {
  const comp = await badge();
  expect(text(comp, '.badge')).toBe('离线模式 · 不联网也能用');
  expect(classes(comp, '.badge')).not.toContain('badge--on');
});

test('only a mode of llm is allowed to claim 本地模型', async () => {
  const comp = await badge({ mode: 'llm' });
  expect(text(comp, '.badge')).toBe('本地模型');
  expect(classes(comp, '.badge')).toContain('badge--on');
  expect(count(comp, '.note')).toBe(0);
});

test('a note from the caller is shown next to the mode', async () => {
  const comp = await badge({ mode: 'llm', note: 'qwen2.5:3b' });
  expect(text(comp, '.note').trim()).toBe('· qwen2.5:3b');
});

test('anything that is not llm falls back to 离线模式, even a typo', async () => {
  expect(text(await badge({ mode: 'LLM' }), '.badge')).toContain('离线模式');
  expect(text(await badge({ mode: '' }), '.badge')).toContain('离线模式');
});
