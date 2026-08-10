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
| [x] | MCP-P0-01 | 阻止 MCP 凭据回显和日志泄露 | MCP DTO、Model、Client、前端表单 | 列表/详情仅返回配置状态；日志无 Header 值；新写入和存量凭据均使用版本化密文；明文运行时回退已禁用 |
| [x] | NET-P0-01 | 建立统一 SSRF 防护并接入 MCP | URL Policy、MCP Client/Endpoint | 全量校验 A/AAAA；固定已验证 IP 连接并保留 Host/SNI；阻断私网、Loopback、Link-local、云元数据、跨 Origin 和重定向 |
| [x] | SEC-06B | 外部数据源密码版本化加密、隔离迁移和 API 不回显 | 数据源 Model/Service/API、连接池、导入前端、MySQL V118、PostgreSQL V17 | 新写入立即加密；存量明文先隔离；运行时拒绝明文；响应仅返回 `has_password`/`credential_status`；轮换销毁旧池 |
| [x] | NET-G | 外部数据库传输加密统一策略 | TLS 构建器、五类数据库连接入口、数据源前端、MySQL V119、PostgreSQL V18 | MySQL/ClickHouse/Oracle 强制 CA 校验；PostgreSQL 支持 CA/身份校验；SQL Server 强制身份校验；生产拒绝 `disabled`；CA 路径不能逃逸审批目录 |

## 二、P1 工程与安全稳定（P0 后 2-6 周）

| 状态 | 编号 | 修复项 | 验收条件 |
|---|---|---|---|
| [x] | AUTH-P1-01 | 浏览器改用 HttpOnly/Secure/SameSite 短期 Session，停止 localStorage 长期 API Key | 登录不返回长期 Key；随机 Session 可解析、撤销和过期；生产 Cookie 强制 Secure |
| [x] | AUTH-P1-02 | SSO 强制 TLS 校验，删除 `verify=False` | 不可信证书连接失败 |
| [x] | AUTH-P1-05 | CORS 默认同源，生产环境禁止通配 Origin 与凭据组合 | 未显式配置的跨域请求不返回 CORS 授权头 |
| [x] | AUTH-P1-03 | 登录、LLM、工具、代码执行统一限流 | 登录、SSO、聊天生成、MCP 工具执行和代码执行均接入 Redis 原子限流 |
| [~] | AUTH-P1-04 | Trace、Agent Active Config、上传文件统一对象授权 | Portal Trace/Span 和 Agent 活跃配置已校验所有者/执行权限；上传路径已按用户隔离，仍需浏览器跨用户负向集成测试 |
| [x] | AI-P1-01 | Prompt Override、Raw Prompt、工具自动批准改为服务端特权 Capability | 普通请求无法弱化运行策略 |
| [~] | ENG-P1-01 | 固定 Python/Node 依赖，拆分 Runtime/Dev/Optional Lock | Node 已有 lock；Python Runtime/Dev 已拆分，开发工具精确固定；Docker 基础镜像固定补丁版本并禁止 `npm install` 回退；仍需生成完整 Python hash lock、固定镜像 Digest 和拆 Optional 依赖 |
| [~] | ENG-P1-02 | 建立 CI：Lint、类型、单测、集成、前端构建、SAST、Secret/依赖/镜像扫描 | 已新增四类 GitHub Actions job、增量 Ruff/SAST 硬门禁、离线测试、前端类型/构建、Secret Scan、依赖审计、双 SBOM、镜像构建/扫描和报告留存；整改分支最新远端 run 31347281603 中前端与供应链成功、容器按条件跳过，后端仍失败，剩余项为向量索引初始化、SQL Server 适配器及 AgentService 测试的基础设施耦合，暂不标记完成 |
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
| [x] | DB-P0-01 | 迁移引入 Ledger、Checksum 和全局锁，修复 MySQL 非原子与重复版本 | MySQL/PostgreSQL Fresh、N-1 Upgrade、重跑测试通过 |
| [ ] | OPS-P1-01 | 结构化日志、Prometheus、OpenTelemetry、告警和容量预算 | Run 可端到端关联，关键 SLI 有 Dashboard/Alert |
| [!] | OPS-P1-02 | API、Worker、Scheduler 跨故障域多副本部署 | 实例、Redis 主节点、DB 主节点故障演练通过 |

### 本轮仍需外部基础设施或架构决策

