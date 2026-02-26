# PROMPT.md — Bitcoin 资金流与阶段判定看板（可部署落地项目）

---

## 系统指令（对 AI / Codex 的元指令，不属于项目需求文档）

你是一个资深全栈工程师 + 数据平台架构师 + 量化研究工程师。
请严格按下方需求文档实现，禁止输出研究散文。所有交付物必须可运行、可部署、可扩展。

输出规则
- 按文件逐个输出，每个文件一个代码块，代码块上方用一行写相对路径。
- 必须先输出目录树，然后依次输出：后端 → 数据库迁移 → 前端 → Docker → README → 初始化脚本。
- 按 `§16 分阶段交付` 的顺序输出。当前只需完成 Phase 1，Phase 2/3 输出接口占位与 TODO。
- 不要输出额外解释，不要输出无关文字。

---

## 0. 总目标与非目标

### 目标

1. 构建一个随时可从浏览器访问的前端看板，展示 BTC 资金流入/流出、市场结构变化、趋势状态、宏观背景，并给出"当前处于哪个阶段"的可复核结论。
2. 数据必须来源权威与一手或机构级来源，建立数据源白名单，所有指标可追溯到原始字段。
3. 具备可扩展性：可新增数据源、可新增指标、可调整评分权重、可重算回填。
4. 对公众用户友好：提供通俗解释层。
5. 对专业用户友好：提供指标口径层与可复核规则。

### 非目标

- 不做交易建议，不做自动下单。
- 不追求纳秒级实时。遵循数据源实际刷新频率，提供"最新更新时间与延迟"展示。

---

## 1. 技术栈与部署约束（必须遵守）

### 必须使用

| 层 | 技术 |
|---|---|
| Backend | Python 3.11 + FastAPI |
| Scheduler | APScheduler（MVP），预留 Celery/Temporal 接口 |
| DB | PostgreSQL 15+ |
| Cache | Redis（可选，默认启用） |
| Frontend | Next.js 14 + TypeScript + ECharts |
| Deploy | Docker Compose（必须一键启动） |
| Reverse Proxy | Nginx（可选模板） |

### 工程约束

- 代码必须可直接运行：`docker compose up -d` 后，前端可访问，后端健康检查通过。
- 必须有数据库迁移脚本（SQL 或 Alembic 二选一，推荐 Alembic）。
- 必须有幂等写入：同一时间点重复采集不得产生重复数据。
- 必须有日志、重试、速率限制、错误隔离（某数据源失败不影响其他源）。
- 必须有口径版本控制：指标定义变更需要版本号。

---

## 2. 系统总体架构（必须实现）

### 数据流

```
Source → Ingest → Normalize → Store(raw/normalized) → Compute(metrics/scores/stage) → API → Frontend
```

### 必须包含的模块

| 模块 | 目录 | 职责 |
|---|---|---|
| 数据源适配器 | `sources/` | 权威源优先，支持 API Key，声明 `max_history_depth` |
| 拉取与原始落库 | `ingest/` | raw tables |
| 单位与字段统一 | `normalize/` | normalized tables |
| 指标计算 | `compute/` | metrics / scores / stage |
| API | `api/` | FastAPI 路由 |
| 前端 | `frontend/` | Next.js 页面与图表组件 |
| 运维 | `ops/` | Docker Compose、env 模板、初始化脚本 |

---

## 3. 权威数据源白名单（硬约束）

### 当前可用 API Key 声明

> **部署者须在 `.env` 中填写实际持有的 Key。**
> 下表标注每个源的认证需求。标记 `FREE` 的源无需 Key 即可使用，是 Phase 1 的基础。

| 源 | 认证 | Phase |
|---|---|---|
| FRED (Federal Reserve Economic Data) | `FREE`（可选注册获得更高速率） | 1 |
| Coinbase 公开 REST API | `FREE` | 1 |
| Farside Investors (ETF flow) | `FREE`（公开网页表格） | 1 |
| CoinGecko 公开 API | `FREE`（有速率限制） | 1 |
| Kraken 公开 REST API | `FREE` | 2 |
| Bitstamp 公开 REST API | `FREE` | 2 |
| Deribit 公开 API（期权/衍生品） | `FREE`（公开端点） | 2 |
| Glassnode | `PAID`，需 API Key | 3 |
| Coin Metrics | `PAID`，需 API Key | 3 |
| Kaiko | `PAID`，需 API Key | 3 |
| Bloomberg | 仅预留接口，不实现 | — |
| CME | 公开数据有限，预留接口 | — |

