// Enable console capture + click button + read state
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
  const consoleMsgs = [];
  ws.on('message', (data) => {
    const m = JSON.parse(data.toString());
    if (m.method === 'Runtime.consoleAPICalled') {
      consoleMsgs.push({
        type: m.params.type,
        args: m.params.args.map(a => a.value || a.description || '').join(' '),
      });
    }
    if (m.id && pending.has(m.id)) {
      pending.get(m.id)(m);
      pending.delete(m.id);
    }
  });
  await new Promise((r) => ws.once('open', r));
  const send = (method, params) => new Promise((r) => {
    const _id = ++id;
    pending.set(_id, r);
    ws.send(JSON.stringify({ id: _id, method, params }));
  });

  // Enable Runtime to capture console
  await send('Runtime.enable');

  // Click the button
  const clickResult = await send('Runtime.evaluate', { expression: `
(() => {
  const btn = document.querySelector('[aria-label*="Project actions"]');
  if (!btn) return 'no btn';
  btn.click();
  return 'clicked';
})()
` });
  console.log('CLICK:', clickResult.result);

  // Read state immediately
  const stateResult = await send('Runtime.evaluate', { expression: `
(() => {
  const m = document.querySelector('[role="menu"].fixed.z-50');
  if (!m) return 'no menu visible';
  let parent = m.parentElement;
  while (parent && !parent.__vueParentComponent) parent = parent.parentElement;
  let inst = parent && parent.__vueParentComponent;
  while (inst && (!inst.setupState || inst.setupState.projectContextMenu === undefined)) {
    inst = inst.parent;
  }
  const state = inst ? inst.setupState : null;
  return JSON.stringify({
    style: m.getAttribute('style'),
    pc: state && state.projectContextMenu ? JSON.parse(JSON.stringify(state.projectContextMenu)) : 'null_or_undefined',
    hasFn: typeof state?.openProjectContextMenu,
  });
})()
` });
  console.log('STATE:', stateResult.result);
  console.log('CONSOLE MSGS:', JSON.stringify(consoleMsgs));

  ws.close();
})().catch(e => { console.error(e); process.exit(1); });
