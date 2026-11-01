# 系统概要设计文档 (High Level Design) - 妖股选股系统

> 版本：v1.0
> 日期：2026-10-31
> 上游依据：`PRD.md` v1.0、`DESIGN_SPEC.md` v1.0

---

## 1. 项目概述

### 1.1 项目背景

《妖股选择框架_跨年总龙.txt》定义了一套跨年妖股筛选方法论，但完全依赖人工在行情软件中执行：门槛核查费时、淘汰原因不可回溯、跟踪表易失真。本系统将该方法论固化为一个可每日运行、每步可解释、每次决策留痕的 Web 工作台。

### 1.2 核心目标

| 目标 | 对应验收 |
|---|---|
| 一键完成全市场硬门槛筛选，覆盖 ≥99% 在市 A 股 | AC-01 / 核心指标 |
| 每只落选股票可查具体淘汰门槛与实测值 | AC-03 / AC-04 |
| 观察池建设、状态流转、淘汰理由 100% 留痕 | AC-05 |
| 评分构成可逐项回溯，权重可配置 | AC-07 |
| 在腾讯云出口 IP 受限环境下通过多源降级保持可用 | AC-09 / R-01 |
| 明确标注一期未校验项，不做虚假完整性承诺 | AC-12 |

### 1.3 一期范围

A 股全市场；硬门槛（总市值 / 股价 / ST / 停牌）；题材与形态筛选（自动 + 人工确认）；观察池与跟踪；规则加减分；手动 + 每日定时刷新；异动与换手人工补录；单用户密码登录。

**明确不做：** 港股、机构持仓与利空事件门槛、盘中实时、多用户、投资建议生成。

---

## 2. 技术框架

### 2.1 技术栈选型

| 层 | 选型 | 版本约束 |
|---|---|---|
| 后端框架 | FastAPI | ≥ 0.110 |
| ASGI 服务器 | Uvicorn | ≥ 0.27 |
| 数据库 | sqlite3（Python 标准库） | 3.40+（需 WAL） |
| 数据校验 | Pydantic | v2 |
| HTTP 客户端 | httpx | ≥ 0.27（异步 + 连接池） |
| 定时任务 | APScheduler | 3.x |
| 前端框架 | React | 18 |
| 构建工具 | Vite | 5.x |
| 语言 | TypeScript | 5.x |
| UI 库 | Bootstrap | 5.3 |
| 图表 | ECharts | 5.x |
| 测试 | pytest / pytest-asyncio / pytest-cov | — |

**约束：**
- 不引入 ORM（SQLAlchemy 等），Repository 层手写 SQL
- 不引入迁移框架（Alembic），用 `db.py` 内置版本号迁移
- 密码哈希使用标准库 `hashlib.pbkdf2_hmac`，会话使用标准库 `hmac` 签名，不引第三方认证库
- 定时任务与 Web 服务同进程，不引入 Celery / Redis

### 2.2 核心技术组件说明

| 组件 | 职责 | 关键设计 |
|---|---|---|
| `SourceAdapter` | 统一行情源契约 | 每个源实现 `async fetch_all() -> list[Quote]`；归一化在适配器内部完成 |
| `market_service` | 抓取编排 | 按 `priority` 依次尝试，成功即停；记录健康状态 |
| `gates.py` | 硬门槛规则注册表 | 每条门槛是一个纯函数，返回结构化判定结果 |
| `screening_service` | 筛选编排 | 四阶段流水，逐条落 `screening_results` |
| `scoring_service` | 评分计算 | 权重从 `settings` 读取，明细整体落库 |
| `watch_pool_service` | 状态机 | 唯一允许写 `watch_pool.status` 的地方，强制写历史 |
| `scheduler` | 定时任务 | 每个交易日 15:30 触发刷新与筛选 |

### 2.3 代码架构

