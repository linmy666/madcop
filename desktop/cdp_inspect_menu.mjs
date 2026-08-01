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

const r = await send('Runtime.evaluate', { expression: `
(() => {
  const btn = document.querySelector('[aria-label*="Project actions"]');
  if (!btn) return 'no btn';
  btn.click();
  return 'clicked';
})()
`, returnByValue: true });
await new Promise(r => setTimeout(r, 200));

const r2 = await send('Runtime.evaluate', { expression: `
(() => {
  const m = document.querySelector('[role="menu"].fixed.z-50');
  if (!m) return 'no menu';
  const r = m.getBoundingClientRect();
  return JSON.stringify({
    rect: {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)},
    innerHTML: m.innerHTML.slice(0, 800),
  });
})()
`, returnByValue: true });
console.log('menu state:', r2.result?.result?.value);

ws.close();
