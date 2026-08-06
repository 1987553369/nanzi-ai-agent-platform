# 知识库与记忆

## 1. 业务流

```text
知识文档 -> RAGFlow Dataset/Document/Chunk 或本地索引
        -> 用户/角色数据集权限 -> 检索 -> 引用卡 -> Knowledge Agent 回答
        -> 反馈、召回测试、质量指标

会话消息 -> Redis history -> 窗口裁剪/摘要
用户偏好/事实 -> LTM HASH + 向量索引 -> Prompt 注入 / memory_search
```

## 2. 核心端点

| 路径 | 方法 | 认证/权限 | 作用 |
|---|---|---|---|
| `/api/portal/ragflow/config` | GET | API key | 配置摘要 |
| `/api/portal/ragflow/datasets*` | 混合 | RBAC/资源权限 | 知识数据集与权限 |
| `/api/portal/ragflow/documents*` | 混合 | RBAC/资源权限 | 文档与切片 |
| `/api/portal/ragflow/retrieval*` | POST | RBAC/resource | 检索测试 |
| `/api/portal/memory/*` | 混合 | Owner/管理员 | LTM、摘要、索引运维 |
| `/api/v1/chat/conversation/*` | 混合 | Owner | 会话历史与摘要 |

RAGFlow 具体外部路径见 `appendix/external-apis.md`；API 字段见 inventory。

## 3. 数据与状态

| 数据 | 存储 | 说明 |
|---|---|---|
| 知识库元数据 | `knowledge_base_metadata` | 本地治理属性 |
| 知识质量指标 | `knowledge_base_metrics` | 使用和召回指标 |
| RAG 文档/切片 | RAGFlow | 外部托管 |
| 会话历史 | Redis LIST | user_id + conversation_id，7 天 |
| 会话摘要 | Redis/索引 | 跨会话回顾 |
| 长期偏好/事实 | Redis HASH | 按用户隔离 |
| 记忆向量 | Redis Stack | 启动 ensure，可从源状态重建 |

## 4. 已有优势

- Knowledge executor 在 ReAct 前执行预检索，能把来源引用注入统一事件流。
- 候选知识数据集和记忆均按当前用户 scope 过滤。
- 对空召回、无引用回答和工具误报已有防护。
- 知识管理提供树、切片、召回测试、语义合并和运营指标。
- Redis 重启后会后台 ensure 记忆索引，避免永久不可用。

## 5. 风险

- Redis 无持久卷时会丢失记忆索引、会话和运行状态；当前 Compose 正是无卷配置。
- 状态、锁、缓存和向量共用单 Redis，内存淘汰或故障会同时影响多个能力。
- RAGFlow 是外部对象系统，平台必须在每次 dataset/document/chunk 操作前做本地资源授权，不能信任客户端 ID。
- 文档正文和模型引用最终进入 Markdown `v-html`，未消毒会形成存储型/反射型 XSS。
- `memory_search` 和 raw prompt 调试输出要防止把其他会话、密钥或隐藏 system prompt 暴露给用户。
- 知识指标聚合使用 Redis `KEYS` 且读取/DB 提交/删除不具原子性，可能丢计数或重复。

## 6. 改进方向

- Redis 拆为 state/cache 与 vector 两个集群；state 使用 AOF、noeviction 和 HA，vector 可重建。
- 记忆从“自动积累”升级为可解释治理：来源、置信度、过期时间、可见范围、删除和导出。
- 引入知识质量 SLO：检索成功率、引用完整率、未回答率、过期内容比例和差评修复时长。
- 将低召回、无引用、差评和内容过期自动转成治理任务，并关联 owner。
- 对外部 RAGFlow 建立 circuit breaker、超时预算、重试分类和 degraded 状态。