```
Yaogu/
├── src/
│   ├── main.py
│   ├── core/{config,db,security,logging}.py
│   ├── api/
│   │   ├── deps.py
│   │   └── routes/{auth,screening,stocks,watch_pool,manual_metrics,data_sources,settings,export,system}.py
│   ├── services/{market_service,screening_service,gates,scoring_service,watch_pool_service,source_health,export_service}.py
│   ├── repositories/{stocks,daily_quotes,themes,screening,watch_pool,manual_metrics,data_sources,settings,jobs}.py
│   ├── models/            # 领域 dataclass（Quote、GateResult、ScoreDetail…）
│   ├── schemas/           # Pydantic 请求/响应
│   ├── integrations/sources/{base,tencent,sina,eastmoney}.py
│   └── tasks/scheduler.py
├── frontend/src/
│   ├── pages/{Login,Workbench,WatchPool,StockDetail,DataSources,Settings}.tsx
│   ├── components/ui/
│   ├── styles/{tokens.css,bootstrap-override.css}
│   ├── charts/theme.ts
│   └── api/client.ts
├── tests/{unit,integration,fixtures}
└── data/yaogu.db          # 运行时生成，不入库
```

**分层规则**：Router 只做参数校验与响应组装；业务规则全部在 `services`；SQL 只在 `repositories`。禁止 Router 直连数据库。

---

## 3. 系统架构设计

### 3.1 架构概述

单机三层架构，前后端分离部署：

```
┌─────────────────────────────────────────────────────────┐
│  浏览器  React 18 SPA (Vite 构建产物)                     │
└───────────────┬─────────────────────────────────────────┘
                │ HTTPS / JSON  /api/v1/*
┌───────────────▼─────────────────────────────────────────┐
│  Nginx（反向代理 + TLS + 静态资源）                        │
└───────────────┬─────────────────────────────────────────┘
                │
┌───────────────▼─────────────────────────────────────────┐
│  FastAPI (Uvicorn)                                      │
│  ┌──────────┐  ┌───────────┐  ┌──────────────────────┐  │
│  │ Routers  │→ │ Services  │→ │ Repositories         │  │
│  └──────────┘  └─────┬─────┘  └──────────┬───────────┘  │
│                      │                    │              │
│              ┌───────▼────────┐   ┌───────▼────────┐     │
│              │ SourceAdapter  │   │ sqlite3 (WAL)  │     │
│              └───────┬────────┘   └────────────────┘     │
│                      │                                   │
│              ┌───────▼────────┐                          │
│              │ APScheduler    │                          │
│              └────────────────┘                          │
└───────────────┬─────────────────────────────────────────┘
                │ HTTPS
┌───────────────▼─────────────────────────────────────────┐
│ 外部免费行情源：腾讯 / 新浪 / 东方财富                      │
└─────────────────────────────────────────────────────────┘
```

### 3.2 各层职责

| 层 | 职责 | 禁止事项 |
|---|---|---|
| Routers | 认证依赖、请求校验、调用 Service、组装响应 | 不写 SQL、不写业务判断 |
| Services | 业务编排、规则计算、事务边界 | 不直接拼 HTML/HTTP 响应 |
| Repositories | 参数化 SQL、行到领域对象映射 | 不包含业务判断 |
| Integrations | 外部 HTTP、字段归一化、重试 | 不感知数据库 |
| Tasks | 定时触发、调用 Service | 不写业务逻辑 |

---

## 4. 数据库设计

### 4.1 数据库选型

sqlite3 单文件，WAL 模式。理由：单用户、数据量可控（5000 股 × 250 交易日 ≈ 125 万行/年，索引下查询毫秒级）、零运维、便于备份（复制 .db 文件）。

连接参数：

```python
conn = sqlite3.connect(DB_PATH)
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA foreign_keys=ON")
conn.execute("PRAGMA busy_timeout=5000")
conn.row_factory = sqlite3.Row
```

### 4.2 核心表结构

