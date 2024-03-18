import os
import shutil
from pathlib import Path
from typing import Callable, Iterator, Sequence

import pytest
import yaml
from packaging.version import Version
from plumbum import local
from plumbum.cmd import git

from copier import Worker, run_copy, run_update
from copier.errors import ShallowCloneWarning
from copier.vcs import checkout_latest_tag, clone, get_git_version, get_repo


def test_get_repo() -> None:
    get = get_repo

    assert get("git@git.myproject.org:MyProject") == "git@git.myproject.org:MyProject"
    assert (
        get("git://git.myproject.org/MyProject") == "git://git.myproject.org/MyProject"
    )
    assert (
        get("https://github.com/jpscaletti/copier.git")
        == "https://github.com/jpscaletti/copier.git"
    )

    assert (
        get("https://github.com/jpscaletti/copier")
        == "https://github.com/jpscaletti/copier.git"
    )
    assert (
        get("https://gitlab.com/gitlab-org/gitlab")
        == "https://gitlab.com/gitlab-org/gitlab.git"
    )

    assert (
        get("gh:/jpscaletti/copier.git") == "https://github.com/jpscaletti/copier.git"
    )
    assert get("gh:jpscaletti/copier.git") == "https://github.com/jpscaletti/copier.git"
    assert get("gl:jpscaletti/copier.git") == "https://gitlab.com/jpscaletti/copier.git"
    assert get("gh:jpscaletti/copier") == "https://github.com/jpscaletti/copier.git"
    assert get("gl:jpscaletti/copier") == "https://gitlab.com/jpscaletti/copier.git"

    assert (
        get("git+https://git.myproject.org/MyProject")
        == "https://git.myproject.org/MyProject"
    )
    assert (
        get("git+ssh://git.myproject.org/MyProject")
        == "ssh://git.myproject.org/MyProject"
    )

    assert get("git://git.myproject.org/MyProject.git@master")
    assert get("git://git.myproject.org/MyProject.git@v1.0")
    assert get("git://git.myproject.org/MyProject.git@da39a3ee5e6b4b0d3255bfef956018")

    assert get("http://google.com") is None
    assert get("git.myproject.org/MyProject") is None
    assert get("https://google.com") is None

    assert (
        get("tests/demo_updatediff_repo.bundle") == "tests/demo_updatediff_repo.bundle"
    )


@pytest.mark.impure
def test_clone() -> None:
    tmp = clone("https://github.com/copier-org/copier.git")
    assert tmp
    assert Path(tmp, "README.md").exists()
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.mark.impure
def test_local_clone() -> None:
    tmp = clone("https://github.com/copier-org/copier.git")
    assert tmp
    assert Path(tmp, "README.md").exists()

    local_tmp = clone(tmp)
    assert local_tmp
    assert Path(local_tmp, "README.md").exists()
    shutil.rmtree(local_tmp, ignore_errors=True)


@pytest.mark.impure
def test_shallow_clone(tmp_path: Path, recwarn: pytest.WarningsRecorder) -> None:
    # This test should always work but should be much slower if `is_git_shallow_repo()`
    # is not checked in `clone()`.
    src_path = str(tmp_path / "autopretty")
    git("clone", "--depth=2", "https://github.com/copier-org/autopretty.git", src_path)
    assert Path(src_path, "README.md").exists()

    if get_git_version() >= Version("2.27"):
        with pytest.warns(ShallowCloneWarning):
            local_tmp = clone(str(src_path))
    else:
        assert len(recwarn) == 0
        local_tmp = clone(str(src_path))
        assert len(recwarn) == 0
    assert local_tmp
    assert Path(local_tmp, "README.md").exists()
    shutil.rmtree(local_tmp, ignore_errors=True)


@pytest.mark.impure
def test_removes_temporary_clone(tmp_path: Path) -> None:
    src_path = "https://github.com/copier-org/autopretty.git"
    with Worker(
        src_path=src_path, dst_path=tmp_path, defaults=True, unsafe=True
    ) as worker:
        worker.run_copy()
        temp_clone = worker.template.local_abspath
    assert not temp_clone.exists()


@pytest.mark.impure
def test_dont_remove_local_clone(tmp_path: Path) -> None:
    src_path = str(tmp_path / "autopretty")
    git("clone", "https://github.com/copier-org/autopretty.git", src_path)
    with Worker(
        src_path=src_path, dst_path=tmp_path, defaults=True, unsafe=True
    ) as worker:
        worker.run_copy()
    assert Path(src_path).exists()


@pytest.mark.impure
def test_update_using_local_source_path_with_tilde(tmp_path: Path) -> None:
    # first, get a local repository clone
    src_path = str(tmp_path / "autopretty")
    git("clone", "https://github.com/copier-org/autopretty.git", src_path)

    # then prepare the user path to this clone (starting with ~)
    if os.name == "nt":
        # in GitHub CI, the user in the temporary path is not the same as the current
        # user: ["C:\\", "Users", "RUNNER~X"] vs. runneradmin
        user = Path(src_path).parts[2]
        user_src_path = str(Path("~", "..", user, *Path(src_path).parts[3:]))
    else:
        # temporary path is in /tmp, so climb back up from ~ using ../
        user_src_path = f"~/{'/'.join(['..'] * len(Path.home().parts))}{src_path}"

    # generate project and assert correct path in answers
    worker = run_copy(
        src_path=user_src_path, dst_path=tmp_path, defaults=True, unsafe=True
    )
    assert worker.answers.combined["_src_path"] == user_src_path

    # assert project update works and correct path again
    with local.cwd(tmp_path):
        git("init")
        git("add", "-A")
        git("commit", "-m", "init")
    worker = run_update(
        dst_path=tmp_path,
        defaults=True,
        overwrite=True,
        answers_file=".copier-answers.autopretty.yml",
        unsafe=True,
    )
    assert worker.answers.combined["_src_path"] == user_src_path


def test_invalid_version(tmp_path: Path) -> None:
    sample = tmp_path / "sample.txt"
    with local.cwd(tmp_path):
        git("init")
        sample.write_text("1")
        git("add", sample)
        git("commit", "-m1")
        git("tag", "not-a-version")
        sample.write_text("2")
        git("commit", "-am2")
        git("tag", "v2")
        sample.write_text("3")
        git("commit", "-am3")
        assert git("describe", "--tags").strip() != "v2"
        checkout_latest_tag(tmp_path)
        assert git("describe", "--tags").strip() == "v2"


@pytest.mark.parametrize("sorter", [iter, reversed])
def test_select_latest_version_tag(
    tmp_path_factory: pytest.TempPathFactory,
    sorter: Callable[[Sequence[str]], Iterator[str]],
) -> None:
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))
    filename = "version.txt"

    with local.cwd(src):
        git("init")
        Path("{{ _copier_conf.answers_file }}.jinja").write_text(
            "{{ _copier_answers|to_nice_yaml }}"
        )
        for version in sorter(["v1", "v1.0", "v1.0.0", "v1.0.1"]):
            Path(filename).write_text(version)
            git("add", ".")
            git("commit", "-m", version)
            git("tag", version)

    run_copy(str(src), dst)

    assert (dst / filename).is_file()
    assert (dst / filename).read_text() == "v1.0.1"
    answers = yaml.safe_load((dst / ".copier-answers.yml").read_text())
    assert answers["_commit"] == "v1.0.1"
