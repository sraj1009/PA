// 智能体状态标注：把「现在是谁在回答」写死在屏幕上，而不是藏在设置里。
// 探测没完成之前一律显示离线，宁可少报也不虚报。
Component({
  properties: {
    mode: { type: String, value: 'offline', observer: 'sync' },
    note: { type: String, value: '', observer: 'sync' },
  },

  // 初始就按离线写：属性没变化时 observer 不会跑，默认值必须自己说得通。
  data: { text: '离线模式', on: false, noteText: '· 不联网也能用' },

  methods: {
    sync() {
      const llm = this.properties.mode === 'llm';
      const note = this.properties.note || '';
      this.setData({
        text: llm ? '本地模型' : '离线模式',
        on: llm,
        noteText: note ? '· ' + note : llm ? '' : '· 不联网也能用',
      });
    },
  },
});
