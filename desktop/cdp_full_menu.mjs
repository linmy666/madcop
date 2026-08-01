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

await send('Runtime.evaluate', { expression: `document.querySelector('[aria-label*="Project actions"]').click(); 'clicked';` });
await new Promise(r => setTimeout(r, 200));

const r = await send('Runtime.evaluate', { expression: `
(() => {
  const m = document.querySelector('[role="menu"].fixed.z-50');
  if (!m) return 'no menu';
  const buttons = Array.from(m.querySelectorAll('button')).map(b => ({
    text: b.innerText.trim(),
    rect: b.getBoundingClientRect().toJSON(),
  }));
  return JSON.stringify({
    rect: m.getBoundingClientRect().toJSON(),
    buttons,
  });
})()
`, returnByValue: true });
console.log('full menu:', r.result?.result?.value);
ws.close();
