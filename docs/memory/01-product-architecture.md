# 产品与总体架构

## 1. 产品判断

NanZi 已经形成企业内部“业务智能体平台”而非聊天 Demo。最强产品资产是：基于授权元数据生成 SQL、以工具结果和引用形成证据、把结果转成报表/任务/通知、再通过场景包和 Embed 交付给业务用户。

建议对外定位：

> 可嵌入、可追溯、基于企业真实数据和知识执行任务的可信业务智能体平台。

不建议同时追逐 Dify/Coze 的全部应用搭建能力、n8n 的全部自动化连接器和 LangSmith/Langfuse 的全部观测能力。产品主线应围绕“数据可信、知识可信、执行可信、交付可复制、价值可度量”。

## 2. 用户与价值

| 用户 | 核心任务 | 当前入口 |
|---|---|---|
| 业务员工/经理 | 提问、继续会话、查看产出、任务和报表 | 工作台、AI Chat、个人中心 |
| BI/数据工程师 | 数据源、元数据、指标、关系、案例和查询治理 | Metadata、ChatBI、Data Portal |
| 知识运营 | 文档、召回测试、引用与内容治理 | Knowledge Hub、RAGFlow |
| Agent 构建者 | Agent、版本、Prompt、Skills、MCP、调试 | Agent Studio、Prompt、Skills、MCP |
| 平台/安全管理员 | 用户、角色、配置、额度、审计和运行治理 | System/Admin/Audit |
| 集成开发者 | 将对话嵌入业务系统并注入上下文 | `/embed/chat`、V1 API |

## 3. 能力架构

```text
体验层       Portal / Personal Workbench / Data Portal / Embed SDK
接口层       Portal API / V1 API / SSE / OpenAPI
身份治理     API Key / SSO / RBAC / Resource Permission / Quota / Audit
编排层       AgentService -> ContextManager -> Router -> Dispatcher
运行层       Assistant / ChatBI / Knowledge / RAGFlow / OpenClaw / Federated
工具层       AgentScope Toolkit / Skills / MCP / API / SQL / Files / Browser / Code
状态层       MySQL|PostgreSQL / Redis Stack / local persistent data
外部层       LLM / Embedding / RAGFlow / MCP / enterprise DB / notifications
```

后端入口和生命周期位于 `app/main.py:39-91`；对话主入口位于 `app/services/ai/agent_service.py:509`；路由和执行器选择分别位于 `router_service.py:184` 与 `dispatcher.py:29`。

## 4. 已形成的产品闭环

### 4.1 工作台闭环

```text
登录 -> 待处理/运行中/最近产出 -> 继续会话/任务/报表 -> 再执行
```

工作台不是空白聊天框，已按业务活动组织待办、产出和资源，并对局部数据失败做降级。

### 4.2 ChatBI 闭环

```text
数据源 -> Profiling -> 元数据/指标/关系 -> 自然语言查询
      -> SQL 证据 -> 图表/分析 -> 暂存报表 -> 订阅与告警
```

### 4.3 知识闭环

```text
文档 -> 切片/索引 -> A/B 召回 -> Agent 绑定 -> 引用回答 -> 反馈/治理
```

### 4.4 场景交付闭环

```text
选择模板 -> 绑定依赖 -> 预检 -> 安装 -> 验收问题 -> 交付清单
```

场景安装已具备交付语义，但模板目录仍硬编码在 `scenario_template_service.py:629-646`，尚不是可运营的资产市场。

## 5. 产品优势

- 多引擎不是简单模型切换，而是 Router、权限复核、Dispatcher 和不同执行器的完整链路。
- ChatBI 已覆盖 Schema、表/列/行权限、只读检查、自愈、联邦查询、结果栈和报表交付。
- Knowledge 路径有预检索、引用卡、空召回/无引用约束和运维指标。
- 工作台、个人资源、任务、报表和聊天已经形成用户连续旅程。
- 场景包具备依赖预检和验收内容，比单纯 Agent 模板更接近业务交付。
- Embed 支持专家直选、主题、会话恢复、业务上下文和宿主事件，集成面较完整。

## 6. 主要产品缺口

| 优先级 | 缺口 | 影响 | 建议 |
|---|---|---|---|
| P0 | 安全边界不足 | 阻断生产可信度 | 先完成 `02-auth-rbac-security.md` 和风险清单中的所有 P0 |
| P1 | 信息架构过载 | 24+ 入口增加学习成本 | 按普通用户/构建者/管理员拆三套导航 |
| P1 | Agent 缺少统一评测和发布门禁 | 发布质量依赖人工调试 | 数据集、评分器、回归、审批、灰度、回滚 |
| P1 | 多租户停留在声明 | 不能安全服务多个客户组织 | tenant/workspace 主键、强制过滤、租户密钥和配额 |
| P1 | 场景市场硬编码 | 无法运营、版本和升级 | 场景资产包、审核、版本、依赖升级 |
| P2 | 可视化工作流不足 | 复杂任务仍靠 Prompt/代码 | 条件、并行、人工确认、补偿和幂等节点 |
| P2 | 缺少业务价值分析 | 难以证明 ROI | 采纳率、任务成功率、节省时间、成本和业务结果 |

## 7. 功能路线图

### 0-6 周：可信基线

- 封闭安全 P0；建立真正的浏览器短期会话和 Embed token。
- 重构导航，把数据门户和场景市场提升为可发现入口。
- 统一前端认证、API client、SSE transport 和错误模型。
- 抽出共享 ChatRuntime，减少 EmbedChat/AgentDebug 重复。
- 建立 CI、前端测试、E2E、可访问性和 bundle budget。
- 埋点“登录 -> 首问 -> 工具成功 -> 反馈 -> 报表/任务转化”漏斗。

### 2-4 个月：交付与治理

- Agent 评测中心和 dev/staging/prod 发布生命周期。
- 场景资产中心和正式 Embed SDK。
- 真正的 tenant/workspace 数据模型。
- ChatBI 认证指标、owner、血缘、质量和时效治理。
- 知识低召回、无引用、差评和过期内容自动形成治理任务。
- 可配置工作流和人工确认节点。

### 4-9 个月：规模化

- Connector/Skill/MCP/场景统一企业市场。
- 组织级成本归集、预算和 ROI 报告。
- 跨 Agent 协作队列、SLA 和行业解决方案包。
- WCAG 2.2 AA、国际化、移动任务体验和统一搜索。

## 8. 产品指标

北极星指标建议使用“每周完成并被用户接受的业务任务数”，而非消息数或 Token 数。配套指标：首问成功率、工具成功率、证据覆盖率、SQL 一次通过率、知识引用完整率、任务按时完成率、报表复访率、7/30 日留存、单成功任务成本、人工节省时间。
