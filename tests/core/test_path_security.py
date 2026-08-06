from pathlib import Path

import pytest

from app.utils.path_security import resolve_contained_file


pytestmark = pytest.mark.no_infrastructure


def test_resolve_contained_file_allows_regular_file(tmp_path: Path):
    root = tmp_path / "dist"
    root.mkdir()
    asset = root / "favicon.ico"
    asset.write_text("icon", encoding="utf-8")

    assert resolve_contained_file(root, "favicon.ico") == asset.resolve()


@pytest.mark.parametrize(
    "requested_path",
    ["../secret.env", "nested/../../secret.env", "/etc/passwd"],
)
def test_resolve_contained_file_rejects_path_escape(tmp_path: Path, requested_path: str):
    root = tmp_path / "dist"
    root.mkdir()
    (tmp_path / "secret.env").write_text("secret", encoding="utf-8")

    assert resolve_contained_file(root, requested_path) is None


def test_resolve_contained_file_rejects_symlink_escape(tmp_path: Path):
    root = tmp_path / "dist"
    root.mkdir()
    secret = tmp_path / "secret.env"
    secret.write_text("secret", encoding="utf-8")
    link = root / "secret-link"
    try:
        link.symlink_to(secret)
    except (OSError, NotImplementedError):
        pytest.skip("当前文件系统不支持符号链接")

    assert resolve_contained_file(root, "secret-link") is None