```sql
-- 1. 用户（单用户）
CREATE TABLE users (
  id            INTEGER PRIMARY KEY CHECK (id = 1),
  password_hash TEXT    NOT NULL,           -- pbkdf2_hmac$iter$salt$hash
  updated_at    TEXT    NOT NULL
);

-- 2. 配置键值
CREATE TABLE settings (
  key         TEXT PRIMARY KEY,
  value_json  TEXT NOT NULL,
  updated_at  TEXT NOT NULL
);

-- 3. 数据源
CREATE TABLE data_sources (
  name            TEXT PRIMARY KEY,
  enabled         INTEGER NOT NULL DEFAULT 1,
  priority        INTEGER NOT NULL,
  last_success_at TEXT,
  last_error      TEXT,
  updated_at      TEXT NOT NULL
);

-- 4. 数据源健康流水
CREATE TABLE source_health_logs (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  source      TEXT    NOT NULL,
  checked_at  TEXT    NOT NULL,
  ok          INTEGER NOT NULL,
  latency_ms  INTEGER,
  error       TEXT
);
CREATE INDEX idx_health_source_time ON source_health_logs(source, checked_at);

-- 5. 股票基础信息
CREATE TABLE stocks (
  code       TEXT PRIMARY KEY,
  name       TEXT NOT NULL,
  market     TEXT NOT NULL,                 -- SH / SZ / BJ
  list_date  TEXT,
  is_st      INTEGER NOT NULL DEFAULT 0,
  status     TEXT NOT NULL DEFAULT 'normal', -- normal / suspended / delisting
  updated_at TEXT NOT NULL
);

-- 6. 日行情（核心表）
CREATE TABLE daily_quotes (
  code          TEXT NOT NULL REFERENCES stocks(code),
  trade_date    TEXT NOT NULL,              -- YYYY-MM-DD
  open REAL, high REAL, low REAL, close REAL, pre_close REAL,
  pct_chg       REAL,                       -- 百分比，如 3.21
  volume        INTEGER,
  amount        REAL,
  turnover_rate REAL,                       -- 百分比
  total_mv      REAL,                       -- 单位：亿元（已归一化）
  float_mv      REAL,                       -- 单位：亿元
  limit_up      REAL,                       -- 当日涨停价，若有
  source        TEXT NOT NULL,
  fetched_at    TEXT NOT NULL,
  PRIMARY KEY (code, trade_date)
);
CREATE INDEX idx_quotes_date ON daily_quotes(trade_date);

-- 7. 题材池
CREATE TABLE themes (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  name       TEXT    NOT NULL UNIQUE,
  branch     TEXT    NOT NULL,              -- main1 / main2 / main3
  enabled    INTEGER NOT NULL DEFAULT 1,
  sort_order INTEGER NOT NULL DEFAULT 0
);

-- 8. 股票-题材
CREATE TABLE stock_themes (
  code     TEXT    NOT NULL,
  theme_id INTEGER NOT NULL REFERENCES themes(id) ON DELETE CASCADE,
  source   TEXT    NOT NULL,                -- auto / manual
  PRIMARY KEY (code, theme_id)
);

-- 9. 筛选批次
CREATE TABLE screening_runs (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at   TEXT NOT NULL,
  finished_at  TEXT,
  status       TEXT NOT NULL,               -- running / success / partial / failed
  params_json  TEXT NOT NULL,
  stats_json   TEXT
);

-- 10. 单股单门槛判定（可解释性核心）
CREATE TABLE screening_results (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id       INTEGER NOT NULL REFERENCES screening_runs(id) ON DELETE CASCADE,
  code         TEXT    NOT NULL,
  stage        TEXT    NOT NULL,            -- hard_gate / theme / pattern
  gate         TEXT    NOT NULL,            -- total_mv / price / st_suspended / theme_match / first_board ...
  passed       INTEGER NOT NULL,
  actual_value TEXT,
  threshold    TEXT,
  reason       TEXT
);
CREATE INDEX idx_results_run ON screening_results(run_id);
CREATE INDEX idx_results_code ON screening_results(code, run_id);

-- 11. 评分
CREATE TABLE scores (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  code          TEXT    NOT NULL,
  run_id        INTEGER NOT NULL REFERENCES screening_runs(id) ON DELETE CASCADE,
  total_score   REAL    NOT NULL,
  details_json  TEXT    NOT NULL,           -- [{item, delta, weight, evidence, source}]
  calculated_at TEXT    NOT NULL
);
CREATE INDEX idx_scores_run ON scores(run_id);

-- 12. 观察池
CREATE TABLE watch_pool (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  code             TEXT    NOT NULL UNIQUE REFERENCES stocks(code),
  status           TEXT    NOT NULL DEFAULT 'keep',  -- keep / watch / drop
  theme_side       TEXT,                             -- main / branch
  first_board_date TEXT,
  tier             TEXT,                             -- leader / follower
  added_at         TEXT    NOT NULL,
  updated_at       TEXT    NOT NULL
);
CREATE INDEX idx_pool_status ON watch_pool(status);

-- 13. 状态流转留痕（理由非空是硬约束）
CREATE TABLE watch_pool_history (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  pool_id     INTEGER NOT NULL REFERENCES watch_pool(id) ON DELETE CASCADE,
  from_status TEXT,
  to_status   TEXT NOT NULL,
  reason      TEXT NOT NULL CHECK (length(trim(reason)) > 0),
  created_at  TEXT NOT NULL
);
CREATE INDEX idx_history_pool ON watch_pool_history(pool_id, created_at);

-- 14. 人工补录
CREATE TABLE manual_metrics (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  code        TEXT NOT NULL,
  trade_date  TEXT NOT NULL,
  metric      TEXT NOT NULL,                -- pct_30d / touch_200 / turnover_history
  value       REAL,
  entered_at  TEXT NOT NULL,
  UNIQUE (code, trade_date, metric)
);

-- 15. 任务执行记录
CREATE TABLE job_runs (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  job         TEXT NOT NULL,
  started_at  TEXT NOT NULL,
  finished_at TEXT,
  status      TEXT NOT NULL,                -- success / failed / skipped
  error       TEXT
);
```

