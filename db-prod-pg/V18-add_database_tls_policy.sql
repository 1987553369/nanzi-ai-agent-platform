-- V18: 为外部数据源增加显式 TLS 策略；存量 SQL Server 保持强制身份校验，其余类型显式标记未启用。

ALTER TABLE "meta_db_connection_configs"
    ADD COLUMN "tls_mode" VARCHAR(32) NOT NULL DEFAULT 'disabled',
    ADD COLUMN "tls_ca_path" VARCHAR(500) NULL,
    ADD CONSTRAINT "ck_meta_db_connection_tls_mode"
        CHECK ("tls_mode" IN ('disabled', 'verify_ca', 'verify_identity'));

COMMENT ON COLUMN "meta_db_connection_configs"."tls_mode"
    IS '传输加密模式：disabled/verify_ca/verify_identity';
COMMENT ON COLUMN "meta_db_connection_configs"."tls_ca_path"
    IS 'DATA_SOURCE_TLS_CA_DIR 下的 CA 相对路径';

UPDATE "meta_db_connection_configs"
SET "tls_mode" = CASE
        WHEN LOWER("db_type") IN ('sqlserver', 'mssql', 'tsql') THEN 'verify_identity'
        ELSE 'disabled'
    END,
    "tls_ca_path" = NULL;

ALTER TABLE "meta_db_connection_configs"
    ADD CONSTRAINT "ck_meta_db_connection_tls_policy"
        CHECK (
            (LOWER("db_type") IN ('sqlserver', 'mssql', 'tsql')
             AND "tls_mode" = 'verify_identity' AND "tls_ca_path" IS NULL)
            OR
            (LOWER("db_type") IN ('postgres', 'postgresql', 'pg') AND (
                ("tls_mode" = 'disabled' AND "tls_ca_path" IS NULL)
                OR ("tls_mode" IN ('verify_ca', 'verify_identity')
                    AND "tls_ca_path" IS NOT NULL AND "tls_ca_path" <> '')
            ))
            OR
            (LOWER("db_type") IN ('mysql', 'clickhouse', 'oracle') AND (
                ("tls_mode" = 'disabled' AND "tls_ca_path" IS NULL)
                OR ("tls_mode" = 'verify_ca'
                    AND "tls_ca_path" IS NOT NULL AND "tls_ca_path" <> '')
            ))
        );
