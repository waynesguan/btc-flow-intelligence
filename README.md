# btcObserver (Phase 1 MVP)

Bitcoin 资金流与阶段判定看板。项目实现了 Phase 1 的可运行全栈能力：

- FastAPI + PostgreSQL + Alembic + APScheduler
- 免费数据源适配器：FRED / Coinbase / Farside / CoinGecko
- 指标链路：raw -> normalized -> metric_values -> scores -> market_stage
- 前端：Next.js 14 + TypeScript + ECharts（概览页、宏观页真实图表）
- Docker Compose 一键启动

## 目录结构

```text
btcObserver/
├── backend/
├── frontend/
├── ops/
├── config/
├── .env.example
├── docker-compose.yml
└── README.md
```

## 快速启动

1. 复制环境变量

```bash
cp .env.example .env
```

必须先填写 `FRED_API_KEY`（免费注册可得）；未配置时宏观指标会跳过拉取。

2. 启动全部服务

```bash
docker compose up -d --build
```

3. 访问地址

- Frontend: http://localhost:3000
- Backend docs: http://localhost:8000/docs
- Health: http://localhost:8000/health

## 启动流程（自动）

Backend 容器启动后会执行：

1. `alembic upgrade head`
2. `python -m seed.init_seed`
3. FastAPI 启动
4. FastAPI startup 触发：
   - APScheduler 初始化
   - Phase 1 bootstrap 后台线程执行（首次 backfill + normalize + compute，不阻塞 API 可用性）

## 关键 API

- `GET /health`
- `GET /sources/status`
- `GET /metrics/catalog?tier=must_have&lead_lag=lead`
- `GET /metrics/{metric_id}?start=&end=&granularity=`
- `GET /scores/{score_id}?start=&end=&granularity=`
- `GET /scores/capital_inflow/latest`
- `GET /scores/structure_risk/latest`
- `GET /scores/capital_inflow?start=&end=&granularity=`
- `GET /stage/latest`
- `GET /stage?start=&end=`
- `GET /stage/explain?ts=`

统一响应结构：

```json
{
  "data": {},
  "meta": {
    "source": "computed",
    "delay": "daily",
    "unit": "0-100",
    "version": 1
  },
  "updated_at": "2026-02-26T00:00:00Z"
}
```

## 数据源与阶段说明

- Phase 1 已接：FRED / Coinbase / Farside / CoinGecko
- Phase 3 已预留占位：Glassnode / Coin Metrics（需 API Key）
- 其余交易所/衍生品扩展（Kraken/Bitstamp/Deribit）留在 Phase 2

## 评分与阶段

- 配置文件：`config/scoring_weights.yaml`
- 评分输出：
  - `capital_inflow_score`
  - `structure_risk_score`
- 阶段状态机：7 阶段（深熊去杠杆 -> 见顶回落与再去杠杆）

## 免责声明

本项目仅供信息参考，不构成投资建议。
