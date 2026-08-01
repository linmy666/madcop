import http from 'node:http';
import WS from 'ws';

const targets = await (await fetch('http://127.0.0.1:9444/json/list')).json();
const page = targets.find(t => t.type === 'page' && t.url.startsWith('file://'));
const ws = new WS(page.webSocketDebuggerUrl);
let id = 0; const pending = new Map();
await new Promise(r => ws.onopen = r);
ws.onmessage = (m) => { if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); } };
const send = (method, params = {}) => new Promise(r => { const _id = ++id; pending.set(_id, r); ws.send(JSON.stringify({id: _id, method, params})); });

await send('Runtime.evaluate', { expression: `document.body.click(); 'r';` });
await new Promise(r => setTimeout(r, 100));
await send('Runtime.evaluate', { expression: `document.querySelector('[aria-label*="Project actions"]').click(); 'clicked';` });
await new Promise(r => setTimeout(r, 200));

const r = await send('Runtime.evaluate', { expression: `
(() => {
  const m = document.querySelector('[role="menu"].fixed.z-50');
  if (!m) return 'no menu';
  let parent = m.parentElement;
  while (parent && !parent.__vueParentComponent) parent = parent.parentElement;
  let inst = parent && parent.__vueParentComponent;
  while (inst && inst.setupState && inst.setupState.projectContextMenu === undefined) {
    inst = inst.parent;
  }
  const state = inst ? inst.setupState : null;
  return JSON.stringify({
    style: m.getAttribute('style'),
    pc: state && state.projectContextMenu ? JSON.parse(JSON.stringify(state.projectContextMenu)) : null,
    rect: { x: Math.round(m.getBoundingClientRect().x), y: Math.round(m.getBoundingClientRect().y) },
  });
})()
`, returnByValue: true });
console.log(r.result?.result?.value);
ws.close();
