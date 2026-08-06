# 任务、报表与通知

## 业务链路

```text
用户/Agent -> 创建定时任务或报表订阅
 -> 校验 Cron/触发条件 -> 登记调度
 -> 使用任务 Owner 和已发布 Agent/资源范围执行
 -> 生成 Run、结果和产物
 -> 通知策略 -> 站内信/Webhook/企业通知 -> 已读和回执
```

## 主要接口

| 前缀 | 作用 |
|---|---|
| `/api/v1/tasks*` | 任务 CRUD、启停和运行记录 |
| `/api/portal/saved-reports*` | 报表、执行、运行历史、共享和订阅 |
| `/api/portal/inbox*` | 个人通知和已读状态 |
| `/api/portal/notifications*` | 通知渠道配置和测试 |
| `/api/portal/workbench/home` | 聚合待办、运行中任务和最近产出 |
| `/api/portal/chatbi-monitors` | 从 ChatBI 结果创建监控 |

## 数据表

| 表 | 作用 |
|---|---|
| `ai_agent_scheduled_tasks` | Prompt、Cron、用户、Agent、会话、配置和运行信息 |
| `portal_saved_reports` | 保存的查询/报表定义 |
| `portal_saved_report_runs` | 报表执行历史和状态 |
| `portal_saved_report_subscriptions` | 调度、阈值和通知策略 |
| `portal_saved_report_shares` | 报表共享 |
| `portal_saved_report_user_prefs` | 用户展示偏好 |
| `portal_saved_report_digest_deliveries` | 摘要通知记录 |
| `portal_notifications` | 站内通知和已读状态 |
| `user_notification_configs` | 用户通知渠道配置 |

## 当前调度问题

`scheduler_service.py` 在 Web 进程内启动 APScheduler，并共享 SQLAlchemy JobStore。每个 API 副本都会启动自己的调度器，无法保证单次执行。

任务锁固定 300 秒且没有续租，长任务可能在锁过期后重复执行；部分知识维护任务在 Redis 锁异常时 Fail-open 继续运行。当前模型不适合横向扩容。

## 目标执行模型

```text
Scheduler Leader -> 插入 task_execution(task_id, scheduled_fire_time)，唯一约束
Worker -> Lease + Heartbeat 领取 -> 幂等执行 -> 持久化结果
       -> 按策略重试 -> 死信/人工处理
Notification Worker -> 领取 Outbox -> 使用幂等键投递 -> 保存回执
```

建议新增 `task_execution`，至少包含：`id`、`tenant_id`、`task_id`、`scheduled_fire_time`、`attempt`、`status`、`lease_owner`、`lease_expires_at`、`started_at`、`finished_at`、`input_snapshot`、`agent_version`、`resource_scope_snapshot`、`result_ref` 和错误信息。

## 正确性要求

1. 每次 Run 固定 Agent 版本，并快照资源范围和关键配置。
2. 区分 Worker 的至少一次投递和业务副作用的一次性语义，写工具和通知必须有幂等键。
3. 使用 Lease、Heartbeat、最大执行时间、重试分类、退避、死信和人工重放。
4. 使用 Transactional Outbox，避免任务提交成功但通知丢失。
5. 时间统一保存 UTC，明确平台/用户时区，并测试 DST 和补跑行为。
6. 按用户/租户限制任务数量、并发、Token 和通知量。
7. 根据数据分类设置 Run 和通知回执保留时间。

## 功能规划

- 统一任务中心：即将执行、运行中、等待审批、失败、超时和可重试任务。
- 高风险工具和大范围报表分发增加人工审批。
- 通知去重、静默窗口、升级策略和摘要合并。
- ChatBI 监控增加结果差异和阈值命中解释。
- 场景包可以安装预定义任务，但必须声明 Owner、权限和验收用例。

## 验收标准

- 两个 Scheduler/API 副本对同一计划时间只产生一个 Execution。
- Worker 领取后宕机可通过 Lease 安全恢复，长任务能持续续租。
- 通知重试不会重复发送业务消息。
- Agent 或配置发布不会改变已经生成的 Run 快照。
- 时区、DST、补跑、暂停/恢复、超时、重试和人工重放都有集成测试。
