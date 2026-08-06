# 核心对话与 Agent 编排

## 端到端链路

```text
POST /api/v1/chat/completions
  -> 认证、会话和资源范围
  -> AgentService
  -> 指定 Agent/@提及 或 RouterService 启发式/LLM 路由
  -> AgentDispatcher
  -> Assistant | ChatBI | Knowledge | RAGFlow | OpenClaw
  -> AgentScope ReAct + Toolkit
  -> SSE 正文/日志/引用/产物/审批/结束事件
  -> 执行历史、Trace、Token 和反馈
```

## 控制面接口

| 路径 | 作用 | 前端 |
|---|---|---|
| `/api/portal/agents*` | Agent 定义、归属和启停 | `api/agent.ts` |
| `/api/portal/agents/{id}/versions*` | 草稿和版本管理 | Agent 管理/调试 |
| `.../versions/{version_id}/publish` | 发布生效配置 | Agent 管理 |
| `/api/portal/models*` | 模型注册、发现和连通测试 | `api/model.ts` |
| `/api/portal/prompts/*` | Prompt 保存、测试和优化 | Prompt Studio |
| `/api/portal/tools*` | API 工具管理 | `api/tool.ts` |

## 运行接口

| 路径 | 作用 |
|---|---|
| `/api/v1/chat/completions` | 主流式对话协议 |
| `/api/v1/chat/agents/{agent_id}/chat` | 指定 Agent 执行 |
| `/api/v1/chat/active`、`/cancel` | 活跃任务和取消 |
| `/api/v1/chat/conversation/{id}*` | 历史、结束、模型调用和资源范围 |
| `/api/v1/chat/code-executions*` | 代码执行和停止，属于最高风险边界 |

完整参数、响应和源码行号见接口与 Schema inventory。

## 核心数据

| 表 | 作用 |
|---|---|
| `ai_agents` | Agent 身份、类型、引擎、Owner 和状态 |
| `ai_agent_versions` | 模型、温度、Prompt、Tools、Skills 和欢迎配置 |
| `ai_models` | Provider、模型、Base URL、Key 和上下文限制 |
| `sys_api_tools`、`sys_mcp_*` | 工具定义和缓存 |
| `ai_agent_execution_history` | 执行摘要、Token、状态和反馈 |
| `ai_agent_execution_traces` | Step、Span 和工具明细 |
| `ai_agent_access_logs` | HTTP 访问审计 |

## 工程问题

- `agent_service.py` 约 2,600 行，同时承载过多策略和执行职责。
- Assistant Runner 和 Federated Executor 均超过 2,000 行，修改回归范围很大。
- SSE 事件缺少正式版本、事件序号和可恢复协议。
- 代码执行状态和部分取消状态保存在内存，无法跨副本协调。
- 模型、工具和外部调用的超时、重试、熔断、脱敏和成本策略不统一。
- Python 依赖大多只有最低版本，不能保证可重复构建。

## 改造建议

1. 建立带版本、`event_id`、`sequence`、终态和重连语义的 SSE 协议。
2. 持久化 Run、Owner、Lease、取消 Token、Checkpoint 和幂等键。
3. 将编排拆成请求标准化、策略判定、路由计划、执行计划、工具循环、合成和持久化。
4. 所有模型/工具调用经过统一 Adapter，提供超时、重试、熔断、Trace、脱敏和成本统计。
5. 建立路由、Prompt、工具选择、引用、取消、SSE 中断和多 Agent 合成评测集。
6. 控制面保留模块化单体，推理、代码/浏览器、调度和索引任务迁移到独立 Worker。

## 目标执行事件

```text
ExecutionRequested(run_id, subject, tenant, agent_version, input, scope, budget)
 -> PolicyAccepted | PolicyDenied
 -> StepStarted | ToolApprovalRequired | StepCompleted
 -> ArtifactCreated | CitationEmitted
 -> ExecutionSucceeded | Failed | Cancelled | TimedOut
```

每个事件都应包含 `run_id`、`trace_id`、`span_id` 和序号，并写入持久化事件源。API 与 Worker 使用同一份执行事实。

## 验收标准

- API 副本被杀死后，Run 不丢失、不重复，客户端可以从最后事件恢复。
- 取消和超时可跨副本终止下游工具与代码进程。
- 已发布 Agent 版本在评测集上的路由和工具决策可解释、可比较。
- 工具不能突破时间、Token、内存、进程、文件系统和网络预算。
- Trace 脱敏测试能证明 Prompt、凭据和敏感数据按策略处理。

更详细的源码链路见 [03-chat-agent-runtime.md](03-chat-agent-runtime.md)。