### 允许的数据源类型

A. **官方与政府机构**
- Federal Reserve（FRED 代理 — 资产负债表、利率、国债收益率）
- U.S. Treasury（收益率曲线等，可通过 FRED 获取）
- BLS/BEA（宏观扩展时使用）

B. **交易所官方公开 API**
- Coinbase、Kraken、Bitstamp 等主流交易所（现货价格与成交量）
- Deribit（期权与期货公开接口）

C. **机构级链上与市场数据提供商**（通常需订阅，必须支持 Key 配置）
- Glassnode
- Coin Metrics
- Kaiko
- Bloomberg（仅接口预留）

D. **ETF 资金流**
- Farside Investors（ETF flow 日度表）
- ETF 发行方/基金披露（预留接口）

### 禁止

- 非权威、无法说明口径与字段来源的数据
- 个人博客 / 不明来源 API
- 任何无法验证数据质量的抓取源

### 适配器实现要求

每个数据源适配器必须声明：

```python
class SourceAdapter:
    source_id: str           # 唯一标识
    auth_type: str           # "none" | "api_key" | "oauth"
    rate_limit: dict         # {"requests_per_minute": N}
    max_history_depth: str   # "30d" | "1y" | "10y" | "all" 等
    field_mapping: dict      # 原始字段 → 规范字段
    ts_spec: str             # 时间戳口径说明
    retry_policy: dict       # {"max_retries": 3, "backoff": "exponential"}
```

---

## 4. 数据模型（必须实现）

以下表字段可扩展但核心字段不可缺少。

### 4.1 `raw_observations` — 原始数据落库

| 字段 | 类型 | 说明 |
|---|---|---|
| id | PK | |
| source_id | varchar | |
| dataset | varchar | |
| symbol | varchar (nullable) | |
| ts | timestamp (UTC) | |
| payload | jsonb | |
| ingested_at | timestamp | |
| **UNIQUE** | | `(source_id, dataset, symbol, ts)` |

### 4.2 `normalized_series` — 规范化时序

| 字段 | 类型 | 说明 |
|---|---|---|
| id | PK | |
| series_id | varchar | 规范键，如 `macro.fed_balance_sheet.total_assets` |
| ts | timestamp (UTC) | |
| value | numeric | |
| unit | varchar | |
| source_id | varchar | |
| quality_flags | jsonb | |
| **UNIQUE** | | `(series_id, ts)` |

### 4.3 `metric_catalog` — 指标字典（核心）

| 字段 | 类型 | 说明 |
|---|---|---|
| metric_id | PK | |
| name | varchar | |
| dimension | int (1-5) | 维度编号 |
| lead_lag | enum | `lead` / `coincident` / `lag` |
| definition_short | text | 小白版一句话解释 |
| definition_pro | text | 专业版口径 |
| calc_spec | jsonb | 公式、所需 series_id / raw fields |
| source_priority | jsonb | 按优先级列出 source_id |
| refresh_policy | jsonb | 频率、延迟、回填窗口 |
| failure_modes | jsonb | |
| chart_spec | jsonb | 图表类型、阈值线、区间带 |
| version | int | 口径版本号 |
| is_active | boolean | |
| tier | enum | `must_have` / `nice_to_have` |

### 4.4 `metric_values` — 指标值

| 字段 | 类型 | 说明 |
|---|---|---|
| metric_id | FK | |
| ts | timestamp (UTC) | |
| value | numeric | |
| aux | jsonb | 分位数、分母、样本量等 |
| **UNIQUE** | | `(metric_id, ts)` |

### 4.5 `scores` — 评分

