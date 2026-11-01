# 开发任务看板

> 规则：一次只专注一个模块；完工后把 `[ ]` 改为 `[x]`。
> 上游：`PRD.md` / `DESIGN_SPEC.md` / `HLD.md`

## 0. 工程骨架
- [x] 目录结构、requirements、pytest 配置
- [x] 配置与日志（core/config、core/logging）
- [x] sqlite 连接、DDL、种子数据（core/db）
- [x] 密码哈希与会话签名（core/security）

## 1. 数据层
- [x] 领域模型（models/domain）
- [x] Repository：stocks / quotes / themes / screening / watch_pool / manual_metrics / data_sources / settings / jobs

## 2. 行情接入
- [x] SourceAdapter 协议 + Quote 契约
- [x] 东方财富适配器（主源，全市场快照）
- [x] 腾讯适配器（备用，需代码全集）
- [x] 新浪适配器（备用，无市值字段）
- [x] market_service：优先级降级、归一化、批量落库、空快照保险丝
- [x] source_health：健康检查与流水

## 3. 业务服务

- [x] gates：硬门槛规则注册表（纯函数，含边界）
- [x] 形态识别（首板 / 一字 / 换手，不可得标记 unavailable）
- [x] screening_service：批次编排、逐条落库、进度、with_theme 候选过滤
- [x] scoring_service：规则加减分 + 明细
- [x] watch_pool_service：状态机 + 强制留痕 + 软移出
- [x] export_service：CSV 导出（UTF-8 BOM）

## 4. API
- [x] deps：数据库依赖、登录校验
- [x] /auth 登录、登出、会话、改密
- [x] /screening 批次、结果、候选
- [x] /stocks 列表、详情、行情、门槛、评分
- [x] /watch-pool 增删改查、历史、统计
- [x] /manual-metrics 查询、写入、CSV 导入
- [x] /data-sources 列表、开关、测试
- [x] /settings 读写
- [x] /export、/system、/health
- [x] main.py 装配 + 生命周期 + 前端路由兜底

## 5. 定时任务
- [x] APScheduler：每日刷新、每周健康检查
- [x] 交易日判断（以返回 trade_date 为准）
- [x] job_runs 记录（含休市 skipped 落库）

## 6. 前端
- [x] Vite + React + TS + Bootstrap 骨架
- [x] 设计 Token 与 Bootstrap 覆盖
- [x] API client（含统一错误处理）
- [x] 基础组件：Button / DataTable / Badge / Card / Modal / Toast / Empty / Skeleton
- [x] 页面：登录
- [x] 页面：选股工作台
- [x] 页面：观察池
- [x] 页面：个股详情
- [x] 页面：数据源健康
- [x] 页面：系统设置
- [x] `npm run build` 通过（tsc + vite）

## 7. 测试

- [x] 单元：门槛边界、评分、归一化、适配器解析、安全、状态机
- [x] 集成：认证、筛选、观察池理由校验、数据源开关、设置、人工补录、导出
- [x] 覆盖率门禁 ≥80%

## 8. 交付
- [x] README.md
- [x] `.env.example` + `scripts/run.sh`
- [x] `.gitignore`

## 9. 交付验证（2026-10-31）

- `python -m pytest`：**159 passed，覆盖率 94.55%**（门禁 80%）
- `npm run build`：tsc + vite 构建成功，产物 `frontend/dist`
- 未执行的真实网络验证：东方财富 / 腾讯 / 新浪接口连通性（测试全部使用固定报文；部署后需在「数据源」页实测）

## 10. 已知偏差 / 后续

- HLD 计划异步适配器，实际为同步 httpx + sqlite + `def` 端点（避免同步库与事件循环混用），契约与分层不变。
- 机构持仓、解禁/减持/监管事件两条门槛降级二期，一期界面永久提示人工核对。
- 题材池一期由种子数据维护，无页面编辑接口。
- 单进程内 APScheduler；多 worker 部署需拆分调度进程。
