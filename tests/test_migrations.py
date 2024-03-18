import json
import platform
from pathlib import Path
from shutil import copytree

import pytest
import yaml
from plumbum import local
from plumbum.cmd import git

from copier import run_copy, run_update
from copier.errors import UserMessageError

from .helpers import BRACKET_ENVOPS_JSON, PROJECT_TEMPLATE, build_file_tree

SRC = Path(f"{PROJECT_TEMPLATE}_migrations").absolute()


# This fails on windows CI because, when the test tries to execute
# `migrations.py`, it doesn't understand that it should be interpreted
# by python.exe. Or maybe it fails because CI is using Git bash instead
# of WSL bash, which happened to work fine in real world tests.
# FIXME Some generous Windows power user please fix this test!
@pytest.mark.xfail(
    condition=platform.system() == "Windows",
    reason="Windows ignores shebang?",
    strict=True,
)
def test_migrations_and_tasks(tmp_path: Path) -> None:
    """Check migrations and tasks are run properly."""
    # Convert demo_migrations in a git repository with 2 versions
    src, dst = tmp_path / "src", tmp_path / "dst"
    copytree(SRC, src)
    with local.cwd(src):
        git("init")
        git("config", "user.name", "Copier Test")
        git("config", "user.email", "test@copier")
        git("add", ".")
        git("commit", "-m1")
        git("tag", "v1.0.0")
        git("commit", "--allow-empty", "-m2")
        git("tag", "v2.0")
    # Copy it in v1
    run_copy(src_path=str(src), dst_path=dst, vcs_ref="v1.0.0", unsafe=True)
    # Check copy was OK
    assert (dst / "created-with-tasks.txt").read_text() == "task 1\ntask 2\n"
    assert not (dst / "delete-in-tasks.txt").exists()
    assert (dst / "delete-in-migration-v2.txt").is_file()
    assert not (dst / "migrations.py").exists()
    assert not (dst / "tasks.py").exists()
    assert not list(dst.glob("*-before.txt"))
    assert not list(dst.glob("*-after.txt"))
    answers = yaml.safe_load((dst / ".copier-answers.yml").read_text())
    assert answers == {"_commit": "v1.0.0", "_src_path": str(src)}
    # Save changes in downstream repo
    with local.cwd(dst):
        git("add", ".")
        git("config", "user.name", "Copier Test")
        git("config", "user.email", "test@copier")
        git("commit", "-m1")
    # Update it to v2
    run_update(dst_path=dst, defaults=True, overwrite=True, unsafe=True)
    # Check update was OK
    assert (dst / "created-with-tasks.txt").read_text() == "task 1\ntask 2\n" * 2
    assert not (dst / "delete-in-tasks.txt").exists()
    assert not (dst / "delete-in-migration-v2.txt").exists()
    assert not (dst / "migrations.py").exists()
    assert not (dst / "tasks.py").exists()
    assert (dst / "v1.0.0-v2-v2.0-before.json").is_file()
    assert (dst / "v1.0.0-v2-v2.0-after.json").is_file()
    assert (dst / "PEP440-1.0.0-2-2.0-before.json").is_file()
    assert (dst / "PEP440-1.0.0-2-2.0-after.json").is_file()
    answers = yaml.safe_load((dst / ".copier-answers.yml").read_text())
    assert answers == {"_commit": "v2.0", "_src_path": str(src)}


def test_pre_migration_modifies_answers(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """Test support for answers modifications in pre-migrations."""
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))

    # v1 of template asks for a favourite song and writes it to songs.json
    with local.cwd(src):
        build_file_tree(
            {
                "[[ _copier_conf.answers_file ]].jinja": (
                    "[[ _copier_answers|tojson ]]"
                ),
                "copier.yml": (
                    f"""\
                    _envops: {BRACKET_ENVOPS_JSON}
                    best_song: la vie en rose
                    """
                ),
                "songs.json.jinja": "[ [[ best_song|tojson ]] ]",
            }
        )
        git("init")
        git("add", ".")
        git("commit", "-m1")
        git("tag", "v1")
    # User copies v1 template into subproject
    with local.cwd(dst):
        run_copy(src_path=str(src), defaults=True, overwrite=True)
        answers = json.loads(Path(".copier-answers.yml").read_text())
        assert answers["_commit"] == "v1"
        assert answers["best_song"] == "la vie en rose"
        assert json.loads(Path("songs.json").read_text()) == ["la vie en rose"]
        git("init")
        git("add", ".")
        git("commit", "-m1")
    with local.cwd(src):
        build_file_tree(
            {
                # v2 of template supports multiple songs, has a different default
                # and includes a data format migration script
                "copier.yml": (
                    f"""\
                    _envops: {BRACKET_ENVOPS_JSON}
                    best_song_list:
                        default: [paranoid android]
                    _migrations:
                    -   version: v2
                        before:
                        -   - python
                            - -c
                            - |
                                import sys, json, pathlib
                                answers_path = pathlib.Path(*sys.argv[1:])
                                answers = json.loads(answers_path.read_text())
                                answers["best_song_list"] = [answers.pop("best_song")]
                                answers_path.write_text(json.dumps(answers))
                            - "[[ _copier_conf.dst_path ]]"
                            - "[[ _copier_conf.answers_file ]]"
                    """
                ),
                "songs.json.jinja": "[[ best_song_list|tojson ]]",
            }
        )
        git("add", ".")
        git("commit", "-m2")
        git("tag", "v2")
    # User updates subproject to v2 template
    with local.cwd(dst):
        run_update(defaults=True, overwrite=True, unsafe=True)
        answers = json.loads(Path(".copier-answers.yml").read_text())
        assert answers["_commit"] == "v2"
        assert "best_song" not in answers
        assert answers["best_song_list"] == ["la vie en rose"]
        assert json.loads(Path("songs.json").read_text()) == ["la vie en rose"]