### 4.3 初始数据

| 内容 | 来源 |
|---|---|
| `users` | 首次启动时以 `INITIAL_PASSWORD` 环境变量初始化；未设置则生成随机密码并打印到日志 |
| `data_sources` | 腾讯(1) / 东财(2) / 新浪(3)，默认全启用 |
| `themes` | 从 `妖股选择框架_跨年总龙.txt` 第三部分种子化：主线 1–3 共 9 个题材 |
| `settings` | 门槛阈值、评分权重、池容量、阶段节奏、调度时间 |

---

## 5. 接口规范

### 5.1 通用约定

- 前缀 `/api/v1`
- JSON 请求/响应，UTF-8
- 认证：`HttpOnly` + `SameSite=Lax` 签名 Cookie（HMAC-SHA256，含过期时间）
- 统一错误体：`{"error": {"code": "GATE_CONFIG_INVALID", "message": "中文可读信息", "detail": {...}}}`
- 分页：`?page=1&size=50`，响应含 `{"items": [], "total": 0, "page": 1, "size": 50}`
- 时间统一 ISO 8601 带时区

### 5.2 接口列表

#### 认证

| 方法 | 路径 | 说明 | 请求 | 响应 |
|---|---|---|---|---|
| POST | `/auth/login` | 登录 | `{password}` | 204 + Set-Cookie |
| POST | `/auth/logout` | 登出 | — | 204 |
| GET | `/auth/me` | 当前会话 | — | `{logged_in: bool, locked_until?: str}` |

#### 筛选

| 方法 | 路径 | 说明 | 请求 | 响应 |
|---|---|---|---|---|
| POST | `/screening/runs` | 启动筛选（后台执行） | `{scope: "all"\|"board", board?: str, with_theme: bool}` | 202 `{run_id}` |
| GET | `/screening/runs` | 批次列表 | `?page&size` | 分页 |
| GET | `/screening/runs/{run_id}` | 批次状态与进度 | — | `{status, progress, stats}` |
| GET | `/screening/runs/{run_id}/results` | 判定明细 | `?stage&passed&page&size` | 分页 |
| GET | `/screening/runs/{run_id}/candidates` | 候选池 | `?page&size&sort=score` | 分页 |

