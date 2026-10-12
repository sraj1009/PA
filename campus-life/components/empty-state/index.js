// 空状态组件：每处的说法都要解释「为什么是空的」，而不是只摆一句「暂无数据」。
// 按钮文字为空时连按钮都不渲染，避免出现一个没有作用的空壳。
Component({
  properties: {
    title: { type: String, value: '还没有内容' },
    desc: { type: String, value: '' },
    action: { type: String, value: '' },
  },

  methods: {
    onTap() { this.triggerEvent('action'); },
  },
});
