# 外部 API 与信任边界

> 外部 URL 也可能保存在数据库中。配置清单记录所有静态引用键；本附录记录依赖语义、传输数据和必要控制。

| 服务 | 接口 | 认证/配置 | 发送数据 | 必要控制 |
|---|---|---|---|---|
| OpenAI 兼容模型 | Provider `/models`、`/chat/completions` | 模型表或 LLM 配置 | Prompt、历史、工具 Schema/结果、可能的业务数据 | Provider 白名单、数据分类、TLS、超时/重试、脱敏、费用和数据驻留 |
| Embedding Provider | 兼容 Embedding API | Embedding 配置和 Key | 文档切片、记忆和元数据文本 | 已固定解析并绑定请求 Origin；继续增加保留期、向量数据分类和 egress 审批 |
| RAGFlow | Dataset、Document/Chunk、`/retrieval`、托管 Agent | `ragflow_api_url`、API Key | 文档、问题、资源 ID 和上下文 | 已固定解析；私网要求专属精确 Host + CIDR，存量 Key 绑定 Origin；继续建设权限交集、熔断和备份责任 |
| OpenClaw | `/v1/chat/completions` | 系统/Agent Base URL 和 Key | 用户认证上下文、数据集范围和消息 | 已固定解析；私网要求专属精确 Host + CIDR，跨 Origin 不发送存量 Key；继续建设上下文签名和响应校验 |
| MCP Server | 用户/管理员配置的 SSE/JSON-RPC URL | `sys_mcp_servers` 和 Auth Header | 工具发现、调用参数和业务数据 | 已接入固定解析与同源限制；继续建设 egress、Secret Vault、审批、幂等和审计 |
| 通用 API 工具 | 可配置外部 HTTP 请求 | `sys_api_tools` | 工具特定业务数据 | 已固定解析且禁止动态 Origin；继续限制任意 Header、响应字节和目标域审批 |
| 企业 SSO | 配置的登录校验接口和固定用户目录接口 | `SSO_API_URL`、Token 和配置 | 登录身份/断言 | 已固定解析、强制 TLS、禁止代理/重定向并 Fail-closed；继续建设响应签名、防重放和审计 |
| External SQL HTTP 网关 | `external_sql_api_url` | 系统 URL 和 `X-API-Key` | 只读 SQL、数据源和查询结果 | 已固定解析；私网要求专属精确 Host + CIDR 并绑定 Origin；继续限制响应字节、幂等重试和审计 |
| 业务数据库 | MySQL/PostgreSQL/Oracle/ClickHouse/SQL Server | `meta_db_connection_configs.password` 保存 `dbpassword:v1:` 密文；API 只返回状态 | SQL、元数据、样本和结果 | 已固定解析；私网要求精确 Host + CIDR + 端口审批；SQL Server 强制证书校验；存量明文由 V118/V17 隔离并通过默认 dry-run 的离线命令迁移；继续建设其他驱动 CA/TLS、只读账号、查询预算、KMS 和轮换演练 |
| 通知/Webhook | 渠道特定 HTTP/SMTP 接口 | 用户/系统通知配置 | 任务、报表内容和身份 | HTTP 与 SMTP 均已固定解析；SMTP 私网要求专属 Host + CIDR、端口审批和强制 TLS；继续建设目标域名审批、数据分类、重试幂等和投递回执 |
| 搜索/公开网页 | Bing、Baidu 或 URL Fetch | 工具配置 | 用户问题和网页 URL | 静态抓取已逐跳固定解析；动态浏览器任意 URL 已关闭，待隔离 Worker/egress 后恢复；继续限制内容大小/类型和 Prompt Injection |

## 统一出网策略

所有外部 HTTP 调用应使用统一的策略感知 Client/Gateway：配置和连接时规范化 URL；只允许声明的协议和端口；解析全部 DNS 地址；拒绝 Loopback、Link-local、Private、Multicast、Unix Socket 和云元数据；每次重定向和连接重新校验；禁止继承环境代理凭据；限制时间、跳转和字节数；脱敏 Secret；记录目标服务和关联 ID。

模型 Base URL 同样属于 SSRF 边界。即使只有管理员能配置，也不能忽略该风险，因为管理员账号可能被盗，配置也可能来自导入。

MCP 请求和响应 DTO 已分离，列表和详情只返回 `has_auth_headers`、
`credential_status` 等无值标记；新写入使用版本化密文，存量明文通过隔离命令迁移，
日志不再输出 Authorization 片段。后续仍需接入 KMS 密钥版本和轮换演练。

外部数据源同样采用请求/响应分离：写请求可携带新密码，读响应仅返回 `has_password` 和
`credential_status`。保存配置的测试、表列表和 DDL 接口只接受配置 ID，解密仅发生在服务端
运行边界内；隔离或无法解密的凭据返回冲突并拒绝连接。

## 可用性契约

每个依赖都应明确超时、最大重试时间、熔断阈值、降级行为和用户提示。检索或模型失败不能被静默包装为“有依据的成功回答”。Readiness 只依赖当前流量类型的必要服务；可选 Provider 通过熔断降级，不应让所有 API 副本退出服务。
