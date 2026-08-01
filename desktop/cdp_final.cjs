// CDP test: verify menu position is correct.
const WS = require('ws');
const http = require('http');

function getJSON(url) {
  return new Promise((resolve, reject) => {
    http.get(url, (res) => {
      let body = '';
      res.on('data', (c) => body += c);
      res.on('end', () => resolve(JSON.parse(body)));
    }).on('error', reject);
  });
}

(async () => {
  const targets = await getJSON('http://127.0.0.1:9444/json/list');
  const page = targets.find(t => t.type === 'page' && t.url.startsWith('file://'));
  const ws = new WS(page.webSocketDebuggerUrl);
  let id = 0;
  const pending = new Map();
  ws.on('message', (data) => {
    const m = JSON.parse(data.toString());
    if (m.id && pending.has(m.id)) {
      pending.get(m.id)(m);
      pending.delete(m.id);
    }
  });
  await new Promise((r) => ws.once('open', r));

  const send = (method, params) => new Promise((r) => {
    const _id = ++id;
    pending.set(_id, r);
    ws.send(JSON.stringify({ id: _id, method, params }));
  });

  // No reset: clicking document.body would close the menu via
  // sidebar's global mousedown listener. Use Escape or just check
  // current state.

  // Click the projectActions more_horiz button — its @click handler
  // sets projectContextMenu. The global click listener will then
  // fire from the same click event, but @click.stop prevents that.
  const clickResult = await send('Runtime.evaluate', { expression: `
(() => {
  const btn = document.querySelector('[aria-label*="Project actions"]');
  if (!btn) return 'no btn';
  const r = btn.getBoundingClientRect();
  btn.click();
  return JSON.stringify({btnRect: {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)}});
})()
` });
  console.log('CLICK:', JSON.stringify(clickResult.result));

  // Read state IMMEDIATELY in same script (don't await between)
  const stateResult = await send('Runtime.evaluate', { expression: `
(() => {
  const m = document.querySelector('[role="menu"].fixed.z-50');
  if (!m) return 'no menu';
  const r = m.getBoundingClientRect();
  // Walk up to find the Sidebar component instance
  let parent = m.parentElement;
  while (parent && !parent.__vueParentComponent) parent = parent.parentElement;
  let inst = parent && parent.__vueParentComponent;
  while (inst && (!inst.setupState || inst.setupState.projectContextMenu === undefined)) {
    inst = inst.parent;
  }
  const state = inst ? inst.setupState : null;
  return JSON.stringify({
    rect: {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)},
    style: m.getAttribute('style'),
    pc: state && state.projectContextMenu ? JSON.parse(JSON.stringify(state.projectContextMenu)) : null,
    items: Array.from(m.querySelectorAll('button')).map(b => b.innerText.trim()),
  });
})()
` });
  console.log('MENU:', JSON.stringify(stateResult.result));

  ws.close();
})().catch(e => { console.error(e); process.exit(1); });