#### 个股

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/stocks` | 搜索/分页 `?q&page&size` |
| GET | `/stocks/{code}` | 基础信息 + 最新行情 |
| GET | `/stocks/{code}/quotes` | 历史行情 `?days=60` |
| GET | `/stocks/{code}/gates` | 门槛判定 `?run_id` |
| GET | `/stocks/{code}/score` | 评分与明细 `?run_id` |

#### 观察池

| 方法 | 路径 | 说明 | 请求 |
|---|---|---|---|
| GET | `/watch-pool` | 列表 `?status&sort` | — |
| POST | `/watch-pool` | 加入 | `{code, theme_side?, first_board_date?, tier?}` |
| PATCH | `/watch-pool/{id}` | 状态变更 | `{status, reason}` |
| DELETE | `/watch-pool/{id}` | 移出 | `{reason}` |
| GET | `/watch-pool/{id}/history` | 流转历史 | — |
| GET | `/watch-pool/stats` | 容量与阶段 | — |

> `PATCH` 与 `DELETE` 的 `reason` 缺失或空白 → 422。这是 AC-05 的接口级保障。

#### 人工补录

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/manual-metrics/{code}` | 查询 |
| PUT | `/manual-metrics/{code}` | 写入 `{trade_date, metric, value}` |
| POST | `/manual-metrics/import` | CSV 导入（multipart） |

#### 数据源与设置

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/data-sources` | 列表 + 健康状态 |
| PATCH | `/data-sources/{name}` | `{enabled?, priority?}` |
| POST | `/data-sources/{name}/test` | 即时探测 |
| GET | `/settings` | 全部配置 |
| PUT | `/settings` | 批量更新 `{key: value}` |

#### 导出与系统

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/export/watch-pool.csv` | 观察池导出 |
| GET | `/export/screening/{run_id}.csv` | 筛选结果导出 |
| GET | `/health` | 存活探针（免认证） |
| GET | `/system/status` | 上次筛选、源摘要、行情快照日期 / 降级标记、阶段（顶栏用） |

### 5.3 外部接口设计

| 源 | 用途 | 关键端点形态 | 归一化要点 |
|---|---|---|---|
| 东方财富 | 全市场快照（主源） | 批量列表接口，一次返回全部 A 股 | 市值单位（元→亿元）、涨跌幅已为百分比 |
| 腾讯 | 批量行情（备用） | `qt.gtimg.cn` 批量代码查询 | 字段以 `~` 分隔，需按索引取值；市值单位需换算 |
| 新浪 | 批量行情（备用） | `hq.sinajs.cn` 批量查询 | 需带 Referer；字段顺序固定 |

**统一内部契约：**

```python
@dataclass
class Quote:
    code: str
    name: str
    trade_date: str
    close: float
    pre_close: float
    pct_chg: float
    turnover_rate: float | None
    total_mv: float | None      # 亿元
    float_mv: float | None      # 亿元
    limit_up: float | None
    status: str                 # normal / suspended / delisting
    source: str
    fetched_at: str
```

---

## 6. 核心功能模块设计

### 6.1 行情接入模块

```
market_service.fetch_market_snapshot()
  1. 读取 data_sources（enabled=1，按 priority 升序）
  2. for source in sources:
       try: quotes = await adapter.fetch_all()     # 超时 10s，重试 2 次
       except SourceError as e: 记录 source_health_logs；continue
       else: 校验条目数 > 1000 才接受；break
  3. 归一化二次校验（市值范围、字段非空率）
  4. 批量 upsert stocks + daily_quotes（executemany，单事务）
  5. 返回 FetchResult{source, count, elapsed_ms, failures, stale, as_of}
```

**失败判定**：

- 全部源失败但存在最近一份完整快照 → 只读回退该快照，返回 `stale=True` / `source="cache"` / `as_of=交易日`；批次状态 `partial`，顶栏与工作台显示「行情降级」。
- 全部源失败且无历史快照、或快照条目不足 → 抛出 `MarketUnavailable`，筛选批次标记 `failed`。
- 每日定时任务遇到 `stale` 只写 `job_runs.status=partial`，不自动发起筛选，避免用旧行情产出新结论。

