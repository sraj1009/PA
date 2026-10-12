// 首页是一块只读本机的仪表盘：三个状态卡 + 两个模块入口。
// 这里只写一样东西——智能体引擎偏好（settings.agentMode），别的数据一条都不编、
// 没有记录的地方就直说没有记录。
const { store, save, tzOffsetMin } = require('../../adapters/local');
const checkin = require('../../core/checkin');
const posts = require('../../core/posts');
const mood = require('../../core/mood');
const fmt = require('../../core/format');
const agent = require('../../agent/index');
const { spots } = require('../../data/spots');

const SOCIAL = [
  { key: 'treehole', glyph: '洞', title: '校园树洞', desc: '写下这一刻，只有你自己看得见', url: '/pages/treehole/index', tab: true },
  { key: 'chat', glyph: '聊', title: '匿名一对一聊天', desc: '对面是本机的模拟同伴，不是真人', url: '/pages/chat/index' },
  { key: 'groups', glyph: '社', title: '兴趣社群匹配', desc: '按你勾的兴趣排序，理由写在卡上', url: '/pages/groups/index' },
  { key: 'radar', glyph: '雷', title: '心情雷达', desc: '六个维度全部由你自己的记录算出', url: '/pages/radar/index' },
];

const TOOLS = [
  { key: 'explore', glyph: '探', title: '本地探索打卡', desc: '按校区分组，打卡只写本机', url: '/pages/explore/index', tab: true },
  { key: 'planner', glyph: '规', title: '时间管理智能规划', desc: '排得下的排上，排不下的直说', url: '/pages/planner/index', tab: true },
  { key: 'shops', glyph: '店', title: '周边好店聚合', desc: '距离按当前定位算，内容为示例', url: '/pages/shops/index', tab: true },
];

// 只给「自动」和「只用离线」两个常驻选项：'llm' 意味着屏幕上要写「本地模型」，
// 而那四个字必须由一次真的回答换来，所以它只能通过下面的测试按钮得到。
const MODES = [
  { value: 'auto', label: '自动' },
  { value: 'local', label: '只用离线' },
];

function noteText(v) {
  if (v === 'local') return '当前：只用离线 · 完全不碰网络';
  if (v === 'llm') return '当前：本地模型 · 刚才真的回答过一次';
  return '当前：自动 · 连得上就用本机模型';
}

Page({
  data: {
    mode: 'offline',
    hasPlan: false,
    planText: '',
    planMeta: '',
    checkText: '',
    checkMeta: '',
    hasMood: false,
    moodText: '',
    moodMeta: '',
    social: SOCIAL,
    tools: TOOLS,
    agentMode: 'auto',
    modes: MODES,
    agentNote: noteText('auto'),
    probing: false,
  },

  onLoad() {
    this.refresh();
    // 探测没回来之前按离线写；回来以后才允许说「本地模型」。
    agent.ready().then(() => { this.setData({ mode: agent.mode() }); });
  },

  onShow() { this.refresh(); },

  refresh() {
    const state = store().read();
    const tz = tzOffsetMin();
    const now = Date.now();
    const today = fmt.day(now, tz);

    const plan = (state.plans || []).filter((p) => p.day === today).pop() || null;
    const busy = plan ? plan.slots.reduce((n, s) => n + (s.end - s.start), 0) : 0;

    const streak = checkin.streak(state.checkins, tz, now);
    const visited = checkin.list(spots, state.checkins).filter((s) => s.visited).length;

    // 心情摘要：手动记的和树洞里标出来的都算，取最近的一条。
    const notes = state.moods || [];
    const holes = posts.feed(state); // feed 已经滤掉收回的那几条
    const lastNote = notes.length ? notes[notes.length - 1] : null;
    const lastHole = holes.length ? holes[0] : null; // feed 是新→旧
    const latest = [lastNote, lastHole].filter(Boolean).sort((a, b) => b.ts - a.ts)[0] || null;

    this.setData({
      mode: agent.mode(),
      agentMode: (state.settings || {}).agentMode || 'auto',
      agentNote: noteText((state.settings || {}).agentMode || 'auto'),
      hasPlan: !!plan,
      planText: plan ? plan.slots.length + ' 段安排 · 占 ' + busy + ' 分钟'
        + (plan.unscheduled.length ? ' · 还有 ' + plan.unscheduled.length + ' 件没排下' : '') : '',
      planMeta: plan ? fmt.clock(plan.ts, tz) + ' 生成' : '',
      checkText: streak ? '连续打卡 ' + streak + ' 天' : '今天还没打卡',
      checkMeta: '走过 ' + visited + ' / ' + spots.length + ' 个校内地点',
      hasMood: !!latest,
      moodText: latest ? mood.label(latest.mood) + ' · ' + fmt.ago(latest.ts, now, tz) : '',
      moodMeta: '本机共 ' + (notes.length + holes.length) + ' 条（心情 ' + notes.length + ' · 树洞 ' + holes.length + '）',
    });
  },

  onGoPlanner() { wx.switchTab({ url: '/pages/planner/index' }); },
  onGoRadar() { wx.navigateTo({ url: '/pages/radar/index' }); },

  /**
   * 引擎偏好的唯一写入口：屏幕、本机存储、agent 内存三处只能有一个说法。
   * 写不进本机（存储满）就退回本机里真的那条，而不是让芯片亮着、重启后又变回去。
   */
  syncMode(next) {
    const saved = save((d) => { d.settings.agentMode = next; });
    const v = saved.ok ? next : ((store().read().settings || {}).agentMode || 'auto');
    agent.setPreference(v);
    this.setData({ agentMode: v, agentNote: noteText(v), mode: agent.mode() });
    agent.ready().then(() => this.setData({ mode: agent.mode() }));
  },

  /** 选「只用离线」后一次网络都不该再发生，所以这里只切换偏好，不探测。 */
  onPickMode(e) {
    this.syncMode(e.currentTarget.dataset.v === 'local' ? 'local' : 'auto');
  },

  // 「本地模型」这四个字只能用一次真的回答换来：先按 llm 偏好问一次，答不上就退回自动。
  onProbeLlm() {
    if (this.data.probing) return;
    this.setData({ probing: true });
    agent.setPreference('llm'); // 这一步只改内存，不落盘：真的答了才写本机
    agent.classify('今天心情还行').then((r) => {
      const ok = r.source === 'llm';
      this.setData({ probing: false });
      this.syncMode(ok ? 'llm' : 'auto');
      wx.showToast({
        title: ok ? '本地模型可用，已切换' : '连不上本机模型，仍用离线词库',
        icon: 'none',
      });
    });
  },
});
