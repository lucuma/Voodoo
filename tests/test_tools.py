from pathlib import Path
from stat import S_IREAD
from tempfile import TemporaryDirectory

import pytest
from plumbum.cmd import git
from poethepoet.app import PoeThePoet

from copier.tools import normalize_git_path


def test_types() -> None:
    """Ensure source code static typing."""
    result = PoeThePoet(Path("."))(["types"])
    assert result == 0


def test_temporary_directory_with_readonly_files_deletion() -> None:
    """Ensure temporary directories containing read-only files are properly deleted, whatever the OS."""  # noqa: E501
    with TemporaryDirectory() as tmp_dir:
        ro_file = Path(tmp_dir) / "readonly.txt"
        with ro_file.open("w") as fp:
            fp.write("don't touch me!")
        ro_file.chmod(S_IREAD)
    assert not Path(tmp_dir).exists()


def test_temporary_directory_with_git_repo_deletion() -> None:
    """Ensure temporary directories containing git repositories are properly deleted, whatever the OS."""  # noqa: E501
    with TemporaryDirectory() as tmp_dir:
        git("init")
    assert not Path(tmp_dir).exists()


@pytest.mark.parametrize(
    ("path", "normalized"),
    [
        ("readme.md", "readme.md"),
        ('quo\\"tes', 'quo"tes'),
        ('"surrounded"', "surrounded"),
        ("m4\\303\\2424\\303\\2614a", "m4â4ñ4a"),
    ],
)
def test_normalizing_git_paths(path: str, normalized: str) -> None:
    assert normalize_git_path(path) == normalized
