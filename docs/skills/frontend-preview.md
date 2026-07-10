---
name: frontend-preview
description: 实时 HTML 预览 — 让 agent 写前端页面并在 MadCop 中实时预览
triggers:
  - "帮我生成一个页面"
  - "帮我写一个前端页面"
  - "生成 HTML"
  - "preview"
  - "实时预览"
  - "写一个登录页"
  - "帮我做个页面"
created_at: "2026-07-06"
updated_at: "2026-07-06"
source: manual
version: "1.0"
tags:
  - frontend
  - html
  - preview
  - design
---

# 实时 HTML 预览

## 工作流

当你需要生成前端页面时，使用以下流程：

### 1. 生成 HTML 文件

用 `WriteFileTool` 将 HTML 写入 `~/.madcop/preview/index.html`：

```
WriteFileTool(path="~/.madcop/preview/index.html", content="<!DOCTYPE html>...")
```

**重要规则**：
- 文件名必须是 `index.html`（预览面板自动加载这个文件）
- CSS 和 JS 写在同一个文件里（单文件 HTML，不需要额外资源）
- 可以引入 CDN 资源（如 Tailwind CDN、Font Awesome 等）
- 使用 Tailwind CDN: `<script src="https://cdn.tailwindcss.com"></script>`
- 推荐 1280×800 左右的尺寸设计

### 2. 预览会自动刷新

MadCop 的预览面板每 2 秒自动检测 `~/.madcop/preview/index.html` 的变化，无需手动刷新。

### 3. 迭代修改

用户说"改大标题颜色"或"把按钮放右边"时：
1. 用 `ReadFileTool` 读取当前的 `~/.madcop/preview/index.html`
2. 修改内容
3. 用 `WriteFileTool` 写回
4. 预览面板会在 2 秒内自动刷新

## 模板示例

### 基础 HTML 模板
```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <script src="https://cdn.tailwindcss.com"></script>
  <title>页面标题</title>
</head>
<body class="bg-gray-50 min-h-screen">
  <div class="container mx-auto px-4 py-8">
    <!-- 内容 -->
  </div>
</body>
</html>
```

### 使用场景
- **登录页**：Tailwind 居中卡片布局，邮箱+密码输入框，登录按钮
- **仪表盘**：网格卡片布局，显示数据指标
- **落地页**：大标题+副标题+CTA按钮+功能列表
- **个人中心**：头像+昵称+设置项列表
- **数据表格**：表格+搜索+分页

### 设计原则
- 使用 Tailwind CDN 快速成型
- 优先考虑响应式设计
- 保持简洁，不要过度设计
- 颜色使用 Tailwind 默认色板（gray, blue, green, red 等）

## 错误处理

| 问题 | 原因 | 解决 |
|------|------|------|
| 预览空白 | HTML 语法错误 | 检查标签闭合，用浏览器 DevTools 调试 |
| 样式不对 | Tailwind CDN 未加载 | 确保加了 `<script src="https://cdn.tailwindcss.com">` |
| 图片没显示 | 用了本地路径 | 改用 CDN 或 base64 嵌入 |
| 布局错乱 | 缺少 viewport meta | 加 `<meta name="viewport" content="width=device-width">` |