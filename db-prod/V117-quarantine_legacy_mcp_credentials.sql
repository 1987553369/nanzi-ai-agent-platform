-- V117: 隔离存量 MCP 明文认证 Header，等待应用层安全迁移命令加密。

ALTER TABLE sys_mcp_servers
    MODIFY COLUMN auth_headers TEXT NULL
        COMMENT 'MCP 认证 Header 版本化密文，不得保存明文 JSON',
    ADD COLUMN auth_headers_status VARCHAR(32) NOT NULL DEFAULT 'empty'
        COMMENT 'empty/encrypted/migration_pending/rotation_required'
        AFTER auth_headers,
    ADD COLUMN auth_headers_restore_enabled_status TINYINT NULL
        COMMENT '凭据迁移成功后恢复的启用状态'
        AFTER auth_headers_status,
    ADD COLUMN auth_headers_migration_error VARCHAR(500) NULL
        COMMENT '不含凭据内容的迁移失败原因'
        AFTER auth_headers_restore_enabled_status,
    ADD COLUMN auth_headers_migrated_at DATETIME NULL
        COMMENT '凭据完成加密或人工轮换的时间'
        AFTER auth_headers_migration_error,
    ADD CONSTRAINT ck_sys_mcp_servers_auth_headers_status
        CHECK (auth_headers_status IN (
            'empty', 'encrypted', 'migration_pending', 'rotation_required'
        ));

UPDATE sys_mcp_servers
SET auth_headers_status = CASE
        WHEN auth_headers IS NULL OR TRIM(auth_headers) = '' THEN 'empty'
        WHEN auth_headers LIKE 'mcpheaders:v1:%' THEN 'encrypted'
        ELSE 'migration_pending'
    END,
    auth_headers_restore_enabled_status = CASE
        WHEN auth_headers IS NOT NULL
             AND TRIM(auth_headers) <> ''
             AND auth_headers NOT LIKE 'mcpheaders:v1:%'
        THEN enabled_status
        ELSE NULL
    END,
    enabled_status = CASE
        WHEN auth_headers IS NOT NULL
             AND TRIM(auth_headers) <> ''
             AND auth_headers NOT LIKE 'mcpheaders:v1:%'
        THEN 0
        ELSE enabled_status
    END,
    auth_headers_migration_error = NULL,
    auth_headers_migrated_at = CASE
        WHEN auth_headers IS NULL OR TRIM(auth_headers) = ''
             OR auth_headers LIKE 'mcpheaders:v1:%'
        THEN NOW()
        ELSE NULL
    END;