| 编号 | 原因 | 下一步 |
|---|---|---|
| AUTH-P0-02 | 第三方跨域 Embed 仍需要短期、限受众 Embed Token 签发/撤销服务 | 新增 Token 表/签发接口、Origin/Agent 绑定、TTL、撤销和审计后再开放生产跨域嵌入 |
| SEC-P0-02 | 代码执行当前只做了权限止血，执行进程仍在平台边界内 | 独立 Worker/Queue，非 root、只读根、无 Secret、网络/CPU/内存/PID/超时策略 |
| NET-P0-02 | 应用层 HTTP、SMTP 和五类数据库原生协议已接入固定解析；受控私网目标要求精确 Host + CIDR 双重审批并限制端口。SMTP 与数据库已具备强制 TLS 策略。动态浏览器任意 URL 已 fail-closed；AgentScope 模型 SDK和生产网络层仍待治理 | 将 Host/CIDR/端口/CA 审批纳入部署变更和审计；继续完成 Browser Worker、egress proxy/NetworkPolicy、响应字节上限和跨协议重绑定演练 |

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
| 2026-08-06 | ENG-B | 修复报表 Cron、元数据首表、数据门户导航、聊天日志步骤号和 Prompt 优化建议的严格空值类型错误；相关 6 个文件已退出全量构建错误列表 |
| 2026-08-06 | ENG-C | 补齐知识推荐与模型能力类型，统一 9 种 Markdown 主题契约，收紧场景安装步骤和技能导入文件边界；本批减少 44 个前端构建错误 |
| 2026-08-06 | ENG-D | 收紧 AgentDebug、数据源、知识库和 Embed 资源范围类型，修正过时契约断言；清零全量前端 TypeScript 错误 |
| 2026-08-06 | P1-E | 注册 `element:chat:debug_prompt`、`element:chat:auto_approve_tools` 两项高风险能力；聊天请求缺少能力返回 403；任务创建/修改按所有者校验，历史任务运行时将未授权自动批准降级为请求批准；前端同步隐藏未授权控件 |
| 2026-08-06 | 验证 | 后端安全/运行时契约 65 项通过；浏览器 Session/Markdown/Embed/MCP 契约 13 项通过；全量前端构建仍被仓库既有 TypeScript 错误阻断 |
| 2026-08-06 | ENG-B 验证 | 相关前端静态契约 25 项通过；1 项未修改的 `PersonalCenter.vue` 旧样式字符串断言失败；全量构建继续暴露其余既有严格类型错误 |
| 2026-08-06 | ENG-C 验证 | 相关前端静态契约 127 项通过；1 项未修改的调度器旧源码字符串断言失败；全量构建剩余错误集中在 AgentDebug、DataSourceManagement、EmbedChat、ExampleManagement 和 KnowledgeBaseManagement |
| 2026-08-06 | ENG-D 验证 | `npm run build` 完整通过（10,386 个模块）；`tests/frontend` 全量 317 项通过；仍有大 Chunk 与静态/动态重复导入构建警告待 ENG-P1-04 处理 |
| 2026-08-06 | P1-E 验证 | AI 执行能力纯逻辑与迁移契约 16 项通过；`tests/frontend` 全量 320 项通过；`npm run build` 完整通过（10,386 个模块）。聊天 API/任务端点负向测试已补齐，本机因 Python 3.9 且缺少 `aiomysql` 未执行，需由标准 Python 3.11 CI 回归 |
| 2026-08-06 | DB-A | MySQL/PostgreSQL 统一引入 `nanzi_schema_migrations` 账本、SHA-256 Checksum 和数据库 advisory lock；MySQL DDL 执行前持久化 `in_progress`，PostgreSQL 单版本 SQL 与成功记录同事务；原生 MySQL 入口改为委托安全执行器；重复版本 V31/V110 已消除 |
| 2026-08-06 | DB-A 验证 | Python 3.11 下 Fresh、重跑、N-1 Upgrade、旧库指定版本基线、Checksum 篡改、脏状态、历史文件缺失、并发锁和 Shell 透传等迁移契约测试 67 项通过；Python 编译、Bash 语法和 `git diff --check` 通过；未连接或修改任何实际数据库 |
| 2026-08-07 | MCP-A | 新增 MySQL V117/PostgreSQL V16 凭据隔离状态；旧明文服务自动禁用；离线命令支持 dry-run、批量加密、逐行锁和失败隔离；运行时删除明文回退并每次校验持久化状态；API/前端提供不回显值的轮换状态，配置变化销毁旧会话 |
| 2026-08-07 | MCP-A 验证 | Python 3.11 凭据状态机/安全契约 29 项及迁移清单契约 25 项通过；MCP 前端专项 31 项及 `tests/frontend` 全量 320 项通过；`npm run build` 完整通过（10,386 个模块）；Python 编译和 `git diff --check` 通过；未执行任何实际数据库迁移 |
| 2026-08-07 | NET-A | 新增固定解析 HTTP Transport：每次请求只解析一次并校验全部 A/AAAA，实际连接使用已验证公网 IP，原域名保留为 Host/SNI/证书校验名称；连接池按原域名和 IP 隔离；MCP 探测、SSE SDK 与 Direct HTTP 全部接入；禁止重定向和跨 Origin 后续 endpoint |
| 2026-08-07 | NET-A 验证 | Python 3.11 URL Policy、固定解析、MCP 安全及凭据状态机契约 56 项通过；迁移相关契约 19 项、`tests/frontend` 全量 320 项通过；`httpx` 下限收敛到已验证的 0.27；Python 编译和 `git diff --check` 通过；本机缺少 MCP SDK 和必填集成环境，未执行真实远端 MCP 联调 |
| 2026-08-07 | NET-B | 用户 HTTP 工具、公开网页抓取/搜索、Generic API、模型发现与 Embedding、个人 HTTP Webhook 统一接入固定解析；安全重定向逐跳校验并在跨 Origin 时剥离凭据；模型存量 Key 绑定 Provider/Origin；动态 Host 模板被禁止，动态 Playwright 任意 URL 在独立 Browser Worker 建成前 fail-closed；日志移除查询值和参数值 |
| 2026-08-07 | NET-B 验证 | Python 3.11 固定解析、重定向、可配置出网、MCP 与凭据安全契约 65 项通过；迁移契约 19 项、`tests/frontend` 全量 320 项通过；`npm run build` 完整通过（10,386 个模块），本批变更 Python 文件编译和 `git diff --check` 通过。本机缺少 `aiomysql`、MCP SDK 和完整 Python 3.11 原生依赖，工具/模型 API 集成测试已更新但需标准 CI 回归；未连接真实外部服务、数据库或执行部署 |
| 2026-08-07 | NET-C（SSO） | SSO 登录和管理员用户目录同步统一接入固定解析 Client，禁止环境代理、自动重定向和非公网目标；用户目录调用改为异步并在远端故障时 fail-closed；登录错误不再向未认证调用者回显底层连接信息；修复用户状态被尾逗号转换为元组的问题 |
| 2026-08-07 | NET-C（SSO）验证 | Python 3.11 出网与 SSO 核心安全契约 67 项通过，Python 3.9 离线 SSO 用户目录单测 1 项通过；本批变更 Python 文件编译和 `git diff --check` 通过；未连接真实 SSO、数据库或启动服务 |
| 2026-08-07 | NET-D（受控内网集成） | 统一出网策略新增集成专属私网审批：精确 Host 与 RFC1918/IPv6 ULA CIDR 必须同时匹配，全部 DNS 结果逐个校验并固定解析，禁止公网/私网混合结果、Loopback、Link-local、通配 Host、跨 Origin 和无 Origin 绑定的私网 Client；RAGFlow、OpenClaw、External SQL HTTP 网关全部接入；删除无目标约束的全局 HTTP 单例；RAGFlow/OpenClaw 存量 Key 禁止跨 Origin 复用；日志移除查询、用户、会话、Key 前缀和远端正文 |
| 2026-08-07 | NET-D 验证 | Python 3.11 出网、集成、MCP、凭据和 SSO 核心安全契约 82 项通过；Python 3.9 配置契约 19 项通过；本批 Python 文件编译和 `git diff --check` 通过。RAGFlow/OpenClaw/External SQL 专项测试已同步更新，但本机缺少 `aiomysql`、`psycopg`、`sqlglot` 和完整 Python 3.11 原生依赖，需标准 CI 回归；未连接真实外部服务、数据库或启动部署 |
| 2026-08-07 | NET-E（SMTP） | 三个重复邮件发送入口统一收敛到策略发送器；全量校验 DNS A/AAAA 后仅连接已批准 IP，TLS SNI/证书主机名仍使用原域名；私网目标要求 SMTP 专属精确 Host + CIDR；部署端口白名单默认仅 465/587；465 使用隐式 TLS，其他批准端口强制 STARTTLS，禁止明文降级；工具和通知接口不再回显底层连接异常 |
| 2026-08-07 | NET-E 验证 | Python 3.9 离线 SMTP/配置安全契约 39 项通过，扩大后的出站/SSO 核心回归 92 项通过；Python 3.11 本批文件定向编译和 `git diff --check` 通过。Python 3.11 本机未安装 pytest，完整应用测试仍受缺少 `aiomysql`、`sqlglot` 等原生依赖影响，需标准 CI 回归；未连接真实 SMTP、数据库或启动部署 |
| 2026-08-07 | NET-F（数据库原生协议） | MySQL、PostgreSQL、ClickHouse、Oracle、SQL Server 的连接池、即时连接、表发现、DDL 拉取和长会话统一接入部署侧 Host + CIDR + 端口审批；全量校验 A/AAAA 后驱动只连接固定 IP；PostgreSQL 使用原 Host + `hostaddr`；SQL Server 使用固定 IP 并强制 `Encrypt=yes`、`TrustServerCertificate=no`、原域名 `HostNameInCertificate`；ODBC 参数统一转义；客户端不再回显驱动底层异常 |
| 2026-08-07 | NET-F 验证 | Python 3.9 数据库出站专项 102 项、扩大后的出站/SSO 核心回归 113 项通过；Python 3.11 本批文件定向编译和 `git diff --check` 通过。本机缺少 `aiomysql`、`asynch`、`oracledb`、`psycopg`、`aioodbc` 和 `sqlglot`，驱动 mock/集成测试需标准 CI 回归；未连接真实数据库或执行迁移。MySQL/ClickHouse/Oracle 的 CA/TLS 配置模型及数据库凭据加密另列后续高优先级批次 |
| 2026-08-07 | SEC-06B（数据源凭据） | 新增 `dbpassword:v1:` 版本化密文和四态凭据状态；MySQL V118/PostgreSQL V17 只隔离存量明文；离线命令默认 dry-run、逐行锁定后加密；运行时拒绝明文和隔离凭据；API/前端不回显密码，保存配置按 ID 在服务端解密；密码轮换销毁旧连接池 |
| 2026-08-07 | SEC-06B 验证 | 数据源凭据、迁移和静态安全契约 17 项通过；前端 `npm run build` 完整通过（10,386 个模块）；Python 3.11 定向编译和 `git diff --check` 通过。未执行真实数据库迁移、数据库连接或部署；真实迁移需先备份并执行 dry-run 审核 |
| 2026-08-07 | NET-G（数据库 TLS） | 新增 `disabled/verify_ca/verify_identity` 策略和审批目录 CA 相对路径；连接池、即时测试、表发现、DDL 与长会话统一使用共享构建器；MySQL/ClickHouse/Oracle 仅宣称 CA 校验，PostgreSQL 支持 `verify-ca/verify-full`，SQL Server 保持系统信任库身份校验；Oracle Thick 使用 Wallet 目录；生产启动和运行时拒绝未启用 TLS；新增 MySQL V119/PostgreSQL V18 |
| 2026-08-07 | NET-G 验证 | 离线 core 与迁移运行时回归 243 项、前端契约 320 项通过；`npm run build` 完整通过（10,386 个模块）；Python 3.11 定向编译和 `git diff --check` 通过。未执行真实数据库连接、迁移或部署；上线前需在隔离环境验证各驱动证书链、吊销和轮换 |
| 2026-08-07 | ENG-E（CI 与供应链基线） | 新增 `Quality Gates`：后端全量编译、增量 Ruff/SAST、无基础设施测试、前端契约/类型/生产构建、Gitleaks、Pip/NPM 审计、CycloneDX 双 SBOM、Docker Buildx 和 Trivy SARIF；硬门禁与存量债务报告分离；所有 Action 使用精确版本并由 Dependabot 覆盖；Runtime/Dev Python 依赖拆分，Docker 固定 Node/Python 补丁版本并移除 `npm ci || npm install` 回退 |
| 2026-08-07 | ENG-E 验证 | 离线 core/迁移回归 252 项、前端契约 320 项和 CI 专项 9 项通过；CI 配置自检、增量 Ruff/SAST、Python 全量编译、前端生产构建和 CycloneDX SBOM 本地通过。远端 GitHub Actions、完整 Python 3.11 干净依赖安装、镜像构建及扫描尚未运行，因此 ENG-P1-01/02 保持进行中 |
| 2026-08-10 | 整改分支回归 | codex/remediation-hardening 已连续推送测试契约修复（b64af4f、3563c3f、2cc4816、ff6ae2e）；本地 Python 3.11 编译、git diff --check、增量 Ruff/SAST 通过。远端 Quality Gates 前端与供应链成功，容器 job skipped；后端剩余失败已收敛到既有向量索引/SQL Server 测试及 AgentService 离线测试的数据库依赖，未执行真实数据库、迁移或部署。 |
