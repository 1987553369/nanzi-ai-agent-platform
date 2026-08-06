from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.no_infrastructure


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_sso_clients_never_disable_tls_certificate_verification():
    sources = "\n".join(
        _source(path)
        for path in (
            "app/services/auth_service.py",
            "app/services/sso_user.py",
        )
    )

    assert "verify=False" not in sources
    assert sources.count("verify=True") >= 2


def test_cors_middleware_uses_explicit_configured_origins():
    source = _source("app/main.py")

    assert "allow_origins=settings.ALLOWED_ORIGINS" in source
    assert 'else ["*"]' not in source
