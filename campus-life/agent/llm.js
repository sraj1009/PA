// 本地 Ollama 传输层：只做"发请求、校验、超时"，不决定业务语义。
// 网络失败一律 reject 交给上层降级；只有解析/校验失败才重试一次。
const prompts = require('./prompts');
const offline = require('./offline');

const CHAT_URL = 'http://localhost:11434/api/chat';
const TAGS_URL = 'http://localhost:11434/api/tags';
const DEFAULT_MODEL = 'qwen2.5:3b';

function netError(message) {
  const e = new Error(message);
  e.network = true;
  return e;
}

function timeoutError() {
  const e = new Error('本地模型没有响应');
  e.timeout = true;
  return e;
}

function createLlm(options) {
  const opts = options || {};
  const request = opts.request;
  if (typeof request !== 'function') throw new Error('createLlm needs a request function');
  const model = opts.model || DEFAULT_MODEL;
  const callTimeout = opts.timeoutMs == null ? 6000 : opts.timeoutMs;

  /** One wx.request-shaped call, promised, with a hard timer so a silent server cannot hang a page. */
  function send(url, body, method, ms) {
    const limit = ms == null ? callTimeout : ms;
    return new Promise((resolve, reject) => {
      let settled = false;
      const timer = setTimeout(() => {
        if (settled) return;
        settled = true;
        reject(timeoutError());
      }, limit);

      const finish = (fn) => (payload) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        fn(payload);
      };

      try {
        request({
          url,
          method: method || 'POST',
          timeout: limit,
          header: { 'content-type': 'application/json' },
          data: typeof body === 'string' ? body : JSON.stringify(body),
          success: (res) => {
            if (!res || res.statusCode !== 200) {
              finish(reject)(netError('本地服务返回 ' + (res && res.statusCode)));
              return;
            }
            finish(resolve)(res.data);
          },
          fail: (err) => finish(reject)(netError((err && err.errMsg) || 'request:fail')),
        });
      } catch (thrown) {
        finish(reject)(netError(thrown.message || 'request threw'));
      }
    });
  }

  function contentOf(data) {
    if (!data) return '';
    if (typeof data === 'string') return data;
    const msg = data.message || (data.responses && data.responses[0] && data.responses[0].message);
    return (msg && msg.content) || data.response || '';
  }

  function clamp(x) {
    const n = Number(x);
    if (!isFinite(n)) return 0;
    return Math.max(0, Math.min(1, Math.round(n * 100) / 100));
  }

  function parseMood(raw) {
    const text = String(raw).replace(/```(json)?/gi, '').trim();
    const start = text.indexOf('{');
    const end = text.lastIndexOf('}');
    if (start < 0 || end <= start) throw new Error('模型没有返回 JSON');
    const obj = JSON.parse(text.slice(start, end + 1));
    if (prompts.MOODS.indexOf(obj.mood) < 0) throw new Error('模型返回了未知情绪');
    return { mood: obj.mood, intensity: clamp(obj.intensity) };
  }

  /** temperature 0 + JSON schema, one retry when the reply cannot be parsed. */
  async function classify(text) {
    const body = {
      model,
      stream: false,
      format: prompts.CLASSIFY_SCHEMA,
      options: { temperature: 0 },
      messages: [
        { role: 'system', content: prompts.CLASSIFY_SYSTEM },
        { role: 'user', content: String(text || '') },
      ],
    };

    let last = null;
    for (let attempt = 0; attempt < 2; attempt += 1) {
      const data = await send(CHAT_URL, body); // transport failures reject immediately
      try {
        return parseMood(contentOf(data));
      } catch (err) {
        last = err;
      }
    }
    throw last || new Error('分类失败');
  }

  async function chat(turns, userText, persona, topics) {
    const messages = [{ role: 'system', content: prompts.chatSystem(persona, topics) }];
    (turns || []).slice(-6).forEach((t) => {
      messages.push({ role: t.role === 'assistant' ? 'assistant' : 'user', content: String(t.text || '') });
    });
    messages.push({ role: 'user', content: String(userText || '') });

    const body = { model, stream: false, options: { temperature: 0.85 }, messages };

    let last = null;
    for (let attempt = 0; attempt < 2; attempt += 1) {
      const data = await send(CHAT_URL, body);
      const text = String(contentOf(data)).trim();
      if (text) return { text };
      last = new Error('模型返回了空回复');
    }
    throw last || new Error('对话失败');
  }

  async function explain(plan) {
    const body = {
      model,
      stream: false,
      options: { temperature: 0.4 },
      messages: [
        { role: 'system', content: prompts.EXPLAIN_SYSTEM },
        { role: 'user', content: JSON.stringify(plan) },
      ],
    };
    const data = await send(CHAT_URL, body);
    const text = String(contentOf(data)).trim();
    if (!text) throw new Error('模型返回了空改写');
    return { text };
  }

  /** Never rejects: an unreachable or uninstalled model simply means 离线模式. */
  async function probe(ms) {
    try {
      const data = await send(TAGS_URL, '', 'GET', ms);
      const names = ((data && data.models) || []).map((m) => String(m.name || ''));
      return names.some((n) => n === model || n.indexOf(model) === 0) ? 'llm' : 'offline';
    } catch (e) {
      return 'offline';
    }
  }

  return {
    kind: 'llm',
    model,
    classify,
    chat,
    explain,
    // 匹配留给本地算法：LLM 不参与排名，理由必须可复现。
    match: (profile, pool) => offline.match(profile, pool),
    probe,
  };
}

module.exports = { createLlm, CHAT_URL, TAGS_URL, DEFAULT_MODEL };
