import http from 'node:http';
import WS from 'ws';

const getJSON = () => new Promise((resolve, reject) => {
  http.get('http://127.0.0.1:9444/json/list', (res) => {
    let body = '';
    res.on('data', (c) => body += c);
    res.on('end', () => resolve(JSON.parse(body)));
  }).on('error', reject);
});

const targets = await getJSON();
const page = targets.find(t => t.type === 'page' && t.url.startsWith('file://'));
const ws = new WS(page.webSocketDebuggerUrl);
let id = 0;
const pending = new Map();
await new Promise(r => ws.onopen = r);
ws.onmessage = (m) => {
  const msg = JSON.parse(m.data);
  if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id); }
};
const send = (method, params = {}) => new Promise(r => {
  const _id = ++id;
  pending.set(_id, r);
  ws.send(JSON.stringify({ id: _id, method, params }));
});

// Close any existing menu first
await send('Runtime.evaluate', { expression: `document.body.click(); 'closed';` });

// Find ALL project-group sections
const r1 = await send('Runtime.evaluate', { expression: `
(() => {
  const sections = document.querySelectorAll('[data-testid^="sidebar-project-group-"]');
  const out = [];
  for (const sec of sections) {
    const projKey = sec.getAttribute('data-testid').replace('sidebar-project-group-', '');
    const allBtns = sec.querySelectorAll('button');
    for (const b of allBtns) {
      const aria = b.getAttribute('aria-label') || '';
      const rect = b.getBoundingClientRect();
      out.push({
        proj: projKey,
        aria: aria.slice(0, 60),
        rect: {x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height)},
      });
    }
  }
  return JSON.stringify(out);
})()
`, returnByValue: true });
console.log('project buttons:', r1.result?.result?.value);

// Click a projectActions button at exact center
const r2 = await send('Runtime.evaluate', { expression: `
(() => {
  const sections = document.querySelectorAll('[data-testid^="sidebar-project-group-"]');
  if (sections.length === 0) return 'no sections';
  // Find the projectActions button (has aria-label starting with 'Project actions')
  let btn = null;
  for (const sec of sections) {
    const candidate = sec.querySelector('[aria-label*="roject actions"], [aria-label*="项目操作"]');
    if (candidate) { btn = candidate; break; }
  }
  if (!btn) return 'no projectActions btn';
  const rect = btn.getBoundingClientRect();
  // Real click — use btn.click() so currentTarget is the button
  btn.click();
  return JSON.stringify({rect: {x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height)}, btnTag: btn.tagName, btnCls: btn.className.toString().slice(0, 60)});
})()
`, returnByValue: true });
console.log('after click:', r2.result?.result?.value);

await new Promise(r => setTimeout(r, 200));

const r3 = await send('Runtime.evaluate', { expression: `
(() => {
  const menu = document.querySelector('[role="menu"]');
  if (!menu) return 'no menu';
  const r = menu.getBoundingClientRect();
  return JSON.stringify({
    rect: {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)},
    style: menu.getAttribute('style'),
    text: (menu.innerText || '').slice(0, 80),
    cls: menu.className.toString().slice(0, 100),
  });
})()
`, returnByValue: true });
console.log('menu state:', r3.result?.result?.value);

ws.close();
