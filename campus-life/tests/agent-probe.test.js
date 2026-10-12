const { createAgent } = require('../agent/index');
const offline = require('../agent/offline');

function stubLlm(behaviour) {
  const b = behaviour || {};
  const calls = { classify: 0, chat: 0, explain: 0, probe: 0, match: 0 };
  return {
    calls,
    kind: 'llm',
    probe: () => {
      calls.probe += 1;
      return b.probeFails ? Promise.reject(new Error('boom')) : Promise.resolve(b.probe || 'llm');
    },
    classify: (t) => {
      calls.classify += 1;
      return b.classifyFails ? Promise.reject(new Error('request:fail')) : Promise.resolve({ mood: 'anxious', intensity: 0.9 });
    },
    chat: () => {
      calls.chat += 1;
      return b.chatFails ? Promise.reject(new Error('request:fail')) : Promise.resolve({ text: '模型回复：先歇一会儿。' });
    },
    explain: () => {
      calls.explain += 1;
      return b.explainFails ? Promise.reject(new Error('request:fail')) : Promise.resolve({ text: '模型改写：上午先把难的做完。' });
    },
    match: () => {
      calls.match += 1;
      return Promise.resolve([{ id: 'x', score: 99, reasons: [] }]);
    },
  };
}

test('auto mode picks the local model when the probe answers', async () => {
  const llm = stubLlm({ probe: 'llm' });
  const a = createAgent({ llm, offline, mode: 'auto' });
  expect(await a.ready()).toBe('llm');
  expect(a.mode()).toBe('llm');
  expect(llm.calls.probe).toBe(1);
});

test('the probe is only paid for once', async () => {
  const llm = stubLlm({ probe: 'llm' });
  const a = createAgent({ llm, offline, mode: 'auto' });
  await Promise.all([a.ready(), a.ready(), a.ready()]);
  expect(llm.calls.probe).toBe(1);
});

test('a refused probe means offline mode', async () => {
  const llm = stubLlm({ probe: 'offline' });
  const a = createAgent({ llm, offline, mode: 'auto' });
  expect(await a.ready()).toBe('offline');
  expect((await a.classify('随便')).source).toBe('offline');
  expect(llm.calls.classify).toBe(0);
});

test('a hanging probe resolves offline instead of blocking the page', async () => {
  const llm = { probe: () => new Promise(() => {}), classify: offline.classify, chat: offline.chat, explain: offline.explain };
  const a = createAgent({ llm, offline, mode: 'auto', probeTimeoutMs: 20 });
  expect(await a.ready()).toBe('offline');
});

test('classify transparently degrades per call while the mode stays llm', async () => {
  const llm = stubLlm({ probe: 'llm', classifyFails: true });
  const a = createAgent({ llm, offline, mode: 'auto' });
  const r = await a.classify('今天还行');
  expect(r.source).toBe('offline');
  expect(r.mood).toBe('calm');
  expect(a.mode()).toBe('llm');
  expect(llm.calls.classify).toBe(1);
});

test('chat falls back to the offline reply and says which engine answered', async () => {
  const ok = stubLlm({ probe: 'llm' });
  const a = createAgent({ llm: ok, offline, mode: 'auto' });
  expect((await a.chat([], '好累', 'warm')).source).toBe('llm');

  const down = stubLlm({ probe: 'llm', chatFails: true });
  const b = createAgent({ llm: down, offline, mode: 'auto' });
  const r = await b.chat([], '好累', 'warm');
  expect(r.source).toBe('offline');
  expect(r.text.length).toBeGreaterThan(4);
});

test('explain keeps the deterministic wording as a fallback the page can show', async () => {
  const plan = { slots: [{ title: '复习高数', start: 540, end: 600 }], unscheduled: [] };
  const a = createAgent({ llm: stubLlm({ probe: 'llm' }), offline, mode: 'auto' });
  const r = await a.explain(plan);
  expect(r.text).toContain('模型改写');
  expect(r.fallback).toContain('09:00');

  const down = createAgent({ llm: stubLlm({ probe: 'llm', explainFails: true }), offline, mode: 'auto' });
  const off = await down.explain(plan);
  expect(off.source).toBe('offline');
  expect(off.text).toContain('09:00 - 10:00 复习高数');
});

test('matching never leaves the device, even with a live model', async () => {
  const llm = stubLlm({ probe: 'llm' });
  const a = createAgent({ llm, offline, mode: 'auto' });
  await a.ready();
  const pool = [{ id: 'photo', name: '摄影社', tags: ['摄影'] }, { id: 'ball', name: '篮球队', tags: ['篮球'] }];
  const r = a.match({ interests: ['摄影'] }, pool);
  expect(r[0].id).toBe('photo');
  expect(llm.calls.match).toBe(0);
});

test('preferring local mode skips the probe entirely', async () => {
  const llm = stubLlm({ probe: 'llm' });
  const a = createAgent({ llm, offline, mode: 'local' });
  expect(await a.ready()).toBe('offline');
  expect(llm.calls.probe).toBe(0);
  expect((await a.classify('还行')).source).toBe('offline');
});

test('preferring the model uses it without probing', async () => {
  const llm = stubLlm({});
  const a = createAgent({ llm, offline, mode: 'llm' });
  expect(await a.ready()).toBe('llm');
  expect(llm.calls.probe).toBe(0);
  expect((await a.classify('明天考')).source).toBe('llm');
});

test('switching the preference re-probes', async () => {
  const llm = stubLlm({ probe: 'llm' });
  const a = createAgent({ llm, offline, mode: 'auto' });
  await a.ready();
  a.setPreference('local');
  expect(a.mode()).toBe('offline');
  expect(llm.calls.probe).toBe(1);
  await a.ready();
  expect(llm.calls.probe).toBe(1);
  a.setPreference('auto');
  expect(await a.ready()).toBe('llm');
  expect(llm.calls.probe).toBe(2);
});

test('an agent with no llm configured still works offline', async () => {
  const a = createAgent({ offline });
  expect(await a.ready()).toBe('offline');
  expect((await a.classify('太开心了')).mood).toBe('joy');
});