### 6.2 硬门槛模块

规则注册表（每条为纯函数）：

| gate | 规则 | 边界 | 数据缺失处理 |
|---|---|---|---|
| `total_mv` | `min_mv ≤ 总市值 ≤ max_mv` | 默认 20 / 45，含边界 | 缺失 → `passed=False, reason="市值数据缺失"` |
| `price` | `min_price ≤ 收盘价 ≤ max_price` | 默认 3 / 10，含边界 | 缺失 → 不通过 |
| `st_suspended` | `not is_st and status == normal` | — | 默认不通过 |
| `float_mv` | `流通市值 ≤ 40`（P1，可配置开启） | 含边界 | 缺失 → 标记 `skipped` |

```python
@dataclass
class GateResult:
    gate: str
    passed: bool
    actual_value: str | None
    threshold: str
    reason: str
```

> 一条不通过即整体淘汰，但**全部门槛都执行并落库**，保证页面能展示完整的逐条判定，而不是只显示第一个失败项。

### 6.3 筛选编排模块

```
run_screening(run_id, params):
  run.status = running
  行情 = market_service.fetch_market_snapshot()
  for quote in 行情:
     hard = [gate(q) for gate in HARD_GATES]
     落库 screening_results(stage="hard_gate")
     if any(not g.passed): continue
     theme = match_theme(q)            # 无命中 → 标记，不淘汰（可配置是否作为门槛）
     落库 stage="theme"
     pattern = detect_pattern(q)       # 首板/换手/一字；不可得的项标记 unavailable
     落库 stage="pattern"
     若通过 → 进入候选
  scoring_service.score(candidates) → scores 落库
  run.status = partial if 任一源失败 else success
```

**进度**：每处理 200 只更新一次 `stats_json.processed`，前端轮询 `GET /screening/runs/{id}`。

### 6.4 形态识别模块（一期降级策略）

| 判据 | 数据需求 | 一期实现 |
|---|---|---|
| 首板涨停 | 当日涨停价 + 前一日收盘 | 有 `limit_up` 且 `close == limit_up` 且前日非涨停 → 自动 |
| 分歧换手板 | 历史 K 线 + 成交额 | 涨停且换手率 > 5% → 自动；否则 `unavailable` |
| 连续一字板 | 开盘=收盘=涨停且换手极低 | 自动 |
| 板块梯队 ≥3 只 | 概念板块成分 + 当日涨停名单 | 依赖源是否提供；不可得 → `unavailable` |
| 换手率 15%–30% | 当日换手率 | 自动 |

`unavailable` 的判据在详情页显示为灰色「待人工确认」，**不计入自动结论，也不伪造通过**。

### 6.5 评分模块

```
总分 = 基础分(60) + Σ(加分项 × 权重) − Σ(减分项 × 权重)
```

| 类型 | 项 | 默认分 | 证据 |
|---|---|---|---|
| 加 | 多概念叠加（≥2 个主线） | +8 | 命中题材数 |
| 加 | 板块梯队龙头 | +6 | tier |
| 加 | 健康换手 15%–30% | +5 | turnover_rate |
| 加 | 次新（上市 2–5 年） | +4 | list_date |
| 加 | 名字辨识度高（人工） | +3 | manual |
| 加 | 年末事件催化（人工） | +5 | manual |
| 减 | 连续缩量一字 | −10 | 形态判定 |
| 减 | 滚动 30 日涨幅 ≥ 150%（接近 200% 红线） | −8 | manual / auto |
| 减 | 板块无跟风梯队 | −6 | unavailable 时不扣分 |

每次计算把 `{item, delta, weight, evidence, source, available}` 整体写入 `details_json`，前端直接渲染。

### 6.6 观察池模块

状态机：

```
        add
  (none) ──→ keep ⇄ watch
               │        │
               └──→ drop ←┘
                (reason 必填)
```

