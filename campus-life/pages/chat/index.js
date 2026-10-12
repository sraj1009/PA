// 匿名一对一聊天：对面永远只有一个本机的模拟同伴，页面把这件事写在屏幕上。
// 关闭时间是 core/chat.js 里那条硬编码的 300000 毫秒，倒计时只是把它读给人看；
// 定时器必须在 onUnload 里清掉，否则人走了 toast 还在响。
const { store, save, tzOffsetMin } = require('../../adapters/local');
const chat = require('../../core/chat');
const fmt = require('../../core/format');
const agent = require('../../agent/index');
const prompts = require('../../agent/prompts');
const { groups: POOL } = require('../../data/groups');

const TICK_MS = 1000;

const PERSONAS = ['warm', 'curious', 'playful'].map((k) => ({
  value: k,
  label: (prompts.PERSONAS[k] || {}).label || k,
}));

function modeText(m) {
  return m === 'llm' ? '本地模型' : '离线模式';
}

/** agent 要的是 {role,text}，本机存的是 {from,text}：转换只在这一处发生。 */
function turnsOf(messages) {
  return (messages || []).map((m) => ({ role: m.from === 'peer' ? 'assistant' : 'user', text: m.text }));
}

Page({
  data: {
    personas: PERSONAS,
    persona: 'warm',
    personaLabel: '倾听型',
    rows: [],
    topics: [],
    topicsText: '',
    joinedCount: 0,
    hasSession: false,
    closed: false,
    closedText: '',
    remaining: '',
    warn: false,
    busy: false,
    draft: '',
    lastSource: '',
    modeText: '离线模式',
    maxLen: chat.maxLen,
  },

  onLoad() {
    this.alive = true;
    this.timer = null;
    this.sessionId = null;
    this.refresh();
    // 没探完之前先按离线写，宁可少报也不虚报。
    agent.ready().then(() => {
      if (this.alive) this.setData({ modeText: modeText(agent.mode()) });
    });
    this.startTimer();
    // 回到页面时期限可能早就过了：立刻结算一次，而不是先显示 0:00 再等一秒。
    this.tick();
  },

  onShow() {
    this.alive = true;
    this.refresh();
    this.startTimer();
    this.tick();
  },

  onHide() { this.stopTimer(); },

  onUnload() {
    this.alive = false;
    this.stopTimer();
  },

  startTimer() {
    if (this.timer) return;
    this.timer = setInterval(() => this.tick(), TICK_MS);
  },

  stopTimer() {
    if (!this.timer) return;
    clearInterval(this.timer);
    this.timer = null;
  },

  tick() {
    const now = Date.now();
    const open = chat.current(store().read());
    if (!open) {
      this.stopTimer(); // 没有开着的会话就不必读盘，更不该顺手写一条 updatedAt
      return;
    }
    const idle = now - open.lastAt;
    if (idle <= chat.idleMs) {
      this.setData({ remaining: fmt.countdown(chat.idleMs - idle), warn: idle >= chat.warnAt });
      return;
    }

    // 到点就关掉、说明一次，然后停表：同一次关闭不该反复弹提示。
    const saved = save((d) => { chat.reap(d, now); });
    this.stopTimer();
    this.refresh();
    // 只有关闭真的写进了本机才说「已自动关闭」；写不成时 save 已经说过那句人话，
    // 屏幕上留着的仍然是开启中的会话——和存储里的一致。
    if (saved.ok) wx.showToast({ title: '5 分钟没有新消息，会话已自动关闭', icon: 'none' });
  },

  refresh() {
    const state = store().read();
    const now = Date.now();
    const tz = tzOffsetMin();
    const all = state.chats || [];
    const s = chat.current(state) || all[all.length - 1] || null;
    const topics = chat.topics(state, POOL);
    const idle = s ? now - s.lastAt : 0;
    const open = !!s && !s.closed;

    this.sessionId = open ? s.id : null;
    if (open) this.startTimer();
    else this.stopTimer();

    const persona = (s && s.persona) || this.data.persona;
    this.setData({
      rows: ((s && s.messages) || []).map((m, i) => ({
        i,
        isMe: m.from === 'me',
        who: m.from === 'me' ? '我' : '模拟同伴',
        text: m.text,
        at: fmt.clock(m.ts, tz),
      })),
      persona,
      personaLabel: (prompts.PERSONAS[persona] || {}).label || persona,
      topics,
      topicsText: topics.join(' · '),
      joinedCount: (state.favourites.groups || []).length,
      hasSession: !!s,
      closed: !open && !!s,
      closedText: s && s.closed
        ? (s.reason === 'timeout' ? '5 分钟没有新消息，会话已自动关闭' : '这个会话已经关闭')
        : '',
      remaining: open ? fmt.countdown(chat.idleMs - idle) : '',
      warn: open && idle >= chat.warnAt,
      modeText: modeText(agent.mode()),
    });
  },

  onPersona(e) {
    const v = e.currentTarget.dataset.v;
    this.setData({ persona: v, personaLabel: (prompts.PERSONAS[v] || {}).label || v });
  },

  onDraft(e) { this.setData({ draft: e.detail.value }); },

  onOpen() {
    const ts = Date.now();
    const saved = save((d) => {
      chat.open(d, { ts, persona: this.data.persona, topics: chat.topics(d, POOL) });
    });
    if (!saved.ok) return; // 会话没落进本机就没有「开始聊天」可宣布
    this.refresh();
    wx.showToast({ title: '开始聊天 · 对面是本机模拟同伴', icon: 'none' });
  },

  async onSend() {
    if (this.data.busy) return;
    const id = this.sessionId;
    const text = (this.data.draft || '').trim();
    if (!id) {
      wx.showToast({ title: '先开一个会话', icon: 'none' });
      return;
    }
    if (!text) {
      wx.showToast({ title: '先写点什么再发', icon: 'none' });
      return;
    }

    // 历史只带到这一句之前：userText 会单独发给 agent。
    const history = turnsOf(((chat.byId(store().read(), id) || {}).messages) || []);
    const topicPool = this.data.topics;

    let res = null;
    const sent = save((d) => { res = chat.send(d, id, text, Date.now()); });
    if (!sent.ok) return; // 我这条都没落进本机：草稿留着，别说发出去了
    if (!res.ok) {
      this.refresh();
      wx.showToast({ title: res.reason, icon: 'none' });
      return;
    }
    this.setData({ draft: '', busy: true });
    this.refresh(); // 我这条先上屏，不等模型回话

    const r = await agent.chat(history, text, this.data.persona, topicPool);
    if (!this.alive) return; // 页面已经走了：不写盘、不 setData、不 toast

    let put = null;
    const replied = save((d) => { put = chat.peer(d, id, r.text, Date.now()); });
    this.setData({ busy: false, lastSource: r.source === 'llm' ? '本地模型回复' : '离线词库回复' });
    this.refresh();
    if (!replied.ok) return; // TA 的话没存下，save 已经说过那句人话
    if (!put.ok) wx.showToast({ title: '会话刚好关闭，回复没留下', icon: 'none' });
  },
});
