-- V116: 注册 AI 执行高风险能力，默认不授予普通用户或角色

INSERT INTO ai_agent_resource_permissions
    (resource_type, resource_id, enabled, created_at, updated_at)
SELECT capabilities.resource_type,
       capabilities.resource_id,
       1,
       NOW(),
       NOW()
FROM (
    SELECT 'element' AS resource_type, 'element:chat:debug_prompt' AS resource_id
    UNION ALL
    SELECT 'element', 'element:chat:auto_approve_tools'
) AS capabilities
WHERE NOT EXISTS (
    SELECT 1
    FROM ai_agent_resource_permissions existing
    WHERE existing.resource_type = capabilities.resource_type
      AND existing.resource_id = capabilities.resource_id
);