- `add` 时若池内 `status != 'drop'` 数量 ≥ 容量 → 返回 409 `POOL_FULL`，前端提示精简
- 任何状态变更都在同一事务内写 `watch_pool` + `watch_pool_history`
- 状态回退（`drop → keep`）同样要求理由

### 6.7 定时任务模块

| 任务 | 时间 | 行为 |
|---|---|---|
| `daily_refresh` | 交易日 15:30 | 抓快照 → 刷新观察池行情 → 重算评分 → 记录 `job_runs` |
| `weekly_health` | 每周一 09:00 | 对各源做一次探测，结果写健康流水 |

**交易日判断**：抓取后校验返回的 `trade_date` 是否等于当日；不等则标记 `skipped`（节假日）。不维护节假日表。

---

## 7. 交互流程设计

### 7.1 执行筛选

```
用户          前端                 后端
 │ 点击执行筛选 │                     │
 ├────────────→│ POST /screening/runs│
 │             ├────────────────────→│ 创建 run(running)，BackgroundTask
 │             │←── 202 {run_id} ────┤
 │             │ 每 1.5s 轮询       │
 │             ├────────────────────→│ GET /runs/{id}
 │             │←── {progress, ...} ─┤
 │             │ 进度条 + 骨架屏     │
 │             │←── status=success ──┤
 │             │ GET /candidates     │
 │             │←── 分页候选 ────────┤
 │ 浏览 → 加入观察池                   │
```

前端**超过 3 分钟仍 running** 时提示「筛选耗时较长，可稍后回来查看」，不自动取消。

### 7.2 淘汰留痕

```
用户点击「标记淘汰」→ 弹窗（必填理由 + 快捷理由）
  → 前端校验非空 → PATCH /watch-pool/{id} {status:"drop", reason}
    → Service 事务：UPDATE watch_pool + INSERT history
    → 200 → Toast + 行状态即时切换
  ← 422（理由为空）→ 弹窗内联报错，不关闭
```

### 7.3 异常处理流程

| 异常 | 后端 | 前端 |
|---|---|---|
| 单源失败 | 记录健康日志，降级到下一源，`run.status` 可能为 `partial` | 顶部黄色提示条「2 个数据源失败，结果可能不完整」 |
| 全部源失败 | `502 SOURCE_UNAVAILABLE`，保留旧快照 | 空状态 + 「数据源不可用」+ 跳健康页 |
| sqlite 写锁 | 重试 3 次（退避 100/300/900ms），仍失败 → 500 | Toast「数据库繁忙，请重试」 |
| 定时任务失败 | 写 `job_runs.status=failed` + error | 顶栏状态条显示「上次刷新失败」 |
| 未登录 | 401 | 跳登录页，保留原目标路径 |
| 会话过期 | 401 | Toast「登录已过期」→ 登录页 |

---

## 8. 非功能需求设计

### 8.1 性能需求

| 指标 | 目标 | 手段 |
|---|---|---|
| 全市场筛选 | ≤ 3 分钟 | 单请求批量快照；批量写库；规则纯函数 |
| 列表接口 p95 | ≤ 300ms | 索引 + 分页；不做全表扫描 |
| 页面可交互 | ≤ 1.5s（首屏） | Vite 代码分割；表格虚拟滚动 |
| 单次行情抓取 | ≤ 10s | 连接池复用；并发上限 3 |

### 8.2 稳定性需求

- sqlite WAL + `busy_timeout`
- 抓取重试 2 次，指数退避
- 筛选批次幂等：同参数重复执行生成新 `run`，不覆盖历史
- 任何失败都留有 `job_runs` / `source_health_logs` 记录，不静默吞错

### 8.3 安全性需求

- 密码 `pbkdf2_hmac('sha256', ..., 390000)`，盐值随机 16 字节
- 会话 Cookie：`HttpOnly`、`Secure`（生产）、`SameSite=Lax`、HMAC-SHA256 签名、7 天过期
- 登录失败 5 次锁定 5 分钟（内存计数 + 记录日志）
- 所有 SQL 参数化；无字符串拼接
- 凭据与密钥仅从环境变量读取：`APP_SECRET`、`INITIAL_PASSWORD`、`DB_PATH`
- 反向代理强制 HTTPS；仅暴露 80/443

