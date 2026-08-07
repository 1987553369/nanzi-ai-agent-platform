-- V17: 隔离外部数据源存量明文密码，等待应用层离线命令加密。

ALTER TABLE "meta_db_connection_configs"
    ALTER COLUMN "password" DROP NOT NULL,
    ALTER COLUMN "password" TYPE TEXT,
    ADD COLUMN "password_status" VARCHAR(32) NOT NULL DEFAULT 'empty',
    ADD COLUMN "password_migration_error" VARCHAR(500) NULL,
    ADD COLUMN "password_migrated_at" TIMESTAMP NULL,
    ADD CONSTRAINT "ck_meta_db_connection_password_status"
        CHECK ("password_status" IN (
            'empty', 'encrypted', 'migration_pending', 'rotation_required'
        ));

COMMENT ON COLUMN "meta_db_connection_configs"."password"
    IS '数据库密码版本化密文，不得保存明文';
COMMENT ON COLUMN "meta_db_connection_configs"."password_status"
    IS '凭据状态：empty/encrypted/migration_pending/rotation_required';
COMMENT ON COLUMN "meta_db_connection_configs"."password_migration_error"
    IS '不含密码内容的迁移失败原因';
COMMENT ON COLUMN "meta_db_connection_configs"."password_migrated_at"
    IS '密码完成加密或人工轮换的时间';

UPDATE "meta_db_connection_configs"
SET "password_status" = CASE
        WHEN "password" IS NULL OR "password" = '' THEN 'empty'
        WHEN "password" LIKE 'dbpassword:v1:%' THEN 'encrypted'
        ELSE 'migration_pending'
    END,
    "password_migration_error" = NULL,
    "password_migrated_at" = CASE
        WHEN "password" IS NULL OR "password" = ''
             OR "password" LIKE 'dbpassword:v1:%'
        THEN CURRENT_TIMESTAMP
        ELSE NULL
    END;
