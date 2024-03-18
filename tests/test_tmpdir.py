from pathlib import Path

import pytest
from plumbum.cmd import git

from copier.cli import CopierApp
from copier.main import run_copy, run_recopy, run_update

from .helpers import build_file_tree


@pytest.fixture(scope="module")
def template_path(tmp_path_factory: pytest.TempPathFactory) -> str:
    # V1 of the template
    root = tmp_path_factory.mktemp("template")
    build_file_tree({
        root / "copier.yml": "favorite_app: Copier",
        root / "fav.txt.jinja": "{{ favorite_app }}",
        root
        / "{{ _copier_conf.answers_file }}.jinja": "{{ _copier_answers|to_nice_yaml }}",
    })
    _git = git["-C", root]
    _git("init")
    _git("add", "-A")
    _git("commit", "-m", "Initial commit")
    _git("tag", "v1")
    # V2 of the template
    build_file_tree({root / "v2": "true"})
    _git("add", "-A")
    _git("commit", "-m", "Second commit")
    _git("tag", "v2")
    return str(root)


def empty_dir(dir: Path) -> None:
    assert dir.is_dir()
    assert dir.exists()
    assert len(list(dir.iterdir())) == 0


def test_api(
    template_path: str,
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
):
    tmp, dst = map(tmp_path_factory.mktemp, ["tmp", "dst"])
    _git = git["-C", dst]
    # Mock tmp dir to assert it ends up clean
    monkeypatch.setattr("tempfile.tempdir", str(tmp))
    # Copy
    run_copy(template_path, dst, vcs_ref="v1", quiet=True, defaults=True)
    assert (dst / "fav.txt").read_text() == "Copier"
    assert not (dst / "v2").exists()
    _git("init")
    _git("add", "-A")
    _git("commit", "-m", "Initial commit")
    empty_dir(tmp)
    # Recopy
    run_recopy(dst, vcs_ref="v1", quiet=True, defaults=True)
    assert (dst / "fav.txt").read_text() == "Copier"
    assert not (dst / "v2").exists()
    empty_dir(tmp)
    # Update
    run_update(dst, quiet=True, defaults=True, overwrite=True)
    assert (dst / "fav.txt").read_text() == "Copier"
    assert (dst / "v2").read_text() == "true"
    empty_dir(tmp)


def test_cli(
    template_path: str,
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
):
    tmp, dst = map(tmp_path_factory.mktemp, ["tmp", "dst"])
    _git = git["-C", dst]
    # Mock tmp dir to assert it ends up clean
    monkeypatch.setattr("tempfile.tempdir", str(tmp))
    # Copy
    run_result = CopierApp.run(
        [
            "copier",
            "copy",
            "-fqrv1",
            template_path,
            str(dst),
        ],
        exit=False,
    )
    assert run_result[1] == 0
    assert (dst / "fav.txt").read_text() == "Copier"
    assert not (dst / "v2").exists()
    empty_dir(tmp)
    _git("init")
    _git("add", "-A")
    _git("commit", "-m", "Initial commit")
    # Recopy
    run_result = CopierApp.run(["copier", "recopy", "-fqrv1", str(dst)], exit=False)
    assert run_result[1] == 0
    assert (dst / "fav.txt").read_text() == "Copier"
    assert not (dst / "v2").exists()
    empty_dir(tmp)
    # Update
    run_result = CopierApp.run(["copier", "update", "-fq", str(dst)], exit=False)
    assert run_result[1] == 0
    assert (dst / "fav.txt").read_text() == "Copier"
    assert (dst / "v2").read_text() == "true"
    empty_dir(tmp)
