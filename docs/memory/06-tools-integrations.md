# 工具与外部集成

## 1. 扩展面

```text
AgentScope Toolkit
  ├─ Built-in tools: time/search/files/documents/notifications
  ├─ SQL/Data API
  ├─ Generic API tools
  ├─ MCP remote tools
  ├─ Skills / SKILL.md
  ├─ Browser/Playwright
  └─ Code execution
```

工具是平台最高风险边界：LLM 产生或用户提交的输入会跨越文件系统、网络、数据库和 OS 进程。工具批准必须是服务端策略，不能由 Prompt 或客户端字段替代。

## 2. 核心端点

| 路径 | 方法 | 作用 |
|---|---|---|
| `/api/portal/tools*` | 混合 | 通用 API 工具管理 |
| `/api/portal/mcp/verify` | POST | 验证并发现 MCP 工具 |
| `/api/portal/mcp/servers*` | 混合 | 全局/个人 MCP 管理与同步 |
| `/api/portal/mcp/tools/{id}/execute` | POST | MCP 调用 |
| `/api/portal/skills*` | 混合 | 平台技能与审核 |
| `/api/portal/skills/personal*` | 混合 | 个人技能 |
| `/api/v1/chat/fs/*` | 混合 | 用户工作区浏览、上传、保存 |
| `/api/v1/chat/code-executions/stream` | POST SSE | 执行代码 |
| `/api/v1/chat/code-executions/stop` | POST | 停止代码 |

## 3. P0：代码执行不是沙箱

任意已登录用户可通过 `/chat` 白名单进入代码执行路由，提交 Python/sh/bash 等代码；服务直接用应用进程 OS 用户启动解释器：

- `app/core/v1_api_access.py:110-115`
- `app/api/v1/endpoints/code_execution.py:30-34,81-110`
- `app/services/ai/code_execution_service.py:343-352`
- `workspace_access_policy.py:40-45` 明确承认 cwd 校验不能限制代码打开任意路径。
- `docker/Dockerfile:22-88` 未设置非 root `USER`。

字符串黑名单和工作区路径校验不能替代 OS 沙箱。短期应关闭接口或只授予极少管理员 capability；正式方案应是一次性 sandbox worker：非 root、只读根 FS、独立临时卷、默认断网、allowlist egress、seccomp/AppArmor、cgroup CPU/内存/PID、超时、无宿主 socket 和平台密钥。

## 4. P0/P1：MCP 凭据和 SSRF

- 历史审计发现响应回显 `auth_headers`、ORM 明文存储并在日志输出 Authorization 前缀。
  `MCP-A` 已完成请求/响应 DTO 分离、`mcpheaders:v1:` 版本化密文、旧明文隔离迁移、
  运行时拒绝明文、配置变化会话失效和只返回无值轮换状态。
- `/mcp/verify` 与 MCP 调用已禁止 HTTP 重定向并接入 URL Policy；应用层 DNS 复查仍不能
  单独证明抗 DNS Rebinding，生产环境仍需固定解析 Transport 或隔离出口代理。

剩余整改：凭据接入 KMS/密钥版本和轮换演练；只允许 HTTPS；固定已校验解析结果；目标域
allowlist/管理员审批；个人 MCP 走隔离 egress proxy；继续限制危险 headers、响应大小、并发和超时。

## 5. 文件与浏览器

已有文件浏览器大量使用 realpath 和用户 workspace 边界；生成文件采用 32-byte capability token、hash 比对和 24 小时 TTL，这是良好基础。

仍需整改：

- `data/uploads` 与 `data/branding` 整目录无鉴权静态公开，见 `app/main.py:353-360`。
- SPA fallback 直接拼接用户路径，存在目录穿越，见 `app/main.py:363-372`。
- URL fetch 首次解析只检查一个 IPv4，重定向和 AAAA/DNS rebinding 未覆盖；Playwright 子资源不限且使用 `--no-sandbox`。
- Skill/archive 上传必须限制压缩展开大小、文件数、路径穿越、符号链接和可执行内容。

文件应改为授权下载接口或短期 capability URL；浏览器放入低权隔离容器并对所有 request 逐个做 egress 校验。

## 6. Generic API 与通知

Generic API、模型发现/测试、通知 webhook、Jira、SSO 都是服务端出网点。统一安全 egress client 应提供：协议与域白名单、DNS/IP 校验、逐跳重定向校验、超时/响应上限、代理策略、凭据注入、日志脱敏、熔断和审计。当前各模块分别创建 `httpx.AsyncClient`，策略不一致。

## 7. 工具治理目标

| 等级 | 例子 | 默认策略 |
|---|---|---|
| 低风险只读 | 时间、公开搜索 | 自动允许 + 配额 |
| 敏感数据读取 | 企业数据、文件、记忆 | Scope 校验 + 审计 |
| 外部写操作 | Jira、通知、业务 API | 人工确认 + 幂等键 |
| 任意计算/网络 | 代码、Browser、MCP | 隔离执行 + 强策略 + 低配额 |

每个工具需要声明 owner、风险级别、数据分类、网络目标、是否写操作、幂等性、超时、最大输入/输出、权限 scope 和审计字段；Agent 绑定工具不等于用户获准执行工具。
