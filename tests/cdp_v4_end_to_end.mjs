/**
 * CDP-driven end-to-end verification for V4ChatPanel.
 *
 * Connects to Electron's --remote-debugging-port CDP endpoint,
 * navigates the session picker (clicks "新对话" until the V4ChatPanel
 * mounts), fires a chat through the textarea + send button, and
 * captures the mid-stream DOM.
 *
 * Asserts that:
 *   - No "出现异常" / ReferenceError appears in the DOM.
 *   - thoughtBlocks + toolCalls render during streaming.
 *   - The answer text eventually appears in a .v4-answer element.
 *
 * Run:
 *   cd /Users/linruihan/PycharmProjects/madcop
 *   node tests/cdp_v4_end_to_end.mjs
 */

import http from 'node:http'
import fs from 'node:fs'

// Use the built-in WebSocket (Node 22+) if available; otherwise
// expect `ws` to be installed alongside this script.
let WebSocket
if (typeof globalThis.WebSocket === 'function') {
  WebSocket = globalThis.WebSocket
} else {
  try {
    WebSocket = (await import('ws')).default
  } catch (e) {
    console.error('This test needs `ws` (npm i ws) or Node 22+ for built-in WebSocket.')
    process.exit(2)
  }
}

const CDP_HTTP = 'http://127.0.0.1:9876/json'

function getPageWs() {
  return new Promise((resolve, reject) => {
    http.get(CDP_HTTP, res => {
      let body = ''
      res.on('data', d => body += d)
      res.on('end', () => {
        try {
          const data = JSON.parse(body)
          const page = data.find(t => t.type === 'page')
          page ? resolve(page.webSocketDebuggerUrl) : reject(new Error('no page'))
        } catch (e) { reject(e) }
      })
    }).on('error', reject)
  })
}

function makeClient(wsUrl) {
  // Use the `ws` package style API. Both `ws` and Node's built-in
  // WebSocket accept addEventListener / .on, but built-in WebSocket
  // requires addEventListener.
  const c = new WebSocket(wsUrl)
  let id = 1
  const pending = new Map()
  const onMsg = (data) => {
    const msg = JSON.parse(typeof data === 'string' ? data : data.toString())
    if (msg.id && pending.has(msg.id)) {
      const { resolve, reject } = pending.get(msg.id)
      pending.delete(msg.id)
      msg.error ? reject(new Error(JSON.stringify(msg.error))) : resolve(msg.result)
    }
  }
  if (c.addEventListener) {
    c.addEventListener('message', ev => onMsg(ev.data))
    c.addEventListener('error', err => {
      // surface on next send attempt
    })
  } else {
    c.on('message', onMsg)
  }

  function send(method, params = {}) {
    return new Promise((resolve, reject) => {
      const myId = id++
      pending.set(myId, { resolve, reject })
      c.send(JSON.stringify({ id: myId, method, params }))
    })
  }

  return new Promise((resolve, reject) => {
    if (c.addEventListener) {
      c.addEventListener('open', () => resolve({ c, send }))
    } else {
      c.on('open', () => resolve({ c, send }))
    }
  })
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)) }

async function evalExpr(send, expression, { awaitPromise = false } = {}) {
  const r = await send('Runtime.evaluate', {
    expression,
    returnByValue: true,
    awaitPromise,
  })
  if (r.exceptionDetails) {
    throw new Error(`JS error: ${r.exceptionDetails.text} :: ${r.exceptionDetails.exception?.description || ''}`)
  }
  // If the expression returned a string (e.g. via JSON.stringify in
  // the body), r.result.value is already a JSON string. If it
  // returned an object/array, we JSON-stringify it for consistency.
  const v = r.result.value
  if (typeof v === 'string') return v
  try { return JSON.stringify(v) } catch { return String(v) }
}

