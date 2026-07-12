# MadCop 构建与测试交接文档

> 给：接手的 agent
> 流程：每次改完代码 → 构建 → 交给用户测试

---

## 一、一键构建 + 启动

```bash
cd /Users/linruihan/PycharmProjects/madcop

# 1. 后端 (必须)
uvicorn madcop.server.app:app --host 127.0.0.1 --port 8765

# 2. 前端 (Vue 3 dev + Electron)
cd desktop
bun run electron:dev
```

> `electron:dev` 会自动：build electron → 启动 Vite (port 1420) → 等待 Vite 就绪 → 启动 Electron 窗口

---

## 二、纯前端构建（不启动 Electron）

```bash
cd /Users/linruihan/PycharmProjects/madcop/desktop

# Vue 3 构建
npx vite build --config vite.vue.config.ts

# 输出到 dist-vue/
# 构建产物: dist-vue/index.html + dist-vue/assets/
```

---

## 三、Electron 构建

```bash
cd /Users/linruihan/PycharmProjects/madcop/desktop

# 只构建 Electron main process
bun build ./electron/main.ts \
  --outfile ./electron-dist/main.cjs \
  --target node --format cjs \
  --external electron --external node-pty

# 构建 preload
bun build ./electron/preload.ts \
  --outfile ./electron-dist/preload.cjs \
  --target node --format cjs --external electron

# 构建 preview-preload
bun build ./electron/preview-preload.ts \
  --outfile ./electron-dist/preview-preload.cjs \
  --target node --format cjs --external electron
```

---

## 四、每次修改代码后必须做的事

### 4.1 后端改动

```bash
# 改完 .py 文件后重启后端
lsof -ti:8765 | xargs -r kill -9
uvicorn madcop.server.app:app --host 127.0.0.1 --port 8765

# 跑测试
cd /Users/linruihan/PycharmProjects/madcop
python3 -m pytest tests/ -q --tb=no
# 预期: 1321 passed
```

### 4.2 前端改动

```bash
# 改完 .vue / .ts 文件后
# 方案 A: Vite HMR 自动热更新（改代码后 Electron 窗口自动刷新）
# 方案 B: 手动触发刷新 → Electron 窗口按 Cmd+R

# 验证构建
cd /Users/linruihan/PycharmProjects/madcop/desktop
npx vite build --config vite.vue.config.ts
# 预期: ✓ built in X.XXs
```

### 4.3 Electron 主进程改动

```bash
# 改完 electron/main.ts 后必须重新 build electron
cd /Users/linruihan/PycharmProjects/madcop/desktop
bun run build:electron

# 然后重启
# 先杀掉旧 Electron 进程
ps aux | grep -i "Electron" | grep -v grep | awk '{print $2}' | xargs -r kill -9
# 重新启动 electron:dev
bun run electron:dev
```

---

## 五、给用户测试的步骤

### 每次改完交给用户时，按这个顺序确认：

```
□ 1. 后端健康: curl http://127.0.0.1:8765/api/health → {"status":"ok"}
□ 2. 1321 测试全过: python3 -m pytest tests/ -q --tb=no
□ 3. Vue 构建通过: npx vite build --config vite.vue.config.ts
□ 4. Electron main.cjs 构建通过: bun run build:electron
□ 5. 启动后 Electron 窗口可见（osascript 检测 "Electron" 进程）
□ 6. 前端 build 输出到 dist-vue/（有 index.html）
□ 7. Github 推送: git push origin main
```

### 如果 Electron 窗口不显示

```bash
# 1. 检查进程
ps aux | grep -i "Electron" | grep -v grep

# 2. 检查窗口是否存在 (用 Quartz)
python3 -c "
import Quartz
opts = Quartz.kCGWindowListOptionAll
for w in Quartz.CGWindowListCopyWindowInfo(opts, Quartz.kCGNullWindowID):
    if w.get('kCGWindowOwnerName') == 'Electron' and 'MadCop' in w.get('kCGWindowName', ''):
        print(f'窗口存在: 位置={w.get(\"kCGWindowBounds\")} onscreen={w.get(\"kCGWindowIsOnscreen\")}')
"

# 3. 强制激活窗口
osascript -e 'tell application id "com.github.Electron" to activate'
```

---

## 六、常见问题

### Q: Electron 启动后窗口在屏幕外？
```bash
# 修改 electron/main.ts 中的 createMainWindow()
# 强制主屏居中:
const primaryDisplay = screen.getPrimaryDisplay()
const workArea = primaryDisplay.workArea
x: Math.max(workArea.x, workArea.x + (workArea.width - 1280) / 2),
y: Math.max(workArea.y, workArea.y + (workArea.height - 820) / 2),
width: 1280, height: 820,
```

### Q: Vite 启动 React 不是 Vue？
`electron:dev` 必须用 `vite.vue.dev.config.ts`（不是 `vite.config.ts`）。
检查 `scripts/electron-dev.ts` 中的 `--config` 参数：

```typescript
const vite = Bun.spawn(['bun', 'x', 'vite', '--config', 'vite.vue.dev.config.ts'], ...)
```

### Q: electron 提示 "Downloading Electron binary..." 然后失败？
```bash
# 本地已有 Electron binary，跳过下载
# 检查 scripts/electron-dev.ts 中 electron bin 路径:
const electronBin = path.join(desktopRoot, 'node_modules', 'electron', 'dist', 'Electron.app', 'Contents', 'MacOS', 'Electron')
```

### Q: 前端改了但 Electron 没更新？
- 如果 Vite 在跑 → 按 `Cmd+R` 刷新 Electron 窗口
- 如果改了 electron/main.ts → 必须重新 `bun run build:electron`
- 如果改了 vite.vue.dev.config.ts → 重启整个 `electron:dev`

### Q: GitHub push 超时？
```bash
# 国内网络问题，重试
git push origin main
# 如果连续失败，等网络恢复再推
```

---

## 七、关键路径速查

| 操作 | 命令 | 耗时 |
|---|---|---|
| 启动后端 | `uvicorn madcop.server.app:app --host 127.0.0.1 --port 8765` | 2s |
| 启动 Electron | `cd desktop && bun run electron:dev` | 30s |
| 跑测试 | `python3 -m pytest tests/ -q --tb=no` | 30s |
| 前端构建 | `npx vite build --config vite.vue.config.ts` | 2s |
| Electron 构建 | `bun run build:electron` | 1s |
| git push | `git push origin main` | 5s-∞ |
| 全量重来 | `kill -9 && 后端 + electron:dev` | 40s |

---

## 八、产出物位置

| 产物 | 路径 |
|---|---|
| Vue 3 构建输出 | `desktop/dist-vue/` |
| Electron main.cjs | `desktop/electron-dist/main.cjs` |
| Electron preload | `desktop/electron-dist/preload.cjs` |
| 测试报告 | `pytest` 输出 |
| Git 提交历史 | `git log --oneline -20` |

---

## 九、最后一句

**改完代码 → 构建通过 → 测试通过 → 用户测试 → 确认 OK → git push**