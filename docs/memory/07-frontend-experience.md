# 前端体验与工程评审

## 当前产品界面

前端基于 Vue 3，覆盖登录、工作台、对话、Agent 构建、数据和知识运营、系统管理以及 `/embed/chat`。路由位于 `frontend/src/router/index.ts`，侧栏菜单则单独维护在 `Dashboard.vue`。

工作台、数据门户、场景安装和 Embed 协议是当前体验最成熟的部分。主要问题是信息层级：约 24 个侧栏入口和 9 个个人中心 Tab 混合了普通用户、构建者和管理员任务。

建议采用“普通用户 / 构建者 / 管理员”三套工作区，并让路由 Meta 成为标题、权限、菜单分组、图标和移动端显示策略的唯一来源。

## 请求与状态体系

| 当前实现 | 使用位置 | 问题 |
|---|---|---|
| 自定义 Axios | `frontend/src/utils/axios.ts` 和部分 API 模块 | 只有部分请求共享拦截和错误处理 |
| 原始 Axios | 登录、用户、角色等页面 | 认证和错误协议容易漂移 |
| 原始 Fetch/SSE | Embed、AgentDebug | 重复实现流解析、取消和重试 |
| Cookie、X-API-Key、Bearer、localStorage | 登录和 Embed | 凭据生命周期混乱 |
| Pinia 已注册但没有 Store | `main.ts` | 用户、权限和会话仍分散在组件状态 |

建议建立 `authStore`、`permissionStore`、`chatSessionStore` 和统一的类型化 API/SSE Transport。Portal 内部对话直接挂载共享 `ChatShell`，只有跨域第三方集成使用 iframe。

## 维护热点

- `EmbedChat.vue` 约 7,821 行，`AgentDebug.vue` 约 5,532 行，重复实现 SSE、历史、审批和 Trace。
- 多个重量级页面在路由入口同步加载。
- 路由、菜单和面包屑维护多份配置。
- UI Primitive 和 Tailwind 样式大量复制，键盘和焦点行为不一致。
- `package.json` 没有 Test、Lint、Format、E2E 或 Accessibility Script。

推荐拆分：

```text
ChatShell
├─ MessageTimeline / MessageRenderer
├─ Composer / Attachments
├─ ApprovalPanel / ResourceScope
├─ TracePanel / ArtifactPanel
└─ ChatRuntime
   ├─ 类型化 SseTransport
   ├─ MessageStore
   ├─ SessionStore
   └─ HostBridge（仅 Embed）
```

## 安全整改

- 禁用模型、工具和知识内容中的原始 HTML，并对最终渲染结果执行严格白名单清洗。
- 配置严格 CSP，消除可执行内联内容路径。
- `postMessage` 校验 Origin、`event.source`、协议版本和 nonce，发送时使用精确 Target Origin。
- Portal 使用安全会话 Cookie，Embed 使用短期 Token，浏览器不再持有长期 API Key。
- Token 不进入 URL、日志、localStorage 和开放宿主消息。

## 性能与质量

1. 除最小 Shell/Login 外，所有路由按页面懒加载；ECharts、Mermaid、Editor、Diff 和文档预览按交互加载。
2. 建立 Bundle Budget 和依赖体积分析，对长会话和大表格使用虚拟列表。
3. 建立 Vitest + Vue Test Utils、Playwright 和 axe，并在 CI 强制执行。
4. 覆盖登录/权限落地、Agent 发布、Embed 握手、SSE 恢复/取消、报表和场景安装。
5. 从 OpenAPI 生成或校验类型化响应和 SSE 事件契约。
6. 统一 Loading、空状态、部分失败、错误边界和用户可见的关联 ID。

## 无障碍与国际化

静态检查发现大量 Button 未声明 `type`、图片缺少 `alt`、焦点 Outline 被移除。应补齐表单 Label/Autocomplete、Dialog 焦点锁定与 Escape、Hover 操作的键盘入口、流式内容播报和 Reduced Motion。

在继续增加硬编码中文前，应引入 i18n 框架。登录、对话、审批、Agent 发布和报表流程应通过 WCAG 2.2 AA 自动与人工检查。

## 验收标准

- 模型、工具和知识内容中的 HTML 无法在浏览器执行。
- Embed 拒绝错误 Origin、Source、协议和 nonce，且不接收长期 API Key。
- 除最小 Shell 外全部路由懒加载，Bundle Budget 通过。
- 单一 Transport 处理认证、错误、SSE 序号/恢复/取消和关联 ID。
- 仅使用键盘和屏幕阅读器能够完成关键业务流程。
