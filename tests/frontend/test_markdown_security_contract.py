from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.no_infrastructure


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_shared_markdown_renderer_disables_raw_html_and_sanitizes_output():
    source = _source("frontend/src/utils/markdown.ts")

    assert source.count("html: false") == 2
    assert "html: true,\n" not in source
    assert "DOMPurify.sanitize" in source
    assert "FORBID_TAGS" in source
    assert "FORBID_ATTR: ['style']" in source
    assert "ALLOWED_URI_REGEXP" in source


def test_message_renderer_sanitizes_after_trusted_post_processing():
    source = _source("frontend/src/components/MessageRenderer.vue")

    assert "sanitizeMarkdownHtml(postProcessHtml(renderMarkdown(text)))" in source
    assert "protectCitationsInMarkdown" not in source


def test_skill_markdown_preview_uses_shared_safe_renderer():
    source = _source("frontend/src/views/SkillsManagement.vue")

    assert "renderMarkdownPreview" in source
    assert "new MarkdownIt" not in source
    assert "html: true" not in source


def test_dompurify_is_a_direct_runtime_dependency():
    package_json = _source("frontend/package.json")
    package_lock = _source("frontend/package-lock.json")

    assert '"dompurify": "^3.3.1"' in package_json
    assert '"dompurify": "^3.3.1"' in package_lock
