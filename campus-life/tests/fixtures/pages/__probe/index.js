Page({
  data: { title: '探针', rows: [{ id: 'a' }, { id: 'b' }, { id: 'c' }], clicks: 0 },
  onLoad() {
    this.setData({ title: '探针' });
  },
  onTap() {
    this.setData({ title: '探针 已点击 ' + (this.data.clicks + 1) + ' 次', clicks: this.data.clicks + 1 });
  },
});
