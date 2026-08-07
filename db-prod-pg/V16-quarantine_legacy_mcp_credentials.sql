-- V16: 隔离存量 MCP 明文认证 Header，等待应用层安全迁移命令加密。

ALTER TABLE "sys_mcp_servers"
    ADD COLUMN "auth_headers_status" VARCHAR(32) NOT NULL DEFAULT 'empty',
    ADD COLUMN "auth_headers_restore_enabled_status" SMALLINT NULL,
    ADD COLUMN "auth_headers_migration_error" VARCHAR(500) NULL,
    ADD COLUMN "auth_headers_migrated_at" TIMESTAMP NULL,
    ADD CONSTRAINT "ck_sys_mcp_servers_auth_headers_status"
        CHECK ("auth_headers_status" IN (
            'empty', 'encrypted', 'migration_pending', 'rotation_required'
        ));

COMMENT ON COLUMN "sys_mcp_servers"."auth_headers"
    IS 'MCP 认证 Header 版本化密文，不得保存明文 JSON';
COMMENT ON COLUMN "sys_mcp_servers"."auth_headers_status"
    IS '凭据状态：empty/encrypted/migration_pending/rotation_required';
COMMENT ON COLUMN "sys_mcp_servers"."auth_headers_restore_enabled_status"
    IS '凭据迁移成功后恢复的启用状态';
COMMENT ON COLUMN "sys_mcp_servers"."auth_headers_migration_error"
    IS '不含凭据内容的迁移失败原因';
COMMENT ON COLUMN "sys_mcp_servers"."auth_headers_migrated_at"
    IS '凭据完成加密或人工轮换的时间';

UPDATE "sys_mcp_servers"
SET "auth_headers_status" = CASE
        WHEN "auth_headers" IS NULL OR BTRIM("auth_headers") = '' THEN 'empty'
        WHEN "auth_headers" LIKE 'mcpheaders:v1:%' THEN 'encrypted'
        ELSE 'migration_pending'
    END,
    "auth_headers_restore_enabled_status" = CASE
        WHEN "auth_headers" IS NOT NULL
             AND BTRIM("auth_headers") <> ''
             AND "auth_headers" NOT LIKE 'mcpheaders:v1:%'
        THEN "enabled_status"
        ELSE NULL
    END,
    "enabled_status" = CASE
        WHEN "auth_headers" IS NOT NULL
             AND BTRIM("auth_headers") <> ''
             AND "auth_headers" NOT LIKE 'mcpheaders:v1:%'
        THEN 0
        ELSE "enabled_status"
    END,
    "auth_headers_migration_error" = NULL,
    "auth_headers_migrated_at" = CASE
        WHEN "auth_headers" IS NULL OR BTRIM("auth_headers") = ''
             OR "auth_headers" LIKE 'mcpheaders:v1:%'
        THEN CURRENT_TIMESTAMP
        ELSE NULL
    END;
