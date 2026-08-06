# NanZi 修复完善清单

> 基线：`main@70e490c`，创建日期：2026-08-06。
> 状态：`[ ]` 待处理，`[~]` 处理中，`[x]` 已完成，`[!]` 需要外部基础设施或决策。

## 一、P0 安全止血（上线前必须全部完成）

| 状态 | 编号 | 修复项 | 代码范围 | 验收条件 |
|---|---|---|---|---|
| [x] | SEC-P0-01 | 关闭普通用户代码执行入口，移除 `/chat` 宽泛白名单 | `v1_api_access.py`、`code_execution.py` | 普通用户调用代码执行返回 403；只有显式 API 权限/管理员可访问 |
| [!] | SEC-P0-02 | 建设真正隔离的代码执行 Worker | Docker/Worker/Queue/Policy | 非 root、只读根 FS、默认断网、CPU/内存/PID/超时限制，无平台 Secret |
| [x] | DATA-P0-01 | 删除 ChatBI `bypass_table_auth` 越权路径 | `chatbi.py`、SQL 执行服务 | 任意 Session ID 都不能跳过数据源、表、列、行权限 |
| [x] | WEB-P0-01 | 修复 SPA fallback 路径穿越 | `app/main.py` | 编码和普通 `../` 均无法读取 `frontend/dist` 外文件 |
| [x] | WEB-P0-02 | 修复 Markdown XSS | `markdown.ts`、`MessageRenderer.vue` | 原始 HTML 默认禁用；恶意模型流无法执行脚本/事件属性 |
| [x] | WEB-P0-03 | 修复 Embed `postMessage` 信任和凭据传递 | `EmbedChat.vue`、`Chat.vue`、Widget Debugger、集成文档 | 校验 Origin/Source/nonce；禁止 `*`；Portal 不再传长期 API Key |
| [x] | AUTH-P0-01 | 删除固定管理员 API Key 和公共默认长期 Secret | 初始化 SQL、安装脚本、示例配置 | 安装随机生成一次性凭据；Secret Scan 无有效固定凭据 |
| [~] | MCP-P0-01 | 阻止 MCP 凭据回显和日志泄露 | MCP DTO、Model、Client、前端表单 | 列表/详情仅返回是否配置凭据；日志无 Header 值；新写入存储加密；旧明文待迁移 |
| [~] | NET-P0-01 | 建立统一 SSRF 防护并接入 MCP | URL Policy、MCP Client/Endpoint | 阻断私网、Loopback、Link-local、云元数据、IPv6、重定向；DNS 复查已接入，最终需固定解析/出口代理 |

## 二、P1 工程与安全稳定（P0 后 2-6 周）

| 状态 | 编号 | 修复项 | 验收条件 |
|---|---|---|---|
| [x] | AUTH-P1-01 | 浏览器改用 HttpOnly/Secure/SameSite 短期 Session，停止 localStorage 长期 API Key | 登录不返回长期 Key；随机 Session 可解析、撤销和过期；生产 Cookie 强制 Secure |
| [x] | AUTH-P1-02 | SSO 强制 TLS 校验，删除 `verify=False` | 不可信证书连接失败 |
| [x] | AUTH-P1-05 | CORS 默认同源，生产环境禁止通配 Origin 与凭据组合 | 未显式配置的跨域请求不返回 CORS 授权头 |
| [x] | AUTH-P1-03 | 登录、LLM、工具、代码执行统一限流 | 登录、SSO、聊天生成、MCP 工具执行和代码执行均接入 Redis 原子限流 |
| [~] | AUTH-P1-04 | Trace、Agent Active Config、上传文件统一对象授权 | Portal Trace/Span 和 Agent 活跃配置已校验所有者/执行权限；上传路径已按用户隔离，仍需浏览器跨用户负向集成测试 |
| [ ] | AI-P1-01 | Prompt Override、Raw Prompt、工具自动批准改为服务端特权 Capability | 普通请求无法弱化运行策略 |
| [ ] | ENG-P1-01 | 固定 Python/Node 依赖，拆分 Runtime/Dev/Optional Lock | 干净环境可重复构建，生成 SBOM |
| [ ] | ENG-P1-02 | 建立 CI：Lint、类型、单测、集成、前端构建、SAST、Secret/依赖/镜像扫描 | PR 必须通过全部门禁 |
| [ ] | ENG-P1-03 | 统一前端 Auth Store、API Client、SSE Transport、错误模型 | Portal/Embed/Debug 共用协议契约 |
| [ ] | ENG-P1-04 | 路由懒加载、Bundle Budget、长列表虚拟化 | 首屏体积和性能预算通过 |
| [ ] | DB-P1-01 | 统一事务 Unit of Work，减少 Service 内部分散 Commit | 部分失败可完整回滚 |

## 三、运行时、运维与高可用（1-2 个版本）

| 状态 | 编号 | 修复项 | 验收条件 |
|---|---|---|---|
| [x] | OPS-P0-01 | 增加 `/live`、`/startup`、`/ready` 和 Graceful Drain | DB/Redis 故障时实例正确摘除，关闭时不接收新流 |
| [ ] | OPS-P0-02 | 调度器从 API 拆分，建立 Durable Execution、Lease、Heartbeat 和幂等键 | 两副本同一计划时间只产生一次执行 |
| [ ] | OPS-P0-03 | Audit Queue 改有界持久队列并支持重试/DLQ | DB 短时故障不丢审计且内存有上限 |
| [!] | OPS-P0-04 | 主数据库 HA、PITR、Redis HA/AOF、对象存储与恢复演练 | 在隔离环境达到目标 RPO/RTO |
| [x] | OPS-P0-05 | 收紧 Compose 默认凭据并补 Redis 基础持久化/健康检查 | 未配置密码时启动即失败；Redis 使用认证、AOF、持久卷和健康依赖 |
| [ ] | DB-P0-01 | 迁移引入 Ledger、Checksum 和全局锁，修复 MySQL 非原子与重复版本 | MySQL/PostgreSQL Fresh、N-1 Upgrade、重跑测试通过 |
| [ ] | OPS-P1-01 | 结构化日志、Prometheus、OpenTelemetry、告警和容量预算 | Run 可端到端关联，关键 SLI 有 Dashboard/Alert |
| [!] | OPS-P1-02 | API、Worker、Scheduler 跨故障域多副本部署 | 实例、Redis 主节点、DB 主节点故障演练通过 |

