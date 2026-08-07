# 认证、RBAC 与租户边界

## 1. 业务流

```text
密码/SSO/API Key -> AuthService -> ai_agent_users
                -> auth cache -> user_info
                -> menu/element/API/resource permission -> handler/service
```

认证实现位于 `app/api/portal/endpoints/auth.py`、`app/services/auth_service.py` 和 `app/core/dependencies.py`。权限由用户角色关系和直接资源授权聚合，缓存键包含用户 ID；对话在 Agent 选择后还会在 `agent_service.py:830-841` 复核 Agent 资源权限。

## 2. 核心端点

| 路径 | 方法 | 认证/权限 | 作用 | 前端 |
|---|---|---|---|---|
| `/api/portal/auth/login` | POST | 公开 | 密码/API Key 登录 | `Login.vue` |
| `/api/portal/auth/sso-login` | POST | 公开 | 企业 SSO | `Login.vue` |
| `/api/portal/auth/logout` | POST | API key/cookie | 清理认证缓存与 Cookie | axios/fetch |
| `/api/portal/auth/me` | GET | 已认证 | 当前用户 | Dashboard/useUser |
| `/api/portal/management/users*` | 混合 | 管理员/显式权限 | 用户管理与同步 | `portal.ts` / `Users.vue` |
| `/api/portal/roles*` | 混合 | 管理员/显式权限 | 角色、用户和权限 | `portal.ts` / `Roles.vue` |
| `/api/portal/keys*` | 混合 | 已认证 | API Key 管理 | Personal Center |

完整参数、响应模型和行号见 `appendix/endpoint-inventory.md` 与 `appendix/api-schema-inventory.md`。

## 3. 凭据与会话现状

| 凭据 | 当前形态 | 风险 |
|---|---|---|
| 用户 API Key | 随机值；SHA-256 hash 查询；Fernet 可逆存储 | 长期凭据同时被当作浏览器会话；可逆副本扩大密钥泄露面 |
| Cookie `admin_token` | 内容仍是 API Key | 登录时 `secure=False`，不是独立短期 session |
| localStorage | `api_key`、`user_info` | XSS 可直接读取长期 API Key |
| SSO | 用户名/密码换取外部 token | 已强制 HTTPS/TLS 与固定解析；仍缺响应签名和防重放验证 |

API Key 的高熵生成和 hash 查询是已有优点，见 `app/utils/encryption.py:32-52`。用户禁用、角色变更会使认证/权限缓存失效，见 `auth_service.py:251-284` 和 `management.py:520-583`。

## 4. 权限模型

| 类型 | 用途 | 数据/代码 |
|---|---|---|
| 菜单权限 `menu:*` | 页面可见和模块进入 | roles/resources + 前端路由 |
| 元素权限 `element:*` | 创建、编辑、审核等动作 | `require_permission` |
| API 资源权限 | V1 接口访问 | `v1_api_access.py` |
| 资源权限 | Agent、Dataset、Knowledge 等对象 | `ai_agent_resource_permissions` |
| 数据权限 | 数据集表/列/行范围 | ChatBI 执行服务 |

当前模型适合“单组织内部 RBAC”，不等同于多租户。仓库没有统一 `tenant_id` 领域键，Agent 仅有 `created_by/owner_group`；租户级唯一约束、密钥、审计、配额和强制查询过滤均未建立。

## 5. 关键风险与整改

### P0/P1

- 浏览器登录响应返回完整长期 API Key，前端写入 localStorage；Cookie 固定 `secure=False`。证据：`auth.py:99-165`、`Login.vue:223-224`。
- 登出只删除 Redis 缓存，数据库 API Key 仍可立即重新认证。证据：`auth_service.py:242-249`。
- SSO 历史上曾禁用 TLS 校验；现已强制 HTTPS/TLS、固定解析、禁用环境代理/重定向，并将
  用户目录同步改为非阻塞异步调用。剩余风险是响应签名、防重放与真实证书失败联调。
- `/chat` 的 V1 白名单规则过宽，连带放行代码执行等子路由。证据：`v1_api_access.py:110-115`。
- Portal 审计 trace 只按 `trace_id` 查询，没有 owner/admin 校验。证据：`audit.py:194-269`。
- Agent active config 对任意登录用户返回 system prompt、tools、skills 和可能含密钥的 `engine_config`。证据：`agents.py:203-228`、`agent_manager.py:351-438`。

### 建议目标模型

```text
Browser login -> 15-60 分钟随机 session token -> HttpOnly/Secure/SameSite Cookie
API integration -> scoped API key -> hash-only storage -> expiry/revoke/rotation
Embed host -> one-time exchange -> short-lived audience-bound Embed token
```

- session 只保存哈希，支持设备、过期、续期、撤销和并发会话管理。
- API Key 仅创建时展示一次，之后不可逆存储；必须有 scope、expiry、last_used、rotation 和 revoke。
- 所有对象查询都接受服务端 `AuthContext(tenant_id, user_id, roles, scopes)`，repository 层强制租户过滤。
- 无权和不存在统一返回 404，降低对象枚举。
- 管理操作、凭据变更、权限变更进入不可抵赖审计；关键操作支持 MFA/二次确认。

## 6. 数据表

| 表 | 关键字段 | 说明 |
|---|---|---|
| `ai_agent_users` | user_name、api_key_hash、password_hash、status | 用户与当前长期凭据 |
| `ai_agent_roles` | code、name | 角色 |
| `ai_agent_user_role_relations` | user_id、role_id | 用户角色关系 |
| `ai_agent_resource_permissions` | user_id/role_id、resource_type/id | 对象级授权 |
| `ai_agent_quota_policies` | scope_type/id、period、limit_tokens | 用户/角色/系统额度 |

完整字段见 `appendix/database-model-inventory.md`。

## 7. 验收用例

- API Key 撤销后，缓存存在与否都必须立即 401。
- 普通用户无法读取其他用户 trace、Agent 私有配置、数据集或任务。
- 任意 `sessionid`、query/body 调试字段都不能改变服务端授权结果。
- Embed token 不能调用 Portal 管理 API，过期或错误 origin 必须失败。
- 租户 A 的任何 ID 放入租户 B 的 endpoint/body 都返回统一 404。
