# 项目记忆库使用说明

本目录记录 NanZi 的产品边界、业务链路、接口、数据、外部集成、安全和运维约束。它服务于项目快速上手、设计评审、故障定位和后续集成，不能代替 OpenAPI、迁移 SQL 或自动化测试。

## 文档地图

| 文件 | 用途 |
|---|---|
| [`PROJECT_MEMORY.md`](../../PROJECT_MEMORY.md) | 总入口和快速定位 |
| `01-product-and-user-journeys.md` | 产品定位、用户旅程、信息架构和能力缺口 |
| `02-auth-rbac-security.md` | 鉴权、RBAC、租户边界、安全风险和验收门槛 |
| `03-core-chat-orchestration.md` | Agent 生命周期、路由、执行器、SSE 和目标运行契约 |
| `04-chatbi-data-platform.md` | 数据源、语义层、SQL 权限、证据和数据产品规划 |
| `05-knowledge-memory-skills-mcp.md` | RAGFlow、记忆、Skills、MCP 和内容安全 |
| `06-tasks-reports-notifications.md` | 调度、任务、报表、通知和幂等执行模型 |
| `07-frontend-experience.md` | 导航、状态、API/SSE、Embed、性能和无障碍 |
| `08-operations-and-high-availability.md` | 部署、迁移、探针、可观测、备份、HA 与灾备 |
| `09-roadmap-and-governance.md` | 分阶段整改、产品规划、Owner、指标和上线定义 |
| `01-product-architecture.md` 至 `06-tools-integrations.md` | 中文源码向专题，保留更细的实现路径和安全证据 |
| `appendix/endpoint-inventory.md` | 377 个装饰器端点静态清单 |
| `appendix/api-schema-inventory.md` | 229 个 API/Pydantic 模型字段清单 |
| `appendix/database-model-inventory.md` | 41 张 ORM 映射表字段清单 |
| `appendix/config-key-inventory.md` | 环境与数据库配置键清单 |
| `appendix/config-reference.md` | 高影响配置的生产约束与已知漂移 |
| `appendix/external-apis.md` | 外部服务、协议、认证和调用位置 |
| `appendix/risk-register.md` | P0/P1/P2 风险、处置动作和关闭证据 |

## 可信度边界

- 端点、模型、配置和 ORM 清单来自源码静态扫描；动态注册和运行时 OpenAPI 仍需集成测试验证。
- ORM 不是物理 DDL 的完整替代。MySQL 以 `db-prod/`、PostgreSQL 以 `db-prod-pg/` 为权威来源。
- 本次没有启动 `./dev.sh`、容器或外部基础设施，也没有修改业务代码。
- Python 语法编译已通过。完整后端测试未执行：本机 Python 3.9，项目要求 3.11，且缺少 `aiomysql` 等依赖。
- 前端契约测试为 290 通过、16 失败；其中 13 项来自缺失的本地 TypeScript/esbuild 依赖，3 项是源码与契约漂移。未安装依赖，因此未执行完整 `vue-tsc` 或生产构建。

## 维护方式

1. 代码合并前，由模块 owner 更新对应文档。
2. CI 生成四份清单，并检查工作树是否出现差异。
3. 每个发布版本做一次“端点-模型-迁移-前端 client”交叉核对。
4. 每季度重新做安全威胁建模、恢复演练和 SLO 复盘。

这套记忆库是项目的永久上下文。每次代码变更后：新端点补模块文档，新字段补 Schema 清单，新 DB 列补数据库文档，新外部 API 和配置分别补附录，并保持根目录 `PROJECT_MEMORY.md` 为唯一入口。
