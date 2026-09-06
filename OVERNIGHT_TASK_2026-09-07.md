# MadCop 夜间自治任务（2026-09-07 深夜 → 早晨）

> 本文档自包含，供夜间无人值守的编码智能体执行。执行者无需任何历史对话上下文。
> 目标：天亮时留下「已验证的本地 commit + 一份晨报」，而不是一堆未验证的改动。

---

## 〇、环境事实（先读）

- 仓库：`/Users/linruihan/PycharmProjects/madcop`（main 分支）
- 形态：Electron + Vue3 桌面端（`desktop/`）+ Python FastAPI 本地服务（仓库根，`madcop/`）
- 前端构建：`cd desktop && node ./node_modules/vite/bin/vite.js build`（产物 dist-vue/）
  - **注意**：`npm run build` 里的 `tsc -b` 有约 202 个**历史遗留**类型错误，与本次任务无关，**不要试图修完它们**，也不要因为 tsc 报错认为构建失败。以 `vite build` 成功为准。
- 后端：`cd /Users/linruihan/PycharmProjects/madcop && nohup env -u http_proxy -u https_proxy -u all_proxy -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY PYTHONUTF8=1 /Users/linruihan/.local/share/uv/python/cpython-3.11-macos-aarch64-none/bin/python3.11 -m madcop.server > /tmp/madcop_server.log 2>&1 &`
- 后端健康检查：`curl -s --noproxy '*' http://127.0.0.1:8765/api/health`
- Tailwind 根字号是 **13px**（非 16px）：所有 `text-lg/base/sm` 等 rem 类都会被等比缩小（text-lg = 14.625px）。标题一律用显式 `text-[18px]`/`text-[26px]`。

---

## 一、硬性红线（违反任何一条 = 立即停止该项任务）

1. **禁止 `git push`**。所有改动只做本地 commit，早晨由主人审查后手动推送（代理不稳定，且需要人工审查）。
2. **禁止写入/删除/移动 `~/.madcop/`**——那是真实的用户数据（供应商 key、会话、记忆）。只可读取用于分析。
3. **禁止升级依赖、修改 `desktop/package.json` 依赖版本、修改 `desktop/electron/` 打包配置**。
4. **禁止修改 `~/.zcode/`、`~/.codex/` 下任何文件**。
5. 每一个修复完成前必须通过 `vite build`（前端）或 Python 语法/导入检查（后端）。**没有验证的修复不算完成**。
6. 改坏了一处就 `git checkout -- <file>` 回滚该项，不要带病继续。
7. commit 信息格式：`chore(night): <一句话>` / `fix(night): <症状-根因-修法>`，按任务分组建 commit，不要把四个任务混进一个 commit。

---

## 二、任务 A：死功能扫描（优先级最高）

目标：找出「界面上有入口/代码里有定义，但实际走不通」的死功能并修复或移除。

扫描清单（逐项做，产出物进晨报）：

1. **按钮/菜单 → 空实现**：在 `desktop/src/vue/` 中 grep 所有 `@click="` 处理器，标记指向不存在函数、函数体只有 `pass`/`console.log`/TODO 的。
2. **注册了但不可达的工具**：`madcop/tools/__init__.py` 中注册的工具（如 MarketQuote/Quant/Paper 系列、CronScheduler）逐一确认前端是否有调用路径、后端是否有路由。
3. **i18n 引用缺失**：扫 `t('...')` 引用的 key 是否在 `i18n/locales/zh.ts` 中存在（历史上有 `settings.skills.distill` 泄漏的先例，已修，但要确认没有同类）。
4. **路由/tab 死链**：`tabStore.openTab` 的调用里 type/id 不存在对应页面组件的。
5. **设置页死控件**：17 个设置子页中 disabled 且永不可用的按钮、指向不存在 API 的操作（重点核对 `settings/exec-policy`、`meta-harness`、`h5-access` 三处的按钮 → 后端路由逐一对照）。

处置原则：**能修则修（补上真实实现或正确引用）；修不动（需要产品决策）就记录进晨报，不要硬删功能入口。** 纯死代码（确认全仓库无引用）才可删除，删除前 grep 三遍。

## 三、任务 B：架构优化（保守，只做安全项）

1. **raw fetch 统一**：`grep -rn "fetch('/api\|fetch(\`/api" desktop/src/vue/` 仍有约 35 处裸调用（当前有 window.fetch shim 兜底所以不是 bug，但 H5 远程模式下 shim 不生效）。统一改为 `getApiUrl()`。**注意**：`components/layout/AppShell.vue` 的 `/api/health` 探测等启动关键路径改动后必须仔细验证。
2. **明显的重复代码块**：只在「同一段 20+ 行代码出现 ≥3 次」时才合并，合并后跑构建。
3. **死代码**：确认无引用的组件/函数/常量可删（用 grep 全仓库验证）。
4. **不做的事**：不重命名跨文件导出、不调整目录结构、不引入新抽象层、不改 store 的持久化格式。保守的意思是：早晨的人能 5 分钟看完每个 diff。

