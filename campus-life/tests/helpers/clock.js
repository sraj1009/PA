// The planner schedules against "minutes left in today", so page tests need a
// clock they can pin; otherwise the same test passes at 09:00 and fails at 23:30.
const RealDate = Date;

class FrozenDate extends RealDate {
  constructor(...args) {
    if (args.length === 0) super(FrozenDate.ts);
    else super(...args);
  }
  static now() {
    return FrozenDate.ts;
  }
}
FrozenDate.ts = new RealDate(2026, 9, 12, 9, 0, 0, 0).getTime();

/** Pin the local clock to 2026-10-12 hh:mm without touching setTimeout. */
function freeze(hour, minute) {
  FrozenDate.ts = new RealDate(2026, 9, 12, hour, minute, 0, 0).getTime();
  global.Date = FrozenDate;
  return FrozenDate.ts;
}

function unfreeze() {
  global.Date = RealDate;
}

/** 只挪时钟，不碰 setTimeout：聊天倒计时用例需要在真实一秒后跳到 275 秒后。 */
function advance(ms) {
  FrozenDate.ts += ms;
  return FrozenDate.ts;
}

module.exports = { freeze, unfreeze, advance };
