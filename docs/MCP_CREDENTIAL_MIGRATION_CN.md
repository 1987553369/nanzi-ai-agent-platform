# MCP 历史凭据加密迁移手册

本手册用于把 `sys_mcp_servers.auth_headers` 中的历史明文 JSON 转换为
`mcpheaders:v1:` 版本化密文。新写入凭据已由应用自动加密，运行时不再接受明文回退。

## 一、影响与安全边界

- MySQL 使用 `V117-quarantine_legacy_mcp_credentials.sql`；
- PostgreSQL 使用 `V16-quarantine_legacy_mcp_credentials.sql`；
- 结构迁移会识别旧明文、保存原启用状态并立即禁用对应 MCP 服务；
- SQL 不读取应用密钥，也不会尝试在数据库内加密；
- `scripts/migrate_mcp_credentials.py` 使用当前进程的 `ENCRYPTION_KEY` 加密；
- 有效旧 JSON 加密成功后恢复原启用状态；
- 无法解析的旧 JSON 会被清空，状态改为 `rotation_required`，必须由管理员重新录入；
- 当前环境无法加密时保持 `migration_pending` 和禁用状态，不删除可恢复的旧值；
- 版本化密文无法解密时也保持 `migration_pending`，保留原密文并提示检查
  `ENCRYPTION_KEY`；不能仅凭一次解密失败认定用户凭据已损坏；
- 列表、轮换队列、日志和命令输出都不会返回 Header 值。

## 二、执行前准备

1. 安排维护窗口，停止 API、Worker、Scheduler 等所有会使用 MCP 的进程；
2. 备份主数据库并验证备份可以恢复；
3. 确认部署环境使用正确且稳定的 `ENCRYPTION_KEY`，迁移期间不得轮换；
4. 确认选择的是平台实际主库，MySQL 与 PostgreSQL 迁移不可混用；
5. 保存当前 MCP 服务启用状态和业务验证清单，但不得导出明文 Header 到工单或日志。

## 三、执行结构迁移

在维护窗口内，通过项目统一迁移入口执行全部待执行版本。不要直接运行单个 SQL 客户端。

MySQL：

```bash
./db-prod/apply-sql.sh
```

PostgreSQL：

```bash
./db-prod-pg/apply-sql.sh
```

结构迁移完成后，旧明文行应处于 `migration_pending` 且 `enabled_status=0`。

## 四、先预检再执行

在与平台相同的 Python 3.11 环境和环境变量下，先运行默认 dry-run：

```bash
python3.11 scripts/migrate_mcp_credentials.py --dry-run
```

确认目标数据库、`ENCRYPTION_KEY` 和扫描数量正确后执行：

```bash
python3.11 scripts/migrate_mcp_credentials.py --apply
```

也可以只处置指定服务；参数可重复：

```bash
python3.11 scripts/migrate_mcp_credentials.py \
  --apply \
  --server-id <server-id-1> \
  --server-id <server-id-2>
```

命令返回码：

- `0`：没有待迁移或待人工轮换项；
- `2`：仍存在 `migration_pending` 或 `rotation_required`，服务保持禁用。

## 五、处理人工轮换队列

管理员可以调用以下接口查看队列，响应只包含服务 ID、名称、作用域、状态和脱敏错误原因：

```text
GET /api/portal/mcp/credential-rotation
```

处理规则：

- `migration_pending`：检查应用环境和 `ENCRYPTION_KEY`，修复后重跑迁移命令；
- `rotation_required`：进入 MCP 管理界面，编辑对应服务并重新填写认证 Header；
- 对已有 `mcpheaders:v1:` 密文，先核对环境使用的密钥版本；只有确认密钥正确且密文
  仍无法恢复时，才由管理员重新录入；
- 禁止通过 SQL 把状态直接改成 `encrypted`；
- 禁止把旧 Header 粘贴到日志、聊天、工单或代码仓库；
- 新凭据保存成功后，应用会清除错误状态、销毁旧内存会话并按管理员选择启用。

## 六、验收与恢复

迁移完成后验证：

1. 轮换队列为空；
2. 所有非空 `auth_headers` 都以 `mcpheaders:v1:` 开头；
3. `migration_pending`、`rotation_required` 数量均为零；
4. 原本启用的 MCP 服务能够同步工具并完成最小只读调用；
5. 原本禁用的服务仍保持禁用；
6. API 响应、应用日志和审计日志中不存在 Header 值。

若批量迁移前需要回滚，应保持业务进程停止并恢复整库备份。不要只回滚状态列或只恢复
`auth_headers`，否则密文、状态和启用状态可能不一致。迁移完成并重新启动后，不得回滚到
仍支持明文 Header 的旧应用版本。
