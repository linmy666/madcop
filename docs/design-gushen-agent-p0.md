# 股神 Agent P0 — 设计草图（研究级，不下真单）

> 状态：**P0 + 前端预设 + 模拟盘 已实现** — 2026-07-18  
> 原则：**数字只能来自工具**；模型只解释；**禁止真实下单**（仅 paper_* 模拟）  
> 单测：`tests/tools/test_market.py` + `test_quant.py` + `test_paper.py`

与 `docs/handover-2026-07-18.md` 独立；本文件可进仓（设计文档），实现时另开 commit。

---

## 1. P0 目标（Done 定义）

用户可以说：

> 「股神帮我看一下 AAPL / 00700 最近动量，给个结构化观点」

系统应：

1. 路由到 **股神** subagent（或拓扑节点）
2. 调用 **行情工具** 拿真实 OHLCV / 报价（不是模型编的）
3. 可选：算简单因子 + 极简回测摘要
4. 输出固定结构报告 + 免责声明
5. **没有任何券商 API / 下单工具**

非目标（P0 不做）：

- 真钱交易、券商 OAuth
- 高频 / 毫秒级
- 完整 quant 平台 UI
- 保证收益话术

---

## 2. 架构落点（对齐现有 MadCop）

```
用户消息 / 拓扑 run-adhoc
        │
        ▼
  Subagent「gushen」  (builtins 或 YAML)
        │  tools allow-list
        ├── market_quote
        ├── market_history
        ├── quant_factors      (可选同一文件)
        ├── quant_backtest_simple
        ├── web_search / web_fetch   (新闻，已有)
        ├── read / write             (报告落盘，已有；目录限制)
        └── get_time                 (已有)
        │
        ▼
  ~/.madcop/quant/   (cache + reports + watchlist)
```

参考现有模式：

| 能力 | 抄谁 |
|------|------|
| Tool 类 | `madcop/tools/weather.py` + `registry.Tool` |
| 注册 | `madcop/tools/__init__.py` → `default_registry()` |
| Subagent | `madcop/agent/subagent/builtins.py` 或用户 YAML `load_subagent_specs` |
| 拓扑预设 | `AgentOverview.vue` 的 `presets[]` 加一项「股神研报」 |
| 技能文档 | `docs/skills/gushen-quant.md`（给模型/人看） |
| 权限 | 写文件仅允许 `~/.madcop/quant/`（与 preview 目录策略类似） |

---

## 3. 文件清单（建议路径）

### 3.1 必做（P0 最小可跑）

| 路径 | 说明 |
|------|------|
| `madcop/tools/market.py` | `MarketQuoteTool` + `MarketHistoryTool` |
| `madcop/tools/quant.py` | `QuantFactorsTool` + `QuantBacktestSimpleTool` |
| `madcop/tools/__init__.py` | 注册上述 tools；`WriteFileTool` allowlist 加 quant 目录 |
| `madcop/agent/subagent/builtins.py` | 增加 `GUSHEN` → `BUILTIN_SUBAGENTS` |
| `docs/skills/gushen-quant.md` | 角色职责、输出模板、禁止事项 |
| `tests/tools/test_market.py` | mock HTTP，不打真网（CI 稳定） |
| `tests/tools/test_quant.py` | 固定 synthetic OHLCV 测因子/回测 |

### 3.2 建议（P0.5，仍可不碰前端）

| 路径 | 说明 |
|------|------|
| `madcop/quant/__init__.py` | 包入口 |
| `madcop/quant/providers/yahoo.py` | 行情适配（urllib + JSON；可选以后换源） |
| `madcop/quant/factors.py` | SMA / 动量 / 波动 纯函数 |
| `madcop/quant/backtest.py` | 单标的 buy&hold vs SMA cross 极简 |
| `madcop/quant/store.py` | `QuantStore`：`~/.madcop/quant/` 读写 |
| `subagents/gushen.yaml` | 用户可改版（loader 已支持）备选，与 builtin 二选一即可 |

### 3.3 前端（可第二周）

| 路径 | 说明 |
|------|------|
| `desktop/src/vue/pages/AgentOverview.vue` | 拓扑预设：`股神研报`（gushen → risk 可选） |
| `desktop/src/vue/lib/spriteStudio.ts` | roster 显示名/色（可选金/绿） |
| 无新大页 | P0 用聊天 + 附件报告即可 |

### 3.4 明确不建（P0）

- `madcop/tools/broker_*.py`
- 任何 `place_order` / `cancel_order`
- 密钥进 prompt

---

## 4. 工具接口草图

命名与 OpenAI function-calling 一致；返回 **JSON 可序列化 dict**，由 `ToolResult.to_message_content` 转字符串。

### 4.1 `market_quote`