def test_prereleases(tmp_path_factory: pytest.TempPathFactory) -> None:
    """Test prereleases support for copying and updating."""
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))
    with local.cwd(src):
        # Build template in v1.0.0
        build_file_tree(
            {
                "version.txt": "v1.0.0",
                "[[ _copier_conf.answers_file ]].jinja": "[[_copier_answers|to_nice_yaml]]",  # noqa: E501
                "copier.yaml": (
                    f"""\
                    _envops: {BRACKET_ENVOPS_JSON}
                    _migrations:
                    -   version: v1.9
                        before:
                        - [python, -c, "import pathlib; pathlib.Path('v1.9').touch()"]
                    -   version: v2.dev0
                        before:
                        - [python, -c, "import pathlib; pathlib.Path('v2.dev0').touch()"]
                    -   version: v2.dev2
                        before:
                        - [python, -c, "import pathlib; pathlib.Path('v2.dev2').touch()"]
                    -   version: v2.a1
                        before:
                        - [python, -c, "import pathlib; pathlib.Path('v2.a1').touch()"]
                    -   version: v2.a2
                        before:
                        - [python, -c, "import pathlib; pathlib.Path('v2.a2').touch()"]
                    """  # noqa: E501
                ),
            }
        )
        git("init")
        git("add", ".")
        git("commit", "-mv1")
        git("tag", "v1.0.0")
        # Evolve template to v2.0.0.dev1
        build_file_tree({"version.txt": "v2.0.0.dev1"})
        git("commit", "-amv2dev1")
        git("tag", "v2.0.0.dev1")
        # Evolve template to v2.0.0.alpha1
        build_file_tree({"version.txt": "v2.0.0.alpha1"})
        git("commit", "-amv2a1")
        git("tag", "v2.0.0.alpha1")
    # Copying with use_prereleases=False copies v1
    run_copy(src_path=str(src), dst_path=dst, defaults=True, overwrite=True)
    answers = yaml.safe_load((dst / ".copier-answers.yml").read_text())
    assert answers["_commit"] == "v1.0.0"
    assert (dst / "version.txt").read_text() == "v1.0.0"
    assert not (dst / "v1.9").exists()
    assert not (dst / "v2.dev0").exists()
    assert not (dst / "v2.dev2").exists()
    assert not (dst / "v2.a1").exists()
    assert not (dst / "v2.a2").exists()
    with local.cwd(dst):
        # Commit subproject
        git("init")
        git("add", ".")
        git("commit", "-mv1")
        # Update it without prereleases; nothing changes
        run_update(defaults=True, overwrite=True)
        assert not git("status", "--porcelain")
    assert not (dst / "v1.9").exists()
    assert not (dst / "v2.dev0").exists()
    assert not (dst / "v2.dev2").exists()
    assert not (dst / "v2.a1").exists()
    assert not (dst / "v2.a2").exists()
    # Update it with prereleases
    run_update(
        dst_path=dst, defaults=True, overwrite=True, use_prereleases=True, unsafe=True
    )
    answers = yaml.safe_load((dst / ".copier-answers.yml").read_text())
    assert answers["_commit"] == "v2.0.0.alpha1"
    assert (dst / "version.txt").read_text() == "v2.0.0.alpha1"
    assert (dst / "v1.9").exists()
    assert (dst / "v2.dev0").exists()
    assert (dst / "v2.dev2").exists()
    assert (dst / "v2.a1").exists()
    assert not (dst / "v2.a2").exists()
    # It should fail if downgrading
    with pytest.raises(UserMessageError):
        run_update(dst_path=dst, defaults=True, overwrite=True)


def test_pretend_mode(tmp_path_factory: pytest.TempPathFactory) -> None:
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))

    # Build template in v1
    with local.cwd(src):
        git("init")
        build_file_tree(
            {
                "[[ _copier_conf.answers_file ]].jinja": "[[_copier_answers|to_nice_yaml]]",  # noqa: E501
                "copier.yml": (
                    f"""\
                    _envops: {BRACKET_ENVOPS_JSON}
                    """
                ),
            }
        )
        git("add", ".")
        git("commit", "-mv1")
        git("tag", "v1")

    run_copy(str(src), dst)
    answers = yaml.safe_load((dst / ".copier-answers.yml").read_text())
    assert answers["_commit"] == "v1"

    with local.cwd(dst):
        git("init")
        git("add", ".")
        git("commit", "-mv1")

    # Evolve template to v2
    with local.cwd(src):
        build_file_tree(
            {
                "[[ _copier_conf.answers_file ]].jinja": "[[_copier_answers|to_nice_yaml]]",  # noqa: E501
                "copier.yml": (
                    f"""\
                    _envops: {BRACKET_ENVOPS_JSON}
                    _migrations:
                    -   version: v2
                        before:
                        -   touch v2-before.txt
                        after:
                        -   touch v2-after.txt
                    """
                ),
            }
        )
        git("add", ".")
        git("commit", "-mv2")
        git("tag", "v2")

    run_update(dst_path=dst, overwrite=True, pretend=True, unsafe=True)
    answers = yaml.safe_load((dst / ".copier-answers.yml").read_text())
    assert answers["_commit"] == "v1"
    assert not (dst / "v2-before.txt").exists()
    assert not (dst / "v2-after.txt").exists()
