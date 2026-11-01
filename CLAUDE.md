# 妖股选股系统

A 股短线「妖股」筛选与跟踪工具：抓取公开行情接口 → 按量化条件选股 → 建立观察池 → 持续跟踪淘汰 → 个股评分与深度分析（一期只做 A 股）。

## 需求源
- `妖股选择框架_跨年总龙.txt`：硬性门槛（一票否决）、加分项、2026 跨年题材池、四步筛选流程、观察池字段、减分项。这是需求的唯一原始依据，改需求先改它。

## 当前阶段

- 一期已实现并通过测试：后端（15 张表、约 30 个端点）、前端 6 个页面、定时任务、CSV 导出。
- 测试基线：`pytest` 159 passed，覆盖率 94.55%；`npm run build` 通过。
- 真实行情接口尚未在部署环境联调；腾讯云出口 IP 可能被部分免费源屏蔽。
- 项目未初始化 git 仓库：没有 `git diff` 兜底，覆盖文件前先确认原内容。

## 技术栈
- 后端：FastAPI（Python）；数据库 sqlite3（标准库，不引 ORM / 迁移框架）
- 前端：React 18 + Bootstrap 5（暗色优先），图表 ECharts
- 数据源：通达信、同花顺、东方财富、腾讯、新浪（HTTP/API，免费与收费混合）
- 产品参照：东方财富、雪球

## 项目结构
```
.claude/prompts/       # 4 个专业 Agent + 协调者提示词（唯一事实源）
妖股选择框架_跨年总龙.txt
PRD.md                 # 产品需求 v1.0（功能清单 / 页面 / 用户故事 / 验收标准）
DESIGN_SPEC.md         # UI/UX 设计规范 v1.0（暗色「暗夜作战台」、Token、组件库、6 页设计）
HLD.md                 # 系统概要设计 v1.0（15 张表 DDL、API 契约、分层与异常处理）
README.md              # 交付说明书（架构、API、页面、运行与运维）
TODO.md                # 任务看板与交付验证记录
src/                   # api / services / repositories / models / schemas / integrations / tasks
frontend/              # React 18 + TS + Vite 前端（src/pages 六个页面）
tests/                 # pytest 测试（9 个文件 + conftest 夹具）
scripts/run.sh         # 启动脚本
.env.example           # 环境变量示例
```

## 工作流
- 触发：`/产品` `/设计` `/开发` `/测试`
- 调度路径与阶段产出以 `.claude/prompts/coordinator.md` 为唯一事实源
- 后置角色必须先读前置文档：设计读 `PRD.md`；开发读 `PRD.md` + `DESIGN_SPEC.md`；测试读前两者 + 实现代码
- 阶段产出：`PRD.md` → `DESIGN_SPEC.md` → 可运行项目 → `tests/` + 测试报告
- Agent 文档与对话统一中文

## 关键约定
- **API**：RESTful + JSON，路径 `/api/v1/`，端点附示例
- **分层**：Routers / Services / Repositories，依赖注入用 FastAPI `Depends`；选股门槛等领域规则放 Services，不写进 Router
- **测试**：关键路径全覆盖，覆盖率 ≥80%（门禁在 `pytest.ini` 落地后生效）；TDD 优先
- **凭据**：不硬编码，走环境变量
- **合规**：本工具仅做历史规律复盘，界面与报告不得表述为投资建议；每条选股结论须带数据来源与抓取时间戳
- **变更联动**：改任一 Agent 提示词后，同步检查 `coordinator.md` 调度路径

## 领域易错点
- 免费行情接口不稳定、限流、字段口径不一：总市值单位是「亿」还是「元」、复权方式、停牌与 ST 标记——抓取后必须统一归一化并记录时间戳
- 硬门槛阈值（总市值 20–45 亿、收盘价 3–10 元）的边界含 / 不含，以 `PRD.md` §3.2 为准再实现
- 机构持仓 <5%、解禁/减持/监管事件已降级为二期（免费源不可得），一期**不参与淘汰**；不要按框架原文把它们当作生效门槛
- 行情数据不要写死在代码或测试里；测试用固定快照 fixture

## 开发命令

```bash
# 后端（Windows 路径；Linux/macOS 用 venv/bin/python）
venv/Scripts/python.exe -m uvicorn src.main:app --reload --env-file .env
venv/Scripts/python.exe -m pytest            # 覆盖率门禁 80% 在 pytest.ini

# 前端
cd frontend
npm install
npm run dev                                  # http://127.0.0.1:5173，/api 代理到 8000
npm run build                                # 产物 dist，后端启动时自动托管

# 生产启动
bash scripts/run.sh
```

首次启动自动建库并写入题材 / 数据源 / 默认阈值种子。

## 已知坑点

- 产品计划部署在腾讯云服务器，已知部分免费股票接口屏蔽腾讯云服务器 IP，需要避开；部署后先在「数据源」页实测。
- sqlite 写操作经 `core/db.py` 的全局锁串行化，新增写路径必须用 `db.transaction(conn)`，否则可能 `database is locked`。
- `skipped`（门槛未启用）不否决候选；`unavailable`（数据缺失）既不通过也不淘汰，界面必须显示「待确认」。
- `with_theme=true` 的批次，候选会排除未命中题材池的标的；候选数与 `screening_results` 同源计算。