## 四、任务 C：前端适配检查

1. **rem 陷阱扩展扫描**：搜索 `text-lg|text-xl|text-2xl|text-base` 在 `h1/h2/h3、页面标题、modal 标题` 上的使用（13px root 下 text-lg=14.6px，太小）。页面级标题应显式 `text-[18px]`（设置内页）或 `text-[26px]`（独立页）。正文/说明性文字的 text-sm/text-base **不动**（那是既定档位）。
2. **深色主题硬编码残留**：`grep -rn "text-white\|#fff\b" --include="*.vue" desktop/src/vue/ | grep -v on-primary` 找背景为深色/brand 但文字写死白色的组合（上一轮修了 39 处，重点复查 `.ts` 文件里的动态 class 拼接和内联 style）。
3. **界面缩放**：确认 `界面的 zoom` 调节（设置里 50%-150%）下 `position: fixed` 元素（composer、onboarding 弹窗）不错位——代码层面检查即可，不必真开浏览器。
4. **中英混排**：`t('...')` 的 key 在 zh.ts 有而 en.ts 缺（或反之）的，补齐（先例：`settings.skills.distill`、`settings.providers.quickConnect`）。

## 五、任务 D：审美一致性（代码级）

1. 奇数尺寸复查：`12.5px` 已清零，再确认无 `11.5px/13.5px/14.5px` 等半像素残留（界面缩放计算产生的 11.375px 属正常，不管）。
2. 图标尺寸档位：`material-symbols-outlined` 的 `text-[Npx]` 应收敛在 {14, 16, 18, 20, 24}，列出超档的并归档。
3. 圆角档位：`rounded-[Npx]` 应收敛在 {4, 6, 8, 10, 12, 14, 16, 24, 999px}，列出超档项。
4. 颜色字面量：`.vue` 里 `#[0-9a-fA-F]{6}` 出现在 `background/color/border` 且未包 `var(--...)` 的，逐个判断：语义色（成功绿/错误红）保留，装饰色改 token。**只改确定项**，拿不准的记录。

## 六、明确不要修的已知问题（已定性，别浪费时间）

| 问题 | 定性 |
|---|---|
| MiniMax-M3 在长会话中幻觉写入文件 | 模型能力边界，引擎已有三层防护，等换模型 |
| 「关于」页版本号显示"未知版本" | 打包问题：dev 运行的 Electron 二进制没有产品版本号 |
| 侧栏里失败会话的残留条目 | 需要产品决策（自动清理 vs 手动） |
| tsc ~202 个类型错误 | 历史遗留，vite build 不受影响 |
| 环境诊断页指标显示"—" | 空态设计问题，低优先级 |
| Agent 拓扑模板缩略图与真实画布风格差 | 插画资产重绘，需要设计资源 |

## 七、收尾（天亮前必做）

1. `vite build` 最终跑一次，确认通过。
2. 写晨报到仓库根：`MORNING_REPORT_2026-09-07.md`，包含：
   - 每个任务的「发现 N 处 → 修复 M 处 → 跳过 K 处（原因）」
   - 所有 commit 的 hash + 一句话说明
   - 你认为需要人工决策的遗留清单（按严重度排序）
   - 如果某项任务完全没做，写明原因（卡住/超时/判断超出安全范围）
3. `git add -A && git commit`（**不要 push**）。
4. 如果改了后端 Python：`python3 -m py_compile <改动文件>` 逐个验证；如果 madcop server 正在运行（8765 端口），**不要 kill 它**——记录"需重启生效"进晨报即可。

---

## 附：启动 prompt（复制给夜间执行的智能体）

```
读取并完整执行 /Users/linruihan/PycharmProjects/madcop/OVERNIGHT_TASK_2026-09-07.md。
该文档自包含（环境、红线、四个任务、验证标准、已知问题清单）。
严格遵守文档第一节的 7 条红线，特别是：禁止 git push、禁止写 ~/.madcop、
每个修复必须 vite build 通过。按 任务A→B→C→D 顺序执行，边做边本地 commit，
最后按文档第七节写 MORNING_REPORT_2026-09-07.md 并 commit（不要 push）。
如果文档不存在或与仓库现状冲突，停止并说明，不要猜测。
```