| 字段 | 类型 | 说明 |
|---|---|---|
| score_id | varchar | 如 `capital_inflow_score` |
| ts | timestamp (UTC) | |
| value | numeric (0-100) | |
| components | jsonb | 分项贡献 |
| **UNIQUE** | | `(score_id, ts)` |

### 4.6 `market_stage` — 阶段判定

| 字段 | 类型 | 说明 |
|---|---|---|
| ts | timestamp (UTC) | |
| stage_id | int (enum) | |
| stage_name | varchar | |
| confidence | numeric (0-1) | |
| explanation_public | text | 通俗版 |
| explanation_pro | text | 专业版 |
| evidence | jsonb | 触发条件与关键指标值 |
| **UNIQUE** | | `(ts)` |

---

## 5. 指标范围（必须覆盖五个维度）

指标分两层优先级：

- **`must_have`**：使用免费公开数据源即可计算，Phase 1 必须有数据。
- **`nice_to_have`**：需要付费数据源，Phase 3 接入后激活。

### 维度 1：链上资本（主要依赖 Glassnode / Coin Metrics）

| 指标 | Tier | Phase 1 替代方案 |
|---|---|---|
| realized_cap, realized_cap_change | nice_to_have | — |
| realized_profit_loss | nice_to_have | — |
| mvrv | nice_to_have | — |
| cost_basis_distribution（成本带） | nice_to_have | — |
| lth_sth_behavior（供给与成本） | nice_to_have | — |
| whale_accumulation（大额地址） | nice_to_have | — |
| exchange_netflow（交易所净流） | nice_to_have | CoinGecko exchange volume 作代理 |

### 维度 2：ETF 与机构

| 指标 | Tier | 数据源 |
|---|---|---|
| us_spot_etf_netflow_total | **must_have** | Farside |
| us_spot_etf_netflow_by_fund | **must_have** | Farside |
| grayscale_holdings_change | nice_to_have | 预留 |
| institution_position_proxy | nice_to_have | 预留 |
| coinbase_premium | **must_have** | Coinbase vs Bitstamp/Kraken 价差计算 |

### 维度 3：稳定币

| 指标 | Tier | Phase 1 替代方案 |
|---|---|---|
| usdt_supply_change | **must_have** | CoinGecko market_cap 变化作代理 |
| usdc_supply_change | **must_have** | CoinGecko market_cap 变化作代理 |
| stablecoin_net_mint_burn | nice_to_have | 用上述两项合成 |
| exchange_stablecoin_balance_change | nice_to_have | — |
| stablecoin_btc_volume_share | nice_to_have | — |

### 维度 4：现货与衍生品

| 指标 | Tier | 数据源 |
|---|---|---|
| spot_volume_trend | **must_have** | Coinbase + CoinGecko |
| futures_open_interest | **must_have** | CoinGecko derivatives / Deribit |
| funding_rate | **must_have** | CoinGecko / 交易所公开 API |
| basis_spread | **must_have** | 期货价 - 现货价计算 |
| liquidation_volume | nice_to_have | Deribit / 预留 |
| leverage_risk_index（自定义合成） | **must_have** | 基于 OI + funding + basis 合成 |

### 维度 5：宏观流动性

| 指标 | Tier | 数据源 |
|---|---|---|
| fed_balance_sheet_change | **must_have** | FRED (WALCL) |
| dxy | **must_have** | FRED (DTWEXBGS) |
| ust_2y_yield | **must_have** | FRED (DGS2) |
| ust_10y_yield | **must_have** | FRED (DGS10) |
| global_liquidity_proxy | **must_have** | FRED 多序列合成（Fed + ECB + BOJ 资产负债表代理） |

### 指标字典要求

每个指标必须在 `metric_catalog` 中具备：`definition_short`、`definition_pro`、`calc_spec`、`source_priority`、`refresh_policy`、`failure_modes`、`chart_spec`、`tier`。

---

## 6. 领先/同步/滞后分类（必须实现）

### 要求

- 每个维度至少 1 个领先、1 个滞后。
- 在 `metric_catalog.lead_lag` 中标记。
- API 支持按 `lead_lag` 筛选。

### 分类建议

