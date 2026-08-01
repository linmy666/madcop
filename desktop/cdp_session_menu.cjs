// Test session right-click menu position
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
    if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
  });
  await new Promise((r) => ws.once('open', r));
  const send = (method, params) => new Promise((r) => {
    const _id = ++id;
    pending.set(_id, r);
    ws.send(JSON.stringify({ id: _id, method, params }));
  });

  // Find a session row and dispatch contextmenu
  const clickResult = await send('Runtime.evaluate', { expression: `
(() => {
  // SessionRow component renders a .sidebar-session-row div
  const rows = document.querySelectorAll('.sidebar-session-row');
  if (rows.length === 0) return 'no rows';
  const row = rows[0];
  const rect = row.getBoundingClientRect();
  // Dispatch a contextmenu event on the row
  const ev = new MouseEvent('contextmenu', {
    bubbles: true, cancelable: true, button: 2,
    clientX: rect.x + 50, clientY: rect.y + 10,
  });
  row.dispatchEvent(ev);
  return JSON.stringify({rowRect: {x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height)}});
})()
` });
  console.log('CLICK:', clickResult.result);

  await new Promise((r) => setTimeout(r, 200));

  // Check the session context menu
  const menuResult = await send('Runtime.evaluate', { expression: `
(() => {
  // Session context menu has min-w-[140px] class (not min-w-[230px])
  const menus = Array.from(document.querySelectorAll('[role="menu"].fixed.z-50'));
  // Find the small one (session menu is 140px min-width)
  const m = menus.find(el => el.className.includes('min-w-[140px]')) || menus[0];
  if (!m) return 'no menu';
  const r = m.getBoundingClientRect();
  return JSON.stringify({
    rect: {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)},
    style: m.getAttribute('style'),
    items: Array.from(m.querySelectorAll('button')).map(b => b.innerText.trim()),
  });
})()
` });
  console.log('MENU:', menuResult.result);

  ws.close();
})().catch(e => { console.error(e); process.exit(1); });