### 8.4 可扩展性需求

- 新增行情源：实现 `SourceAdapter` 并在 `data_sources` 插入一行，无需改 Service
- 新增门槛：在 `gates.py` 注册函数 + 默认配置，落库格式不变
- 新增评分项：配置驱动，无需改前端渲染（明细 JSON 通用）
- 二期机构持仓/利空事件：新增 `manual_metrics.metric` 枚举 + 一个门槛函数即可接入，无需改表结构

### 8.5 易用性需求

- 所有异步操作有 Loading / 成功 / 空 / 失败四态
- 合规提示常驻工作台
- 键盘可达、焦点可见（DESIGN_SPEC §9）
- 错误文案面向用户、可操作（不是堆栈）

---

## 9. 系统边界与依赖

### 9.1 系统边界

**系统内：** 行情抓取、归一化、筛选、评分、观察池、跟踪留痕、导出、定时任务、源健康管理。

**系统外（不负责）：** 交易下单、资金账户、行情实时推送、投资建议、港股、机构持仓与公告数据。

### 9.2 系统依赖

| 依赖 | 类型 | 不可用影响 |
|---|---|---|
| 腾讯 / 东财 / 新浪 免费接口 | 外部 HTTP | 无法刷新行情；保留旧快照并告警 |
| 腾讯云服务器 + 公网 IP | 基础设施 | 服务不可访问 |
| Nginx | 基础设施 | 无 TLS / 静态资源 |
| Python 3.11+ | 运行时 | — |
| Node 18+（仅构建期） | 工具链 | 无法构建前端 |

---

## 10. 风险与应对措施

| 编号 | 风险 | 概率 | 影响 | 应对 |
|---|---|---|---|---|
| R-01 | 免费源屏蔽腾讯云 IP | 高 | 高 | 多源 + 禁用配置 + 健康页；必要时走代理或换区域 |
| R-02 | 源字段变更/限流 | 中 | 中 | 适配器防御式解析（缺字段不抛全局错）+ 单测固定快照 |
| R-03 | 概念/涨停数据不可得 | 中 | 中 | 形态判据降级为 `unavailable` + 人工确认，不伪造 |
| R-04 | sqlite 写并发瓶颈 | 低 | 低 | 单写者 + 短事务 + WAL |
| R-05 | 一期未校验机构持仓/利空 | 确定 | 中 | 界面常驻提示 + 加入池前人工核对 |
| R-06 | 免费源全量快照覆盖不全 | 中 | 中 | 条目数阈值校验（<1000 视为失败）；覆盖率指标展示 |
| R-07 | 定时任务漏跑 | 低 | 中 | `job_runs` 记录 + 手动补跑 + 顶栏状态提示 |

---

## 11. 附录

### 11.1 术语表

| 术语 | 含义 |
|---|---|
| 硬门槛 | 任一不满足即淘汰的条件，见 PRD §3.2 |
| 候选池 | 通过硬门槛（及可选题材/形态）的标的集合 |
| 观察池 | 人工确认后纳入跟踪的标的，容量 30 |
| 首板 | 一段行情中的第一个涨停 |
| 分歧板 | 有真实换手、非一字封板的涨停 |
| 梯队 | 同题材内龙头之外的跟风连板群体 |
| `unavailable` | 数据不可得，判据既不通过也不淘汰，标为待人工确认 |

### 11.2 环境准备清单

```
Python 3.11+
Node 18+（构建前端）
环境变量：APP_SECRET、INITIAL_PASSWORD、DB_PATH、TZ=Asia/Shanghai
目录：data/（sqlite 文件与备份）
生产：Nginx + Uvicorn（systemd 或 docker）
```

### 11.3 变更记录

| 版本 | 日期 | 变更 |
|---|---|---|
| v1.0 | 2026-10-31 | 初版：基于 PRD v1.0 与 DESIGN_SPEC v1.0 输出 |
