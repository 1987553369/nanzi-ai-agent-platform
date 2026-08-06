# MySQL 数据库初始化与版本升级

`db-prod` 是平台主库 MySQL 的版本迁移目录。生产迁移统一通过
`apply-sql.sh` 执行，由 `apply_sql.py` 在一个数据库全局锁内完成迁移计划、执行和账本更新。

## 一、运行机制

- 迁移文件名必须符合 `V<版本>-<描述>.sql`，版本支持整数和一段小版本号，例如
  `V31-...sql`、`V31.1-...sql`；
- 同一版本只能有一个文件，重复版本会在连接数据库前被拒绝；
- 执行记录保存在目标库的 `nanzi_schema_migrations` 表；
- 已成功执行或建立基线的文件会校验 SHA-256 Checksum，相同则跳过；
- 已登记文件被修改、账本中的历史文件从代码库消失时，迁移立即失败；
- 整个批次使用 MySQL `GET_LOCK` 串行化，同一数据库不能并发迁移；
- MySQL DDL 可能隐式提交，因此执行前先持久化 `in_progress`，成功后改为 `success`；
- 任何 SQL 错误都会失败，不再吞掉 `1050`、`1060`、`1061` 等 DDL 错误冒充幂等。

`apply-sql-native.sh` 仅保留为兼容入口。原生多进程导入无法可靠持有同一数据库锁，
因此该脚本现在会委托给安全的 Python 执行器，不再提供“免 Python 依赖”模式。

## 二、新环境初始化

准备 Python 3.11 环境并安装项目锁定依赖：

```bash
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
./db-prod/apply-sql.sh
```

无 SQL 文件参数时，入口会发现并自然排序当前目录全部 `V*.sql`，一次性传给执行器。
目标数据库不存在时会自动以 `utf8mb4` 创建。Host 和 Port 留空分别使用
`localhost`、`3306`；User 和 Target database 必须显式输入。

密码通过 `NANZI_MIGRATION_PASSWORD` 传给 Python 子进程，不出现在进程命令行中。
完成结构初始化后，可按提示创建随机管理员凭据，也可稍后运行：

```bash
./db-prod/create-admin-user.sh
./db-prod/create-admin-key.sh admin
```

## 三、已有环境首次启用迁移账本

旧环境已经存在业务表、但没有 `nanzi_schema_migrations` 时，执行器会拒绝从 V0 自动重放。
必须由 DBA 完成以下步骤：

1. 备份目标数据库并验证备份可恢复；
2. 核对该环境实际已完成的最后迁移版本，不要仅依据应用版本号猜测；
3. 使用全量入口，将已完成版本登记为 `baseline`，并继续执行更高版本：

```bash
./db-prod/apply-sql.sh --baseline-through <当前版本>
```

截止版本必须精确存在于本次全量迁移清单中，拼错或不存在的版本会被拒绝。

例如数据库已确认完成 V110，代码中还有 V111 及后续版本：

```bash
./db-prod/apply-sql.sh --baseline-through 110
```

空库禁止建立假基线。`--baseline-existing` 会把本次选中的全部迁移仅登记、不执行，
只用于已逐文件核对的特殊恢复场景；常规旧库接入应使用 `--baseline-through`。

历史版本映射需要特别核对：

- 旧仓库的 `V31-add_user_real_name.sql` 已调整为 `V32-add_user_real_name.sql`。如果旧库已经有
  `ai_agent_users.real_name`，建立基线时应把它视为至少已完成 V32；
- 旧仓库的 `V110-create-skill-publications.sql` 已调整为
  `V111.1-create-skill-publications.sql`。如果旧库已经有技能发布相关表，应把它视为至少已完成
  V111.1。

这两个判断都必须以实际 Schema 为准，不能只看旧文件名中的重复版本号。

## 四、后续升级与重跑

推荐始终运行全量入口：

```bash
./db-prod/apply-sql.sh
```

执行器会跳过账本中 Checksum 一致的成功版本，只执行缺失的新版本。也可以显式传入一个
或多个版本文件，执行器仍会按自然版本排序并在同一个数据库锁内处理：

```bash
./db-prod/apply-sql.sh \
  db-prod/V115-add_ai_execution_capabilities.sql \
  db-prod/V116-add_ai_execution_capabilities_compat.sql
```

可用运维参数：

```text
--baseline-through VERSION  登记至指定版本，执行更高版本
--baseline-existing         仅登记本次选中的全部文件
--lock-timeout SECONDS      获取迁移锁的等待秒数，默认 30
```

## 五、失败处理与历史文件规则

- `success` / `baseline`：Checksum 一致时安全跳过；
- `in_progress` / `failed`：禁止自动重试。MySQL DDL 可能已经部分生效，必须由 DBA 对照
  迁移 SQL、账本错误信息和实际 Schema 人工核对，再决定补偿或修复账本；
- Checksum 不一致：禁止覆盖历史文件。恢复原文件，并新增更高版本的修复迁移；
- 账本有记录但代码缺少文件：恢复历史文件，禁止删除已发布迁移；
- 锁获取失败：确认其他迁移进程状态，不能绕过全局锁并发执行。

生产环境执行前必须备份，且不得直接运行单个 SQL 客户端绕过迁移账本。

## 六、常见问题

### 缺少 `aiomysql`

请在项目要求的 Python 3.11 虚拟环境安装依赖后重试。`apply-sql-native.sh` 同样会委托
Python 安全执行器，不能绕过该依赖。

### SQL 返回“对象已存在”

这现在属于真实失败，不会被自动忽略。若账本为空但 Schema 已存在，应按“已有环境首次
启用迁移账本”处理；若账本已有该版本，则先排查账本状态或历史文件是否被改变。

### 如何维护管理员

```bash
./db-prod/create-admin-user.sh
./db-prod/create-admin-key.sh admin
./db-prod/reset-admin-password.sh admin
```

随机 API Key 明文只显示一次，应立即保存到密钥管理系统。
