import pytest
from plumbum import local
from plumbum.cmd import git

import copier
from copier.errors import UnsupportedVersionError

from .helpers import build_file_tree


@pytest.fixture(scope="module")
def template_path(tmp_path_factory) -> str:
    root = tmp_path_factory.mktemp("template")
    build_file_tree(
        {
            root
            / "copier.yaml": """\
                _min_copier_version: "10.5.1"
            """,
            root / "README.md": "",
        }
    )
    return str(root)


def test_version_less_than_required(template_path, tmp_path, monkeypatch):
    monkeypatch.setattr("copier.__version__", "0.0.0a0")
    with pytest.raises(UnsupportedVersionError):
        copier.copy(template_path, tmp_path)


def test_version_equal_required(template_path, monkeypatch):
    monkeypatch.setattr("copier.__version__", "10.5.1")
    # assert no error
    copier.copy(template_path)


def test_version_greater_than_required(template_path, monkeypatch):
    monkeypatch.setattr("copier.__version__", "99.99.99")
    # assert no error
    copier.copy(template_path)


def test_minimum_version_update(template_path, tmp_path, monkeypatch):
    monkeypatch.setattr("copier.__version__", "11.0.0")
    copier.copy(template_path, tmp_path)

    with local.cwd(tmp_path):
        git("init")
        git("config", "user.name", "Copier Test")
        git("config", "user.email", "test@copier")
        git("add", ".")
        git("commit", "-m", "hello world")

    monkeypatch.setattr("copier.__version__", "0.0.0.post0")
    with pytest.raises(UnsupportedVersionError):
        copier.copy(template_path, tmp_path)

    monkeypatch.setattr("copier.__version__", "10.5.1")
    # assert no error
    copier.copy(template_path, tmp_path)

    monkeypatch.setattr("copier.__version__", "99.99.99")
    # assert no error
    copier.copy(template_path, tmp_path)


def test_version_0_0_0_ignored(template_path, monkeypatch):
    monkeypatch.setattr("copier.__version__", "0.0.0")
    # assert no error
    copier.copy(template_path)
