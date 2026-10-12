// 规格要求的"真实跑一次"：这台机器上的 Ollama 必须真的回答，而不是只存在这段代码。
// 未运行时会打印原因并跳过；运行时会把耗时和原文打出来，供报告引用。
const { createLlm } = require('../agent/llm');
const { request } = require('./helpers/http');
const agent = require('../agent/index');
const offline = require('../agent/offline');

jest.setTimeout(180000);

const llm = createLlm({ request, timeoutMs: 120000 });
let up = false;
let probeMs = 0;

beforeAll(async () => {
  const t0 = Date.now();
  up = (await llm.probe(5000)) === 'llm';
  probeMs = Date.now() - t0;
});

function skipNote() {
  console.log('[live-ollama] SKIPPED：本机 http://localhost:11434 没有响应，Ollama 未运行或模型未加载。');
}

test('live: the model answers the mood classifier with valid JSON', async () => {
  if (!up) {
    skipNote();
    return;
  }
  const text = '明天要交论文，紧张得一点也睡不着';
  const t0 = Date.now();
  const r = await llm.classify(text);
  const ms = Date.now() - t0;
  console.log(`[live classify] 探测 ${probeMs} ms · 分类 ${ms} ms · 原文输入「${text}」→ ${JSON.stringify(r)}`);

  expect(['joy', 'low', 'anxious', 'angry', 'calm']).toContain(r.mood);
  expect(['anxious', 'low']).toContain(r.mood);
  expect(r.intensity).toBeGreaterThan(0);
  expect(r.intensity).toBeLessThanOrEqual(1);
});

test('live: the model holds a short in-tone Chinese reply', async () => {
  if (!up) {
    skipNote();
    return;
  }
  const turns = [{ role: 'user', text: '今天一个人吃饭' }, { role: 'assistant', text: '一个人吃饭也挺安静的。' }];
  const t0 = Date.now();
  const r = await llm.chat(turns, '但还是有点失落', 'warm');
  const ms = Date.now() - t0;
  console.log(`[live chat] ${ms} ms → ${r.text}`);

  expect(r.text.length).toBeGreaterThan(4);
  expect(/[\u4e00-\u9fa5]/.test(r.text)).toBe(true);
  expect(r.text).not.toContain('```');
  expect(r.text.length).toBeLessThan(200);
});

test('live: the adapter reports which engine is in use', async () => {
  if (!up) {
    skipNote();
    return;
  }
  const a = agent.createAgent({ llm, offline, mode: 'auto' });
  const m = await a.ready();
  console.log(`[live mode] agent.mode() = ${m}`);
  expect(m).toBe('llm');

  const c = await a.classify('拿到奖学金了，超开心');
  console.log(`[live mode] classify source=${c.source} mood=${c.mood} intensity=${c.intensity}`);
  expect(c.source).toBe('llm');
  expect(['joy']).toContain(c.mood);
});

test('live: a killed transport degrades to offline instead of failing the page', async () => {
  if (!up) {
    skipNote();
    return;
  }
  const down = createLlm({ request: (o) => o.fail({ errMsg: 'request:fail could not connect' }) });
  const a = agent.createAgent({ llm: down, offline, mode: 'llm' });
  const r = await a.classify('明天要交论文');
  console.log(`[live degrade] llm 不可达 → source=${r.source} degraded=${r.degraded} mood=${r.mood}`);
  expect(r.source).toBe('offline');
  expect(r.degraded).toBe(true);
  expect(r.mood).toBe('anxious');
});
