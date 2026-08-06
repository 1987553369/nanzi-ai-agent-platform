"""Contract: 项目会话门户横幅与技能 scope 增删一致性。"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EMBED = ROOT / "frontend" / "src" / "views" / "EmbedChat.vue"


def test_portal_banners_use_matching_resource_scope_flags():
    source = EMBED.read_text(encoding="utf-8")
    knowledge_block = source.split("<KnowledgePortalDrawer", 1)[1].split("/>", 1)[0]
    dataset_block = source.split("<DatasetPortalDrawer", 1)[1].split("/>", 1)[0]
    assert "projectSessionHasKnowledgeScope" in knowledge_block
    assert "已挂载的知识库" in knowledge_block
    assert "projectSessionHasDatasetScope" not in knowledge_block
    assert "projectSessionHasDatasetScope" in dataset_block
    assert "已挂载的数据集" in dataset_block
    assert "projectSessionHasKnowledgeScope" not in dataset_block


def test_skill_scope_is_used_for_keys_and_removal():
    source = EMBED.read_text(encoding="utf-8")
    assert "resourceScopeEntryKey" in source
    assert "resourceScopeEntriesMatch" in source
    assert "key: resourceScopeEntryKey(type, item, index)" in source
    assert "type ResourceScopeGroupKey" in (
        ROOT / "frontend" / "src" / "types" / "resourceScope.ts"
    ).read_text(encoding="utf-8")
    assert "resourceScopeEntriesMatch(entry, item)" in source
    assert "...(item.scope ? { scope: item.scope } : {})" in source
    assert "scope }" in source or "scope: item.scope" in source
