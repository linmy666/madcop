# Skill: 股神（Gushen）量化研究

研究级行情与因子，**不是**自动交易系统。

## 何时使用

- 用户要看某个标的报价、动量、均线、极简回测
- 需要结构化「观点 + 风险 + 失效条件」，且数字必须可追溯

## 可用工具

| 工具 | 作用 |
|------|------|
| `market_quote` | 延迟报价 |
| `market_history` | OHLCV（响应内仅 tail；全量可在 cache） |
| `quant_factors` | SMA / 动量 / 波动 |
| `quant_backtest_simple` | buy_hold vs sma_cross |
| `paper_account` | 查看本地**模拟盘**账户 |
| `paper_order` | **模拟**买卖（按研究报价成交） |
| `paper_reset` | 重置模拟盘 |
| `web_search` / `web_fetch` | 新闻与背景（需标注非官方行情） |
| `write_file` | 报告写入 `~/.madcop/quant/reports/` |

## 硬规则

1. **禁止编造**价格、收益率、回撤、成交量。
2. 工具报错 → 明确「数据不可用」。
3. **禁止真实券商下单**；`paper_*` 必须口头标明「模拟盘」。
4. 禁止要券商密码、承诺收益。
5. 每份输出含免责声明。
6. 子代理 `gushen` 无 `bash` / `computer_use`。
7. Agent 页拓扑预设：**股神研报**（gushen → 风控）。

## 标的写法

- 美股：`AAPL`
- 港股：`0700.HK` 或 `0700` + market=HK
- A 股：`600519.SS` / `000001.SZ` 或六位代码

## 输出模板

见 builtin `gushen` system_prompt。

## 环境变量

- `MADCOP_QUANT_ENABLE=0` 关闭量化工具
- `MADCOP_QUANT_DIR` 覆盖数据根目录（默认 `~/.madcop/quant`）
