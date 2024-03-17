from pathlib import Path
from shutil import copy2, copytree

import pytest
from plumbum import local
from plumbum.cmd import git
from pytest_gitconfig import GitConfig

import copier
from copier.errors import DirtyLocalWarning
from copier.main import run_copy, run_update

from .helpers import DATA, PROJECT_TEMPLATE, build_file_tree


def test_copy(tmp_path_factory: pytest.TempPathFactory) -> None:
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))

    for item in PROJECT_TEMPLATE.iterdir():
        item_src_path = item
        item_dst_path = src / item.name
        if item_src_path.is_dir():
            copytree(item_src_path, item_dst_path)
        else:
            copy2(item_src_path, item_dst_path)

    with local.cwd(src):
        git("init")

    with pytest.warns(DirtyLocalWarning):
        copier.run_copy(str(src), dst, data=DATA, vcs_ref="HEAD", quiet=True)

    generated = (dst / "pyproject.toml").read_text()
    control = (Path(__file__).parent / "reference_files" / "pyproject.toml").read_text()
    assert generated == control

    # assert template still dirty
    with local.cwd(src):
        assert bool(git("status", "--porcelain").strip())


def test_copy_dirty_head(tmp_path_factory: pytest.TempPathFactory) -> None:
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))
    build_file_tree({
        src / "tracked": "",
        src / "untracked": "",
    })
    with local.cwd(src):
        git("init")
        git("add", "tracked")
        git("commit", "-m1")
    with pytest.warns(DirtyLocalWarning):
        copier.run_copy(str(src), dst, vcs_ref="HEAD")
    assert (dst / "tracked").exists()
    assert (dst / "untracked").exists()


def test_copy_dirty_head_with_gpg(
    tmp_path_factory: pytest.TempPathFactory, gitconfig: GitConfig
) -> None:
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))
    build_file_tree({
        src / "tracked": "",
        src / "untracked": "",
    })
    with local.cwd(src):
        git("init")
        git("add", "tracked")
        git("commit", "-m1")
    gitconfig.set({"user.signinkey": "123456", "commit.gpgsign": "true"})

    with pytest.warns(DirtyLocalWarning):
        copier.run_copy(str(src), dst, vcs_ref="HEAD")

    assert (dst / "tracked").exists()
    assert (dst / "untracked").exists()


def test_update(tmp_path_factory: pytest.TempPathFactory) -> None:
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))

    build_file_tree({
        (src / ".copier-answers.yml.jinja"): (
            """\
                # Changes here will be overwritten by Copier
                {{ _copier_answers|to_nice_yaml }}
                """
        ),
        (src / "copier.yml"): (
            """\
                _envops:
                    "keep_trailing_newline": True
                """
        ),
        (src / "aaaa.txt"): (
            """
                Lorem ipsum
                """
        ),
        (src / "to_delete.txt"): (
            """
                delete me.
                """
        ),
        (src / "symlink.txt"): Path("./to_delete.txt"),
    })

    with local.cwd(src):
        git("init")
        git("add", "-A")
        git("commit", "-m", "first commit on src")

    run_copy(str(src), dst, defaults=True, overwrite=True)

    with local.cwd(src):
        # test adding a file
        Path("test_file.txt").write_text("Test content")

        # test updating a file
        with open("aaaa.txt", "a") as f:
            f.write("dolor sit amet")

        # test updating a symlink
        Path("symlink.txt").unlink()
        Path("symlink.txt").symlink_to("test_file.txt")

        # test removing a file
        Path("to_delete.txt").unlink()

    # dst must be vcs-tracked to use run_update
    with local.cwd(dst):
        git("init")
        git("add", "-A")
        git("commit", "-m", "first commit on dst")

    # make sure changes have not yet propagated
    assert not (dst / "test_file.txt").exists()

    assert (src / "aaaa.txt").read_text() != (dst / "aaaa.txt").read_text()

    p1 = src / "symlink.txt"
    p2 = dst / "symlink.txt"
    assert p1.read_text() != p2.read_text()

    assert (dst / "to_delete.txt").exists()

    with pytest.warns(DirtyLocalWarning):
        run_update(dst, defaults=True, overwrite=True)

    # make sure changes propagate after update
    assert (dst / "test_file.txt").exists()

    assert (src / "aaaa.txt").read_text() == (dst / "aaaa.txt").read_text()

    p1 = src / "symlink.txt"
    p2 = dst / "symlink.txt"
    assert p1.read_text() == p2.read_text()
    assert not (dst / "symlink.txt").is_symlink()

    # HACK https://github.com/copier-org/copier/issues/461
    # TODO test file deletion on update
    # assert not (dst / "to_delete.txt").exists()


def test_update_with_gpg_sign(
    tmp_path_factory: pytest.TempPathFactory, gitconfig: GitConfig
) -> None:
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))

    build_file_tree({
        (src / ".copier-answers.yml.jinja"): (
            """\
                # Changes here will be overwritten by Copier
                {{ _copier_answers|to_nice_yaml }}
                """
        ),
        (src / "copier.yml"): (
            """\
                _envops:
                    "keep_trailing_newline": True
                """
        ),
        (src / "aaaa.txt"): (
            """
                Lorem ipsum
                """
        ),
    })

    with local.cwd(src):
        git("init")
        git("add", "-A")
        git("commit", "-m", "first commit on src")

    run_copy(str(src), dst, defaults=True, overwrite=True)

    with local.cwd(src):
        Path("test_file.txt").write_text("Test content")
        Path("aaaa.txt").write_text("dolor sit amet")

    # dst must be vcs-tracked to use run_update
    with local.cwd(dst):
        git("init")
        git("add", "-A")
        git("commit", "-m", "first commit on dst")

    gitconfig.set({"user.signinkey": "123456", "commit.gpgsign": "true"})
    with pytest.warns(DirtyLocalWarning):
        run_update(dst, defaults=True, overwrite=True)