| 类型 | 指标 |
|---|---|
| **领先 (lead)** | ETF 连续净流入、稳定币净铸造/supply 变化、coinbase premium、realized cap 斜率拐点、fed_balance_sheet_change |
| **同步 (coincident)** | 现货成交趋势、OI、资金费率、交易所净流、basis_spread |
| **滞后 (lag)** | MVRV、NUPL（如接入）、LTH/STH 成本带确认、dxy（对 BTC 的影响滞后） |

---

## 7. 资金回流评分系统（必须实现）

### 输出

- `capital_inflow_score`：0-100
- 组件来自五个维度，必须可解释与可调参。

### 规则

1. **分项标准化**：每个子指标转为 0-1 或 z-score，再映射到 0-100。
2. **缺失处理**：缺失指标按权重重新归一化，不得把缺失当 0。
3. **权重默认**（可配置，通过 `config/scoring_weights.yaml`）：

| 维度 | 权重 |
|---|---|
| ETF 与机构 | 0.30 |
| 链上资本 | 0.25 |
| 稳定币 | 0.20 |
| 现货与衍生品 | 0.15 |
| 宏观 | 0.10 |

### 等级定义

| 等级 | 条件 |
|---|---|
| 强回流 | >= 70 且连续 7 天不低于 60 |
| 弱回流 | 40-69 |
| 无回流 | < 40 |

### 必须提供的 API

- `GET /scores/capital_inflow/latest`
- `GET /scores/capital_inflow?start=&end=&granularity=`

---

## 8. 阶段判定状态机（必须实现，可回测）

### 至少 7 个阶段

| ID | 阶段名 |
|---|---|
| 1 | 深熊去杠杆 |
| 2 | 筑底与换手 |
| 3 | 复苏与吸筹 |
| 4 | 上升趋势早期 |
| 5 | 加速上涨与泡沫化 |
| 6 | 高位派发与结构脆弱 |
| 7 | 见顶回落与再去杠杆 |

### 进入/退出条件

必须量化。以 `capital_inflow_score`、`structure_risk_score`、趋势强度、关键成本带位置、ETF 连续流入、稳定币供给增速等构成规则。

每次输出必须生成 `evidence`（JSON），列出触发条件与当期指标值。

### 必须提供的 API

- `GET /stage/latest`
- `GET /stage?start=&end=`
- `GET /stage/explain?ts=`

---

## 9. 前端看板信息架构（必须实现）

### 5 个页面

| 页面 | 内容 |
|---|---|
| **概览** | 价格、两大评分、当前阶段、关键告警、最新更新时间 |
| **资金流** | ETF 流、链上净流、稳定币流动性、资金回流评分分解 |
| **结构风险** | 杠杆风险、清算、基差、趋势破坏信号、结构风险评分 |
| **宏观** | Fed 资产负债表、DXY、2Y/10Y、全球流动性代理 |
| **指标详情** | 单指标解释、来源、公式、图表、历史阶段对照 |

### 图表要求

- 每张图标注数据源与更新时间。
- 支持时间窗：7D / 30D / 90D / 1Y / All。
- 提供阈值线与区间带（来自 `chart_spec`）。
- 当某指标因数据源限制历史深度不足时，图表显示 `available_since` 并灰化不可用区间。

---

## 10. API 设计（必须实现）

### 端点列表

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 健康检查 |
| GET | `/sources/status` | 各数据源状态、最近成功时间、错误信息 |
| GET | `/metrics/catalog` | 指标字典，支持 `?tier=must_have&lead_lag=lead` 筛选 |
| GET | `/metrics/{metric_id}?start=&end=&granularity=` | 指标值查询 |
| GET | `/scores/{score_id}?start=&end=&granularity=` | 评分查询 |
| GET | `/scores/capital_inflow/latest` | 最新资金回流评分 |
| GET | `/stage/latest` | 最新阶段 |
| GET | `/stage?start=&end=` | 历史阶段序列 |
| GET | `/stage/explain?ts=` | 指定时间点阶段解释 |

### 响应格式

所有端点统一响应结构：

