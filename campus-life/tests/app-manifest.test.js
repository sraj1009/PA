// 没有 DevTools 可点，就把「清单」层面能被机器证明的事证明掉：
// pages/ 目录必须和 app.json 的 pages 一一对应（多出来的页面会被打包带上设备，
// 少掉的页面一点就白屏）；wxml 里的自定义标签必须在对应 json 里声明过，
// 否则设备上只是一个不渲染的空标签，而测试里 simulate 同样不会替你报错。
const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const app = JSON.parse(fs.readFileSync(path.join(ROOT, 'app.json'), 'utf8'));

const BUILTIN_TAGS = [
  'view', 'scroll-view', 'swiper', 'swiper-item', 'icon', 'progress', 'button', 'text',
  'textarea', 'input', 'label', 'form', 'radio', 'radio-group', 'checkbox', 'checkbox-group',
  'picker', 'picker-view', 'picker-view-column', 'slider', 'switch', 'image', 'video',
  'camera', 'live-player', 'live-pusher', 'audio', 'ad', 'official-account', 'open-data',
  'navigator', 'tab-bar', 'tab-bar-item', 'functional-page-navigator', 'page-container',
  'share-element', 'match-media', 'keyboard-accessory', 'block', 'template', 'slot',
  'import', 'include', 'wxs', 'canvas', 'page-meta',
];

function readJson(rel) {
  return JSON.parse(fs.readFileSync(path.join(ROOT, rel), 'utf8'));
}

/** 从一段 wxml 里取出所有开闭标签名，去掉内置组件。 */
function customTags(src) {
  const out = new Set();
  const re = /<\/?([a-z][a-z0-9]*(?:-[a-z0-9]+)*)\b[^>]*>/g;
  let m = re.exec(src);
  while (m) {
    if (BUILTIN_TAGS.indexOf(m[1]) < 0) out.add(m[1]);
    m = re.exec(src);
  }
  return [...out].sort();
}

const pageDirs = fs
  .readdirSync(path.join(ROOT, 'pages'))
  .filter((n) => fs.statSync(path.join(ROOT, 'pages', n)).isDirectory());

test('pages/ 目录与 app.json 的 pages 一一对应，一个不多一个不少', () => {
  const fromApp = app.pages.map((p) => p.split('/')[1]).sort();
  expect(pageDirs.slice().sort()).toEqual(fromApp);
});

test('每个页面都带齐 index 的四个文件', () => {
  app.pages.forEach((p) => {
    ['.js', '.json', '.wxml', '.wxss'].forEach((ext) => {
      expect(fs.existsSync(path.join(ROOT, p + ext))).toBe(true);
    });
  });
});

test('页面 wxml 用到的自定义标签都在该页 usingComponents 里声明', () => {
  app.pages.forEach((p) => {
    const json = readJson(p + '.json');
    const declared = Object.keys(json.usingComponents || {}).sort();
    customTags(fs.readFileSync(path.join(ROOT, p + '.wxml'), 'utf8')).forEach((tag) => {
      expect(declared).toContain(tag);
    });
  });
});

test('声明了的组件路径真的存在，且组件自己也带齐四个文件', () => {
  app.pages.forEach((p) => {
    const json = readJson(p + '.json');
    Object.keys(json.usingComponents || {}).forEach((tag) => {
      // 声明写作 '../../components/mode-badge/index'，按页面所在目录解析。
      const abs = path.resolve(path.dirname(path.join(ROOT, p)), json.usingComponents[tag]);
      ['js', 'json', 'wxml', 'wxss'].forEach((ext) => {
        expect(fs.existsSync(abs + '.' + ext)).toBe(true);
      });
    });
  });
});

test('没有声明了却没人用的组件——懒加载下它只会白占包体', () => {
  app.pages.forEach((p) => {
    const json = readJson(p + '.json');
    const wxml = fs.readFileSync(path.join(ROOT, p + '.wxml'), 'utf8');
    Object.keys(json.usingComponents || {}).forEach((tag) => {
      expect(new RegExp('<' + tag + '\\b').test(wxml)).toBe(true);
    });
  });
});

test('代码要用的每个私有接口都写进了 requiredPrivateInfos', () => {
  // 真机上 wx.getLocation 不在清单里就直接 fail，DevTools 却照样能用，最容易漏。
  const src = fs
    .readdirSync(path.join(ROOT, 'adapters'))
    .map((f) => fs.readFileSync(path.join(ROOT, 'adapters', f), 'utf8'))
    .join('\n');
  const used = ['getLocation', 'chooseLocation', 'getFuzzyLocation'].filter((n) => src.indexOf('wx.' + n) >= 0);
  used.forEach((n) => expect(app.requiredPrivateInfos).toContain(n));
  expect(used).toEqual(['getLocation']);
});

test('申请定位的地方说明了它只留在本机', () => {
  const desc = app.permission['scope.userLocation'].desc;
  expect(desc).toContain('位置不会上传');
  expect(desc.length).toBeLessThanOrEqual(120); // 设备上的弹窗有长度限制，超了会被截断
});

// 项目根就是小程序根：新加一个开发用目录却忘了 ignore，它会跟着上设备。
// 这条把「什么该设备上」写死成一份清单，忘了就会被拦住。
const SOURCE_DIRS = ['pages', 'components', 'core', 'data', 'adapters', 'agent', 'assets', 'theme'];
const SOURCE_FILES = ['app.js', 'app.json', 'app.wxss', 'project.config.json', 'sitemap.json'];

test('开发用的目录与文件都在 packOptions.ignore 里，源码一个都没被忽略', () => {
  const cfg = readJson('project.config.json');
  const ignored = cfg.packOptions.ignore.map((x) => x.value);

  const dirs = fs.readdirSync(ROOT).filter((n) => fs.statSync(path.join(ROOT, n)).isDirectory());
  dirs.forEach((d) => {
    if (SOURCE_DIRS.indexOf(d) >= 0) return expect(ignored).not.toContain(d);
    expect(ignored).toContain(d);
  });

  const files = fs.readdirSync(ROOT).filter((n) => fs.statSync(path.join(ROOT, n)).isFile());
  files.forEach((f) => {
    if (SOURCE_FILES.indexOf(f) >= 0) return expect(ignored).not.toContain(f);
    expect(ignored).toContain(f);
  });
});
