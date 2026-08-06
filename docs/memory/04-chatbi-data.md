# ChatBI 与数据链路

## 1. 业务流

```text
数据源配置 -> 连接测试/Profiling -> Dataset/Table/Column/Metric/Relationship
          -> 授权 Schema + Few-shot -> Text-to-SQL / sql_plan
          -> SQL AST 与复杂度门禁 -> 表/列/行权限 -> 单源或联邦执行
          -> 结构化结果/结果栈 -> 图表/分析 -> 简报/报表/订阅
```

## 2. 核心端点

| 路径 | 方法 | 认证/权限 | 作用 |
|---|---|---|---|
| `/api/portal/metadata/datasets*` | CRUD | 菜单/元素/资源权限 | 数据集 |
| `/api/portal/metadata/db/*` | 混合 | 显式权限 | 数据源、DDL、Profiling |
| `/api/portal/metadata/*tables*` | 混合 | 显式权限 | 表/列资产 |
| `/api/portal/metadata/*metrics*` | 混合 | 显式权限 | 指标 |
| `/api/v1/schema` | POST | API key/API policy | 授权 Schema |
| `/api/v1/chatbi/sql/execute` | POST | API key/API policy | 只读 SQL 直连 |
| `/api/v1/chatbi/sql/checkauth` | POST | API key/public variant | OpenClaw 授权检查 |
| `/api/portal/data-portal/*` | GET/POST | 已认证 | 门户导航与推荐 |
| `/api/portal/chatbi-briefs/*` | 混合 | Owner | 业务简报 |

完整端点与参数见 `appendix/endpoint-inventory.md`。

## 3. 核心数据对象

| 对象 | 表 | 关键关系 |
|---|---|---|
| 数据集 | `meta_datasets` | 数据源、启用状态、数据权限开关 |
| 数据表 | `meta_tables` | `dataset_id` 指向数据集 |
| 字段 | `meta_columns` | `table_id` 指向数据表 |
| 指标 | `meta_metrics` | `dataset_id` 指向数据集 |
| 关系 | `meta_relationships` | 来源表/目标表 |
| 数据库连接 | `meta_db_connection_configs` | 外部业务库凭据 |
| Profiling | Profile Task/Table Profile | 数据质量与统计 |
| Few-shot | `ai_chatbi_examples` 和 Usage | 审核案例与使用统计 |
| 简报/报表 | `chatbi_briefs` 和 Saved Report 表族 | 查询结果交付 |

## 4. SQL 安全链

已有能力：

- `sqlglot` 解析单语句并阻止写 AST，见 `app/services/ai/tools/data_api.py:19-74`。
- 从 SQL 提取物理表并校验数据集范围和表权限。
- 对绑定 Schema 做列校验，对启用数据权限的数据集做行级条件重写。
- `sql_sandbox_gate.py:23-126` 检查笛卡尔积、复杂度和 EXPLAIN 扫描规模。
- 本地执行有超时、1000 行、2 MiB 结果上限；缓存含用户 scope。
- 联邦查询对总 LLM 调用数、repair 和中间数据做限制。

## 5. P0 数据越权

`/api/v1/chatbi/sql/execute` 对普通请求设置 `bypass_table_auth=True`：

- `chatbi.py:295-322`：只要 `sessionid` 不是 OpenClaw 格式就绕过。
- `sql_query_execution_service.py:434-464`：只有 `not bypass_table_auth` 才执行物理表范围与权限校验。

这使拥有该 API 资源权限的普通用户可查询未授权甚至未注册物理表，实际边界退化为外部数据库账号权限。

修复要求：

1. 删除任何客户端输入可触发的 bypass。
2. 所有入口统一调用表/列/行权限；内部管理员 bypass 使用不可由 HTTP 传入的 capability。
3. 对 `data_source` 本身做资源授权。
4. 回归测试断言任意 `sessionid` 不能改变授权结果。
5. 外部业务数据库账号必须只读、按 schema 最小权限，并设置原生 statement timeout/read-only transaction。

## 6. 其他问题

- `validate_sql` 仍允许 SHOW/DESC/EXPLAIN，可能绕过对象授权枚举数据库元信息。生产查询应只允许 `SELECT/WITH SELECT`。
- 数据连接池每数据源每实例可达约 50 条，副本和数据源增长后存在连接风暴。
- 查询、修复、合成和联邦路径复杂，缺少统一 query budget：扫描行、内存、并发、LLM 次数、结果大小应统一计费。
- MySQL/PostgreSQL 平台主库与 Oracle/ClickHouse/MySQL 等业务数据源是不同信任域，不能共用凭据或迁移策略。

## 7. 产品完善方向

- 建立认证语义层：指标 owner、公式、口径版本、适用范围、时效和认证状态。
- 增加字段/指标血缘、质量告警、口径冲突检测和变更影响分析。
- 建立 Text-to-SQL 离线评测集：执行正确率、语义正确率、权限拦截率、成本和延迟。
- 查询 UI 必须展示数据来源、时间范围、口径、权限裁剪和结果截断状态。
- 报表订阅使用冻结版本的 SQL/语义定义；升级需重新验证并支持回滚。
