const { createLlm } = require('../agent/llm');

function okReply(content) {
  return (o) => o.success({ statusCode: 200, data: { message: { content } } });
}

test('classify sends a JSON schema and parses the reply', async () => {
  let sent;
  const llm = createLlm({
    request: (o) => {
      sent = o;
      o.success({ statusCode: 200, data: { message: { content: '{"mood":"anxious","intensity":0.7}' } } });
    },
  });
  const r = await llm.classify('明天要交论文');
  expect(sent.url).toBe('http://localhost:11434/api/chat');
  expect(sent.method).toBe('POST');
  expect(JSON.parse(sent.data).format).toBeTruthy();
  expect(r).toEqual({ mood: 'anxious', intensity: 0.7 });
});

test('classify pins the model and asks for deterministic output', async () => {
  let sent;
  const llm = createLlm({ request: (o) => { sent = o; okReply('{"mood":"calm","intensity":0.2}')(o); } });
  await llm.classify('还行');
  const body = JSON.parse(sent.data);
  expect(body.model).toBe('qwen2.5:3b');
  expect(body.stream).toBe(false);
  expect(body.options.temperature).toBe(0);
});

test('malformed JSON retries once then falls back to offline', async () => {
  let n = 0;
  const llm = createLlm({
    request: (o) => {
      n += 1;
      o.success({
        statusCode: 200,
        data: { message: { content: n === 1 ? 'not json' : '{"mood":"low","intensity":0.4}' } },
      });
    },
  });
  expect((await llm.classify('有点难过')).mood).toBe('low');
  expect(n).toBe(2);
});

test('a reply outside the mood enum is rejected, not trusted', async () => {
  const llm = createLlm({ request: (o) => okReply('{"mood":"hungry","intensity":0.5}')(o) });
  await expect(llm.classify('肚子饿了')).rejects.toBeTruthy();
});

test('request failure rejects so the caller can use offline', async () => {
  const llm = createLlm({ request: (o) => o.fail({ errMsg: 'request:fail' }) });
  await expect(llm.classify('x')).rejects.toBeTruthy();
});

test('a non-200 status rejects instead of parsing garbage', async () => {
  const llm = createLlm({ request: (o) => o.success({ statusCode: 500, data: '<html>boom</html>' }) });
  await expect(llm.classify('x')).rejects.toBeTruthy();
});

test('a silent transport times out instead of hanging the page', async () => {
  const llm = createLlm({ request: () => {}, timeoutMs: 20 });
  await expect(llm.classify('x')).rejects.toMatchObject({ timeout: true });
});

test('chat sends the persona plus recent turns and keeps the reply text', async () => {
  let sent;
  const llm = createLlm({
    request: (o) => {
      sent = o;
      okReply('听起来你今天挺累的，先坐下歇会儿。')(o);
    },
  });
  const r = await llm.chat(
    [{ role: 'user', text: '今天好累' }, { role: 'assistant', text: '累到不想说话了？' }],
    '但还是把作业写完了',
    'warm',
  );
  const body = JSON.parse(sent.data);
  expect(body.options.temperature).toBe(0.85);
  expect(body.messages.length).toBe(4);
  expect(body.messages[0].role).toBe('system');
  expect(body.messages[0].content).toContain('模拟');
  expect(body.messages[1].content).toBe('今天好累');
  expect(body.messages[3].content).toContain('但还是把作业写完了');
  expect(r.text).toContain('歇会儿');
});

test('the peer is only ever told the topics joined on this device', async () => {
  let sent;
  const llm = createLlm({ request: (o) => { sent = o; okReply('这周去哪儿拍好？')(o); } });
  await llm.chat([], '周末想出去走走', 'curious', ['摄影', '骑行']);
  const sys = JSON.parse(sent.data).messages[0].content;
  expect(sys).toContain('共同话题只有这些：摄影、骑行');
  expect(sys).toContain('不要假装知道对方的其他事情');
});

test('no joined groups means the prompt offers no topics to fake', async () => {
  let sent;
  const llm = createLlm({ request: (o) => { sent = o; okReply('那就随便聊聊。')(o); } });
  await llm.chat([], '在吗', 'warm', []);
  expect(JSON.parse(sent.data).messages[0].content).not.toContain('共同话题');
});

test('an empty model reply rejects rather than showing a blank bubble', async () => {
  const llm = createLlm({ request: (o) => okReply('   ')(o) });
  await expect(llm.chat([], '在吗', 'warm')).rejects.toBeTruthy();
});

test('probe reports llm only when the model is actually installed', async () => {
  const withModel = createLlm({
    request: (o) => o.success({ statusCode: 200, data: { models: [{ name: 'qwen2.5:3b' }, { name: 'other:1b' }] } }),
  });
  expect(await withModel.probe()).toBe('llm');

  const wrongModel = createLlm({
    request: (o) => o.success({ statusCode: 200, data: { models: [{ name: 'other:1b' }] } }),
  });
  expect(await wrongModel.probe()).toBe('offline');

  const down = createLlm({ request: (o) => o.fail({ errMsg: 'connection refused' }) });
  expect(await down.probe()).toBe('offline');
});

test('probe never rejects, even on a silent endpoint', async () => {
  const silent = createLlm({ request: () => {}, timeoutMs: 20 });
  expect(await silent.probe()).toBe('offline');
});

// adapters/local.request 曾经把调用方自带的 success/fail 覆盖成自己的
// resolve/reject，于是 llm.send 永远收不到响应，页面拿到的是一个没人接管的
// rejection。这是真机上唯一会走的路径，所以接缝必须钉住。
test('the device adapter keeps the caller handlers intact', async () => {
  const real = global.wx.request;
  const { request } = require('../adapters/local');

  let seen = null;
  global.wx.request = (o) => {
    seen = o;
    o.success({ statusCode: 200, data: { message: { content: '{"mood":"anxious","intensity":0.7}' } } });
  };
  try {
    const llm = createLlm({ request });
    expect(await llm.classify('明天要交论文')).toEqual({ mood: 'anxious', intensity: 0.7 });
    expect(seen.url).toBe('http://localhost:11434/api/chat');
    expect(await llm.probe()).toBe('offline'); // 同一个 request 也撑得住 GET 探测
  } finally {
    global.wx.request = real;
  }

  global.wx.request = (o) => o.fail({ errMsg: 'request:fail adapter test' });
  try {
    const down = createLlm({ request });
    await expect(down.classify('在吗')).rejects.toBeTruthy();
    expect(await down.probe()).toBe('offline');
  } finally {
    global.wx.request = real;
  }
});
