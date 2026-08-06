-- V111.1: create personal skill publication lineage and immutable versions.

CREATE TABLE IF NOT EXISTS skill_publications (
    id VARCHAR(36) NOT NULL PRIMARY KEY COMMENT '发布谱系 ID，UUID',
    platform_skill_id VARCHAR(128) NULL UNIQUE COMMENT '平台公共技能唯一 ID，首次审核通过时生成',
    source_user_id BIGINT NOT NULL COMMENT '原个人技能所属用户 ID',
    source_personal_skill_id VARCHAR(128) NOT NULL COMMENT '原个人技能 ID',
    name VARCHAR(255) NOT NULL COMMENT '平台技能名称快照',
    description TEXT NULL COMMENT '平台技能描述快照',
    current_version INT NULL COMMENT '当前已发布版本号',
    status VARCHAR(32) NOT NULL DEFAULT 'PENDING' COMMENT '发布谱系状态：PENDING 待首发、PUBLISHED 已发布、UNPUBLISHED 未发布、REVOKED 已下架',
    created_at DATETIME NOT NULL COMMENT '发布谱系创建时间',
    updated_at DATETIME NOT NULL COMMENT '发布谱系更新时间',
    revoked_at DATETIME NULL COMMENT '平台技能下架时间',
    revoked_by BIGINT NULL COMMENT '执行下架的用户 ID',
    CONSTRAINT fk_skill_publications_source_user
        FOREIGN KEY (source_user_id) REFERENCES ai_agent_users(id),
    CONSTRAINT fk_skill_publications_revoked_by
        FOREIGN KEY (revoked_by) REFERENCES ai_agent_users(id),
    INDEX idx_skill_publications_source (source_user_id, source_personal_skill_id),
    INDEX idx_skill_publications_status (status)
) COMMENT='个人技能发布到平台公共技能库的发布谱系';

CREATE TABLE IF NOT EXISTS skill_publication_versions (
    id VARCHAR(36) NOT NULL PRIMARY KEY COMMENT '发布版本 ID，UUID',
    publication_id VARCHAR(36) NOT NULL COMMENT '所属发布谱系 ID',
    version_number INT NOT NULL COMMENT '候选或发布版本号，从 1 开始递增',
    status VARCHAR(32) NOT NULL DEFAULT 'PENDING' COMMENT '版本状态：PENDING 待审核、APPROVED 已发布、REJECTED 已驳回、WITHDRAWN 提交者已撤销、SUPERSEDED 已被新版本替代',
    snapshot_path VARCHAR(1024) NOT NULL COMMENT '受控快照目录路径',
    content_sha256 CHAR(64) NOT NULL COMMENT '快照内容 SHA-256 指纹',
    file_count INT NOT NULL DEFAULT 0 COMMENT '快照文件数量',
    total_size BIGINT NOT NULL DEFAULT 0 COMMENT '快照总大小，单位字节',
    submitted_by BIGINT NOT NULL COMMENT '提交审核的用户 ID',
    submitted_at DATETIME NOT NULL COMMENT '提交审核时间',
    reviewed_by BIGINT NULL COMMENT '审核用户 ID',
    reviewed_at DATETIME NULL COMMENT '审核时间',
    review_comment TEXT NULL COMMENT '审核意见或驳回原因',
    published_at DATETIME NULL COMMENT '平台发布生效时间',
    materialized_path VARCHAR(1024) NULL COMMENT '平台技能活动目录路径',
    withdrawn_by BIGINT NULL COMMENT '撤销提交的用户 ID',
    withdrawn_at DATETIME NULL COMMENT '提交撤销时间',
    CONSTRAINT ux_skill_publication_version_number UNIQUE (publication_id, version_number),
    CONSTRAINT fk_skill_publication_versions_publication
        FOREIGN KEY (publication_id) REFERENCES skill_publications(id) ON DELETE CASCADE,
    CONSTRAINT fk_skill_publication_versions_submitted_by
        FOREIGN KEY (submitted_by) REFERENCES ai_agent_users(id),
    CONSTRAINT fk_skill_publication_versions_reviewed_by
        FOREIGN KEY (reviewed_by) REFERENCES ai_agent_users(id),
    CONSTRAINT fk_skill_publication_versions_withdrawn_by
        FOREIGN KEY (withdrawn_by) REFERENCES ai_agent_users(id),
    INDEX idx_skill_publication_versions_status (status),
    INDEX idx_skill_publication_versions_publication (publication_id, status)
) COMMENT='个人技能平台发布的候选与审核版本';