```json
{
  "data": {},
  "meta": {
    "source": "fred",
    "delay": "1d",
    "unit": "USD",
    "version": 1
  },
  "updated_at": "2026-02-26T00:00:00Z"
}
```

---

## 11. 调度与数据刷新（必须实现）

### Scheduler 任务

| 任务 | 频率 | 说明 |
|---|---|---|
| `ingest_*` | 按数据源频率 | 每个源独立调度 |
| `normalize_*` | ingest 后触发或定时批量 | |
| `compute_metrics` | 每 5-15 分钟（实时源）/ 每日（日频源） | |
| `compute_scores_stage` | 每次 metrics 更新后 | |

### 要求

- **backfill 支持**：可指定时间范围回填 raw → normalized → metrics。
- **幂等**：同一 ts 重跑不会重复插入（UPSERT / ON CONFLICT）。
- **失败隔离**：单数据源失败不阻断全局调度。
- **日志**：每次任务记录 `started_at`、`finished_at`、`records_affected`、`errors`。

---

## 12. 历史数据自动回填（必须实现）

### 核心原则

> **禁止依赖 CSV 手动导入。所有数据必须通过 API 自动获取。**

### 要求

- 首次部署时，自动触发 backfill 任务，从各数据源 API 拉取可获得的最大历史深度。
- 每个数据源适配器必须声明 `max_history_depth`（如 FRED 可拉 20+ 年；CoinGecko 免费 tier 可拉 365 天；Glassnode 免费 tier 仅 24h，Pro 可拉全量）。
- backfill 按 source 独立并行执行，失败不阻断其他源。
- 在前端与 API 响应中明确标注 `available_since` 字段，告知用户该指标可追溯到的最早时间。

### 首次启动流程

```
1. DB migration（Alembic）
2. 初始化 metric_catalog（seed data）
3. 并行执行各 source 的 backfill（按 max_history_depth）
4. 计算 metrics → scores → stage
5. 前端可访问，数据持续更新
```

### 回测与历史对比

基于自动回填的历史数据：
- 生成历史阶段序列与评分序列。
- 前端指标详情页展示已有历史区间的"典型形态摘要"。
- 统计输出：
  - 每个阶段累计天数
  - 阶段切换次数
  - 评分分布统计（均值、中位数、分位数）

---

## 13. 安全与合规（必须实现）

- `.env` 管理密钥，禁止硬编码在代码中。`.env.example` 作为模板。
- 对外公开部署时提供免责声明页面与 API 响应 header 提示。
- API 速率限制（如 60 req/min per IP）。
- Redis 缓存热数据，减少 DB 压力。
- 前端免责声明：`本看板仅供信息参考，不构成任何投资建议。`

---

## 14. 交付物与验收标准（必须满足）

### 交付物

- 完整可运行代码仓库
- Docker Compose + `.env.example` + README
- 数据库迁移脚本（Alembic）
- Phase 1 中所有 `FREE` 数据源适配器可运行（FRED + Coinbase + Farside + CoinGecko）
- 付费数据源（Glassnode 等）提供完整接口与占位实现
- 指标字典 `metric_catalog` 初始化种子数据（全量指标定义，含 `must_have` 与 `nice_to_have`）
- 前端 5 页面可访问且有图表展示

### 验收标准

| 检查项 | 标准 |
|---|---|
| 一键启动 | `docker compose up -d` 后 5 分钟内健康检查通过并开始拉取数据 |
| 健康检查 | `/health` 返回 `ok` |
| 数据入库 | 首次 backfill 开始后，`raw_observations` 有数据写入（FRED + Coinbase 最快） |
| 概览页 | 显示：最新更新时间、`capital_inflow_score`、当前阶段名称 |
| 指标详情页 | 至少能查 10 个 `must_have` 指标并显示来源与公式 |
| 缺失容错 | 缺失 `nice_to_have` 指标不会导致评分崩溃，权重自动重归一化 |
| 数据源隔离 | 关闭某数据源（如清空其 API Key）后，其他源继续正常运行 |

---

## 15. 评分权重配置文件格式

文件路径：`config/scoring_weights.yaml`

