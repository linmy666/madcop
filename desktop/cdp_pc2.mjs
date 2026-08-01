import http from 'node:http';
import WS from 'ws';

async function main() {
  const targets = await (await fetch('http://127.0.0.1:9444/json/list')).json();
  const page = targets.find(t => t.type === 'page' && t.url.startsWith('file://'));
  const ws = new WS(page.webSocketDebuggerUrl);
  let id = 0; const pending = new Map();
  await new Promise(r => ws.onopen = r);
  ws.onmessage = (m) => { if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); } };
  const send = (method, params = {}) => new Promise(r => { const _id = ++id; pending.set(_id, r); ws.send(JSON.stringify({id: _id, method, params})); });

  // Reset state
  await send('Runtime.evaluate', { expression: `document.body.click(); 'r';` });
  await new Promise(r => setTimeout(r, 100));

  // Click projectActions and observe state IMMEDIATELY
  const result = await send('Runtime.evaluate', { expression: `
(() => {
  const btn = document.querySelector('[aria-label*="Project actions"]');
  if (!btn) return 'no btn';
  // We need to find where the Sidebar component's setupState is.
  // Walk up the DOM to find a __vueParentComponent ancestor.
  const btns = document.querySelectorAll('button');
  for (const b of btns) {
    const p = b.__vueParentComponent;
    if (p && p.setupState && 'projectContextMenu' in p.setupState) {
      // Trigger click
      btn.click();
      // Read state right after
      const pc = p.setupState.projectContextMenu;
      return JSON.stringify({
        pcNow: pc ? JSON.parse(JSON.stringify(pc)) : null,
        clickTargetRect: btn.getBoundingClientRect().toJSON(),
      });
    }
  }
  return 'no sidebar instance found';
})()
  `, returnByValue: true });
  console.log('PC STATE:', result.result?.result?.value);

  // Wait and check menu
  await new Promise(r => setTimeout(r, 200));
  const m = await send('Runtime.evaluate', { expression: `
(() => {
  const m = document.querySelector('[role="menu"].fixed.z-50');
  if (!m) return 'no menu';
  return JSON.stringify({
    style: m.getAttribute('style'),
    rect: { x: Math.round(m.getBoundingClientRect().x), y: Math.round(m.getBoundingClientRect().y) },
  });
})()
  `, returnByValue: true });
  console.log('MENU:', m.result?.result?.value);
  ws.close();
}

main().catch(e => { console.error(e); process.exit(1); });
