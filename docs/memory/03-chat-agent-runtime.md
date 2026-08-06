# 对话与智能体运行时

## 1. 完整链路

```text
POST /api/v1/chat/completions
  -> require_api_key + V1 API access
  -> AgentService.chat_completion_stream
  -> Redis conversation lane + server history
  -> @mention/direct agent/RouterService
  -> server-side Agent permission check
  -> skill/LTM/resource scope/prompt assembly
  -> AgentDispatcher
       -> AssistantExecutor -> AgentScope ReAct
       -> DataQueryExecutor -> ChatBI
       -> KnowledgeExecutor -> pre-retrieval + ReAct
       -> RAGExecutor -> RAGFlow
       -> OpenClawExecutor -> OpenClaw
       -> FederatedQueryExecutor -> multi-source SQL
  -> SSE content/log/router_log/citation/meta/error
  -> Redis history + execution history/traces/audit
```

## 2. 核心端点

| 路径 | 方法 | 认证/权限 | 用途 |
|---|---|---|---|
| `/api/v1/chat/completions` | POST | API key + V1 policy | 流式/非流式对话 |
| `/api/v1/chat/history` | GET | Owner | 会话列表 |
| `/api/v1/chat/conversation/{id}` | GET/DELETE | Owner | 会话历史与删除 |
| `/api/v1/chat/conversation/{id}/finalize` | POST | Owner | 强制生成跨会话摘要 |
| `/api/v1/chat/logs` | GET | 已认证 | 当前用户执行日志 |
| `/api/v1/chat/traces/{trace_id}` | GET | Owner/admin | Trace |
| `/api/portal/agents*` | 混合 | RBAC/资源权限 | Agent 与版本生命周期 |
| `/api/portal/models*` | 混合 | RBAC | 模型注册、发现、测试 |
| `/api/portal/prompts*` | 混合 | RBAC | Prompt 管理 |

## 3. 主请求字段

| 字段 | 类型 | 必需 | 作用 |
|---|---|---|---|
| `messages` | list | 是 | OpenAI 风格消息；最后一条可含 files |
| `stream` | bool | 否 | SSE 或普通 JSON |
| `agent_id` / `agent_name` | string | 否 | 直选 Agent |
| `version_id` | string | 否 | 调试指定版本 |
| `conversation_id` | string | 否 | 服务端历史和会话锁 |
| `enable_multi_agent` | bool | 否 | 多 Agent 路由/合成 |
| `debug_options` | object | 否 | 当前允许覆盖 Prompt/上下文，需收紧 |
| `permission_options` | object | 否 | 当前可影响工具批准，需改服务端策略 |
| `knowledge_dataset_ids` | list | 否 | 知识范围 |
| `metadata_dataset_ids` | list | 否 | 数据范围 |

字段权威定义见 `app/api/v1/endpoints/chat.py:66-87` 和 `appendix/api-schema-inventory.md`。

## 4. SSE 事件契约

| 类型 | 语义 |
|---|---|
| 初始化 / `trace_id` | 初始化执行身份 |
| `content` | 可见回答增量 |
| `log` | 思考、工具和执行步骤 |
| `router_log` | 路由选择、置信度和通用 turn hints |
| `citation` | 知识来源 |
| `meta` | Agent 显示信息等元数据 |
| 审批/等待 | 工具授权挂起 |
| `retraction` | 撤回并覆盖已输出内容 |
| `error` | 额度、忙、执行异常 |
| `[DONE]` | 流结束 |

前端 Embed 和 Debug 各自实现 SSE 消费，是当前重复和漂移来源。

## 5. 状态与数据

| 状态 | Key/表 | 生命周期 |
|---|---|---|
| 会话历史 | `conversation:{user_id}:{conversation_id}:history` | Redis LIST，默认 7 天 |
| 最近数据结果 | `...:last_data_result` | Redis JSON，7 天 |
| ChatBI 结果栈 | `...:data_result_stack_v1` | Redis JSON |
| 长期记忆 | `nanzi:agent:ltm:{user_id}` | Redis HASH/向量 |
| 会话串行锁 | user_id + conversation_id | Redis token lock |
| AgentScope 状态 | State Store | 默认 7 天 |
| 工具审批快照 | pending store | 默认 600 秒 |
| 执行摘要 | `ai_agent_execution_history` | 主库 |
| Trace 步骤 | `ai_agent_execution_traces` | 主库 |

用户 ID 已进入会话 key，历史、导出和 V1 trace 有 owner 校验，这是正确的隔离基础。

## 6. 架构优点

- Router 候选在路由前按用户权限过滤，选择后再次复核 Agent 权限。
- direct selection、@mention、启发式短路、LLM 路由和多专家合成都有明确路径。
- AgentScope runtime 已抽象消息、事件、状态、审批、会话锁、工具和 trace。
- 会话并发通过分布式 lane 串行化，避免同会话状态交叉。
- Tool loop detector、context compaction、quota 和 grounding 已进入运行链。
- 执行器按 Assistant/Data/Knowledge/External 分界，比在一个 Agent 内堆所有工具更易治理。

## 7. 主要问题

- `agent_service.py` 约 2,600 行、Assistant runner 约 2,154 行、federated executor 约 2,268 行，职责仍过度集中。
- 客户端可提交 `system_prompt_override`、`injected_context`、`return_raw_prompt`，普通请求和调试请求未真正隔离。见 `agent_service.py:1720-1769`。
- 客户端 `approval_mode=allow` 可自动批准原本需询问的工具。见 `runtime/agentscope/tools.py:282-310`。
- 指定 Agent 快捷 route 直接调用另一个 FastAPI endpoint 函数，依赖默认值可能成为 `Depends` 对象。见 `chat.py:1158-1173`。
- Redis 同时承载状态、审批、会话、锁和向量，故障域过大。
- Trace 存储工具输入/输出和模型内容，但 Portal trace 对象授权不足。

## 8. 研发改造

1. 将 API schema 与内部 `ChatExecutionCommand` 分离；服务端生成安全上下文和工具批准策略。
2. 将 AgentService 拆成 TurnCoordinator、AgentResolver、ContextAssembler、ExecutionRecorder。
3. 建立统一事件 schema 和版本号；Embed、Portal、Debug 共用一个 `ChatRuntime`/transport。
4. execution trace 增加 tenant_id/user_id，工具输入输出做字段级脱敏和大小限制。
5. 对每个 executor 建立契约测试：权限、取消、超时、重试、SSE 顺序、空输出、外部依赖失败。
6. Redis 状态层和向量层分离；需要恢复的执行状态持久化到 DB/对象存储。
