# PostgreSQL 数据库初始化与版本升级

`db-prod-pg` 是平台主库 PostgreSQL 的独立迁移链，与 `db-prod` 的 MySQL 迁移链并行维护。
同一平台运行环境只能选择一套主库迁移。

## 一、运行机制

- 文件名必须符合 `V<版本>-<描述>.sql`，重复版本直接拒绝；
- `nanzi_schema_migrations` 记录版本、描述、SHA-256 Checksum、状态和执行耗时；
- 已成功执行或建立基线的版本在 Checksum 一致时跳过；
- 已执行文件被修改、历史文件缺失、账本出现 `failed` / `in_progress` 时拒绝继续；
- 整个批次持有 PostgreSQL advisory lock，避免多个实例同时升级同一数据库；
- 单个版本的 SQL 与 `success` 账本更新位于同一事务；失败 SQL 会回滚该版本，并单独记录
  `failed` 状态；
- 迁移不依赖“每次重放全部 SQL”的幂等假设，任何错误都真实失败。

## 二、新环境初始化

准备 Python 3.11 环境并安装项目依赖：

```bash
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
./db-prod-pg/apply-sql.sh
```

无文件参数时，脚本会自然排序并一次性提交全部 `V*.sql`，数据库锁覆盖完整批次。目标库
不存在时自动创建，但禁止把 `postgres`、`template0`、`template1` 作为应用库。
Host 和 Port 留空分别使用 `localhost`、`5432`。

脚本交互读取密码，并通过 `NANZI_MIGRATION_PASSWORD` 环境变量传给 Python 子进程，
避免密码出现在进程参数中。全量初始化完成后，如果包含 V0，脚本会询问是否创建随机
管理员凭据。

## 三、已有环境首次启用迁移账本

检测到已有业务表但账本为空时，执行器会拒绝从 V0 重放。必须先备份并验证恢复能力，
再由 DBA 核对最后一个真实完成的版本：

```bash
./db-prod-pg/apply-sql.sh --baseline-through <当前版本>
```

截止版本必须精确存在于本次全量迁移清单中，拼错或不存在的版本会被拒绝。

例如已确认数据库完成 V12，命令会把 V0 至 V12 登记为 `baseline`，并执行 V13 及以后版本：

```bash
./db-prod-pg/apply-sql.sh --baseline-through 12
```

空库禁止建立假基线。`--baseline-existing` 会把本次选中的所有文件仅登记、不执行，
只适用于已经逐文件核对的特殊恢复场景。

## 四、日常升级

推荐运行全量入口，让账本决定跳过和执行：

```bash
./db-prod-pg/apply-sql.sh
```

也可以显式选择一个或多个文件；执行器会按自然版本排序，并保持单一全局锁：

```bash
./db-prod-pg/apply-sql.sh \
  db-prod-pg/V14-add_ai_execution_capabilities.sql \
  db-prod-pg/V15-add_ai_execution_capabilities_compat.sql
```

支持从项目根目录、当前调用目录或 `db-prod-pg` 目录解析相对路径。兼容通过
`sh apply-sql.sh` 启动，脚本会自动重新进入 Bash。

可用运维参数：

```text
--baseline-through VERSION  登记至指定版本，执行更高版本
--baseline-existing         仅登记本次选中的全部文件
--lock-timeout SECONDS      获取迁移锁的等待秒数，默认 30
```

## 五、失败恢复

- 某版本失败时，该版本 SQL 事务会回滚，后续版本不会执行；
- 账本会记录 `failed`，下次运行不会自动重试；
- DBA 必须核对错误、Schema 和事务状态，完成修复或新增补偿迁移后再人工处置账本；
- 不得直接修改已经登记的 SQL 文件，否则 Checksum 校验会失败；
- 不得删除已登记的历史迁移；
- 获取锁超时时，应检查现有迁移进程，不能绕过 advisory lock 并发执行。

即便 PostgreSQL 单版本具备事务性，也应在生产执行前备份并验证恢复流程。

## 六、迁移文件维护规则

- `V0-baseline.sql` 是 PostgreSQL 新环境基线，不是 MySQL 文件的逐条翻译；
- 变更必须新增当前最高版本之后的迁移，不要插入或复用已发布版本号；
- PostgreSQL 使用 `TRUE` / `FALSE`、`JSONB`、`BYTEA` 等原生类型和语法；
- 需要兼容重复对象时，应在 SQL 本身表达明确的前置条件，而不是由执行器吞掉错误；
- 配置数据更新必须明确是否允许覆盖管理员在部署后的修改；
- PostgreSQL 专用 SQL 不得回写 MySQL 迁移目录。

## 七、直接调用 Python 执行器

自动化环境可直接调用核心执行器。密码优先通过安全的环境变量或 Secret 注入，不要写入
Shell 历史：

```bash
NANZI_MIGRATION_PASSWORD='<password>' \
python3 db-prod-pg/apply_sql.py \
  --host localhost \
  --port 5432 \
  --user postgres \
  --database nanzi_demo \
  --yes \
  db-prod-pg/V15-add_ai_execution_capabilities_compat.sql
```

## 八、管理员与运行时配置

### MCP 历史明文凭据迁移

V16 会先隔离并禁用旧明文 MCP 服务，随后必须在维护窗口使用当前
`ENCRYPTION_KEY` 运行应用层迁移命令。完整步骤、返回码和人工轮换队列处理方式见
[MCP 历史凭据加密迁移手册](../docs/MCP_CREDENTIAL_MIGRATION_CN.md)。

### 管理员凭据

```bash
./db-prod-pg/create-admin-user.sh
./db-prod-pg/create-admin-key.sh admin
./db-prod-pg/reset-admin-password.sh admin
```

选择 PostgreSQL 作为平台主库时：

```dotenv
DATABASE_TYPE=postgresql
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=nanzi_ai_agent_platform
POSTGRES_USER=postgres
POSTGRES_PASSWORD=<password>
```

随机 API Key 明文只显示一次，应立即保存到密钥管理系统。
