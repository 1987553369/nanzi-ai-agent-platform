# 知识、记忆、Skills 与 MCP

## 核心链路

```text
知识：知识库/文档 -> RAGFlow 解析和索引 -> 授权检索 -> 引用回答 -> 运营指标
记忆：对话 -> 摘要/LTM 提取 -> Redis 向量索引 -> 按策略召回 -> 注入 Prompt
Skill：本地文件/压缩包 -> 校验 -> 个人使用 -> 发布申请 -> 审核版本
MCP：登记 SSE URL/认证 -> 验证/同步工具 -> 绑定资源 -> JSON-RPC 调用
```

## 接口范围

| 前缀 | 作用 |
|---|---|
| `/api/portal/ragflow/datasets*`、`/documents*`、`/retrieval-test` | 知识生命周期和检索测试 |
| `/api/portal/memory/*` | LTM、摘要、向量健康、合并和重建 |
| `/api/portal/personal-skills*` | 个人 Skill、文件、导入和发布申请 |
| `/api/portal/skills*` | 公共 Skill、绑定和发布审核 |
| `/api/portal/mcp/servers*`、`/tools*`、`/verify` | MCP 服务、工具发现和执行 |

## 状态与存储

| 资源 | 当前存储 | 高可用影响 |
|---|---|---|
| 知识文档和切片 | RAGFlow | 需要外部服务 SLA、权限映射和备份责任 |
| 知识元数据/指标 | `knowledge_base_metadata`、`knowledge_base_metrics` | 本地主库是治理事实来源 |
| 记忆和向量索引 | Redis | RediSearch 要求 DB 0，TTL 和故障切换会影响连续性 |
| Skill 文件 | 本地挂载目录 | 多副本不一致，应迁移对象存储 |
| Skill 发布记录 | `skill_publications`、`skill_publication_versions` | 版本应引用不可变 Artifact Digest |
| MCP 定义和缓存 | `sys_mcp_servers`、`sys_mcp_tool_cache` | Header 使用版本化密文；存量迁移失败项隔离禁用，缓存随配置变化失效 |

## 关键安全边界

- MCP Verify 和 Personal MCP 历史上允许直接连接任意 URL；`NET-A` 已接入固定解析
  Transport，校验全部 A/AAAA、只连接已验证公网 IP，并禁止重定向和跨 Origin 后续 endpoint。
- 历史审计曾发现 MCP 响应回显 `auth_headers`、数据库明文保存和日志输出
  Authorization 前缀；`MCP-A` 已改为请求/响应 DTO 分离、版本化密文、无值状态响应、
  旧明文隔离迁移和日志仅输出 Header 名称。后续仍需验证密钥轮换和 KMS 托管。
- Skill 压缩包可能包含路径穿越、符号链接、超大解压和可执行内容。
- 检索文档属于不可信 Prompt 和 UI 输入，可能包含 Prompt Injection、数据外传指令和 XSS。
- 记忆是敏感衍生个人数据，应提供查看、修改、删除、保留期限和用途控制。
- 本地权限和 RAGFlow 权限可能漂移，每次检索必须取两者授权集合的交集。

## 必须建立的控制

1. MCP、用户 HTTP 工具、Generic API、模型发现/Embedding、公开网页抓取、HTTP Webhook、
   SSO、RAGFlow、OpenClaw、External SQL HTTP 网关、SMTP 和数据库原生协议已完成固定解析；
   私网集成要求精确 Host 与最小 CIDR 双重审批，SMTP/数据库同时要求端口审批。生产继续覆盖
   AgentScope SDK、数据库驱动 CA/TLS 配置，并增加
   egress proxy/NetworkPolicy。
2. 文件安全：MIME 检测、压缩包大小/文件数/深度限制、Canonical Path、恶意文件扫描，默认禁止可执行内容。
3. Prompt Injection 防护：明确标记外部内容为不可信数据，工具权限由独立策略决定，不能被文档指令改变。
4. 知识证据：引用片段、文档版本、分数、检索问题、访问判定和数据时效。
5. 记忆治理：保留期、用途、来源、用户删除、租户命名空间，禁止保存 Token 和密码。
6. Skill 发布：签名不可变包、依赖清单、审核人、策略扫描、兼容版本、回滚和审计记录。

## 可靠性改造

- Redis 状态与向量搜索拆分，分别设置内存和 `noeviction` 策略。
- 用 Stream 或原子 Claim/Ack 代替阻塞 `KEYS` 和读取/提交/删除的指标聚合。
- 索引重建和文档处理迁移到独立 Worker，API 启动只做就绪检查。
- Skills、上传文件和生成产物迁移到支持版本和校验和的对象存储。
- MCP Session 必须有生命周期上限、健康状态、熔断和严格日志脱敏。

## 产品演进

可以把 Skills、MCP、API 工具和场景统一展示为受治理的企业资产市场，统一 Owner、风险等级、权限、依赖、版本、质量和用量。但底层仍应保留不同执行安全模型，不能因为前端目录统一就把风险边界合并。

## 验收标准

- SSRF 测试覆盖私有 IPv4/IPv6、云元数据、重定向、编码变体和 DNS Rebinding。
- 恶意文档不能触发未批准工具调用，也不能在浏览器执行 HTML。
- 跨用户和跨租户检索/记忆负向测试全部通过。
- 任意 Run 使用的 Skill 可以按 Digest 恢复到完全相同的字节内容。
- Redis/RAGFlow 故障必须明确降级，不能把无依据回答伪装成有依据回答。

源码向详细分析见 [05-knowledge-memory.md](05-knowledge-memory.md) 和 [06-tools-integrations.md](06-tools-integrations.md)。
