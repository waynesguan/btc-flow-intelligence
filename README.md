# btcObserver — Bitcoin 资金流与阶段判定看板

实时追踪 BTC 资金流入/流出、市场结构变化、趋势状态与宏观背景，给出可复核的市场阶段结论。

当前版本已覆盖 Phase 1/2/3 目标：免费 + 扩展 + 付费数据源 → must_have + nice_to_have 指标 → 2 项评分 + 7 阶段状态机 + 回测面板 → 前端 5 页面看板。

## 架构总览

```text
Source (FRED / Coinbase / Farside / CoinGecko / Kraken / Bitstamp / Deribit / Glassnode / Coin Metrics)
  │
  ▼
Ingest ──► raw_observations (jsonb)
  │
  ▼
Normalize ──► normalized_series (统一 series_id / ts / value)
  │
  ▼
Compute Metrics ──► metric_values (must_have + nice_to_have 全量计算)
  │
  ▼
Compute Scores ──► scores (capital_inflow_score + structure_risk_score)
  │
  ▼
Compute Stage ──► market_stage (7 阶段状态机)
  │
  ▼
FastAPI ──► Next.js Frontend
```

## 目录结构

```text
btcObserver/
├── backend/
│   ├── alembic/                    # 数据库迁移 (Alembic)
│   │   └── versions/
│   │       └── 20260226_0001_init.py
│   ├── api/                        # FastAPI 路由与中间件
│   │   ├── main.py                 # 应用入口 + lifespan
│   │   ├── cache.py                # Redis 缓存层
│   │   ├── schemas.py              # Pydantic 响应模型
│   │   └── routes/
│   │       ├── health.py           # GET /health (DB + Redis 检测)
│   │       ├── sources.py          # GET /sources/status
│   │       ├── metrics.py          # GET /metrics/catalog, /metrics/{id}
│   │       ├── scores.py           # GET /scores/*, 含 latest 端点
│   │       └── stage.py            # GET /stage/latest, /stage/explain
│   ├── sources/                    # 数据源适配器
│   │   ├── base.py                 # SourceAdapter 基类 (重试/限速/backfill)
│   │   ├── registry.py             # 源注册与发现
│   │   ├── fred.py                 # Phase 1 - 宏观 (WALCL/DXY/DGS2/DGS10)
│   │   ├── coinbase.py             # Phase 1 - 现货价格与成交量
│   │   ├── farside.py              # Phase 1 - ETF 日度净流入
│   │   ├── coingecko.py            # Phase 1 - BTC 市场/稳定币/衍生品
│   │   ├── kraken.py               # 现货补充数据源
│   │   ├── bitstamp.py             # 现货补充数据源
│   │   ├── deribit.py              # 衍生品 OI/Funding/Basis/Liquidation
│   │   ├── glassnode.py            # 付费链上数据源 (API Key)
│   │   └── coin_metrics.py         # 付费链上数据源 (API Key)
│   ├── ingest/
│   │   └── ingester.py             # 原始数据拉取 + UPSERT 落库
│   ├── normalize/
│   │   └── normalizer.py           # 字段统一 → normalized_series
│   ├── compute/
│   │   ├── metrics.py              # must_have + nice_to_have 指标计算
│   │   ├── scoring.py              # 评分系统 (z-score + 权重归一化)
│   │   └── stage.py                # 7 阶段状态机
│   ├── scheduler/
│   │   └── jobs.py                 # APScheduler 定时任务 + backfill
│   ├── config/
│   │   └── settings.py             # Pydantic Settings (从 .env 加载)
│   ├── db/
│   │   ├── models.py               # SQLAlchemy ORM (8 张表)
│   │   └── session.py              # 数据库连接工厂
│   ├── seed/
│   │   ├── init_seed.py            # metric_catalog 种子初始化
│   │   └── metric_catalog.json     # 26 个指标完整定义
│   ├── requirements.txt
│   ├── Dockerfile
│   └── start.sh                    # 容器启动脚本
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx            # 概览页 (两大评分 + 阶段 + 图表)
│   │   │   ├── macro/page.tsx      # 宏观页 (Fed/DXY/收益率曲线)
│   │   │   ├── metrics/page.tsx    # 指标详情页 (可点击展开 + 回测面板)
│   │   │   ├── capital-flow/page.tsx    # 资金流页 (ETF/稳定币/评分分解)
│   │   │   ├── structure-risk/page.tsx  # 结构风险页 (杠杆/基差/清算/评分分解)
│   │   │   ├── disclaimer/page.tsx # 免责声明
│   │   │   ├── error.tsx           # 全局错误边界
│   │   │   ├── loading.tsx         # 加载状态
│   │   │   ├── layout.tsx          # 根布局
│   │   │   └── globals.css         # 全局样式
│   │   ├── components/
│   │   │   ├── charts/
│   │   │   │   └── LineChart.tsx   # ECharts 折线图 (阈值线 + 渐变)
│   │   │   └── layout/
│   │   │       ├── Nav.tsx         # 顶部导航
│   │   │       └── WindowTabs.tsx  # 时间窗口选择 (7D/30D/90D/1Y/ALL)
│   │   └── lib/
│   │       └── api.ts              # API 客户端 + 类型定义
│   ├── package.json
│   ├── tsconfig.json
│   ├── next.config.mjs             # output: standalone
│   └── Dockerfile                  # 多阶段构建
├── ops/
│   ├── docker-compose.yml          # 备用 compose
│   ├── nginx.conf                  # Nginx 反向代理模板
│   └── init-db.sh                  # 数据库初始化脚本
├── config/
│   └── scoring_weights.yaml        # 评分权重配置
├── .env.example                    # 环境变量模板
├── docker-compose.yml              # 主 compose (4 服务)
├── PROMPT.md                       # 项目需求规格
└── README.md
```

