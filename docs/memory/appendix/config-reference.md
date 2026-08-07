# 配置项说明

环境变量和数据库配置键的完整列表见 [config-key-inventory.md](config-key-inventory.md)。本文件解释高影响配置的生产语义和约束。

| 领域 | 配置键 | 生产要求 |
|---|---|---|
| 运行环境 | `API_SERVICE_ENV`、`APP_PUBLIC_URL`、`LOG_LEVEL` | 使用明确生产 Profile，未知值或必填项缺失时拒绝启动 |
| 浏览器安全 | `ALLOWED_ORIGINS` | 只能配置精确 HTTPS Origin，携带凭据时禁止 `*` |
| 主数据库 | `DATABASE_TYPE`、`MYSQL_*`、`POSTGRES_*` | Secret Manager、TLS，并根据副本数计算连接池预算 |
| Redis | `REDIS_*` | Redis Stack/向量使用 DB 0；认证/TLS 与部署一致；状态层 HA 且 `noeviction` |
| 加密 | `ENCRYPTION_KEY` | KMS/Secret Manager、密钥版本和轮换方案，密钥版本随数据一起备份 |
| 模型 | `LLM_*`、模型表配置 | Provider 和目标地址审批，Key 加密，明确数据分类、驻留和费用预算 |
| 知识 | `RAGFLOW_*`、`knowledge_ragflow_*` | 私网目标必须配置 `RAGFLOW_ALLOWED_PRIVATE_HOSTS/CIDRS`，最小权限 Key，本地与 RAGFlow 权限取交集 |
| Embedding | `embed_*` | Key 加密，并检查模型和维度兼容性 |
| SSO | `SSO_*`、`yovole_sso_enabled` | 禁止公开默认 Token，响应防重放，异常 Fail-closed |
| OpenClaw | `openclaw_*`、`OPENCLAW_ALLOWED_PRIVATE_HOSTS/CIDRS` | 私网精确 Host + CIDR，认证上下文签名并绑定 Audience |
| SQL | `sql_execution_mode`、外部 SQL 配置、`EXTERNAL_SQL_ALLOWED_PRIVATE_HOSTS/CIDRS` | HTTP 网关私网精确 Host + CIDR；数据库账号默认只读，生产拒绝不安全开发模式 |
| SMTP | 用户邮件配置、`SMTP_ALLOWED_PRIVATE_HOSTS/CIDRS`、`SMTP_ALLOWED_PORTS` | 私网精确 Host + CIDR；端口按部署白名单；465 隐式 TLS，其他批准端口强制 STARTTLS；连通性错误不回显内部地址 |
| Agent 运行 | `agent_*`、`sub_agent_*` | 限制迭代、上下文、锁 TTL、超时和输出；变更需审计和版本化 |
| Skills | `skill_auto_*`、Workspace Root | 文件字节/数量限制、Canonical 隔离路径和不可变发布包 |
| 审计 | `audit_log_retention_days` | 根据法律和安全要求确定保留期，并验证容量和删除结果 |

## 已知配置漂移

- 根目录 `env.example` 设置 `REDIS_DB=2`，但 RediSearch 要求 DB 0。
- Compose 给应用配置 Redis 密码，但内置 Redis 服务没有配置对应密码。
- Compose 使用 `API_SERVICE_LOG_LEVEL`，应用读取 `LOG_LEVEL`，主程序又硬编码 INFO。
- 示例文件包含固定 SSO、加密、数据库和 Redis 密钥，必须删除并停止在安装输出中展示。

## 启动校验

出现以下情况时，生产启动应使用脱敏错误直接失败：Secret 为空或仍为默认值；Origin 策略不安全；Redis DB 不兼容；加密密钥无法解密校验值；数据库 Schema 版本过旧或过新；多副本模式仍使用本地可写存储；启用代码/浏览器执行但没有隔离 Worker。

数据库配置与环境变量配置应执行相同的 Schema 校验、加密、变更审批、审计历史和回滚。连通性测试和日志禁止输出 Secret 值。
