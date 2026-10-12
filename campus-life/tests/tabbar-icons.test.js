// 这五枚图标是 tools/make-tabbar-icons.js 画出来的，仓库里只有脚本 + 生成物。
// 没有 DevTools 可看，所以这里钉的是能被机器证明的那部分：app.json 指的文件在不在、
// 是不是真的 81×81 RGBA、微信 40KB 的上限有没有破、图里是不是真的画了像素、
// 未选/已选两张是否只有颜色不同、以及重新生成一次字节是否一模一样。
// 「在手机上好不好看」不在这个文件的能力范围内，README 的缺口清单仍然写着它。
const fs = require('fs');
const path = require('path');
const zlib = require('zlib');
const { render, ICONS, OFF, ON, SIZE } = require('../tools/make-tabbar-icons');

const ROOT = path.join(__dirname, '..');
const app = JSON.parse(fs.readFileSync(path.join(ROOT, 'app.json'), 'utf8'));
const MAX_BYTES = 40 * 1024; // 微信对 tabBar 图片的硬上限

function readPng(file) {
  const buf = fs.readFileSync(file);
  const sig = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
  expect(buf.slice(0, 8)).toEqual(sig);

  let p = 8;
  let ihdr = null;
  const idat = [];
  let sawIend = false;
  while (p < buf.length) {
    const len = buf.readUInt32BE(p);
    const type = buf.toString('ascii', p + 4, p + 8);
    const data = buf.slice(p + 8, p + 8 + len);
    if (buf.length < p + 12 + len) throw new Error('chunk ' + type + ' runs off the end of the file');
    if (type === 'IHDR') ihdr = data;
    if (type === 'IDAT') idat.push(data);
    if (type === 'IEND') sawIend = true;
    p += 12 + len;
  }
  expect(p).toBe(buf.length); // 块长度必须刚好走完整个文件，错一个字节都说明写坏了
  expect(sawIend).toBe(true);

  const w = ihdr.readUInt32BE(0);
  const h = ihdr.readUInt32BE(4);
  const raw = zlib.inflateSync(Buffer.concat(idat));
  expect(raw.length).toBe(h * (w * 4 + 1)); // 每行一个 filter 字节 + RGBA 像素

  const rgba = Buffer.alloc(w * h * 4);
  const filters = new Set();
  for (let y = 0; y < h; y += 1) {
    const row = y * (w * 4 + 1);
    filters.add(raw[row]);
    raw.copy(rgba, y * w * 4, row + 1, row + 1 + w * 4);
  }
  return { w, h, depth: ihdr[8], colorType: ihdr[9], filters, rgba };
}

function fileFor(rel) {
  return path.join(ROOT, rel);
}

const list = app.tabBar.list;

test('every tabBar entry points at a page that exists and an icon that exists', () => {
  expect(list.length).toBe(5);
  list.forEach((item) => {
    expect(app.pages).toContain(item.pagePath);
    expect(item.text).toBeTruthy();
    expect(fs.existsSync(fileFor(item.iconPath))).toBe(true);
    expect(fs.existsSync(fileFor(item.selectedIconPath))).toBe(true);
  });
  expect(list.map((i) => i.pagePath)).toEqual([
    'pages/index/index', 'pages/explore/index', 'pages/planner/index', 'pages/shops/index', 'pages/treehole/index',
  ]);
});

test('the icons stay inside the WeChat budget: 81×81 RGBA, under 40 KB, filter none', () => {
  list.forEach((item) => {
    [item.iconPath, item.selectedIconPath].forEach((rel) => {
      const buf = fs.readFileSync(fileFor(rel));
      expect(buf.length).toBeLessThanOrEqual(MAX_BYTES);
      const png = readPng(fileFor(rel));
      expect(png.w).toBe(SIZE);
      expect(png.h).toBe(SIZE);
      expect(png.depth).toBe(8);
      expect(png.colorType).toBe(6); // RGBA：底色透明，深浅色 tabBar 上都不会糊边
      expect([...png.filters]).toEqual([0]);
    });
  });
});

