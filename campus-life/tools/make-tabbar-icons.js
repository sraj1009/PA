// tabBar 的五枚图标（未选/已选各一张）由这个脚本画出来，仓库里只留一份可复现的源码。
// 这台机器上没有图像库，所以 PNG 是直接用 zlib 手写的：单色 RGBA、filter 0、level 9，
// 同样的输入一定得到同样的字节。图案按 4 倍超采样（324×324）判定覆盖，再平均回 81×81，
// 边缘因此是渐变的而不是台阶。
const fs = require('fs');
const path = require('path');
const zlib = require('zlib');

const SIZE = 81; // WeChat 推荐的 tabBar 图标边长
const SS = 4; // 超采样倍数
const T = 5; // 线宽（逻辑像素）
const OUT = path.join(__dirname, '..', 'assets', 'tabbar');

// 与 app.json 的 tabBar.color / selectedColor 保持一致，改一处就得改两处。
const OFF = [0x7b, 0x89, 0xa6];
const ON = [0x3b, 0x6e, 0xf6];

function distToSeg(px, py, ax, ay, bx, by) {
  const vx = bx - ax;
  const vy = by - ay;
  const wx = px - ax;
  const wy = py - ay;
  const len = vx * vx + vy * vy;
  const k = len === 0 ? 0 : Math.max(0, Math.min(1, (wx * vx + wy * vy) / len));
  return Math.hypot(px - (ax + vx * k), py - (ay + vy * k));
}

/** 圆角矩形的带符号距离（中心 + 半宽高 + 圆角），和 SDF 的常用写法一致。 */
function sdRoundRect(px, py, cx, cy, hw, hh, r) {
  const rr = Math.min(r, hw, hh);
  const qx = Math.abs(px - cx) - hw + rr;
  const qy = Math.abs(py - cy) - hh + rr;
  const ax = Math.max(qx, 0);
  const ay = Math.max(qy, 0);
  return Math.min(Math.max(ax, ay), 0) + Math.hypot(ax, ay) - rr;
}

const line = (ax, ay, bx, by, w = T) => (x, y) => distToSeg(x, y, ax, ay, bx, by) <= w / 2;
const ring = (cx, cy, r, w = T) => (x, y) => Math.abs(Math.hypot(x - cx, y - cy) - r) <= w / 2;
const rrect = (cx, cy, hw, hh, rad, w = T) => (x, y) => Math.abs(sdRoundRect(x, y, cx, cy, hw, hh, rad)) <= w / 2;
const blob = (cx, cy, rx, ry) => (x, y) => ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1;
const arc = (cx, cy, r, a0, a1, w = T) => (x, y) => {
  if (Math.abs(Math.hypot(x - cx, y - cy) - r) > w / 2) return false;
  let a = Math.atan2(y - cy, x - cx);
  if (a < 0) a += Math.PI * 2;
  return a >= a0 && a <= a1;
};

const PI = Math.PI;

const ICONS = {
  // 首页：屋顶 + 墙 + 门
  index: [
    line(13, 37, 40, 15), line(40, 15, 67, 37),
    line(19, 34, 19, 66), line(19, 66, 61, 66), line(61, 66, 61, 34),
    line(34, 66, 34, 51), line(34, 51, 46, 51), line(46, 51, 46, 66),
  ],
  // 探索：定位针（外圈 + 实心点 + 两条收口的边）
  explore: [
    ring(40, 29, 16), blob(40, 29, 5, 5),
    line(29, 40.6, 40, 63), line(51, 40.6, 40, 63),
  ],
  // 规划：日历（外框 + 两个挂环 + 分隔线 + 2x2 的日子点）
  planner: [
    rrect(40, 42, 26, 22, 6),
    line(26, 12, 26, 21), line(54, 12, 54, 21),
    line(15, 31, 65, 31),
    blob(29, 42, 3.4, 3.4), blob(51, 42, 3.4, 3.4),
    blob(29, 54, 3.4, 3.4), blob(51, 54, 3.4, 3.4),
  ],
  // 好店：购物袋（袋身 + 提手）
  shops: [
    rrect(40, 49, 22, 16, 5),
    arc(40, 33, 12, PI, PI * 2),
  ],
  // 树洞：树干外圈 + 中间的空洞
  treehole: [
    ring(40, 40, 25),
    blob(40, 42, 10, 13),
  ],
};

function coverage(prims, ox, oy) {
  let hit = 0;
  for (let sy = 0; sy < SS; sy += 1) {
    for (let sx = 0; sx < SS; sx += 1) {
      const x = (ox * SS + sx + 0.5) / SS;
      const y = (oy * SS + sy + 0.5) / SS;
      for (let i = 0; i < prims.length; i += 1) {
        if (prims[i](x, y)) { hit += 1; break; }
      }
    }
  }
  return hit;
}

const CRC = (() => {
  const t = new Int32Array(256);
  for (let n = 0; n < 256; n += 1) {
    let c = n;
    for (let k = 0; k < 8; k += 1) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c;
  }
  return t;
})();

function crc32(buf) {
  let c = 0xffffffff;
  for (let i = 0; i < buf.length; i += 1) c = CRC[(c ^ buf[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

function chunk(type, data) {
  const head = Buffer.alloc(4);
  head.writeUInt32BE(data.length, 0);
  const name = Buffer.from(type, 'ascii');
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(Buffer.concat([name, data])), 0);
  return Buffer.concat([head, name, data, crc]);
}

function encodePng(rgba) {
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(SIZE, 0);
  ihdr.writeUInt32BE(SIZE, 4);
  ihdr[8] = 8; // bit depth
  ihdr[9] = 6; // RGBA
  const raw = Buffer.alloc(SIZE * (SIZE * 4 + 1));
  for (let y = 0; y < SIZE; y += 1) {
    const row = y * (SIZE * 4 + 1);
    raw[row] = 0; // filter: None
    rgba.copy(raw, row + 1, y * SIZE * 4, (y + 1) * SIZE * 4);
  }
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', ihdr),
    chunk('IDAT', zlib.deflateSync(raw, { level: 9 })),
    chunk('IEND', Buffer.alloc(0)),
  ]);
}

function render(name, color) {
  const prims = ICONS[name];
  if (!prims) throw new Error('unknown icon: ' + name);
  const rgba = Buffer.alloc(SIZE * SIZE * 4);
  for (let oy = 0; oy < SIZE; oy += 1) {
    for (let ox = 0; ox < SIZE; ox += 1) {
      const hit = coverage(prims, ox, oy);
      if (!hit) continue;
      const i = (oy * SIZE + ox) * 4;
      rgba[i] = color[0];
      rgba[i + 1] = color[1];
      rgba[i + 2] = color[2];
      rgba[i + 3] = Math.round((255 * hit) / (SS * SS));
    }
  }
  return encodePng(rgba);
}

function main() {
  fs.mkdirSync(OUT, { recursive: true });
  Object.keys(ICONS).forEach((name) => {
    const off = render(name, OFF);
    const on = render(name, ON);
    fs.writeFileSync(path.join(OUT, name + '.png'), off);
    fs.writeFileSync(path.join(OUT, name + '-on.png'), on);
    console.log(name + '.png ' + off.length + ' B · ' + name + '-on.png ' + on.length + ' B');
  });
}

if (require.main === module) main();

module.exports = { render, ICONS, OFF, ON, SIZE, SS, OUT };
