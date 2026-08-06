from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.no_infrastructure


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_embed_protocol_requires_source_origin_version_and_nonce():
    protocol = _source("frontend/src/utils/embedProtocol.ts")

    assert "event.source === expectedSource" in protocol
    assert "event.origin === expectedOrigin" in protocol
    assert "data.protocol_version === EMBED_PROTOCOL_VERSION" in protocol
    assert "data.handshake_nonce === handshakeNonce" in protocol
    assert "crypto.getRandomValues" in protocol


def test_portal_and_widget_use_exact_target_origin_without_forwarding_api_key():
    portal = _source("frontend/src/views/Chat.vue")
    widget = _source("frontend/src/views/EmbedChat.vue")

    assert "isTrustedEmbedMessage" in portal
    assert "isTrustedEmbedMessage" in widget
    assert "embedTargetOrigin" in portal
    assert "trustedHostOrigin" in widget
    assert "localStorage.getItem('api_key')" not in portal
    assert "token: apiKey" not in portal
    assert "'*'" not in portal
    assert '"*"' not in widget


def test_widget_debugger_and_guide_do_not_publish_wildcard_examples():
    debugger = _source("frontend/src/views/WidgetDebugger.vue")
    guide = _source("docs/md/embed_integration_guide.md")

    assert "event.source !== frame.contentWindow" in debugger
    assert "event.origin !== targetOrigin" in debugger
    assert "SHORT_LIVED_EMBED_TOKEN" in debugger
    assert "}, '*')" not in debugger
    assert "}, '*');" not in guide
    assert "event.source !== widgetFrame.contentWindow" in guide
    assert "event.origin !== targetOrigin" in guide
    assert "短期" in guide
    assert "长期 API Key 写入 iframe URL" in guide
