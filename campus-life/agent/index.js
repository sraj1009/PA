// 智能体适配层：页面只知道 agent，不知道 answers 来自本机模型还是离线词库。
// auto 模式先探测一次 Ollama；之后每一次调用都独立降级，
// 这样模型中途关掉时页面只会多一个「离线模式」标注，而不是报错。
const offlineEngine = require('./offline');
const { createLlm } = require('./llm');

function withTimeout(promise, ms) {
  return new Promise((resolve) => {
    const timer = setTimeout(() => resolve('offline'), ms);
    promise
      .then((m) => {
        clearTimeout(timer);
        resolve(m === 'llm' ? 'llm' : 'offline');
      })
      .catch(() => {
        clearTimeout(timer);
        resolve('offline');
      });
  });
}

function createAgent(config) {
  const c = config || {};
  const offline = c.offline || offlineEngine;
  const llm = c.llm || null;
  const probeMs = c.probeTimeoutMs == null ? 1500 : c.probeTimeoutMs;

  let preference = c.mode || 'auto'; // auto | local | llm
  let resolved = null;
  let pending = null;
  let lastSource = preference === 'local' ? 'offline' : null;

  function mode() {
    if (preference === 'local') return 'offline';
    if (preference === 'llm') return 'llm';
    return resolved === 'llm' ? 'llm' : 'offline';
  }

  function useLlm() {
    return mode() === 'llm' && !!llm;
  }

  function decide() {
    if (preference === 'local') return Promise.resolve('offline');
    if (preference === 'llm') return Promise.resolve('llm');
    if (resolved) return Promise.resolve(resolved);
    if (!llm) {
      resolved = 'offline';
      return Promise.resolve('offline');
    }
    if (!pending) {
      pending = withTimeout(Promise.resolve().then(() => llm.probe(probeMs)), probeMs)
        .then((m) => {
          resolved = m;
          pending = null;
          return m;
        });
    }
    return pending;
  }

  async function ready() {
    return decide();
  }

  function setPreference(next) {
    preference = next === 'local' || next === 'llm' ? next : 'auto';
    resolved = null;
    pending = null;
    return decide();
  }

  async function classify(text) {
    await decide();
    if (useLlm()) {
      try {
        const r = await llm.classify(text);
        lastSource = 'llm';
        return { mood: r.mood, intensity: r.intensity, source: 'llm' };
      } catch (e) {
        const r = offline.classify(text);
        lastSource = 'offline';
        return { mood: r.mood, intensity: r.intensity, source: 'offline', degraded: true };
      }
    }
    const r = offline.classify(text);
    lastSource = 'offline';
    return { mood: r.mood, intensity: r.intensity, source: 'offline' };
  }

  // topics 只有本机模型用得上（离线词库按关键词回指，不需要话题池）。
  async function chat(turns, userText, persona, topics) {
    await decide();
    if (useLlm()) {
      try {
        const r = await llm.chat(turns, userText, persona, topics);
        lastSource = 'llm';
        return { text: r.text, source: 'llm' };
      } catch (e) {
        lastSource = 'offline';
        return Object.assign(offline.chat(turns, userText, persona), { source: 'offline', degraded: true });
      }
    }
    lastSource = 'offline';
    return Object.assign(offline.chat(turns, userText, persona), { source: 'offline' });
  }

  async function explain(plan) {
    await decide();
    // 无论谁写这段文字，算法原文都跟着返回，页面可以对照展示。
    const fallback = offline.explain(plan);
    if (useLlm()) {
      try {
        const r = await llm.explain(plan);
        lastSource = 'llm';
        return { text: r.text, fallback, source: 'llm' };
      } catch (e) {
        lastSource = 'offline';
        return { text: fallback, fallback, source: 'offline', degraded: true };
      }
    }
    lastSource = 'offline';
    return { text: fallback, fallback, source: 'offline' };
  }

  /** 匹配是确定性本地算法：排名和理由必须可复现，所以永远不走模型。 */
  function match(profile, pool) {
    return offline.match(profile, pool);
  }

  return { ready, mode, setPreference, classify, chat, explain, match, lastCallSource: () => lastSource };
}

let singleton = null;

/** The device-wired agent: real wx.request to localhost, preference from local storage. */
function instance() {
  if (!singleton) {
    const { request, store } = require('../adapters/local');
    let preference = 'auto';
    try {
      preference = (store().read().settings || {}).agentMode || 'auto';
    } catch (e) {
      preference = 'auto'; // a broken profile key must not stop the whole app from starting
    }
    singleton = createAgent({ llm: createLlm({ request }), offline: offlineEngine, mode: preference });
  }
  return singleton;
}

function reset() {
  singleton = null;
}

module.exports = {
  createAgent,
  instance,
  reset,
  ready: () => instance().ready(),
  mode: () => instance().mode(),
  setPreference: (m) => instance().setPreference(m),
  classify: (t) => instance().classify(t),
  chat: (turns, text, persona, topics) => instance().chat(turns, text, persona, topics),
  explain: (plan) => instance().explain(plan),
  match: (profile, pool) => instance().match(profile, pool),
};
