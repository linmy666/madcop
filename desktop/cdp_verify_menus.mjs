// Verify both projectActions menu and session right-click menu
// positions are correct.
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

// === TEST 1: projectActions menu ===
const r1 = await send('Runtime.evaluate', { expression: `
(() => {
  const btn = document.querySelector('[aria-label*="Project actions"]');
  if (!btn) return 'no btn';
  const rect = btn.getBoundingClientRect();
  btn.click();
  return JSON.stringify({btnRect: {x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height)}});
})()
`, returnByValue: true });
console.log('1. projectActions click:', r1.result?.result?.value);

await new Promise(r => setTimeout(r, 200));

const r2 = await send('Runtime.evaluate', { expression: `
(() => {
  const m = document.querySelector('[role="menu"].fixed.z-50');
  if (!m) return 'no menu';
  const r = m.getBoundingClientRect();
  return JSON.stringify({
    menuRect: {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)},
    items: Array.from(m.querySelectorAll('button')).map(b => b.innerText.trim()),
    itemCount: m.querySelectorAll('button').length,
  });
})()
`, returnByValue: true });
console.log('2. projectActions menu:', r2.result?.result?.value);

// === TEST 3: session right-click menu ===
await send('Runtime.evaluate', { expression: `document.body.click(); 'reset';` });
await new Promise(r => setTimeout(r, 100));

const r3 = await send('Runtime.evaluate', { expression: `
(() => {
  // Find first session row
  const row = document.querySelector('.sidebar-session-row, [data-session-id], button.sidebar-session-row');
  if (!row) return 'no session row';
  // The right-click happens on the row or the section. Find a session element.
  const allBtns = Array.from(document.querySelectorAll('button, [class*="session"], div'));
  const sessionEl = allBtns.find(el => el.textContent && el.textContent.match(/今天的天气|你是谁|临时菜鸟|你好|最近的台风/));
  if (!sessionEl) return 'no session with name';
  const rect = sessionEl.getBoundingClientRect();
  // Trigger contextmenu
  const ev = new MouseEvent('contextmenu', { bubbles: true, clientX: rect.x + 50, clientY: rect.y + 10 });
  sessionEl.dispatchEvent(ev);
  return JSON.stringify({sessionRect: {x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height)}});
})()
`, returnByValue: true });
console.log('3. session contextmenu dispatched:', r3.result?.result?.value);

await new Promise(r => setTimeout(r, 200));

const r4 = await send('Runtime.evaluate', { expression: `
(() => {
  const m = document.querySelector('[role="menu"].fixed.z-50:not([class*="rounded-[18px"])');
  if (!m) {
    // Fall back: find any small min-w-140 menu
    const menus = Array.from(document.querySelectorAll('[role="menu"].fixed.z-50'));
    return JSON.stringify({found: menus.length, allMenus: menus.map(m => ({width: m.offsetWidth, cls: m.className.toString().slice(0, 80)}))});
  }
  const r = m.getBoundingClientRect();
  return JSON.stringify({
    menuRect: {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)},
    items: Array.from(m.querySelectorAll('button')).map(b => b.innerText.trim()),
  });
})()
`, returnByValue: true });
console.log('4. session contextmenu:', r4.result?.result?.value);

ws.close();
