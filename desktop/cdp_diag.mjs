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

// Find Vue instance and read projectContextMenu state
const r1 = await send('Runtime.evaluate', { expression: `
(() => {
  // The Vue app uses Pinia + Vue 3. We need to find the Sidebar component
  // instance to read its projectContextMenu ref. Vue 3 mounts via
  // __vue_app__; components are reachable via DOM nodes.
  // Walk up from .project-header-menu's sibling to find the Sidebar
  // component.
  const sidebar = document.querySelector('.sidebar-panel, [data-testid*="sidebar"]');
  if (!sidebar) {
    // Find any parent containing the menu
    const menu = document.querySelector('.fixed.z-50[role="menu"]');
    if (menu && menu.__vueParentComponent) {
      let inst = menu.__vueParentComponent;
      while (inst && inst.type?.__name !== 'Sidebar') {
        inst = inst.parent;
      }
      if (inst) {
        const ctx = inst.setupState || {};
        return JSON.stringify({
          projectContextMenu: ctx.projectContextMenu,
          x: ctx.projectContextMenu?.x,
          y: ctx.projectContextMenu?.y,
        });
      }
    }
    return 'sidebar not found';
  }
  // Vue 3 devtools uses __vue_app__
  const app = document.querySelector('#app')?.__vue_app__;
  if (!app) return 'no vue app';
  // Walk to Sidebar
  const queue = [app._instance];
  let found = null;
  while (queue.length) {
    const node = queue.shift();
    if (!node) continue;
    if (node.type?.__name === 'Sidebar' || node.type?.name === 'Sidebar') {
      found = node;
      break;
    }
    const subTree = node.subTree;
    if (subTree?.children) {
      // crude BFS
      function walk(n) {
        if (!n) return;
        if (n.component) queue.push(n.component);
        if (n.children && Array.isArray(n.children)) n.children.forEach(walk);
      }
      walk(subTree);
    }
    if (node.children && Array.isArray(node.children)) {
      function walk2(n) {
        if (!n) return;
        if (n.component) queue.push(n.component);
        if (Array.isArray(n.children)) n.children.forEach(walk2);
      }
      walk2(node.children);
    }
  }
  if (found) {
    const ctx = found.setupState || {};
    return JSON.stringify({
      projectContextMenu: ctx.projectContextMenu,
      x: ctx.projectContextMenu?.x,
      y: ctx.projectContextMenu?.y,
    });
  }
  return 'sidebar not found in tree';
})()
`, returnByValue: true });
console.log('projectContextMenu state:', r1.result?.result?.value);
ws.close();
