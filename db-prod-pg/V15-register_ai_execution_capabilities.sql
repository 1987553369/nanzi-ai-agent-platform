-- V15: 注册 AI 执行高风险能力，默认不授予普通用户或角色

INSERT INTO "ai_agent_resource_permissions"
    ("resource_type", "resource_id", "enabled", "created_at", "updated_at")
SELECT values_to_insert.resource_type,
       values_to_insert.resource_id,
       TRUE,
       NOW(),
       NOW()
FROM (
    VALUES
        ('element', 'element:chat:debug_prompt'),
        ('element', 'element:chat:auto_approve_tools')
) AS values_to_insert(resource_type, resource_id)
WHERE NOT EXISTS (
    SELECT 1
    FROM "ai_agent_resource_permissions" existing
    WHERE existing."resource_type" = values_to_insert.resource_type
      AND existing."resource_id" = values_to_insert.resource_id
);
