// CDP check - find the menu that's actually shown and its position
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

// First check what's on the page right now
const r1 = await send('Runtime.evaluate', { expression: `
(() => {
  // List ALL [role=menu] elements
  const menus = Array.from(document.querySelectorAll('[role="menu"]'));
  return JSON.stringify(menus.map(m => {
    const r = m.getBoundingClientRect();
    return {
      cls: m.className.toString().slice(0, 100),
      rect: {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)},
      style: (m.getAttribute('style') || '').slice(0, 200),
      text: (m.innerText || '').slice(0, 80),
      btnCount: m.querySelectorAll('button').length,
    };
  }));
})()
`, returnByValue: true });
console.log('All role=menu elements:', JSON.stringify(r1.result?.result?.value, null, 2));

// Also dump everything fixed-positioned
const r2 = await send('Runtime.evaluate', { expression: `
(() => {
  const fixed = Array.from(document.querySelectorAll('div, ul')).filter(el => {
    const cs = getComputedStyle(el);
    return cs.position === 'fixed' && el.offsetParent !== null;
  });
  return JSON.stringify(fixed.map(el => {
    const r = el.getBoundingClientRect();
    return {
      cls: el.className.toString().slice(0, 60),
      tag: el.tagName,
      rect: {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)},
      text: (el.innerText || '').slice(0, 50),
    };
  }).slice(0, 10));
})()
`, returnByValue: true });
console.log('Fixed-positioned elements (first 10):', JSON.stringify(r2.result?.result?.value, null, 2));

ws.close();
