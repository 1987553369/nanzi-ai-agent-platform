# ChatBI 与数据平台评审

## 业务链路

```text
数据库连接 -> 连通测试 -> Profiling/DDL 导入 -> 数据集/表/字段元数据
 -> 术语/指标/关系/案例 -> 资源授权
 -> 自然语言问题 -> Schema 门禁与语义识别 -> SQL 计划/查询
 -> SQL 沙箱与数据适配器 -> 必要时修复 -> 结果与引用
 -> 业务简报或保存报表 -> 订阅与通知
```

## 主要接口

| 前缀 | 作用 | 前端 |
|---|---|---|
| `/api/portal/metadata/db/*` | 数据源配置、测试、Profiling 和导入 | `frontend/src/api/metadata.ts` |
| `/api/portal/metadata/datasets*` | 数据集、权限、表、指标、关系、RAG 同步 | `metadata.ts` |
| `/api/portal/examples*` | ChatBI 案例审核、增强和同步 | 元数据/管理页面 |
| `/api/v1/schema*` | 授权 Schema 和查询辅助 | Chat 运行时 |
| `/api/portal/data-portal/home` | 用户数据门户首页 | Data Portal composables |
| `/api/portal/chatbi-briefs`、`/chatbi-monitors` | 分析交付和监控 | 聊天结果操作 |
| `/api/portal/saved-reports*` | 报表、执行、共享和订阅 | 数据门户/报表页面 |

## 数据模型

| 表 | 作用 |
|---|---|
| `meta_db_connection_configs` | 加密物理数据源连接和适配器类型 |
| `db_profile_tasks`、`db_table_profiles` | 数据库摸排进度和增强后的物理元数据 |
| `meta_datasets` | 业务数据产品和访问上下文 |
| `meta_tables`、`meta_columns` | 物理 Schema 到业务语义的映射 |
| `meta_metrics`、`meta_relationships` | 指标和表关联关系 |
| `meta_changelog` | 语义资产变更历史 |
| `ai_chatbi_examples`、`ai_chatbi_example_usages` | 审核 SQL 案例及其召回使用记录 |
| `chatbi_briefs` | 带证据的业务分析简报 |
| `portal_saved_reports*` | 报表、执行、共享、偏好和订阅生命周期 |

## P0 数据越权

普通 ChatBI HTTP 入口在 `app/api/v1/endpoints/chatbi.py:295-322` 设置 `bypass_table_auth=True`，而 `sql_query_execution_service.py:434-464` 只有在 bypass 为 false 时才执行物理表权限检查。

必须立即删除这条绕过路径。客户端字段、Session ID、Agent 类型或入口不同，都不能降低数据源、表、列和行级权限。

## 其他风险

- 数据库凭据和模型生成 SQL 属于高影响信任边界，连接测试、Profiling 和查询必须使用同一安全策略。
- 权限应在构造 Prompt/Schema 前执行，并在真正查询前再次执行；前端菜单不可作为数据边界。
- 需要明确限制 DDL/DML、多语句、注释、危险函数、查询成本、行数、字节数和自动修复次数。
- 指标缺少完整 Owner、版本、粒度、血缘、时效和认证状态，暂不适合宣称完整企业语义层。
- 每个进程和数据源单独建立连接池，副本增加后可能耗尽业务数据库连接。
- AI 生成的结论必须保留 SQL、参数、数据快照、语义版本和数据时间，才能真正复现。

## 改造建议

1. 建立认证指标体系：Owner、定义、粒度、维度、血缘、质量、时效 SLA 和审批版本。
2. 数据源使用只读最小权限账号，并配置并发、超时、行数、字节数和查询成本预算。
3. 持久化查询证据包：问题、授权 Schema 版本、计划、SQL、参数、来源、时间、行数、转换和引用。
4. 建立黄金问题集，评测 SQL 正确性、执行成功率、口径一致性和回答忠实度。
5. Profiling/导入迁移到持久化 Worker，支持 Checkpoint、取消和可观测。
6. 为 MySQL、PostgreSQL、Oracle、ClickHouse、SQL Server 建立真实集成测试和能力矩阵。
7. 敏感字段增加脱敏、聚合策略和字段访问审计。

## 验收标准

- 未授权的数据源、表、列和行不会出现在 Prompt、日志、SQL 或结果中。
- 所有查询在生产数据库账号下只读、可限额、可取消。
- 认证指标在版本化测试集上通过 MySQL/PostgreSQL 双引擎验证。
- 保存报表可以通过不可变证据重现，或明确提示数据源发生漂移。
- 单个慢数据源不会耗尽全部连接和 Worker。

源码向详细分析见 [04-chatbi-data.md](04-chatbi-data.md)。
