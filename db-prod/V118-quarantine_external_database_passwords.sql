-- V118: 隔离外部数据源存量明文密码，等待应用层离线命令加密。

ALTER TABLE meta_db_connection_configs
    MODIFY COLUMN password TEXT NULL
        COMMENT '数据库密码版本化密文，不得保存明文',
    ADD COLUMN password_status VARCHAR(32) NOT NULL DEFAULT 'empty'
        COMMENT 'empty/encrypted/migration_pending/rotation_required'
        AFTER password,
    ADD COLUMN password_migration_error VARCHAR(500) NULL
        COMMENT '不含密码内容的迁移失败原因'
        AFTER password_status,
    ADD COLUMN password_migrated_at DATETIME NULL
        COMMENT '密码完成加密或人工轮换的时间'
        AFTER password_migration_error,
    ADD CONSTRAINT ck_meta_db_connection_password_status
        CHECK (password_status IN (
            'empty', 'encrypted', 'migration_pending', 'rotation_required'
        ));

UPDATE meta_db_connection_configs
SET password_status = CASE
        WHEN password IS NULL OR password = '' THEN 'empty'
        WHEN password LIKE 'dbpassword:v1:%' THEN 'encrypted'
        ELSE 'migration_pending'
    END,
    password_migration_error = NULL,
    password_migrated_at = CASE
        WHEN password IS NULL OR password = ''
             OR password LIKE 'dbpassword:v1:%'
        THEN NOW()
        ELSE NULL
    END;
