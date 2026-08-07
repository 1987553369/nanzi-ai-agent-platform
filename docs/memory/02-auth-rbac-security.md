# 认证、RBAC 与安全评审

## 信任链路

```text
密码/SSO -> 登录接口 -> API Key/Cookie -> 当前用户
        -> 菜单/元素权限 -> 资源权限 -> Agent、数据和工具操作

业务宿主 -> Embed postMessage/token -> iframe -> V1 Chat API
```

## 身份与权限数据

| 表 | 作用 |
|---|---|
| `ai_agent_users` | 用户、密码 Hash、API Key 加密值/Hash、组织属性和状态 |
| `ai_agent_roles` | 角色代码和名称 |
| `ai_agent_user_role_relations` | 用户与角色关系 |
| `ai_agent_resource_permissions` | 用户/角色对具体资源的访问权限 |
| `ai_agent_quota_policies` | 系统、角色和用户额度 |

当前实现本质上是单组织 RBAC 加资源过滤。由于没有贯穿全领域的 `tenant_id`，不能将其描述为已经完成生产级多租户隔离。

## P0 上线阻断问题

| 风险 | 代码证据 | 必须整改 |
|---|---|---|
| `/chat` 宽泛白名单让普通登录用户访问代码执行 | `app/core/v1_api_access.py:110-115` | 使用精确操作权限，关闭普通用户代码执行 |
| Python/Shell 在主应用容器直接运行 | `code_execution_service.py` | 迁移到一次性隔离 Worker，默认断网、非 root、资源限额 |
| ChatBI 入口设置 `bypass_table_auth=True` | `chatbi.py:295-322`、`sql_query_execution_service.py:434-464` | 所有入口统一执行数据源、表、列、行权限 |
| SPA fallback 可越过 `frontend/dist` | `app/main.py:363-372` | resolve/commonpath 校验或只使用安全静态文件组件 |
| AI/工具/知识 Markdown 允许原始 HTML | `markdown.ts:5-9,131-136`、`MessageRenderer.vue` | `html:false`、DOMPurify 白名单和 CSP |
| Embed 不校验消息来源并向 `*` 传 API Key | `EmbedChat.vue:4893-4938`、`Chat.vue:80-115` | Origin/Source/nonce 校验和短期 Embed Token |
| 安装脚本包含固定管理员 API Key | `db-prod/INIT-USER-ADMIN.sql` | 随机一次性初始化凭据、强制轮换、不打印长期密钥 |

## P1 高风险问题

- MCP 凭据回显、明文保存和日志前缀泄露属于历史发现，已在 `MCP-A` 修复：响应只返回
  `has_auth_headers`/`credential_status`，新写入使用 `mcpheaders:v1:` 密文，存量明文先禁用
  隔离再由离线命令迁移，运行时拒绝明文回退。剩余工作是接入 KMS 和演练密钥轮换。
- `NET-A/NET-B` 已为 MCP、用户 HTTP 工具、公开网页抓取、Generic API、模型发现/
  Embedding 和 HTTP Webhook 接入固定解析；模型存量 Key 绑定 Provider/Origin。RAGFlow、
  OpenClaw、External SQL、SSO、AgentScope SDK、SMTP 与生产 egress 仍需继续治理。
- SSO 客户端存在 `verify=False`，无法验证服务端证书。
- Cookie 固定 `secure=False`，长期 API Key 返回浏览器并保存在 `localStorage`。
- 登出只清认证缓存，数据库中的长期 API Key 仍有效。
- 限流辅助函数没有实际接入登录、LLM、代码或工具接口。
- Portal Trace 和 Agent active config 缺少一致的 Owner/Admin 对象权限检查。
- 客户端可提交 Prompt Override、Raw Prompt 和工具自动批准策略，可能弱化服务端策略。
- `/static/uploads` 和 branding 目录直接公开挂载。
- 默认 CORS 为 `*` 且允许凭据。

## 目标安全模型

1. 浏览器只使用 `HttpOnly + Secure + SameSite` 短期会话 Cookie，并对写请求提供 CSRF 防护。
2. 机器 API Key 必须具备名称、Scope、过期时间、最后使用时间和即时撤销能力。
3. Embed 使用服务端签发、分钟级、绑定租户/用户/Agent/Origin/会话的短期 Token。
4. 授权默认拒绝，使用精确操作 ID，并在 Service/Repository 层执行对象和租户过滤。
5. 工具按风险分级，写操作具备人工审批、参数验证、幂等键和签名回执。
6. 密钥进入 Secret Manager/KMS，支持版本、轮换和日志脱敏测试。
7. 依赖锁定并生成 SBOM，执行依赖/容器扫描，使用非 root 最小运行镜像。

## 多租户完成标准

- 所有租户数据表增加不可变 `tenant_id`/workspace 字段以及组合唯一索引。
- 租户身份只能来自可信认证上下文，不能相信请求 Body 中的租户字段。
- Repository 层统一追加租户条件，并为每类资源建立跨租户负向测试。
- 隔离租户密钥、向量命名空间、对象存储路径、额度、审计导出和备份恢复。
- 制定全量存量数据回填方案，不能只修改 Agent 表。

## 上线安全门槛

所有 P0 必须有自动化回归测试和独立复核。至少覆盖：恶意 Markdown、编码路径穿越、跨 Origin Embed、代码/工具权限矩阵、ChatBI 跨用户数据权限、SSRF 重定向/DNS Rebinding/IPv6/云元数据、初始化凭据、容器隔离和 Secret Scan。

完整风险台账见 [risk-register.md](appendix/risk-register.md)，源码向认证分析见 [02-auth-rbac-tenancy.md](02-auth-rbac-tenancy.md)。
