# 妖股选股系统

A 股短线「妖股」筛选与跟踪工作台。抓取公开行情快照 → 硬门槛淘汰 → 题材匹配 → 形态判定 → 规则评分 → 建立观察池 → 持续跟踪与留痕淘汰。

[![CI](https://github.com/congwang1972/Yaogu/actions/workflows/ci.yml/badge.svg)](https://github.com/congwang1972/Yaogu/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.13%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)
![Tests](https://img.shields.io/badge/tests-159%20passed-brightgreen)
![Coverage](https://img.shields.io/badge/coverage-94.55%25-brightgreen)

> **合规声明**：本工具仅做历史规律复盘，不构成任何投资建议。筛选结论均带数据来源与抓取时间。

<!-- 截图占位：补充界面截图后取消注释
<p align="center"><img src="docs/screenshot-workbench.png" width="820" alt="选股工作台"></p>
-->

## 目录

- [核心特性](#核心特性)
- [快速开始](#快速开始)
- [技术栈](#技术栈)
- [架构与关键设计](#架构与关键设计)
- [数据模型](#数据模型)
- [API 一览](#api-一览)
- [页面清单](#页面清单)
- [项目结构](#项目结构)
- [运维与已知限制](#运维与已知限制)
- [合规](#合规)
- [文档索引](#文档索引)

## 核心特性

一期已交付：

- **三源级联抓取**：东方财富 / 腾讯 / 新浪，失败自动降级并记录健康流水
- **硬门槛筛选**：总市值 20–45 亿、收盘价 3–10 元、非 ST / 非停牌，流通市值门槛可选
- **题材与形态**：题材匹配、首板 / 一字 / 换手形态识别、规则加减分与逐项明细
- **观察池**：容量与阶段目标、状态机（保留 / 观察 / 淘汰）、变更理由强制留痕、软移出
- **人工补录**：30 日涨幅、200 日新高、换手历史、名称辨识度、年末催化，支持 CSV 导入
- **数据导出**：筛选结果与观察池 CSV（UTF-8 BOM，Excel 直接打开）
- **认证**：单用户密码登录、登录锁定、改密后旧会话自动失效
- **定时任务**：每日 15:30 自动刷新 + 每周数据源健康检查
- **前端 6 个页面**：登录、工作台、观察池、个股详情、数据源、设置，暗色「暗夜作战台」

## 快速开始

### 1. 准备环境变量

```bash
cp .env.example .env
```

至少修改 `APP_SECRET` 与 `INITIAL_PASSWORD`。

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `APP_SECRET` | 空 | 会话签名密钥；为空时每次启动随机生成（重启后需重新登录） |
| `INITIAL_PASSWORD` | 空 | 首次建库的登录密码；为空则随机生成并打印到日志 |
| `DB_PATH` | `data/yaogu.db` | sqlite 文件路径 |
| `DATA_DIR` | `./data` | 数据目录 |
| `COOKIE_SECURE` | `0` | HTTPS 部署时置 `1` |
| `LOGIN_MAX_ATTEMPTS` | `5` | 连续失败锁定次数 |
| `LOGIN_LOCK_SECONDS` | `300` | 锁定秒数 |
| `HTTP_TIMEOUT_SECONDS` | `10` | 抓取超时 |
| `HTTP_MAX_RETRIES` | `2` | 预留重试次数 |
| `DAILY_REFRESH_TIME` | `15:30` | 每日刷新时间 |
| `SCHEDULER_ENABLED` | `1` | 是否启用进程内定时任务 |
| `MIN_QUOTE_COUNT` | `1000` | 有效行情条目下限，低于即判该源失败 |

### 2. 启动后端

```bash
python -m venv venv
# Windows: venv\Scripts\activate    Linux/macOS: source venv/bin/activate
pip install -r requirements.txt

python -m uvicorn src.main:app --host 0.0.0.0 --port 8000 --env-file .env
```

首次启动会建库、写入 22 个题材种子、3 个数据源与默认阈值；若未配置 `INITIAL_PASSWORD`，随机密码只打印一次到日志。

API 文档：<http://127.0.0.1:8000/docs>

### 3. 启动前端开发服务器

```bash
cd frontend
npm install
npm run dev
```

Vite 已把 `/api` 代理到 `127.0.0.1:8000`，访问 <http://127.0.0.1:5173>。

### 4. 生产构建

```bash
cd frontend && npm run build
```

构建产物在 `frontend/dist`。后端启动时会自动托管该目录，并支持前端路由刷新（`/pool` 等不会 404）。也可由 Nginx 托管静态资源、反向代理 `/api` 到 uvicorn。

### 5. 运行测试

```bash
python -m pytest
```

基线：**159 passed，覆盖率 94.55%**（门禁 80%，配置在 `pytest.ini`）。测试不访问真实行情接口：适配器用 `httpx.MockTransport` 固定报文，筛选用固定 `FetchResult` 快照。

## 技术栈

**后端**

- Python 3.13+ / FastAPI 0.162 / Pydantic v2
- sqlite3（标准库，WAL 模式，`PRAGMA user_version` 迁移，不引 ORM）
- httpx 同步客户端 + APScheduler 后台调度
- pytest + pytest-cov，覆盖率门禁 80%

**前端**

- 结构层：HTML5 语义化标签，React 18 + TypeScript
- 样式层：CSS3（Grid / Flexbox）+ Bootstrap 5.3 暗色主题 + 设计 Token
- 逻辑层：TypeScript（ES2020+）、Vite 5 构建、react-router-dom 6、ECharts 5
- 视觉规范见 `DESIGN_SPEC.md`；主色 `#D84A3C` 仅用于 CTA，涨跌用红绿 + 符号双编码，状态色不复用红绿

## 架构与关键设计

```text
src/
  api/routes/        # Router：只做 HTTP 契约与参数校验
  api/deps.py        # get_db / require_login（FastAPI Depends）
  services/          # 领域规则：门槛、评分、筛选编排、观察池状态机、抓取降级
  repositories/      # SQL 访问，不暴露裸 UPDATE
  integrations/sources/  # eastmoney / tencent / sina 适配器 + 归一化工具
  models/domain.py   # Quote / GateResult / ScoreDetail 等领域对象
  core/              # 配置、sqlite、日志、安全
  tasks/scheduler.py # 每日刷新、每周健康检查
```

关键设计：

- **三态门槛**：`pass` / `fail` / `unavailable`。数据缺失的 `unavailable` 不否决、也不放行，界面显示「待确认」。
- **未启用 ≠ 不合格**：`skipped` 门槛不参与一票否决。
- **每次判定可回看**：实测值、阈值、淘汰理由成对落库，对应 AC-04。
- **抓取保险丝**：有效条目少于 `MIN_QUOTE_COUNT` 视为整源失败，避免空快照覆盖旧数据。
- **人工补录优先最新日期**：每项指标取最新一条计入评分。

## 数据模型

15 张表：

| 表 | 用途 |
| --- | --- |
| `users` | 单用户密码哈希 |
| `settings` | 阈值 / 评分 / 观察池 / 定时任务配置（JSON） |
| `data_sources` | 数据源启停、优先级、最近成功 / 失败 |
| `source_health_logs` | 每次抓取或探测的健康流水 |
| `stocks` | 股票基础信息（代码、名称、市场、ST、交易状态） |
| `daily_quotes` | 日行情快照（市值统一亿元，主键 code + trade_date） |
| `themes` | 2026 跨年题材池（主线 / 支线 / 储备） |
| `stock_themes` | 股票-题材关联 |
| `screening_runs` | 筛选批次（参数、状态、进度、耗时） |
| `screening_results` | 每条门槛 / 题材 / 形态判定，含实测值、阈值、理由 |
| `scores` | 评分总分与逐项明细 JSON |
| `watch_pool` | 观察池记录（容量、题材方向、首板日期、梯队） |
| `watch_pool_history` | 状态变更留痕，reason 非空由 CHECK 约束兜底 |
| `manual_metrics` | 人工补录指标（code + trade_date + metric 唯一） |
| `job_runs` | 定时任务执行记录 |

## API 一览

统一前缀 `/api/v1`，JSON；错误统一为 `{"error": {"code", "message", "detail"}}`。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/auth/login` | 登录，204 并下发 HttpOnly Cookie |
| POST | `/auth/logout` | 登出 |
| GET | `/auth/me` | 当前会话 |
| POST | `/auth/password` | 修改密码（旧会话立即失效） |
| GET | `/health` | 健康探针（免登录） |
| GET | `/system/status` | 顶栏状态：数据源、最近批次、最近任务、池统计 |
| POST | `/screening/runs` | 启动筛选（202，后台执行） |
| GET | `/screening/runs` | 批次列表（分页） |
| GET | `/screening/runs/{id}` | 批次详情与进度 |
| GET | `/screening/runs/{id}/results` | 门槛 / 题材 / 形态判定（可按 stage、passed 过滤） |
| GET | `/screening/runs/{id}/candidates` | 候选池（含题材与评分） |
| GET | `/stocks` | 股票搜索（分页） |
| GET | `/stocks/{code}` | 详情：基础信息、最新行情、题材、观察池状态 |
| GET | `/stocks/{code}/quotes` | 历史行情（默认 60 日） |
| GET | `/stocks/{code}/gates` | 最近批次的门槛判定 |
| GET | `/stocks/{code}/score` | 最近批次的评分明细 |
| GET | `/watch-pool/stats` | 容量、状态计数、当前阶段与目标 |
| GET | `/watch-pool` | 观察池列表（可按 status 过滤） |
| POST | `/watch-pool` | 加入观察池 |
| GET | `/watch-pool/{id}/history` | 变更历史 |
| PATCH | `/watch-pool/{id}` | 变更状态，`reason` 必填 |
| DELETE | `/watch-pool/{id}` | 软移出（置为淘汰，保留历史） |
| GET | `/manual-metrics/{code}` | 人工补录记录 |
| PUT | `/manual-metrics/{code}` | 写入 / 覆盖单条指标 |
| POST | `/manual-metrics/import` | CSV 导入（code,trade_date,metric,value） |
| GET | `/data-sources` | 数据源与最近健康 |
| PATCH | `/data-sources/{name}` | 启停 / 调整优先级 |
| POST | `/data-sources/{name}/test` | 实时探测 |
| GET | `/settings` | 读取配置 |
| PUT | `/settings` | 保存配置（仅 thresholds/scoring/pool/schedule） |
| GET | `/export/watch-pool.csv` | 观察池导出 |
| GET | `/export/screening/{run_id}.csv` | 筛选结果导出 |

## 页面清单

- [x] **登录页 `/login`**：密码登录、错误提示、合规声明
- [x] **选股工作台 `/workbench`**：执行筛选、进度轮询、候选池 / 落选明细切换、加入观察池、批次导出、失败 / 部分失败提示、二期门槛人工核对提醒
- [x] **观察池 `/pool`**：容量进度、状态计数、全部 / 保留 / 观察 / 淘汰筛选、状态变更弹窗（理由必填 + 常用理由）、导出
- [x] **个股详情 `/stocks/:code`**：核心指标、K 线 + 换手率图、门槛与形态判定、评分明细、人工补录表单与最近记录、观察池变更时间线
- [x] **数据源 `/sources`**：三源卡片、启停、实时测试、最近健康与错误、腾讯云 IP 屏蔽提示
- [x] **设置 `/settings`**：硬门槛阈值、评分基准分与逐项分值 / 权重、池容量与阶段目标、定时任务、修改密码

## 项目结构

```text
Yaogu/
├── .github/workflows/ci.yml    # CI：pytest + 覆盖率门禁、前端构建
├── .claude/prompts/            # 产品 / 设计 / 开发 / 测试 / 协调者提示词
├── src/
│   ├── api/
│   │   ├── deps.py
│   │   └── routes/             # auth, screening, stocks, watch_pool, manual_metrics,
│   │                           # data_sources, settings, export, system
│   ├── core/                   # config, db, logging, security
│   ├── integrations/sources/   # base, eastmoney, tencent, sina
│   ├── models/domain.py
│   ├── repositories/
│   ├── schemas/common.py
│   ├── services/
│   ├── tasks/scheduler.py
│   └── main.py
├── frontend/
│   ├── src/
│   │   ├── api/client.ts
│   │   ├── charts/theme.ts
│   │   ├── components/         # Layout + ui（Button/Card/Badge/DataTable/Modal/Toast）
│   │   ├── pages/              # Login, Workbench, WatchPool, StockDetail, DataSources, Settings
│   │   ├── styles/
│   │   ├── types.ts
│   │   └── utils/format.ts
│   ├── index.html
│   ├── package.json
│   └── vite.config.ts
├── tests/                      # 9 个测试文件 + conftest 夹具
├── scripts/run.sh
├── .env.example
├── requirements.txt
├── pytest.ini
├── PRD.md / DESIGN_SPEC.md / HLD.md / TODO.md
└── README.md
```

## 运维与已知限制

- **腾讯云 IP 屏蔽**：部分免费接口会屏蔽云服务器出口 IP。部署后先在「数据源」页逐个测试；若主源长期失败，可改用收费源适配器（新增实现并注册到 `SOURCE_REGISTRY`）。
  - 2026-11-01 实测腾讯云出口：东方财富 `push2.eastmoney.com` 持续 502，新浪 `hq.sinajs.cn` 返回 403，腾讯 `qt.gtimg.cn` 正常。
  - 腾讯适配器会用涨幅榜接口（`getBoardRankList`）自行获取约 4600 只 A 股代码，因此东财不可用时仍可独立冷启动，不再卡在「缺少代码全集」。
  - 东财长期不可用可在「数据源健康」停用它，但**不要停用腾讯**——它当前是云机房唯一可用的行情源。
  - 「测试连接」对批量源只取一只探针（`600000`），不会触发全市场抓取；东财只取 5 条。
- **一期不做**：机构持仓 <5%、解禁 / 减持 / 监管事件两条门槛（免费源不可得），界面永久提示人工核对；港股、形态深度分析、龙虎榜为二期。
- **题材池**：一期由种子数据维护，不支持页面编辑；`stock_themes`（个股-题材关联）默认无数据。
  - `with_theme=true` 时所有股票都会在题材阶段被淘汰，候选为 0。
  - 工作台已提供「仅看题材池」勾选框，**默认关闭**；补好 `stock_themes` 后再勾选即可按题材过滤。
  - 也可直接调 API `POST /api/v1/screening/runs`，传 `{"scope":"all","with_theme":false}`。
- **单进程调度**：APScheduler 运行在应用进程内。多 worker 部署时须只在一个进程启用调度，或迁移到外部任务队列。
- **同步实现偏差**：HLD 原计划 `async` 适配器 + `pytest-asyncio`；实际采用同步 httpx / sqlite + FastAPI 线程池（`def` 端点），避免 sqlite 同步调用与事件循环混用。契约与分层不变。

## 合规

- 界面与报告均标注「仅做历史规律复盘，不构成投资建议」。
- 筛选结论附带批次、数据来源与抓取时间；详情页展示数据日期。
- 凭据全部来自环境变量，不写入代码或仓库。

## 文档索引

| 文档 | 内容 |
| --- | --- |
| [PRD.md](PRD.md) | 产品需求：用户故事、验收标准（AC） |
| [HLD.md](HLD.md) | 概要设计：分层、模块职责、数据流 |
| [DESIGN_SPEC.md](DESIGN_SPEC.md) | 视觉规范：配色、排版、组件、暗色主题 |
| [TODO.md](TODO.md) | 二期待办与已知缺口 |
| [CLAUDE.md](CLAUDE.md) | 协作约定：代码风格、分层约束、提交要求 |
