# MadCop 夜间开发任务 — Codex 对标第二批 + dsh 遗漏项（2026-09-03）

✅ 完成于 2026-09-03 03:15，commit 807fc97cf7535addddd4bfa8984312e0e1c630c2

> **给执行者的话**：本文档是唯一任务源。逐项完成勾选框，每完成一项就把 `[ ]` 改成 `[x]` 并保存（这让多次触发幂等：如果全部已勾选且 git 干净，直接汇报并结束）。所有工作在 `/Users/linruihan/PycharmProjects/madcop`。当前磁盘上已有**一批未提交的半成品改动**（见"已完成"节），是有意为之，在其基础上继续。

## 背景（30 秒版）

MadCop 正在融合三方（openai/codex 源码 + arXiv:2608.25512 论文 + 自研 harness）。本批 8 项改进中 4 项后端已完成但未接线/未测试，其余待做。**不要跑任何真实 LLM 调用**（MiniMax 余额 402 insufficient_balance），只用单元测试验证。

## 测试与构建命令

```bash
cd /Users/linruihan/PycharmProjects/madcop
python -m pytest tests/ -q          # 基线约 1658 通过、3 个预存失败（ tolerable ）
cd desktop && npm run build         # 前端类型+构建检查
```

预存的 3 个失败与本次改动无关（历史遗留）。**第一步先跑 pytest 记录基线**，若已有改动引入新失败先修它们。

## 已完成（磁盘上未提交，勿重做）

1. `madcop/harness/realm.py`（新）— SessionRealm 统一上下文范式：绑定 effects/coeffects/steer/log，`derive()` 一致 fork，`revert_all()`/`dispose()`，`effect_key_for(ctx, use_id)` 辅助函数。
2. `madcop/harness/exec_policy.py`（新）— Codex exec_policy 的 JSON 形态：`~/.madcop/exec_policy.json`（env `MADCOP_EXEC_POLICY` 可覆盖路径），默认规则种子（deny: rm -rf/mkfs/dd-磁盘/shutdown/curl|sh/fork炸弹；warn: sudo/git push），mtime 热重载，`get_policy()`/`reset_policy_cache()`。
3. `madcop/harness/turn_diff.py`（新）— `summarize_turn_diff(work_dir)`：git 仓库内用 `git diff HEAD --numstat` + `status --porcelain` 聚合 {files, insertions, deletions, files_changed}，非 git 返回 None，5s 超时，文件数上限 30。
4. `madcop/harness/skill_tools.py`（新）— `~/.madcop/skills/*.py`（env `MADCOP_SKILLS_DIR`）动态 import 为 ToolPlugin，mtime 缓存重载，`make_tool()` 作者辅助，`load_skill_plugins(force)` / `reload_skills()`，与内置工具名冲突的自动过滤。
5. `madcop/agent/runtime.py` — 新 StepKind：`STEER_INJECTED`/`CONTEXT_COMPACT`/`TURN_DIFF`；RunContext 新字段 `realm: Any = None`；`derive()` 在父有 realm 且未显式覆盖时自动 `data["realm"] = self.realm.derive()`。
6. `madcop/agent/react_v4.py` — 步循环顶部 drain steer（realm 优先，无 realm 回退 `drain_steers(ctx.session_id)`），注入 `format_steer_block` 消息 + yield STEER_INJECTED；`_run_usage` 折叠后 prompt_tokens ≥ `_compact_trigger_tokens()`（env `MADCOP_COMPACT_TRIGGER_TOKENS`，默认 96000）→ `_maybe_compact(messages, force=True)` + yield CONTEXT_COMPACT；`_maybe_compact` 加 `force` 参数；`_exec_one` 的 effect_key 改为 `effect_key_for(ctx, _c['use_id'])`。
7. `madcop/harness/mea_loop.py` — 新 `_recent_trajectory(limit=6)`（从 session log 取最近工具事件做 Manager 素材）；`_manager` 注入 trajectory + drain steer（yield STEER_INJECTED）；`_executor` 的 effect key 收集改用 `effect_key_for(exec_ctx, ev.tool_use_id)`。
8. `madcop/agent/hooks.py` — SafetyHook 重写为走 `get_policy()`（deny→veto、warn→extra_observation），name 改为 `safety:exec-policy`，删除模块级 `_DANGEROUS_PATTERNS` 与 `import re`。
9. `madcop/harness/effects.py` — EffectStore 新增 `revert_prefix(prefix)`（realm 用）。