## 前置依赖

| 依赖 | 最低版本 |
|---|---|
| Docker | 24+ |
| Docker Compose | v2 (docker compose) |
| FRED API Key | 必须 (免费注册: https://fred.stlouisfed.org/docs/api/api_key.html) |

其他 API Key (CoinGecko/Glassnode/Coin Metrics) 可选，不填不影响 Phase 1 运行。

## 快速启动

```bash
# 1. 克隆项目
git clone git@github.com:waynesguan/btc-flow-intelligence.git
cd btc-flow-intelligence

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 FRED_API_KEY (必须)

# 3. 一键启动
docker compose up -d --build

# 4. (可选) 启用 Nginx 反向代理
docker compose --profile proxy up -d nginx

# 5. 验证服务
curl http://localhost:8000/health          # 后端健康检查
curl http://localhost:8000/sources/status   # 数据源状态
open http://localhost:3000                  # 前端看板
open http://localhost:8000/docs             # Swagger UI
```

## 启动流程

Backend 容器启动后自动执行：

```text
1. 等待 PostgreSQL 就绪 (最多 60 次重试)
2. alembic upgrade head (建表/迁移)
3. python -m seed.init_seed (写入 26 个指标定义)
4. uvicorn 启动 FastAPI
5. lifespan 中:
   ├── 初始化 APScheduler (4 个定时任务)
   └── 后台线程执行 bootstrap_phase1():
       ingest → normalize → compute_metrics → compute_scores → compute_stage
       (不阻塞 API，前端在数据就绪前显示"数据初始化中")
```

首次 backfill 约需 2-5 分钟 (取决于网络)，完成后前端自动展示真实数据。

## 前端页面

| 路径 | 页面 | 状态 | 说明 |
|---|---|---|---|
| `/` | 概览 | Phase 1 完成 | Capital Inflow Score + Structure Risk Score + 当前阶段 + 时序图表 |
| `/macro` | 宏观 | Phase 1 完成 | Fed 资产负债表变化、DXY、2Y vs 10Y 收益率利差 |
| `/metrics` | 指标详情 | 已完成 | 点击指标展开时序图 + 阶段统计面板 + 多周期叠加图 |
| `/capital-flow` | 资金流 | 已完成 | ETF 分基金流入、稳定币流动性、评分分解 |
| `/structure-risk` | 结构风险 | 已完成 | 杠杆风险、基差、清算代理、评分分解 |
| `/disclaimer` | 免责声明 | 完成 | 法律免责文本 |

所有页面支持时间窗口切换：**7D / 30D / 90D / 1Y / ALL**

## 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `APP_NAME` | btcObserver | 应用名称 |
| `ENV` | dev | 运行环境 |
| `LOG_LEVEL` | INFO | 日志级别 |
| `POSTGRES_HOST` | db | PostgreSQL 主机 |
| `POSTGRES_PORT` | 5432 | PostgreSQL 端口 |
| `POSTGRES_DB` | btc_observer | 数据库名 |
| `POSTGRES_USER` | postgres | 数据库用户 |
| `POSTGRES_PASSWORD` | postgres | 数据库密码 |
| `REDIS_ENABLED` | true | 是否启用 Redis 缓存 |
| `REDIS_URL` | redis://redis:6379/0 | Redis 连接 URL |
| `SCHEDULER_TIMEZONE` | UTC | 调度器时区 |
| `BACKFILL_ON_STARTUP` | true | 启动时是否自动回填历史数据 |
| `REQUEST_TIMEOUT_SECONDS` | 20 | 外部 API 请求超时 |
| `RATE_LIMIT_PER_MINUTE` | 60 | API 速率限制 (每 IP 每分钟) |
| `FRED_API_KEY` | **必填** | FRED API 密钥 |
| `COINGECKO_API_KEY` | 空 (可选) | CoinGecko API 密钥，填入可提高速率限制 |
| `GLASSNODE_API_KEY` | 空 (Phase 3) | Glassnode 付费密钥 |
| `COIN_METRICS_API_KEY` | 空 (Phase 3) | Coin Metrics 付费密钥 |
| `CORS_ORIGINS` | localhost:3000 | 允许的前端域名 (逗号分隔) |
| `DISCLAIMER_TEXT` | 本看板仅供信息参考... | 免责声明文本 |
| `NEXT_PUBLIC_API_BASE` | http://localhost:8000 | 前端浏览器端 API 地址 |
| `INTERNAL_API_BASE` | http://backend:8000 | 前端 SSR 内部 API 地址 |

## 数据源

| 源 | source_id | 认证 | 历史深度 | 刷新频率 | Phase |
|---|---|---|---|---|---|
| FRED | `fred` | API Key (必填) | 2005 至今 (全量) | 每 30 分钟 | 1 |
| Coinbase | `coinbase` | 无需 | 1 年 | 每 30 分钟 | 1 |
| Farside Investors | `farside` | 无需 (网页抓取) | 全量 (ETF 上市以来) | 每 30 分钟 | 1 |
| CoinGecko | `coingecko` | 可选 Key | 365 天 | 每 30 分钟 | 1 |
| Kraken | `kraken` | 无需 | 1 年 | 每 30 分钟 | 2 |
| Bitstamp | `bitstamp` | 无需 | 3 年 | 每 30 分钟 | 2 |
| Deribit | `deribit` | 无需 | 快照 + 调度累积 | 每 15 分钟 | 2 |
| Glassnode | `glassnode` | 付费 Key | 全量 | 每 30 分钟 | 3 |
| Coin Metrics | `coin_metrics` | 付费 Key | 全量 | 每 30 分钟 | 3 |

每个适配器声明：`source_id`、`auth_type`、`rate_limit`、`max_history_depth`、`field_mapping`、`ts_spec`、`retry_policy`。

## 数据库表

| 表名 | 主要用途 | 唯一约束 |
|---|---|---|
| `raw_observations` | 原始数据落库 (jsonb) | `(source_id, dataset, symbol, ts)` |
| `normalized_series` | 规范化时序 | `(series_id, ts)` |
| `metric_catalog` | 指标字典 (26 条定义) | `metric_id` (PK) |
| `metric_values` | 计算后的指标值 | `(metric_id, ts)` |
| `scores` | 评分值 (0-100) | `(score_id, ts)` |
| `market_stage` | 阶段判定结果 | `ts` |
| `source_status` | 数据源运行状态 | `source_id` (PK) |
| `job_runs` | 调度任务执行日志 | — |

所有写入均为 UPSERT (ON CONFLICT DO UPDATE)，支持幂等重跑与 backfill。

## 指标体系

### 五个维度 × 16 个 must_have 指标

| 维度 | 指标 | lead_lag | 数据源 |
|---|---|---|---|
| **2 ETF 与机构** | `us_spot_etf_netflow_total` | lead | Farside |
| | `us_spot_etf_netflow_by_fund` | lead | Farside |
| | `coinbase_premium` | lead | Coinbase + CoinGecko |
| **3 稳定币** | `usdt_supply_change` | lead | CoinGecko |
| | `usdc_supply_change` | lead | CoinGecko |
| **4 现货与衍生品** | `spot_volume_trend` | coincident | Coinbase |
| | `futures_open_interest` | coincident | CoinGecko |
| | `funding_rate` | coincident | CoinGecko (代理) |
| | `basis_spread` | coincident | Coinbase + CoinGecko |
| | `leverage_risk_index` | coincident | 合成 (OI + funding + basis) |
| **5 宏观流动性** | `fed_balance_sheet_change` | lead | FRED (WALCL) |
| | `dxy` | lag | FRED (DTWEXBGS) |
| | `ust_2y_yield` | coincident | FRED (DGS2) |
| | `ust_10y_yield` | coincident | FRED (DGS10) |
| | `global_liquidity_proxy` | lead | 合成 (Fed + DXY + 利差) |

维度 1 (链上资本) 的 `nice_to_have` 指标已接入计算链路：有付费数据源时优先用真实值，缺失时会明确标注 `proxy` 并自动退化。

其余 `nice_to_have` 指标（交易所稳定币余额、清算量、机构仓位代理等）已纳入计算逻辑，并在数据不足时通过 `aux.proxy=true` 明确标记。

## 评分系统

### Capital Inflow Score (0-100)

衡量资金是否在回流 BTC 市场。

**权重分配** (可在 `config/scoring_weights.yaml` 中调整)：

| 组件 | 权重 | 来源指标 |
|---|---|---|
| etf_institutional | 0.30 | `us_spot_etf_netflow_total` |
| onchain_capital | 0.25 | `realized_cap_change` + `whale_accumulation` + `exchange_netflow` |
| stablecoin | 0.20 | `usdt_supply_change` + `usdc_supply_change` |
| spot_derivatives | 0.15 | `spot_volume_trend` + `funding_rate` + `basis_spread` |
| macro | 0.10 | `fed_balance_sheet_change` + `dxy` |

**缺失处理**：缺失组件 (如 Phase 1 无 onchain_capital) 不计为 0，而是按剩余可用权重重新归一化。

**等级判定**：

| 等级 | 条件 |
|---|---|
| **强回流** | >= 70 且连续 7 天不低于 60 |
| **弱回流** | 40 - 69 |
| **无回流** | < 40 |

### Structure Risk Score (0-100)

衡量市场结构脆弱程度。

| 组件 | 权重 | 来源指标 |
|---|---|---|
| leverage | 0.35 | `leverage_risk_index` |
| liquidation | 0.25 | `liquidation_volume` (缺失时退化到 funding 代理) |
| basis | 0.20 | `basis_spread` |
| trend | 0.20 | `spot_volume_trend` (反向) |

**风险等级**：高风险 (>= 70) / 中风险 (40-69) / 低风险 (< 40)

### 标准化方法

每个组件先 z-score 标准化 (基于全量历史均值与标准差)，再映射到 0-100 区间，最后加权平均。

## 阶段状态机

7 个阶段构成完整市场周期：

| ID | 阶段 | 进入条件 |
|---|---|---|
| 1 | 深熊去杠杆 | capital < 25 且 risk >= 70 |
| 2 | 筑底与换手 | capital < 40 且 risk >= 45 |
| 3 | 复苏与吸筹 | 40 <= capital < 55 且 risk < 60 且 trend >= -5 |
| 4 | 上升趋势早期 | 55 <= capital < 70 且 risk < 55 且 trend > 0 |
| 5 | 加速上涨与泡沫化 | capital >= 70 且 risk < 45 且 trend > 5 |
| 6 | 高位派发与结构脆弱 | capital >= 60 且 risk >= 55 |
| 7 | 见顶回落与再去杠杆 | 其他 (默认兜底) |

每次阶段判定输出：
- `stage_name` — 阶段名称
- `confidence` — 置信度 (0.5 - 0.95)
- `explanation_public` — 通俗解释
- `explanation_pro` — 专业解释 (含触发规则与具体指标值)
- `evidence` — JSON 证据 (capital/risk/trend 数值)

## 调度任务

| 任务 | 频率 | 说明 |
|---|---|---|
| `ingest_all` | 每 30 分钟 | 拉取所有已启用数据源（免费 + 扩展 + 付费） |
| `normalize_all` | 每 30 分钟 | 原始数据规范化写入 normalized_series |
| `compute_metrics` | 每 15 分钟 | 计算 must_have + nice_to_have 指标 |
| `compute_scores_stage` | 每 15 分钟 | 计算两项评分 + 阶段判定 |

首次启动的 bootstrap 是一次性的全量 backfill，后续由定时任务增量更新。

所有任务执行记录写入 `job_runs` 表 (任务名、状态、耗时、影响行数、错误信息)。

## API 端点

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 健康检查 (DB + Redis 连通性) |
| GET | `/sources/status` | 各数据源最近成功/失败时间与错误信息 |
| GET | `/metrics/catalog?tier=&lead_lag=` | 指标字典，支持 tier 和 lead_lag 筛选 |
| GET | `/metrics/{metric_id}?start=&end=&granularity=` | 指标时序查询 (daily/weekly/monthly 聚合) |
| GET | `/scores/capital_inflow/latest` | 最新 Capital Inflow Score + 等级 |
| GET | `/scores/structure_risk/latest` | 最新 Structure Risk Score + 风险等级 |
| GET | `/scores/capital_inflow?start=&end=&granularity=` | Capital Inflow 时序 |
| GET | `/scores/structure_risk?start=&end=&granularity=` | Structure Risk 时序 |
| GET | `/scores/{score_id}?start=&end=&granularity=` | 任意评分时序 |
| GET | `/stage/latest` | 最新阶段判定 |
| GET | `/stage?start=&end=` | 历史阶段序列 |
| GET | `/stage/explain?ts=` | 指定时间点阶段解释 (含 evidence) |
| GET | `/stage/stats?start=&end=` | 阶段累计天数、切换次数、评分分布、多周期叠加 |

**统一响应格式**：

```json
{
  "data": { },
  "meta": {
    "source": "fred",
    "delay": "1d",
    "unit": "pct",
    "version": 1
  },
  "updated_at": "2026-02-26T00:00:00+00:00"
}
```

**Granularity 聚合**：
- `daily` — 原始日频数据
- `weekly` — 按 ISO 周分组取均值
- `monthly` — 按自然月分组取均值

## Docker Compose 服务

```yaml
services:
  db:        # PostgreSQL 15, 端口 5432, 数据持久化到 volume
  redis:     # Redis 7 Alpine, 端口 6379
  backend:   # Python 3.11 + FastAPI, 端口 8000
  frontend:  # Node 20 + Next.js 14, 端口 3000
  nginx:     # 可选 profile=proxy, 端口 80 反向代理 frontend/backend
```

`backend` 依赖 `db` 和 `redis` 健康检查通过后才启动。

## 故障排查

### 启动后前端显示"数据初始化中"

正常现象。首次 backfill 需要 2-5 分钟从各数据源拉取历史数据。检查后端日志：

```bash
docker compose logs -f backend
```

看到 `job_done name=bootstrap_phase1` 即表示初始化完成，刷新页面即可。

### FRED 数据拉取失败

确认 `.env` 中 `FRED_API_KEY` 已填入有效密钥。免费注册: https://fred.stlouisfed.org/docs/api/api_key.html

FRED 失败不影响其他数据源 (Coinbase / CoinGecko / Farside)，但宏观维度指标会缺失。

### CoinGecko 频繁 429 限速

CoinGecko 免费 tier 速率较低。可选方案：
1. 在 `.env` 填入 `COINGECKO_API_KEY` (免费 demo key 可提高限额)
2. 等待重试，适配器内置指数退避重试策略 (最多 3 次)

### Farside ETF 数据解析失败

Farside 数据通过网页抓取获得，HTML 结构变化可能导致解析失败。查看日志中是否有 `farside_table_not_found` 警告。ETF 数据缺失不影响其他维度评分 (权重自动重归一化)。

### Redis 连接失败

Redis 为可选组件。如 Redis 不可用：
- `/health` 会返回 `degraded` 状态但 API 仍可用
- 缓存层自动降级，所有请求直接查询 DB

### 数据库连接失败

检查 PostgreSQL 容器状态：

```bash
docker compose ps db
docker compose logs db
```

确认 `.env` 中数据库配置与 `docker-compose.yml` 一致。

## 分阶段路线图

### 已完成项 (Phase 1 + 2 + 3)

- [x] 后端框架 + DB + Alembic 迁移
- [x] 免费数据源适配器: FRED / Coinbase / Farside / CoinGecko
- [x] 扩展数据源适配器: Kraken / Bitstamp / Deribit
- [x] 付费数据源适配器: Glassnode / Coin Metrics (按 API Key 启用)
- [x] must_have + nice_to_have 指标计算链路
- [x] 评分系统 (capital_inflow + structure_risk + onchain_capital 真实组件)
- [x] 7 阶段状态机 + 阶段解释
- [x] 回测增强: 阶段累计天数/切换次数/评分分布/多周期叠加
- [x] 全部 API 端点 + 速率限制 + 缓存
- [x] Docker Compose 一键启动
- [x] 首次启动自动 backfill (后台线程)
- [x] 前端 5 页面完整可访问 (概览/资金流/结构风险/宏观/指标详情)
- [x] 指标详情页点击展开时序图
- [x] 时间窗口选择器 (7D/30D/90D/1Y/ALL)
- [x] Nginx 反向代理模板 + Compose profile

## 技术栈

| 层 | 技术 |
|---|---|
| Backend | Python 3.11, FastAPI 0.111, SQLAlchemy 2.0, Alembic 1.13 |
| Scheduler | APScheduler 3.10 (预留 Celery/Temporal 接口) |
| Database | PostgreSQL 15 |
| Cache | Redis 7 (可选，graceful fallback) |
| Frontend | Next.js 14, TypeScript 5.5, ECharts 5.5 |
| HTTP Client | httpx 0.27 (带重试与超时) |
| Deploy | Docker Compose |
| Rate Limit | SlowAPI (默认 60 req/min/IP) |

## 免责声明

本看板仅供信息参考，不构成任何投资建议。数据来源于公开 API，可能存在延迟或不准确。使用者应自行判断并承担投资风险。
