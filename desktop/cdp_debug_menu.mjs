// Debug: directly test openProjectContextMenu's behavior
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

// Reset
await send('Runtime.evaluate', { expression: `document.body.click(); 'reset';` });
await new Promise(r => setTimeout(r, 100));

// Simulate what happens with real mouse event vs CDP .click()
const r = await send('Runtime.evaluate', { expression: `
(() => {
  const btn = document.querySelector('[aria-label*="Project actions"]');
  if (!btn) return 'no btn';
  const rect = btn.getBoundingClientRect();
  // Inspect the actual click event listeners
  const events = getEventListeners ? getEventListeners(btn) : null;
  // Try with a fully populated MouseEvent
  const mouseEvent = new MouseEvent('click', {
    bubbles: true,
    cancelable: true,
    clientX: rect.x + 5,
    clientY: rect.y + 5,
  });
  // The currentTarget in click() will be the button
  btn.dispatchEvent(mouseEvent);
  return JSON.stringify({
    btnRect: {x: Math.round(rect.x), y: Math.round(rect.y)},
    mouseClientX: mouseEvent.clientX,
    mouseClientY: mouseEvent.clientY,
    currentTargetTag: mouseEvent.currentTarget?.tagName,
  });
})()
`, returnByValue: true });
console.log('debug:', r.result?.result?.value);

await new Promise(r => setTimeout(r, 200));

// Check final menu state
const r2 = await send('Runtime.evaluate', { expression: `
(() => {
  const m = document.querySelector('[role="menu"].fixed.z-50');
  if (!m) return 'no menu';
  return JSON.stringify({
    rect: {x: Math.round(m.getBoundingClientRect().x), y: Math.round(m.getBoundingClientRect().y)},
    style: m.getAttribute('style'),
  });
})()
`, returnByValue: true });
console.log('menu state:', r2.result?.result?.value);

ws.close();