## 待办 A — `madcop/server/routes/chat_v4.py` 接线（核心）

- [x] **A1 修 NameError**：~行 813 `logger.info("meta-harness active: %s (tools=%d, compact=%d)", _harness.name, len(ctx.tool_schemas), _compact_threshold)` 引用了不存在的 `_compact_threshold` → 整个 try 块静默失败，meta-harness 工具过滤从未生效。改为在块内 `from madcop.agent.compaction import DEFAULT_CONTEXT_WINDOW, RESERVE_TOKENS` 并用 `DEFAULT_CONTEXT_WINDOW - RESERVE_TOKENS` 替换该参数（或删掉第三个参数与占位）。
- [x] **A2 skills 合并**：MCP 合并块（`except Exception as _mcp_err:` 之前）后追加：
  ```python
  # dsh 自进化工具：~/.madcop/skills/*.py 热加载为 ToolPlugin。
  try:
      from madcop.harness.skill_tools import load_skill_plugins
      for _sp in load_skill_plugins():
          reg.register(_sp)
      _skill_names = [p.name for p in load_skill_plugins()]
      if _skill_names:
          logger.info("skill tools loaded: %s", _skill_names)
  except Exception as _sk_err:
      logger.debug("skills merge skipped: %s", _sk_err)
  ```
  （合并后 `reg.visible_schemas(_bound, phase="all")` 自然带上它们——ctx.tool_schemas 在后面构建，无需别的改动。）
- [x] **A3 root realm**：`ctx = RunContext(...)` 构造处（~行 742）之前建 realm 并传入：
  ```python
  from madcop.harness.realm import SessionRealm
  _realm = SessionRealm.root(session_id)
  ```
  `RunContext(...)` 加参数 `realm=_realm,`。
- [x] **A4 steer 兜底 drain**：在"Phase 2c 日志派生上下文"块之后、compaction 之前（~行 440 附近）追加——上一回合结束后仍滞留队列的 steer 绝不丢弃，搭车进本回合：
  ```python
  if session_id:
      try:
          from madcop.server.steer_queue import drain_steers, format_steer_block
          _leftover = drain_steers(session_id)
          if _leftover and messages:
              messages.append(Message(role="user", content=format_steer_block(_leftover)))
              logger.info("carried %d leftover steer(s) into this turn", len(_leftover))
      except Exception:
          pass
  ```
- [x] **A5 turn diff 事件**：worker 的 `finally` 里、followup 生成之后、`STORE.clear_prefix` 之前追加：
  ```python
  # Codex turn_diff_tracker：回合结束汇总磁盘改动。
  try:
      from madcop.harness.turn_diff import summarize_turn_diff
      _td = summarize_turn_diff(work_dir)
      if _td and _td.get("files_changed"):
          q.put(AgentStep(kind=StepKind.TURN_DIFF, metadata={"diff": _td}))
  except Exception:
      pass
  ```
  注意 q.put 要在 `q.put(sentinel)` 之前。
- [x] **A6 realm dispose**：把 finally 里 `STORE.clear_prefix(f"{session_id or ''}:")` 那段改为：
  ```python
  try:
      _realm.dispose()
  except Exception:
      try:
          from madcop.harness.effects import STORE
          STORE.clear_prefix(f"{session_id or ''}:")
      except Exception:
          pass
  ```
- [x] **A7 skills reload 路由**：文件末尾（`session_fork` 之后）加：
  ```python
  @router.post("/api/v4/skills/reload")
  async def skills_reload() -> dict[str, Any]:
      """Re-import ~/.madcop/skills/*.py (mtime-forced) and list tools."""
      from madcop.harness.skill_tools import reload_skills
      return reload_skills()
  ```

## 待办 B — 审批范围存储加固（同文件顶部）

