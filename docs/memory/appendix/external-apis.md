# 外部 API 与信任边界

> 外部 URL 也可能保存在数据库中。配置清单记录所有静态引用键；本附录记录依赖语义、传输数据和必要控制。

| 服务 | 接口 | 认证/配置 | 发送数据 | 必要控制 |
|---|---|---|---|---|
| OpenAI 兼容模型 | Provider `/models`、`/chat/completions` | 模型表或 LLM 配置 | Prompt、历史、工具 Schema/结果、可能的业务数据 | Provider 白名单、数据分类、TLS、超时/重试、脱敏、费用和数据驻留 |
| Embedding Provider | 兼容 Embedding API | Embedding 配置和 Key | 文档切片、记忆和元数据文本 | 同上，并增加保留期和向量数据分类 |
| RAGFlow | Dataset、Document/Chunk、`/retrieval`、托管 Agent | `ragflow_api_url`、API Key | 文档、问题、资源 ID 和上下文 | 精确 Host、最小权限 Key、权限交集、熔断和备份责任 |
| OpenClaw | `/v1/chat/completions` | 系统/Agent Base URL 和 Key | 用户认证上下文、数据集范围和消息 | 上下文签名、精确 Audience、出网白名单和响应校验 |
| MCP Server | 用户/管理员配置的 SSE/JSON-RPC URL | `sys_mcp_servers` 和 Auth Header | 工具发现、调用参数和业务数据 | SSRF 防护网关、Secret Vault、风险策略、审批、幂等和审计 |
| 通用 API 工具 | 可配置外部 HTTP 请求 | `sys_api_tools` | 工具特定业务数据 | URL 模板白名单、参数 Schema、禁止任意 Header/URL、响应和超时限制 |
| 企业 SSO | 配置的登录校验接口 | `SSO_API_URL`、Token 和配置 | 登录身份/断言 | TLS、签名响应、防重放、超时、Fail-closed 和审计 |
| 业务数据库 | MySQL/PostgreSQL/Oracle/ClickHouse/SQL Server | 加密的 `meta_db_connection_configs` | SQL、元数据、样本和结果 | 网络白名单、只读账号、查询预算、脱敏、连接池和凭据轮换 |
| 通知/Webhook | 渠道特定 HTTP 接口 | 用户/系统通知配置 | 任务、报表内容和身份 | 域名审批、数据分类、签名、重试幂等和投递回执 |
| 搜索/公开网页 | Bing、Baidu 或 URL Fetch | 工具配置 | 用户问题和网页 URL | 安全浏览/出网代理、内容大小/类型限制、Prompt Injection 隔离 |

## 统一出网策略

所有外部 HTTP 调用应使用统一的策略感知 Client/Gateway：配置和连接时规范化 URL；只允许声明的协议和端口；解析全部 DNS 地址；拒绝 Loopback、Link-local、Private、Multicast、Unix Socket 和云元数据；每次重定向和连接重新校验；禁止继承环境代理凭据；限制时间、跳转和字节数；脱敏 Secret；记录目标服务和关联 ID。

模型 Base URL 同样属于 SSRF 边界。即使只有管理员能配置，也不能忽略该风险，因为管理员账号可能被盗，配置也可能来自导入。

MCP 请求和响应 DTO 已分离，列表和详情只返回 `has_auth_headers`、
`credential_status` 等无值标记；新写入使用版本化密文，存量明文通过隔离命令迁移，
日志不再输出 Authorization 片段。后续仍需接入 KMS 密钥版本和轮换演练。

## 可用性契约

每个依赖都应明确超时、最大重试时间、熔断阈值、降级行为和用户提示。检索或模型失败不能被静默包装为“有依据的成功回答”。Readiness 只依赖当前流量类型的必要服务；可选 Provider 通过熔断降级，不应让所有 API 副本退出服务。
