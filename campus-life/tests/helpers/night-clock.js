// 整套测试的「深夜回归防线」：把整机时钟假成 23:47，即规划器工作窗口（08:00-22:00）之外。
// 页面按「今天还剩多少分钟」排班、店铺按小时判断营业，任何忘记钉时钟的新用例都会在这里暴露，
// 而不是等到某天晚上 CI / 本机跑测试时才挂。
// 配套配置见 jest.night.config.js（npm run test:night）。
const RealDate = Date;
const BASE = new RealDate(2026, 9, 12, 23, 47, 0, 0).getTime();
let tick = BASE;

class NightDate extends RealDate {
  constructor(...args) {
    if (args.length === 0) super(tick);
    else super(...args);
  }
  static now() {
    tick += 1; // 每次前进 1ms：小时钉在 23:47，但 Date.now() 生成的 id 不会撞车
    return tick;
  }
}

global.Date = NightDate;