```yaml
version: 1

capital_inflow_score:
  weights:
    etf_institutional: 0.30
    onchain_capital: 0.25
    stablecoin: 0.20
    spot_derivatives: 0.15
    macro: 0.10
  thresholds:
    strong_inflow: 70
    strong_inflow_sustained_days: 7
    strong_inflow_min_during_sustained: 60
    weak_inflow_min: 40
  normalization: "z-score"  # or "min-max"

structure_risk_score:
  weights:
    leverage: 0.35
    liquidation: 0.25
    basis: 0.20
    trend: 0.20
  thresholds:
    high_risk: 70
    moderate_risk: 40
  normalization: "z-score"
```

---

## 16. 分阶段交付（必须遵守）

### Phase 1 — MVP（必须完整可运行）

- 后端框架 + DB + Alembic 迁移
- 4 个真实可运行免费数据源适配器：
  - **FRED**（宏观：Fed 资产负债表、DXY、2Y/10Y 收益率）
  - **Coinbase**（现货价格、成交量）
  - **Farside**（ETF 日度净流入）
  - **CoinGecko**（BTC 市场数据、稳定币市值、衍生品概览）
- `metric_catalog` 全量初始化（含全部指标定义）
- 所有 `must_have` 指标可计算并入库
- 评分系统（缺失 `nice_to_have` 指标自动重归一化）
- 阶段判定状态机
- 全部 API 端点可用
- Docker Compose 一键启动
- 首次启动自动 backfill
- 前端概览页 + 宏观页可用（至少展示真实数据图表）

### Phase 2 — 前端完善

- 前端全部 5 页面完整可用
- ECharts 图表全部渲染
- 时间窗筛选（7D/30D/90D/1Y/All）
- 免责声明页
- Nginx 反向代理模板
- Kraken + Bitstamp + Deribit 适配器

### Phase 3 — 付费数据源扩展

- Glassnode 适配器（需用户提供 API Key）
- Coin Metrics 适配器（需用户提供 API Key）
- 全部 `nice_to_have` 指标激活
- 完整链上资本维度
- 回测对比增强：多周期叠加图、阶段统计面板

---

## 附录 A：目录结构参考

```
btcObserver/
├── backend/
│   ├── alembic/                 # DB 迁移
│   │   ├── versions/
│   │   └── env.py
│   ├── sources/                 # 数据源适配器
│   │   ├── base.py              # SourceAdapter 基类
│   │   ├── fred.py
│   │   ├── coinbase.py
│   │   ├── farside.py
│   │   ├── coingecko.py
│   │   ├── glassnode.py         # Phase 3 占位
│   │   ├── coin_metrics.py      # Phase 3 占位
│   │   └── registry.py          # 源注册与发现
│   ├── ingest/
│   │   └── ingester.py
│   ├── normalize/
│   │   └── normalizer.py
│   ├── compute/
│   │   ├── metrics.py
│   │   ├── scoring.py
│   │   └── stage.py
│   ├── api/
│   │   ├── main.py              # FastAPI app
│   │   ├── routes/
│   │   │   ├── health.py
│   │   │   ├── sources.py
│   │   │   ├── metrics.py
│   │   │   ├── scores.py
│   │   │   └── stage.py
│   │   └── schemas.py
│   ├── scheduler/
│   │   └── jobs.py
│   ├── config/
│   │   └── scoring_weights.yaml
│   ├── db/
│   │   ├── models.py
│   │   └── session.py
│   ├── seed/
│   │   └── metric_catalog.json
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── app/                 # Next.js app router
│   │   │   ├── page.tsx         # 概览
│   │   │   ├── capital-flow/
│   │   │   ├── structure-risk/
│   │   │   ├── macro/
│   │   │   └── metrics/
│   │   ├── components/
│   │   │   ├── charts/
│   │   │   └── layout/
│   │   └── lib/
│   │       └── api.ts
│   ├── package.json
│   ├── tsconfig.json
│   └── Dockerfile
├── ops/
│   ├── docker-compose.yml
│   ├── nginx.conf               # 可选
│   └── init-db.sh
├── .env.example
├── PROMPT.md
└── README.md
```
