// 首页是一块只读本机的仪表盘：三个状态卡 + 两个模块入口。
// 这里不写任何数据，也不编任何统计——没有记录的地方就直说没有记录。
const { store, tzOffsetMin } = require('../../adapters/local');
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
});
