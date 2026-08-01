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

await send('Runtime.evaluate', { expression: `document.body.click(); 'reset';` });
await new Promise(r => setTimeout(r, 100));

// Inject debug into openProjectContextMenu
const r = await send('Runtime.evaluate', { expression: `
(() => {
  // Trigger the button using a real MouseEvent so we have clientX/Y
  const btn = document.querySelector('[aria-label*="Project actions"]');
  if (!btn) return 'no btn';
  const rect = btn.getBoundingClientRect();
  // Create a real click event with proper coordinates
  const ev = new MouseEvent('click', {
    bubbles: true, cancelable: true, button: 0,
    clientX: rect.x + 5, clientY: rect.y + 5,
  });
  btn.dispatchEvent(ev);
  return JSON.stringify({
    btnRect: {x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height)},
    evClientX: ev.clientX, evClientY: ev.clientY,
  });
})()
`, returnByValue: true });
console.log('1:', r.result?.result?.value);

await new Promise(r => setTimeout(r, 200));

// Now check the menu state
const r2 = await send('Runtime.evaluate', { expression: `
(() => {
  const m = document.querySelector('[role="menu"].fixed.z-50');
  if (!m) return 'no menu';
  // Get the inline style
  const style = m.getAttribute('style');
  // Find the parent component's setup state
  let inst = m.__vueParentComponent;
  while (inst && !inst.setupState?.projectContextMenu && !inst.setupState?.contextMenu) {
    inst = inst.parent;
  }
  if (!inst) return JSON.stringify({style});
  const s = inst.setupState;
  return JSON.stringify({
    style,
    projectContextMenu: s.projectContextMenu ? JSON.parse(JSON.stringify(s.projectContextMenu)) : null,
  });
})()
`, returnByValue: true });
console.log('2:', r2.result?.result?.value);
ws.close();
