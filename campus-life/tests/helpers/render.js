const path = require('path');

const shim = require('./shim');

const simulate = shim.simulate;
const ROOT = path.join(__dirname, '..', '..');

let seq = 0;
const compiled = new Map(); // simulate can only load a given file once per process

function compile(kind, name) {
  const key = kind + ':' + name;
  if (!compiled.has(key)) {
    const file = path.join(ROOT, kind, name, 'index');
    const tag = kind.slice(0, 2) + '-' + name.replace(/[^a-z0-9]/gi, '') + '-' + ++seq;
    compiled.set(key, { id: simulate.load(file, tag, { rootPath: ROOT }), file });
  }
  return compiled.get(key);
}

function container() {
  if (!global.__mount) {
    global.__mount = document.createElement('div');
    document.body.appendChild(global.__mount);
  }
  return global.__mount;
}

/** Mount a real page directory (pages/<name>/index.{js,wxml,wxss,json}). */
function loadPage(name, query) {
  shim.install();
  const { id, file } = compile('pages', name);
  const comp = simulate.render(id, { launchQuery: query || {} });
  if (!comp) throw new Error('simulate.render returned nothing for ' + file);
  comp.attach(container());
  return comp;
}

/** Mount a real component directory (components/<name>/index.*). */
function loadComponent(name, props) {
  shim.install();
  const { id, file } = compile('components', name);
  const comp = simulate.render(id, props || {});
  if (!comp) throw new Error('simulate.render returned nothing for ' + file);
  comp.attach(container());
  return comp;
}

function find(node, selector) {
  const el = node.querySelector(selector);
  if (!el) throw new Error('querySelector found nothing for ' + selector);
  return el;
}

/** simulate dispatches events as async microtasks; always await this. */
async function tap(node, selector) {
  const el = find(node, selector);
  el.dispatchEvent('tap');
  await simulate.sleep(10);
  return el;
}

/** Tap the nth element matching selector (chip rows repeat the same class). */
async function tapN(node, selector, index) {
  const els = node.querySelectorAll(selector);
  if (!els[index]) {
    throw new Error('querySelectorAll(' + selector + ') has no item ' + index + ', found ' + els.length);
  }
  els[index].dispatchEvent('tap');
  await simulate.sleep(10);
  return els[index];
}

async function input(node, selector, value) {
  const el = find(node, selector);
  el.dom.value = value;
  el.dispatchEvent('input', { detail: { value } });
  await simulate.sleep(10);
  return el;
}

function text(node, selector) {
  return find(node, selector).dom.textContent || '';
}

/** Joined textContent of every match, for repeating blocks where order is not the point. */
function allText(node, selector) {
  return Array.prototype.slice
    .call(node.querySelectorAll(selector))
    .map((el) => el.dom.textContent || '')
    .join(' | ');
}

function html(node, selector) {
  return find(node, selector).dom.innerHTML || '';
}

function classes(node, selector) {
  return find(node, selector).dom.className || '';
}

/** simulate has no :nth-child support, so indexed classes go through querySelectorAll. */
function classAt(node, selector, index) {
  const els = node.querySelectorAll(selector);
  if (!els[index]) {
    throw new Error('querySelectorAll(' + selector + ') has no item ' + index + ', found ' + els.length);
  }
  return els[index].dom.className || '';
}

function count(node, selector) {
  return node.querySelectorAll(selector).length;
}

/**
 * simulate 的 querySelector 停在自定义组件边界，它的 facade 也只肯给「自己那层模板」
 * 里的节点派发事件。但真 DOM 上的每个元素都带 __wxElement（exparser 节点），
 * j-component 自己就是这么送事件的（src/render/component.js:375
 * exparser.Event.dispatchEvent(evt.target, exparser.Event.create(...))）。
 * 复用同一套机制，跨边界的「组件内部 bindtap -> triggerEvent -> 页面 bind:action」
 * 才会真的被点通，而不是靠手调方法糊过去。
 */
const exparser = require('miniprogram-exparser');

function innerEl(node, hostSelector, innerClass) {
  const host = find(node, hostSelector);
  const tag = host.dom.nodeName.toLowerCase();
  const el = host.dom.querySelector('.' + tag + '--' + innerClass);
  if (!el) throw new Error('no inner .' + innerClass + ' inside <' + tag + '> at ' + hostSelector);
  return el;
}

async function tapInner(node, hostSelector, innerClass) {
  const el = innerEl(node, hostSelector, innerClass);
  if (!el.__wxElement) throw new Error('inner element has no exparser node: ' + hostSelector + ' .' + innerClass);
  exparser.Event.dispatchEvent(el.__wxElement, exparser.Event.create('tap', {}, {
    bubbles: true,
    capturePhase: true,
    composed: true,
  }));
  await simulate.sleep(10);
}

function innerText(node, hostSelector, innerClass) {
  return innerEl(node, hostSelector, innerClass).textContent || '';
}

module.exports = {
  ROOT,
  simulate,
  loadPage,
  loadComponent,
  tap,
  tapN,
  tapInner,
  innerEl,
  innerText,
  input,
  text,
  allText,
  html,
  classes,
  classAt,
  count,
  find,
  wxState: () => global.__wxState,
  resetWxState() {
    const s = global.__wxState;
    s.store.clear();
    s.nav.length = 0;
    s.toasts.length = 0;
    s.requests.length = 0;
    s.quotaFailTimes = 0;
    s.denyLocation = false;
  },
};
