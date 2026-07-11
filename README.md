# A股行业轮动与资金流向监控仪表盘

一个**长期维护**的 A 股板块轮动 + 主力资金流向可视化仪表盘（暗色金融终端风，红涨绿跌）。

## 功能
- 16 个行业 / 概念板块热力网格（涨跌幅 + 主力净流入）
- 主力资金净流入排行（板块 / 个股维度）
- 大小盘 × 价值 / 成长 风格轮动视图
- 板块 K 线 + MACD(12,26,9)
- 板块历史趋势（自部署起每日累积）

## 架构
- **数据**：腾讯财经指数 + 东方财富板块 / 概念 / 资金流 / K线（公开行情接口）
- **抓取**：GitHub Actions 每个交易日 16:30（北京时间）自动运行 `fetch_a股.py`
- **托管**：腾讯云 CloudBase 静态托管（国内访问快）
- **仓库即数据源**：`data.json`（每日快照）+ `history.json`（跨日累积趋势）

## 本地运行
- 双击 `run.bat`：自动装依赖 → 抓取 → 起本地服务 `http://localhost:8000/index.html`
- 或手动：
  - `python fetch_a股.py` 在线抓取真实行情
  - `python fetch_a股.py --demo` 仅验证管线（不联网）

## 自动更新配置（仓库 Secrets）
在 GitHub 仓库 `Settings → Secrets and variables → Actions` 中添加：
| 名称 | 取值 |
|---|---|
| `CLOUDBASE_SECRET_ID` | 腾讯云 API 密钥 SecretId |
| `CLOUDBASE_SECRET_KEY` | 腾讯云 API 密钥 SecretKey |
| `CLOUDBASE_ENV_ID` | `stock711-d9g478sq2cb9ff1b5` |

配置后：每个交易日收盘后自动抓取并重部署；也可在 `Actions` 页手动 **Run workflow** 立即触发。

> ⚠️ 数据来源为公开行情接口，本项目仅供学习研究，**不构成任何投资建议**。
