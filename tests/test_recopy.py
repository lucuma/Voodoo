from pathlib import Path

import pytest
from plumbum import local

from copier import run_copy, run_recopy
from copier.cli import CopierApp
from copier.vcs import get_git

from .helpers import build_file_tree, git_save


@pytest.fixture(scope="module")
def tpl(tmp_path_factory: pytest.TempPathFactory) -> str:
    """A simple template that supports updates."""
    dst = tmp_path_factory.mktemp("tpl")
    with local.cwd(dst):
        build_file_tree(
            {
                "copier.yml": "your_name: Mario",
                "{{ _copier_conf.answers_file }}.jinja": "{{ _copier_answers|to_nice_yaml }}",  # noqa: E501
                "name.txt.jinja": "This is your name: {{ your_name }}.",
            }
        )
        git_save()
    return str(dst)


def test_recopy_discards_evolution_api(tpl: str, tmp_path: Path) -> None:
    # First copy
    run_copy(tpl, tmp_path, data={"your_name": "Luigi"}, defaults=True, overwrite=True)
    git_save(tmp_path)
    name_path = tmp_path / "name.txt"
    assert name_path.read_text() == "This is your name: Luigi."
    # Evolve subproject
    name_path.write_text("This is your name: Luigi. Welcome.")
    git_save(tmp_path)
    # Recopy
    run_recopy(tmp_path, defaults=True, overwrite=True)
    assert name_path.read_text() == "This is your name: Luigi."


def test_recopy_discards_evolution_cli(tpl: str, tmp_path: Path) -> None:
    # First copy
    run_copy(tpl, tmp_path, data={"your_name": "Peach"}, defaults=True, overwrite=True)
    git_save(tmp_path)
    name_path = tmp_path / "name.txt"
    assert name_path.read_text() == "This is your name: Peach."
    # Evolve subproject
    name_path.write_text("This is your name: Peach. Welcome.")
    git_save(tmp_path)
    # Recopy
    with local.cwd(tmp_path):
        _, retcode = CopierApp.run(["copier", "recopy", "-f"], exit=False)
    assert retcode == 0
    assert name_path.read_text() == "This is your name: Peach."


def test_recopy_works_without_replay(tpl: str, tmp_path: Path) -> None:
    # First copy
    run_copy(tpl, tmp_path, defaults=True, overwrite=True)
    git_save(tmp_path)
    assert (tmp_path / "name.txt").read_text() == "This is your name: Mario."
    # Modify template altering git history
    Path(tpl, "name.txt.jinja").write_text("This is my name: {{ your_name }}.")
    tpl_git = get_git(tpl)
    tpl_git("commit", "-a", "--amend", "--no-edit")
    # Make sure old dangling commit is lost
    # DOCS https://stackoverflow.com/a/63209363/1468388
    tpl_git("reflog", "expire", "--expire=now", "--all")
    tpl_git("gc", "--prune=now", "--aggressive")
    # Recopy
    run_recopy(tmp_path, skip_answered=True, overwrite=True)
    assert (tmp_path / "name.txt").read_text() == "This is my name: Mario."
