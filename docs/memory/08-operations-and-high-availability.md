# 运维与高可用评审

## 当前部署拓扑

```text
浏览器/API Client -> :8001 单个 ai-agent 容器
                       ├─ Vue 静态资源 + FastAPI/Uvicorn
                       ├─ 进程内 Audit Queue
                       ├─ APScheduler + 报表/维护任务
                       └─ 启动阶段向量/索引维护
                       -> 单一数据库地址
                       -> 单 Redis Stack
                       -> 本地 ./data 和 Skill Volume
                       -> LLM/RAGFlow/MCP/业务数据库
```

模块化单体作为代码组织没有根本问题，但当前运行进程同时承担控制面、执行面和后台任务，不能安全地直接横向扩容。

## 已有基础

- SQLAlchemy 使用连接预检查、回收和统一关闭。
- PostgreSQL 迁移工具按文件事务执行。
- MySQL/PostgreSQL 最终静态 Schema 均约 47 张表，功能大体对齐。
- Redis Session Lock 使用 Lua 校验 Owner Token 后释放。
- Audit 日志具备敏感字段脱敏、截断和批量写入。

## 高可用阻断问题

| 等级 | 问题 | 后果 |
|---|---|---|
| P0 | 每个 API 副本都会启动 APScheduler | 多副本重复执行定时和维护任务 |
| P0 | 任务锁 300 秒无续租，部分锁错误 Fail-open | 长任务重复和业务副作用 |
| P0 | 关闭前没有 Drain 状态，探针无法区分 DB/Redis 故障 | 故障实例继续接收流量 |
| P0 | DB、Redis、文件和密钥没有经过恢复演练 | 无法承诺 RTO/RPO |
| P0 | 单 Redis 同时承载状态、锁、审批、向量和缓存 | 单点故障影响整个运行面 |
| P0 | 本地文件和 Skill 目录不是共享存储 | 多副本看到不同产物 |
| P1 | Audit Queue 无界，写库失败整批丢弃 | 内存风险和审计缺口 |
| P1 | 代码执行 Registry/Cancel 在内存 | 无法跨副本停止和恢复 |

## 部署与配置问题

- Compose 给应用配置 Redis 密码，但 Redis 服务没有匹配的 `requirepass`，也没有 Volume 和 Healthcheck。
- 根 `env.example` 设置 `REDIS_DB=2`，而 RediSearch 要求 DB 0。
- Compose 使用 `API_SERVICE_LOG_LEVEL`，应用读取 `LOG_LEVEL`，主程序又硬编码 INFO。
- 基础镜像和 Redis 使用可变 Tag，Docker 构建允许从 `npm ci` 回退到 `npm install`。
- 运行镜像默认 root，并包含 Git、Node、浏览器和大量系统工具。
- 没有 CI Workflow、Helm/Kubernetes、Prometheus、OpenTelemetry、SBOM、镜像签名和漏洞门禁。
- 启动脚本先删除旧容器再启动新容器，存在明确停机窗口。

## 数据库迁移问题

| 问题 | 整改 |
|---|---|
| MySQL Importer 使用 Autocommit，Native 脚本逐语句新连接 | 使用正式事务迁移工具，对非事务 DDL 单独评审 |
| 无迁移 Ledger、Checksum 和全局锁 | 建立不可变迁移历史并串行执行 |
| MySQL 存在重复 `V31` 和 `V110` | 建立规范版本顺序，不能静默修改已执行脚本 |
| Request 依赖和 Service 都可能 Commit | 每个请求/任务只保留一个明确 Unit of Work |
| 双数据库主要靠文本测试验证 | MySQL 8 和 PostgreSQL 14/16 真实 Fresh/Upgrade CI |
| PostgreSQL Audit 无分区 | 使用原生时间分区或独立日志存储 |

## 目标高可用拓扑

```text
Ingress / Load Balancer
  ├─ API Pod x2+，跨故障域，只处理 HTTP/SSE
  ├─ Scheduler Candidate x2，通过 Lease 选主，只创建 Execution
  ├─ 交互推理 Worker
  ├─ 定时任务/报表 Worker
  ├─ 隔离 Browser/Code/Tool Worker
  └─ Profiling/Index Worker
        -> 多可用区 MySQL/PostgreSQL + 连接代理
        -> Redis State HA：AOF everysec、noeviction
        -> Redis Vector/Search HA 或可重建层
        -> S3/OSS 兼容版本化对象存储
        -> OTel Collector、Metrics、Logs、Alerting
```

## 探针与生命周期

| 探针 | 语义 |
|---|---|
| `/live` | 进程和 Event Loop 存活，不访问依赖 |
| `/startup` | 初始化、Schema 和必要配置检查完成 |
| `/ready` | 当前实例可以安全接收对应流量，检查受限 DB/Redis 和 Draining 状态 |

当前实现已提供 `/live`、`/startup`、`/ready`。`/ready` 使用 `SELECT 1` 和 Redis `PING`
进行依赖检查，关闭流程先标记 `runtime_health.draining` 再释放 Scheduler、连接池和 Redis；
仍需在部署环境配置探针轮询、优雅终止宽限时间和故障演练。

关闭时先标记 Unready，再停止接收新流，限定时间排空，将持久化任务 Checkpoint 或重新入队，最后关闭连接。

## 可观测与目标

日志和 Trace 至少包含 `trace_id`、`run_id`、租户/用户、Agent 版本、模型/工具/数据源、状态和脱敏错误。需要监控 HTTP/SSE 延迟、活跃流、队列年龄、任务重试、模型/工具耗时、Token/成本、DB Pool、Redis 内存和 Scheduler Lag。

| 组件 | 初始目标 |
|---|---|
| 单区域平台 | 99.9%，稳定后提升到 99.95% |
| 主数据库 | RPO <= 1 分钟，RTO <= 15 分钟 |
| Redis 状态层 | RPO <= 1 秒，RTO <= 5 分钟 |
| 文件/Skills/Artifact | RPO <= 15 分钟，RTO <= 30 分钟 |
| 区域级灾难 | RPO <= 15 分钟，RTO <= 4 小时 |

## 上线门槛

- MySQL 8、PostgreSQL 14/16 通过全新安装、N-1 升级、重跑和支持的回滚测试。
- 两个 API/Scheduler 副本对同一计划时间只执行一次。
- API、Redis 主节点和 DB 主节点故障都能在目标时间自动恢复。
- 备份可在隔离环境恢复数据库、对象、状态和所需密钥版本。
- 压测中 DB 连接、Redis 内存、队列、SSE 和 Worker 利用率低于规划预算的 70%。
- 使用 Digest 固定的非 root 最小镜像，具备 Lock、SBOM、扫描和签名。