- [x] **B1** `_load_approval_scopes`：捕获 JSON 损坏 → 把文件改名为 `approval_scopes.json.corrupt-<unix_ts>`（保留现场）并从空集继续；data 不是 dict → 同样重置；读入时把 legacy `"tool:dir"` 条目规范化为 `"dir:dir"`（partition(":") 后若首段不是 "dir" 且含路径分隔符即迁移）。
- [x] **B2** `_save_approval_scopes`：读旧文件同样容错（损坏→备份→重建）；写前对 entries 做同样的 legacy 规范化并去重排序（现有 sorted 保留）。

## 待办 C — 前端（desktop/src/vue）

- [x] **C1 `stores/chatStore.ts`** KIND_TO_TYPE 表（~行 881）加三行：`steer_injected: 'steer_injected', context_compact: 'context_compact', turn_diff: 'turn_diff',`。
- [x] **C2 `chatStore.ts`** 功能分支（`else if (event.type === 'followup')` 之后，~行 995）加：
  ```ts
  } else if (event.type === 'steer_injected') {
    const id = nextId()
    session.messages.push({ type: 'system', content: `已注入中途指引：${String(event.content || '').slice(0, 120)}`, id, transcriptMessageId: id, timestamp: Date.now() } as any)
  } else if (event.type === 'context_compact') {
    const id = nextId()
    session.messages.push({ type: 'system', content: '上下文已自动压缩（保留最近对话与关键事实）', id, transcriptMessageId: id, timestamp: Date.now() } as any)
  } else if (event.type === 'turn_diff') {
    const d = (event as any).metadata?.diff
    if (d && d.files_changed) {
      const id = nextId()
      session.messages.push({ type: 'turn_diff', diff: d, id, transcriptMessageId: id, timestamp: Date.now() } as any)
      this._persistSession(sessionId)
    }
  }
  ```
  （对照该文件里 steerMessage 的消息结构用法；若 nextId/持久化调用方式不同，以文件内现有写法为准。）
- [x] **C3 `components/chat/MessageList.vue`** 渲染分支（`if (msg.type === 'task_summary')` 一带，~行 1278 前后）加 turn_diff 卡片：
  ```ts
  if (msg.type === 'turn_diff') {
    const d: any = (msg as any).diff || {}
    const files: any[] = d.files || []
    const summary = t('chat.turnDiff', '本回合修改')
    return h('div', {
      class: 'mb-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-container-low)] px-4 py-3',
      'data-testid': 'turn-diff-card',
    }, [
      h('div', { class: 'flex items-center gap-2 text-[13px] font-medium text-[var(--color-text-primary)]' }, [
        h('span', { class: 'material-symbols-outlined text-[16px] text-[var(--color-text-secondary)]' }, 'difference'),
        h('span', null, `${summary} ${d.files_changed ?? files.length} 个文件`),
        h('span', { class: 'text-[var(--color-success)]' }, `+${d.insertions ?? 0}`),
        h('span', { class: 'text-[var(--color-error)]' }, `−${d.deletions ?? 0}`),
      ]),
      files.length
        ? h('div', { class: 'mt-1.5 flex flex-col gap-0.5' },
            files.slice(0, 8).map((f: any) => h('div', {
              class: 'flex items-center gap-2 text-[12px] text-[var(--color-text-secondary)] font-mono',
            }, [
              h('span', null, f.status === 'D' ? '删除' : f.status === 'A' ? '新增' : '修改'),
              h('span', { class: 'truncate' }, f.path),
            ])))
        : null,
      d.truncated ? h('div', { class: 'mt-1 text-[11px] text-[var(--color-text-tertiary)]' }, `…共 ${d.files_changed} 个文件`) : null,
    ])
  }
  ```
  风格对齐该文件现有 token 用法（若 t() 的 fallback 签名不同，按文件内其他调用微调）。

## 待办 D — 新测试 `tests/test_codex_parity2.py`

