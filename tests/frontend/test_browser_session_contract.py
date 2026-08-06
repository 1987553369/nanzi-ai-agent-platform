from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_login_does_not_persist_returned_api_key():
    source = _source("frontend/src/views/Login.vue")

    assert "userData.api_key" not in source
    assert "localStorage.setItem('api_key'" not in source


def test_shared_client_does_not_send_local_storage_api_key():
    source = _source("frontend/src/utils/axios.ts")

    assert "localStorage.getItem('api_key')" not in source


def test_frontend_does_not_read_or_write_long_lived_api_key_storage():
    frontend_root = ROOT / "frontend/src"
    sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in frontend_root.rglob("*")
        if path.suffix in {".ts", ".vue"}
    )

    assert "localStorage.getItem('api_key')" not in sources
    assert 'localStorage.getItem("api_key")' not in sources
    assert "localStorage.setItem('api_key'" not in sources
    assert 'localStorage.setItem("api_key"' not in sources


def test_backend_login_response_does_not_return_api_key():
    source = _source("app/api/portal/endpoints/auth.py")

    assert '"api_key": api_key' not in source
    assert "BrowserSessionService.create" in source
    assert "httponly=True" in source
    assert "secure=settings.API_SERVICE_ENV" in source