### 本轮仍需外部基础设施或架构决策

| 编号 | 原因 | 下一步 |
|---|---|---|
| AUTH-P0-02 | 第三方跨域 Embed 仍需要短期、限受众 Embed Token 签发/撤销服务 | 新增 Token 表/签发接口、Origin/Agent 绑定、TTL、撤销和审计后再开放生产跨域嵌入 |
| SEC-P0-02 | 代码执行当前只做了权限止血，执行进程仍在平台边界内 | 独立 Worker/Queue，非 root、只读根、无 Secret、网络/CPU/内存/PID/超时策略 |
| MCP-P0-02 | 存量 MCP 明文 Header 需要在当前 `ENCRYPTION_KEY` 下轮换 | 备份后批量解密重加密，失败行进入人工轮换队列，完成后禁止 legacy fallback |
| NET-P0-02 | 应用层 DNS 复查无法单独证明抗 DNS Rebinding | egress proxy/NetworkPolicy 固定出口，或实现带 SNI 的 IP pinning transport，并做重绑定演练 |

## 四、产品与平台完善（2-9 个月）

| 状态 | 编号 | 完善项 | 验收条件 |
|---|---|---|---|
| [ ] | PROD-P1-01 | 普通用户、构建者、管理员三套信息架构 | 核心任务可发现性和完成率提升 |
| [ ] | PROD-P1-02 | 将数据门户和场景市场提升为一级入口 | 新用户无需隐藏路径即可进入 |
| [ ] | PROD-P1-03 | Agent 评测中心：数据集、评分器、版本对比、质量门禁 | 发布必须绑定评测结果 |
| [ ] | PROD-P1-04 | 发布生命周期：开发/预发/生产、审批、灰度和回滚 | 一键回滚演练通过 |
| [ ] | PROD-P1-05 | 场景模板改成受治理资产包 | 支持版本、审核、依赖检查、导入导出和升级 |
| [ ] | PROD-P1-06 | 真正的 Tenant/Workspace 领域模型 | 跨租户负向测试、密钥/额度/审计/备份隔离通过 |
| [ ] | DATA-P1-01 | ChatBI 认证指标、血缘、Owner、质量和时效 SLA | 认证语义资产可版本化和回归验证 |
| [ ] | KNOW-P1-01 | 知识低召回、无引用、差评、过期内容自动生成治理任务 | 质量问题有 Owner、SLA 和闭环状态 |
| [ ] | PROD-P2-01 | 条件、并行、人工审批、补偿和幂等工作流 | 典型跨 Agent 业务流程验收通过 |
| [ ] | PROD-P2-02 | Connector/Skill/MCP/场景企业私有市场 | 签名、版本、权限、兼容性和回滚完整 |
| [ ] | PROD-P2-03 | 成本、预算、Showback/Chargeback 和业务 ROI | 可计算单次成功任务成本和业务价值 |
| [ ] | UX-P2-01 | i18n、WCAG 2.2 AA、移动/PWA 任务体验 | 关键流程无障碍和多语言验收通过 |

## 五、本轮执行记录

| 日期 | 批次 | 结果 |
|---|---|---|
| 2026-08-06 | 清单建立 | 开始第一批 P0 代码修复 |
| 2026-08-06 | P0-A | 完成代码执行 API 权限收紧、ChatBI 权限绕过关闭、SPA 穿越修复 |
| 2026-08-06 | P0-B | 完成 Markdown XSS 清洗、Embed Source/Origin/nonce 协议、MCP 凭据回显/日志收口、URL SSRF 基线 |
| 2026-08-06 | P0-C | 完成固定管理员凭据移除、示例 Secret 占位化、`/live`/`/startup`/`/ready` 与 Graceful Drain |
| 2026-08-06 | P0-D | 收紧 Compose 默认凭据，启用 Redis requirepass/AOF/健康检查，统一 `LOG_LEVEL` 配置并移除 SSO 固定默认值 |
| 2026-08-06 | P0-E | 增加生产启动配置校验，拒绝 `CHANGE_ME_*`/`GENERATE_A_*` 占位安全参数 |
| 2026-08-06 | P1-A | SSO 强制证书校验；CORS 改为显式 Origin 白名单，生产禁止通配符 |
| 2026-08-06 | P1-B | 增加 Redis Lua 原子限流，覆盖登录、SSO、聊天生成和代码执行，并保留 `Retry-After` |
| 2026-08-06 | P1-C | 浏览器登录改用 Redis 短期随机 Session，移除响应和 localStorage 中的长期 API Key |
| 2026-08-06 | P1-D | Portal Trace/Span 与 Agent 活跃配置增加对象授权；MCP 工具执行补分布式限流 |
| 2026-08-06 | ENG-A | 清理 MCP 表单与 6 个共享前端工具的严格类型错误，全量构建错误集合持续收敛 |
| 2026-08-06 | 验证 | 后端安全/运行时契约 65 项通过；浏览器 Session/Markdown/Embed/MCP 契约 13 项通过；全量前端构建仍被仓库既有 TypeScript 错误阻断 |
