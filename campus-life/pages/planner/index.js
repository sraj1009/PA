const { store, save, tzOffsetMin } = require('../../adapters/local');
const planner = require('../../core/planner');
const fmt = require('../../core/format');
const agent = require('../../agent/index');

const PRIORITIES = [
  { value: 3, label: '高' },
  { value: 2, label: '中' },
  { value: 1, label: '低' },
];
const DURATIONS = [30, 60, 90, 120];
const DEADLINES = [
  { value: -1, label: '不限' },
  { value: 720, label: '12:00' },
  { value: 1080, label: '18:00' },
  { value: 1320, label: '22:00' },
];
const WINDOW = [480, 1320];

function minutesNow(d) {
  return d.getHours() * 60 + d.getMinutes();
}

Page({
  data: {
    title: '',
    durationMin: 60,
    priority: 2,
    deadline: null,
    deadlineLabel: '不限',
    durations: DURATIONS,
    priorities: PRIORITIES,
    deadlines: DEADLINES,
    tasks: [],
    slots: [],
    overflow: [],
    busyLabel: '',
    freeLabel: '',
    generatedAt: '',
    hasPlan: false,
    empty: true,
    advice: '',
    adviceMode: 'offline',
    explainBusy: false,
  },

  onLoad() {
    this.alive = true;
    this.refresh();
  },
  onShow() { this.refresh(); },
  onUnload() { this.alive = false; },

  refresh() {
    const state = store().read();
    this.setData({
      tasks: state.tasks.map((t) => ({
        id: t.id,
        title: t.title,
        durationMin: t.durationMin,
        priority: t.priority,
        priorityLabel: (PRIORITIES.find((p) => p.value === t.priority) || PRIORITIES[1]).label,
        deadlineLabel: t.deadline == null ? '不限' : planner.mmhh(t.deadline),
        fixed: !!t.fixed,
        when: t.fixed ? planner.mmhh(t.start) + ' - ' + planner.mmhh(t.end) : '',
      })),
      empty: state.tasks.length === 0,
    });
    if (this.lastPlan) this.renderPlan(this.lastPlan);
  },

  renderPlan(plan) {
    this.lastPlan = plan;
    this.setData({
      hasPlan: true,
      slots: plan.slots.map((s) => ({
        taskId: s.taskId,
        title: s.title,
        range: planner.mmhh(s.start) + ' - ' + planner.mmhh(s.end),
      })),
      overflow: plan.unscheduled.map((id) => {
        const t = store().read().tasks.find((x) => x.id === id);
        return t ? t.title : id;
      }),
      busyLabel: plan.busyMin + ' 分钟',
      freeLabel: plan.freeMin + ' 分钟空闲',
      generatedAt: fmt.stamp(Date.now(), tzOffsetMin()),
    });
  },

  onTitle(e) { this.setData({ title: e.detail.value }); },
  onPickDuration(e) { this.setData({ durationMin: Number(e.currentTarget.dataset.v) }); },
  onPickPriority(e) { this.setData({ priority: Number(e.currentTarget.dataset.v) }); },
  onPickDeadline(e) {
    const v = Number(e.currentTarget.dataset.v);
    const hit = DEADLINES.find((d) => d.value === v) || DEADLINES[0];
    this.setData({ deadline: v < 0 ? null : v, deadlineLabel: hit.label });
  },

  onAdd() {
    const title = this.data.title.trim();
    if (!title) {
      wx.showToast({ title: '先写点要做的事', icon: 'none' });
      return;
    }
    const ts = Date.now();
    const saved = save((d) => {
      d.tasks.push({
        id: 't_' + ts,
        title,
        priority: this.data.priority,
        durationMin: this.data.durationMin,
        deadline: this.data.deadline,
        createdAt: ts,
      });
    });
    if (!saved.ok) return; // 没存进本机就留着这行字，别把人的输入擦掉
    this.setData({ title: '' });
    this.refresh();
  },

  onDel(e) {
    const id = e.currentTarget.dataset.id;
    if (!save((d) => { d.tasks = d.tasks.filter((t) => t.id !== id); }).ok) return;
    this.refresh();
  },

  onGenerate() {
    const tasks = store().read().tasks;
    if (!tasks.length) {
      wx.showToast({ title: '还没有待办事项', icon: 'none' });
      return;
    }
    const plan = planner.solve({ tasks, now: minutesNow(new Date()), workWindow: WINDOW });
    const entry = { id: 'plan_' + Date.now(), ts: Date.now(), slots: plan.slots, unscheduled: plan.unscheduled };
    const saved = save((d) => {
      const today = fmt.day(Date.now(), tzOffsetMin());
      d.plans = d.plans.filter((p) => p.day !== today);
      d.plans.push(Object.assign({ day: today }, entry));
    });
    if (!saved.ok) return; // 安排没存进本机：不摆上屏，更不说「已生成」
    this.renderPlan(plan);
    // 说明永远只属于生成它的那份安排：重排一次就得收回，否则屏幕上留下的是上一天的话。
    this.setData({ advice: '', adviceMode: 'offline', explainBusy: false });
    wx.showToast({ title: '已生成今日安排', icon: 'success' });
  },

  onExplain() {
    if (!this.lastPlan || this.data.explainBusy) return;
    this.setData({ explainBusy: true });
    // solver 的 unscheduled 是任务 id，给人看的说明不能念 id：在这里换成页面已经算好的标题。
    const viewPlan = { slots: this.lastPlan.slots, unscheduled: this.data.overflow };
    agent.explain(viewPlan).then((r) => {
      if (!this.alive) return;
      this.setData({ explainBusy: false, advice: r.text, adviceMode: r.source });
    });
  },
});