```text
name: market_quote
description: >
  获取标的最新报价（延迟行情，研究用）。symbol 用 Yahoo 风格：
  美股 AAPL；港股 0700.HK；A股 600519.SS / 000001.SZ。
  禁止编造价格——若拉取失败返回 error 字段。
parameters:
  symbol: string (required)
  # 可选
  market: "US" | "HK" | "CN" | "auto"  # default auto
```

**成功 output 示例：**

```json
{
  "symbol": "AAPL",
  "currency": "USD",
  "price": 198.12,
  "change_pct": -0.42,
  "as_of": "2026-07-18T14:30:00+08:00",
  "source": "yahoo_chart",
  "delayed": true,
  "disclaimer": "Not investment advice. Delayed research quote."
}
```

### 4.2 `market_history`

```text
name: market_history
description: 拉取日线 OHLCV，供因子/回测。默认 1y。
parameters:
  symbol: string (required)
  range: "1mo" | "3mo" | "6mo" | "1y" | "2y"   # default 1y
  interval: "1d" | "1wk"                         # default 1d
```

**成功 output：**

```json
{
  "symbol": "AAPL",
  "interval": "1d",
  "bars": [
    {"date": "2026-01-02", "o": 1, "h": 1, "l": 1, "c": 1, "v": 1000}
  ],
  "count": 252,
  "source": "yahoo_chart"
}
```

实现注意：

- bars 过长时 **截断摘要**（只回最近 N 根 + 统计），完整序列可写  
  `~/.madcop/quant/cache/{symbol}_{range}.json`，工具返回 path + summary。  
- 避免把 2000 根 K 线塞满 context。

### 4.3 `quant_factors`

```text
name: quant_factors
description: 基于 history 或 cache 计算简单因子（工具计算，非 LLM 口算）。
parameters:
  symbol: string (required)
  range: string (default "1y")
  windows:                    # optional
    type: object
    properties:
      sma_fast: integer       # default 10
      sma_slow: integer       # default 30
      mom_days: integer       # default 20
```

**output：**

```json
{
  "symbol": "AAPL",
  "last_close": 198.12,
  "sma_10": 195.0,
  "sma_30": 190.1,
  "momentum_20d_pct": 4.2,
  "volatility_20d_ann_pct": 22.5,
  "trend": "above_both_sma" | "mixed" | "below_both_sma",
  "as_of_bar": "2026-07-17"
}
```

### 4.4 `quant_backtest_simple`

```text
name: quant_backtest_simple
description: >
  单标的极简回测：buy_hold 与 sma_cross 对比。仅教育/研究。
  不考虑融资、税费细节；含简单手续费 bps。
parameters:
  symbol: string (required)
  range: string (default "1y")
  strategy: "buy_hold" | "sma_cross"   # default both via report
  sma_fast: integer (default 10)
  sma_slow: integer (default 30)
  fee_bps: number (default 5)
```

**output：**

```json
{
  "symbol": "AAPL",
  "range": "1y",
  "strategies": {
    "buy_hold": {"total_return_pct": 12.3, "max_drawdown_pct": -15.1, "n_trades": 1},
    "sma_cross": {"total_return_pct": 8.1, "max_drawdown_pct": -11.0, "n_trades": 6}
  },
  "caveats": ["No slippage model beyond fee_bps", "Past ≠ future"]
}
```

### 4.5 刻意不提供的 tools

```
place_order, cancel_order, broker_login, transfer_funds, ...
```

若未来加 L3，必须：

- 独立 permission level（高于 computer_use）
- UI 二次确认
- 审计日志
- 默认 settings 关闭

---

## 5. 股神 Subagent 规格

### 5.1 Builtin 草案（`builtins.py`）

```python
GUSHEN = SubagentSpec(
    name="gushen",
    description=(
        "量化研究助理（股神）：行情、简单因子与回测摘要。"
        "只做研究与结构化观点，不下单、不承诺收益。"
    ),
    system_prompt=...,  # 见 5.2
    tools=(
        "market_quote",
        "market_history",
        "quant_factors",
        "quant_backtest_simple",
        "web_search",
        "web_fetch",
        "read",
        "write",      # 若 write 工具名不同，对齐 registry 实际 name
        "get_time",
    ),
    disallowed_tools=("task", "bash", "computer"),  # P0 收紧
    max_turns=24,
    timeout_seconds=240,
)
```

工具 **真实 name** 以实现时 `Tool.name` 为准（可能是 `read_file` / `write_file`，需对照 registry）。

### 5.2 system_prompt 要点（写入技能文档全文）