async function main() {
  const wsUrl = await getPageWs()
  console.log('Connecting to', wsUrl)
  const { c, send } = await makeClient(wsUrl)

  // Wait for the renderer to fully boot
  await sleep(5000)

  // Helper: log the visible state in a stable JSON form
  async function probeState() {
    return JSON.parse(await evalExpr(send, `(() => ({
      hasV4Wrap: !!document.querySelector('.v4-chat-wrap'),
      hasTextarea: !!document.querySelector('.v4-input__textarea'),
      hasSend: !!document.querySelector('.v4-input__send'),
      hasMode: !!document.querySelector('.v4-input__mode'),
      bodyText: document.body.innerText.slice(0, 200),
      errorVisible: document.body.innerText.includes('出现异常'),
    }))()`))
  }

  // Phase A: probe initial state
  console.log('\n=== Phase A: initial probe ===')
  let state = await probeState()
  console.log('  initial:', state)

  if (!state.hasV4Wrap) {
    // We need to either click the "新对话" button (creates + opens session)
    // OR an existing session row.
    // The "新对话" button at the top has "新对话\n1" or similar short text.
    // Walk through candidate buttons in order of priority:
    //   1. button whose visible text starts with "新对话" (create new session)
    //   2. any existing session row (button.group\/session)
    //   3. any project/workdir picker to seed a session first
    console.log('  No V4 panel yet — trying to open a session...')

    // Step 1: if a project picker is showing ("选择目录"), try to use
    // the file:// preview path or skip past it.
    const hasPicker = await evalExpr(send, `(() => {
      const labels = Array.from(document.querySelectorAll('button, [role=button]')).map(b => b.innerText.trim()).filter(Boolean);
      return JSON.stringify({hasPicker: labels.some(l => l.includes('选择目录') || l.includes('打开')), labels: labels.slice(0, 30)});
    })()`)
    const pickerInfo = JSON.parse(hasPicker)
    console.log('  picker info:', pickerInfo)

    // Try clicking 新对话 repeatedly until V4 panel mounts
    let attempts = 0
    while (attempts < 5) {
      const clicked = await evalExpr(send, `(async () => {
        // Find any button whose first line of innerText is exactly '新对话'
        const btns = Array.from(document.querySelectorAll('button'));
        for (const b of btns) {
          const text = (b.innerText || '').trim();
          if (text.startsWith('新对话')) {
            b.click();
            return JSON.stringify({clicked: text.slice(0, 30)});
          }
        }
        return JSON.stringify({noBtn: true});
      })()`, { awaitPromise: true })
      console.log(`  attempt ${attempts + 1}:`, clicked)
      attempts += 1
      await sleep(1500)
      state = await probeState()
      console.log('    state after click:', state)
      if (state.hasV4Wrap) break
    }
  }

  if (!state.hasV4Wrap) {
    console.log('ERROR: could not mount V4ChatPanel after 5 attempts')
    console.log('Dumping body:')
    console.log(await evalExpr(send, 'document.body.innerText'))
    c.close()
    process.exit(1)
  }

  // Phase B: fire a chat
  console.log('\n=== Phase B: fire chat ===')
  const fireResult = await evalExpr(send, `(async () => {
    const ta = document.querySelector('.v4-input__textarea');
    const btn = document.querySelector('.v4-input__send');
    const sel = document.querySelector('.v4-input__mode');
    if (!ta || !btn) return JSON.stringify({err: 'missing controls'});
    // Standard mode for tool call (uses get_current_time tool)
    if (sel) {
      sel.value = 'standard';
      sel.dispatchEvent(new Event('change', { bubbles: true }));
    }
    ta.focus();
    ta.value = '获取当前时间';
    // Vue 3 v-model listens for 'input' events
    ta.dispatchEvent(new Event('input', { bubbles: true }));
    await new Promise(r => setTimeout(r, 300));
    btn.click();
    return JSON.stringify({clicked: true, ta: ta.value});
  })()`, { awaitPromise: true })
  console.log('  fire result:', fireResult)

  // Phase C: mid-stream snapshot — catch thought + tool in flight
  console.log('\n=== Phase C: mid-stream snapshot ===')
  await sleep(3500)
  const midState = await probeState()
  const midDetail = JSON.parse(await evalExpr(send, `(() => ({
    thoughtBlocks: document.querySelectorAll('.v4-thought').length,
    toolCalls: document.querySelectorAll('.v4-tool').length,
    answers: document.querySelectorAll('.v4-answer').length,
    activeTurn: !!document.querySelector('.v4-turn--active'),
    turns: document.querySelectorAll('.v4-turn').length,
    thoughtTexts: Array.from(document.querySelectorAll('.v4-thought__text, .v4-thought')).map(e => (e.innerText||'').slice(0, 60)).filter(Boolean),
    toolNames: Array.from(document.querySelectorAll('.v4-tool__name')).map(e => e.innerText),
    answerTexts: Array.from(document.querySelectorAll('.v4-answer')).map(e => (e.innerText||'').slice(0, 200)).filter(Boolean),
    errorVisible: document.body.innerText.includes('出现异常'),
  }))()`))
  console.log('  state:', midState)
  console.log('  detail:', midDetail)

  // Save mid-stream DOM
  const midHtml = await evalExpr(send, `document.querySelector('.v4-chat-wrap')?.outerHTML || 'no wrap'`)
  fs.writeFileSync('/tmp/v4chat_streaming.html', midHtml)
  console.log('  streaming DOM saved (' + midHtml.length + ' chars) to /tmp/v4chat_streaming.html')

  // Phase D: wait for completion + final snapshot
  console.log('\n=== Phase D: completion snapshot ===')
  await sleep(15000)
  const finalDetail = JSON.parse(await evalExpr(send, `(() => ({
    thoughtBlocks: document.querySelectorAll('.v4-thought').length,
    toolCalls: document.querySelectorAll('.v4-tool').length,
    answers: document.querySelectorAll('.v4-answer').length,
    turns: document.querySelectorAll('.v4-turn').length,
    answerTexts: Array.from(document.querySelectorAll('.v4-answer')).map(e => (e.innerText||'').slice(0, 300)).filter(Boolean),
    errorVisible: document.body.innerText.includes('出现异常'),
    bodyErrors: document.body.innerText.split('\\n').filter(l => l.includes('ReferenceError') || l.includes('Error')).slice(0, 5),
  }))()`))
  console.log('  final:', finalDetail)

  const finalHtml = await evalExpr(send, `document.querySelector('.v4-chat-wrap')?.outerHTML || 'no wrap'`)
  fs.writeFileSync('/tmp/v4chat_final.html', finalHtml)
  console.log('  final DOM saved (' + finalHtml.length + ' chars) to /tmp/v4chat_final.html')

  // Phase E: verdict
  console.log('\n=== Verdict ===')
  let failed = 0
  function check(cond, msg) {
    console.log(`  ${cond ? 'ok' : 'FAIL'} - ${msg}`)
    if (!cond) failed++
  }
  check(!finalDetail.errorVisible, 'no error overlay visible in final DOM')
  check(finalDetail.bodyErrors.length === 0, 'no ReferenceError / Error in body')
  check(midDetail.thoughtBlocks > 0 || midDetail.toolCalls > 0,
        'mid-stream: thought OR tool rendered')
  check(finalDetail.answers > 0 || finalDetail.turns > 0,
        'final: at least one turn / answer in DOM')
  check(finalDetail.answerTexts.some(t => t.length > 5),
        'final: answer text has substance')

  c.close()
  console.log(`\n=== ${failed === 0 ? 'PASS' : 'FAIL'} (${failed} failures) ===`)
  process.exit(failed === 0 ? 0 : 1)
}

main().catch(e => {
  console.error('FATAL:', e.stack || e.message)
  process.exit(2)
})