test('each icon really has drawn pixels, a transparent background, and only the palette colour', () => {
  Object.keys(ICONS).forEach((name) => {
    [[`${name}.png`, OFF], [`${name}-on.png`, ON]].forEach(([file, color]) => {
      const png = readPng(path.join(ROOT, 'assets', 'tabbar', file));
      let painted = 0;
      for (let i = 0; i < png.rgba.length; i += 4) {
        const a = png.rgba[i + 3];
        if (a === 0) continue;
        painted += 1;
        expect([png.rgba[i], png.rgba[i + 1], png.rgba[i + 2]]).toEqual(color);
      }
      // 81×81 的图标如果只画出几十个点，那就是画错了，不是「简洁」。
      expect(painted).toBeGreaterThan(400);
      expect(painted).toBeLessThan(SIZE * SIZE * 0.6); // 也不能糊成一整块
      expect(png.rgba[3]).toBe(0); // 左上角
      expect(png.rgba[(SIZE * SIZE - 1) * 4 + 3]).toBe(0); // 右下角
    });
  });
});

test('selected and unselected differ only in colour', () => {
  Object.keys(ICONS).forEach((name) => {
    const off = readPng(path.join(ROOT, 'assets', 'tabbar', name + '.png'));
    const on = readPng(path.join(ROOT, 'assets', 'tabbar', name + '-on.png'));
    let painted = 0;
    for (let i = 0; i < off.rgba.length; i += 4) {
      expect(on.rgba[i + 3]).toBe(off.rgba[i + 3]); // 透明度（也就是形状）一模一样
      if (off.rgba[i + 3] === 0) continue;
      painted += 1;
      expect([on.rgba[i], on.rgba[i + 1], on.rgba[i + 2]]).toEqual(ON);
      expect([off.rgba[i], off.rgba[i + 1], off.rgba[i + 2]]).toEqual(OFF);
    }
    expect(painted).toBeGreaterThan(0);
  });
});

test('regenerating an icon gives byte-identical output', () => {
  Object.keys(ICONS).forEach((name) => {
    [[`${name}.png`, OFF], [`${name}-on.png`, ON]].forEach(([file, color]) => {
      expect(render(name, color)).toEqual(fs.readFileSync(path.join(ROOT, 'assets', 'tabbar', file)));
    });
  });
});

// switchTab 只能去 tabBar 上的页，navigateTo 去 tabBar 上的页会静默失败：
// 这条把首页入口标的那个 flag 和 app.json 的真实列表钉在一起。
test('the dashboard opens exactly the pages the tabBar can actually answer to', () => {
  const tabs = new Set(list.map((i) => i.pagePath));
  const src = fs.readFileSync(path.join(ROOT, 'pages', 'index', 'index.js'), 'utf8');

  const entries = [...src.matchAll(/\{ key: '([^']+)'[^}]*?url: '([^']+)'([^}]*)/g)].map((m) => ({
    key: m[1],
    pagePath: m[2].replace(/^\//, ''),
    tab: /tab:\s*true/.test(m[3]),
  }));
  expect(entries.length).toBe(7); // 四个社交 + 三个本地生活工具
  entries.forEach((e) => {
    expect(app.pages).toContain(e.pagePath);
    expect(e.tab).toBe(tabs.has(e.pagePath));
  });

  const calls = [...src.matchAll(/wx\.(switchTab|navigateTo)\(\{ url: '([^']+)' \}\)/g)]
    .map((m) => ({ kind: m[1], pagePath: m[2].replace(/^\//, '') }));
  expect(calls.length).toBe(2); // 两张空状态卡上的「去规划」「去心情雷达」
  calls.forEach((c) => {
    expect(c.kind === 'switchTab' ? tabs.has(c.pagePath) : !tabs.has(c.pagePath)).toBe(true);
  });
});