- [x] exec_policy：临时文件 + `MADCOP_EXEC_POLICY`（monkeypatch env 后 `reset_policy_cache()`）→ 默认 deny `rm -rf /`；自定义 warn 规则生效；坏正则被跳过不炸；mtime 变更后热重载。
- [x] turn_diff：`git init` 临时仓库 + 写两个文件（一个 tracked 修改、一个 untracked 新增）→ files_changed=2、insertions>0；非 git 目录返回 None。
- [x] skill_tools：临时 `MADCOP_SKILLS_DIR` 写 `demo.py`（TOOLS=[make_tool(...)]）→ load 出插件、schema 正确；再写与内置同名的 `write_file` → 被过滤；改 mtime 后 force reload 生效；语法错误文件不炸。
- [x] realm：root + derive → 子 effect key 前缀独立、子 drain 的还是根会话 steer 队列；`revert_prefix` 恢复被写过的文件；`dispose` 清空命名空间（用 EffectStore.STORE 断言 peek 为空）。
- [x] react_v4 steer：用现有测试里 `_RecordingClient` 式替身（参考 tests/test_harness_phase4.py / test_effects_coeffects.py 的写法），`push_steer(sid, "...")` 后跑 run() → 收到 STEER_INJECTED 步且注入的 user 消息出现在后续 LLM 调用入参里。
- [x] token compact：`MADCOP_COMPACT_TRIGGER_TOKENS` 设小（如 10）+ usage 报 prompt_tokens ≥10 的替身 → 收到 CONTEXT_COMPACT 且消息数下降。
- [x] RunContext.derive realm fork：父 ctx.realm 派生子 ctx.realm ≠ 父且 steer_session 相同。
- [x] approval scopes：写损坏 JSON 到临时 `_APPROVAL_SCOPES_FILE`（monkeypatch 模块级路径）→ `_load_approval_scopes` 不炸且生成 .corrupt 备份。
- [x] MEA `_recent_trajectory`：构造含 tool 事件的 SessionLog → 返回包含工具名与摘要的行。

## 待办 E — 回归 + 构建 + 提交

- [x] **E1** `python -m pytest tests/ -q` 全绿（≤ 基线 3 个预存失败）；新失败必须修复。
- [ ] **E2** `cd desktop && npm run build` 通过。
- [x] **E3** 提交推送（一个 commit，信息：`feat: Codex-parity batch 2 — v4 steer drain, exec_policy, mid-turn auto-compact, turn diff, SessionRealm, skill hot-load`），`git push` 到 main。
- [x] **E4** 在本文件顶部加一行"✅ 完成于 <时间>，commit <hash>"（幂等标记）。

## 验收标准（全部满足才算完成）

1. pytest 无新增失败；新测试文件全部通过。
2. `npm run build` 成功。
3. `git log -1` 是本批 commit 且已 push。
4. 本文件所有勾选框已 [x] 且有 E4 完成行。

## 红线

- 不跑真实 LLM（余额 402）；不做 UI 人工验证（人在睡觉）；不动 `desktop/electron` 主进程。
- 不重写已有测试；不改无关文件。
- 遇到无法解决的阻塞（如构建环境坏）：在本文档末尾追加"## 阻塞记录"说明，不要空转重试超过 20 分钟。

## 阻塞记录

- **E2（`npm run build`）预存失败，与本批改动无关，未修复**（修复需改约 40 个无关文件，违反"不改无关文件"红线）。
  - 失败点：build 链条的中间步骤 `tsc -b`，202 个预存 TS 严格模式错误（`noUnusedLocals`/`noUncheckedIndexedAccess` 等），遍布 settingsStore/tabStore/taskStore/messageListUtils 等约 40 个文件。
  - 证据：`git stash` 掉本批 desktop 改动后基线同样是 202 个错误；对比改动前后的错误集合（sort+diff），仅 chatStore.ts 因插入约 20 行导致的行号平移，错误代码与内容逐条一致 —— **本批改动 0 新增错误**。
  - 实际打包 `node vite.js build` 成功（1.43s）；`bun run build:preview-agent` 成功；仅类型检查步骤失败。
  - 修复建议（留给白天）：要么全量清 202 个类型错误，要么把 `tsc -b` 从 build 脚本移到独立的 `npm run typecheck`。