```
你是 MadCop「股神」研究助理，不是持牌投顾。

硬规则：
1. 价格、涨跌、因子、回测数字必须来自工具结果；禁止编造。
2. 工具失败时明确说「数据不可用」，不要猜。
3. 不下单、不指导开户、不索要券商密码。
4. 每份结论必须含：逻辑 / 关键观察点 / 失效条件 / 风险 / 免责声明。
5. 区分事实（工具数据）与观点（你的解读）。
6. 默认语言跟随用户；报告可写 Markdown。

输出模板：
## 标的与数据时点
## 市场事实（引用工具）
## 因子快照
## 观点（非建议）
## 关键观察 / 失效条件
## 风险
## 免责声明：本输出仅供研究学习，不构成投资建议。
```

### 5.3 YAML 用户版（可选，同结构）

`~/.madcop/subagents/gushen.yaml` 或仓库 `subagents/gushen.yaml`，便于用户改 prompt 不改 Python。

---

## 6. 数据与存储

```
~/.madcop/quant/
  cache/           # OHLCV JSON，带 TTL（如 1h 日内 / 1d 日线）
  reports/         # 股神 write 的 md/json
  watchlist.json   # P0.5：自选
  paper/           # L2 模拟盘，P0 不建
```

`WriteFileTool` allowlist 增加：`str(Path.home() / ".madcop" / "quant")`。

环境变量（可选）：

| 变量 | 含义 |
|------|------|
| `MADCOP_QUANT_DIR` | 覆盖根目录 |
| `MADCOP_MARKET_PROVIDER` | `yahoo`（默认） |
| `MADCOP_QUANT_ENABLE` | `1`/`0` 总开关，默认开 |

---

## 7. 行情源（P0）

**默认：Yahoo Chart API**（无 key，延迟，研究够用）

- 注意：可用性与 ToS 随时间变化；provider 做成可替换接口：

```python
class MarketProvider(Protocol):
    def quote(self, symbol: str) -> dict: ...
    def history(self, symbol: str, range: str, interval: str) -> dict: ...
```

失败策略：

1. 返回 `{"error": "...", "symbol": "..."}`  
2. Agent prompt 要求展示错误，不编价格  
3. 单测全部 mock provider

可选依赖：P0 **尽量 stdlib urllib**（对齐 weather）；若 yfinance 已在环境可选用但不要强制重依赖。

---

## 8. 拓扑预设（前端，可选同步）

在 `AgentOverview.vue` `presets` 增加：

```
id: gushen-research
label: 股神研报
nodes:
  - gushen（research，tools = market* + quant* + web）
  - optional risk（general-purpose 或专用 risk prompt，只审报告）
edges: gushen → risk →（用户看结果）
```

run 时用户输入示例：

`对 0700.HK 做 1y 动量与 sma_cross 对比，输出中文研报`

---

## 9. 权限与安全

| 项 | P0 |
|----|-----|
| 真下单 | 无工具 = 做不到 |
| 外网 | 仅行情/搜索域名；可后续收紧 |
| 写盘 | 仅 quant + 现有 workspace |
| bash | 股神 disallowed（防乱装包/乱下单脚本） |
| 披露 | 每条 tool output 带 `disclaimer` 字段更好 |

---

## 10. 测试计划

```bash
# 单元（mock）
pytest tests/tools/test_market.py tests/tools/test_quant.py -q

# 手工
# 1. 注册 tools 后 chat: 「用 market_quote 查 AAPL」
# 2. task → gushen: 「AAPL 1y 因子 + 极简回测」
# 3. 断网：应 error，不编价
```

验收：

- [ ] `market_quote` 返回含 price 或 error，无幻觉字段要求模型自造  
- [ ] `quant_factors` 对固定 CSV/fixture 数值可回归  
- [ ] gushen 无法调用 computer/bash（若 executor 执行 allow-list）  
- [ ] 报告含免责声明  

---

## 11. 实现顺序（建议 2–4 天可打完 P0）

| Day | 任务 |
|-----|------|
| 0.5 | `market.py` quote + history + mock 测 |
| 0.5 | `quant.py` factors + simple backtest + fixture 测 |
| 0.5 | registry 注册 + quant 写目录 allowlist |
| 0.5 | `GUSHEN` builtin + skills md |
| 0.5 | 手工 chat/拓扑跑通 |
| 可选 | AgentOverview 预设 + 精灵显示名 |

L1/L2 以后：watchlist cron 简报 → paper broker →（很久以后）真券商。

---

## 12. 给实现 Agent 的开场提示

```
实现 MadCop 股神 Agent P0：读 docs/design-gushen-agent-p0.md。
按 weather 工具模式加 market_quote / market_history / quant_factors /
quant_backtest_simple；注册进 default_registry；builtins 增加 gushen；
写盘仅 ~/.madcop/quant；单测 mock 网络；禁止任何下单工具。
先后端可跑，前端拓扑预设可另开 PR。
```

---

## 13. 一句话

> **P0 = 行情工具 + 简单因子/回测 + 股神 subagent + 硬免责；数字出工具、真钱永不进 P0。**
