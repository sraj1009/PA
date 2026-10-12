// 校园地点示例数据：坐标为演示用近似值，非官方测绘数据。
const spots = [
  { id: 'lib', name: '图书馆一楼自习区', zone: 'teach', lat: 30.5148, lng: 114.4291, tip: '靠窗位早上七点后就满了' },
  { id: 'lab3', name: '第三教学楼', zone: 'teach', lat: 30.5162, lng: 114.4305, tip: '晚自习人最少的是五楼' },
  { id: 'studio', name: '设计工坊', zone: 'teach', lat: 30.5155, lng: 114.4318, tip: '可以借到三脚架' },
  { id: 'gym', name: '体育馆羽毛球场', zone: 'sport', lat: 30.5198, lng: 114.4276, tip: '工作日中午不用排队' },
  { id: 'track', name: '南区田径场', zone: 'sport', lat: 30.5205, lng: 114.4322, tip: '晚上八点后灯光最亮' },
  { id: 'court5', name: '五号篮球场', zone: 'sport', lat: 30.5189, lng: 114.4334, tip: '傍晚风大，适合投篮' },
  { id: 'canteen2', name: '二食堂窗口', zone: 'food', lat: 30.5134, lng: 114.4310, tip: '三楼小炒出锅最快' },
  { id: 'coffee', name: '咖啡馆（校内）', zone: 'food', lat: 30.5141, lng: 114.4302, tip: '有插座的位置在东侧' },
  { id: 'noodle', name: '后街面馆', zone: 'food', lat: 30.5119, lng: 114.4339, tip: '加辣要提前说' },
  { id: 'store', name: '北门便利店', zone: 'life', lat: 30.5126, lng: 114.4283, tip: '关东煮十点后打折' },
  { id: 'laundry', name: '宿舍楼下洗衣房', zone: 'life', lat: 30.5172, lng: 114.4268, tip: '周日下午最空' },
  { id: 'clinic', name: '校医院', zone: 'life', lat: 30.5181, lng: 114.4255, tip: '白天门诊到五点' },
];

module.exports = { spots };
