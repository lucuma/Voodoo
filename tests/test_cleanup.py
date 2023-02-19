from pathlib import Path
from subprocess import CalledProcessError

import pytest

import copier


def test_cleanup(tmp_path: Path) -> None:
    """Copier creates dst_path, fails to copy and removes it."""
    dst = tmp_path / "new_folder"
    with pytest.raises(CalledProcessError):
        copier.copy(str(Path("tests", "demo_cleanup")), dst, quiet=True)
    assert not dst.exists()


def test_do_not_cleanup(tmp_path: Path) -> None:
    """Copier creates dst_path, fails to copy and keeps it."""
    dst = tmp_path / "new_folder"
    with pytest.raises(CalledProcessError):
        copier.copy(
            str(Path("tests", "demo_cleanup")), dst, quiet=True, cleanup_on_error=False
        )
    assert dst.exists()


def test_no_cleanup_when_folder_existed(tmp_path: Path) -> None:
    """Copier will not delete a folder if it didn't create it."""
    preexisting_file = tmp_path / "something"
    preexisting_file.touch()
    with pytest.raises(CalledProcessError):
        copier.copy(
            str(Path("tests", "demo_cleanup")),
            tmp_path,
            quiet=True,
            cleanup_on_error=True,
        )
    assert tmp_path.exists()
    assert preexisting_file.exists()
