const DAY_MS = 86400000;

const pad = (n) => (n < 10 ? '0' + n : '' + n);
const shifted = (ts, tzOffsetMin) => new Date(ts + (tzOffsetMin || 0) * 60000);

function day(ts, tzOffsetMin) {
  const d = shifted(ts, tzOffsetMin);
  return (d.getUTCMonth() + 1) + '月' + d.getUTCDate() + '日';
}

function clock(ts, tzOffsetMin) {
  const d = shifted(ts, tzOffsetMin);
  return pad(d.getUTCHours()) + ':' + pad(d.getUTCMinutes());
}

function stamp(ts, tzOffsetMin) {
  return day(ts, tzOffsetMin) + ' ' + clock(ts, tzOffsetMin);
}

/** Relative label a student actually reads: 今天 / 昨天 / 3天前. */
function ago(ts, now, tzOffsetMin) {
  const diff = Math.floor((now + (tzOffsetMin || 0) * 60000) / DAY_MS) - Math.floor((ts + (tzOffsetMin || 0) * 60000) / DAY_MS);
  if (diff <= 0) return '今天';
  if (diff === 1) return '昨天';
  if (diff < 30) return diff + '天前';
  return day(ts, tzOffsetMin);
}

function pct(x) {
  return Math.round(Math.max(0, Math.min(1, x)) * 100) + '%';
}

/** 把剩余毫秒读成人会看的 4:59；负数一律收成 0:00，不显示"-0:12"。 */
function countdown(ms) {
  const left = Math.max(0, Math.floor(Number(ms) / 1000) || 0);
  return Math.floor(left / 60) + ':' + pad(left % 60);
}

module.exports = { DAY_MS, day, clock, stamp, ago, pct, countdown };
