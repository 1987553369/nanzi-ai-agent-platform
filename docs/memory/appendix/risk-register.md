# 风险台账

| 编号 | 等级 | 风险 | 立即措施 | 关闭证据 |
|---|---|---|---|---|
| SEC-01 | P0 | 普通登录用户可通过宽泛 `/chat` 权限在主容器执行 Python/Shell | 关闭接口、精确权限、隔离 Worker | 权限矩阵和 Sandbox Escape 测试 |
| SEC-01A | P0 | ChatBI HTTP 入口可绕过物理表授权 | 删除 Bypass，统一数据源/表/列/行权限 | 所有 SQL 入口跨用户负向测试 |
| SEC-02 | P0 | SPA fallback 路径穿越可能读取服务端文件 | Resolve/Commonpath 或安全静态文件组件 | 编码路径穿越回归测试 |
| SEC-03 | P0 | 模型/工具/知识 HTML 通过 Markdown `v-html` 执行 | 禁用 HTML、DOMPurify、CSP | 恶意流式 XSS 测试 |
| SEC-04 | P0 | Embed 信任任意 `postMessage` 并向 `*` 传长期 Key | Origin/Source/nonce 和短期 Scope Token | 跨域和协议浏览器测试 |
| SEC-05 | P0 | 固定管理员初始化凭据和默认加密材料 | 删除、随机一次性初始化、轮换 | Secret Scan 和 Bootstrap 生命周期测试 |
| SEC-06 | P1（应用 HTTP 路径已缓解） | MCP 和其他可配置 URL 存在 SSRF | 公网 HTTP 路径已固定解析；RAGFlow/OpenClaw/External SQL 私网 HTTP 要求集成专属 Host + CIDR 并绑定凭据 Origin；继续覆盖数据库原生协议、模型 SDK、SMTP、Browser Worker 和网络层 egress | Redirect、Rebinding、IPv4/IPv6/元数据、私网审批、跨 Origin 与跨协议测试 |
| SEC-06A | P1（已缓解） | 历史 MCP 凭据被回显、明文保存和写入日志 | 已完成 DTO 分离、版本化密文、存量隔离迁移和日志脱敏；继续建设 KMS 轮换 | API/状态机契约、双数据库迁移清单、日志脱敏检查 |
| SEC-07 | P1 | 浏览器长期 API Key、localStorage 和不安全 Cookie/CORS | 安全会话 Cookie、CSRF、精确 Origin | 浏览器安全和会话轮换测试 |
| SEC-08 | P1（已缓解） | SSO 历史上关闭 TLS 校验且用户目录调用阻塞事件循环 | 已强制 HTTPS/TLS 与固定解析、禁用代理/重定向、异步化目录同步并稳定错误映射；继续建设响应签名和防重放 | 固定解析契约、离线目录单测；待无效/不可信证书集成测试 |
| SEC-09 | P1 | Trace 和 Agent active config 缺少统一对象授权 | Owner/Admin/资源授权统一层 | 跨用户 Trace/配置负向测试 |
| SEC-10 | P1 | 客户端 Prompt Override/工具自动批准可弱化策略 | 服务端特权 Capability 模型 | 普通用户 Override 拒绝测试 |
| OPS-01 | P0 | 每个 API 副本都启动 Scheduler 和后台任务 | 拆分 Scheduler/Worker，持久化幂等执行 | 双副本同计划时间单次执行测试 |
| OPS-02 | P0 | Health Endpoint 无条件返回成功 | `/live`、`/startup`、`/ready` | 依赖故障流量摘除测试 |
| OPS-03 | P0 | 没有验证过 Backup、PITR 和恢复 | 实施并演练灾备 | 隔离恢复报告和实测 RPO/RTO |
| OPS-04 | P0 | 单 Redis 故障影响状态、锁、审批、向量和缓存 | HA，并拆分状态和向量负载 | Failover 和重建演练 |
| OPS-05 | P1 | 本地文件和内存 Registry 破坏副本等价性 | 对象存储和持久化执行状态 | 副本故障和 Artifact 一致性测试 |
| DB-01 | P0 | 迁移没有 Ledger/Checksum/Lock，MySQL 非原子 | 标准迁移工具、规范重复版本 | 双数据库 Fresh/N-1/重跑测试 |
| DB-02 | P1 | 事务 Commit 分散在依赖和 Service | 明确 Unit of Work | 回滚和部分失败集成测试 |
| ENG-01 | P1 | 依赖未锁定，缺少 CI 和质量门禁 | Lock 和强制 CI | 可重复构建、SBOM、测试和扫描 |
| ENG-02 | P1 | 超大后端/前端组件重复关键逻辑 | 类型化运行边界和渐进拆分 | 特征测试和重复路径减少 |
| PROD-01 | P1 | 多租户声明缺少 Tenant 主键和领域模型 | 修正文案或完整实现 Tenant | 跨租户测试和迁移证据 |
| PROD-02 | P2 | 没有统一评测、发布和回滚生命周期 | 评测中心和发布门禁 | 基线对比、灰度和回滚演练 |
| DATA-01 | P1 | SQL 权限和数据源资源预算可能漂移 | 统一 Scope、只读执行和证据包 | 未授权字段和查询预算测试 |
| AI-01 | P1 | 检索/工具内容可能注入指令或外传数据 | 不可信内容隔离和独立工具策略 | Prompt Injection 红队测试 |

## 评审频率

存在 P0 时每周评审，之后每次发布评审；发生安全事件或信任边界变化时立即重审。每个 P0/P1 必须有 Owner、截止时间和状态（`open`、`mitigated`、`accepted`、`closed`）。风险接受必须有业务批准人和失效时间；关闭状态必须链接代码、测试和运维证据。
