from __future__ import annotations

import platform
from pathlib import Path
from shutil import rmtree
from textwrap import dedent
from typing import Literal

import pexpect
import pytest
import yaml
from plumbum import local
from plumbum.cmd import git

from copier.cli import CopierApp
from copier.errors import UserMessageError
from copier.main import Worker, run_copy, run_update
from copier.tools import normalize_git_path

from .helpers import (
    BRACKET_ENVOPS_JSON,
    COPIER_CMD,
    COPIER_PATH,
    SUFFIX_TMPL,
    Spawn,
    build_file_tree,
    git_init,
)


@pytest.mark.impure
def test_updatediff(tmp_path_factory: pytest.TempPathFactory) -> None:
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))
    # Prepare repo bundle
    repo = src / "repo"
    bundle = src / "demo_updatediff_repo.bundle"
    last_commit = ""
    build_file_tree(
        {
            (repo / ".copier-answers.yml.jinja"): (
                """\
                # Changes here will be overwritten by Copier
                {{ _copier_answers|to_nice_yaml }}
                """
            ),
            (repo / "copier.yml"): (
                """\
                _envops:
                    "keep_trailing_newline": True
                project_name: to become a pirate
                author_name: Guybrush
                """
            ),
            (repo / "README.txt.jinja"): (
                """
                Let me introduce myself.

                My name is {{author_name}}, and my project is {{project_name}}.

                Thanks for your attention.
                """
            ),
        }
    )
    with local.cwd(repo):
        git("init")
        git("add", ".")
        git("commit", "-m", "Guybrush wants to be a pirate")
        git("tag", "v0.0.1")
    build_file_tree(
        {
            (repo / "copier.yml"): (
                """\
                _envops:
                    "keep_trailing_newline": True
                project_name: to become a pirate
                author_name: Guybrush
                _migrations:
                    -   version: v0.0.1
                        before:
                            - touch before-v0.0.1
                        after:
                            - touch after-v0.0.1
                    -   version: v0.0.2
                        before:
                            - touch before-v0.0.2
                        after:
                            - touch after-v0.0.2
                    -   version: v1.0.0
                        before:
                            - touch before-v1.0.0
                        after:
                            - touch after-v1.0.0
                """
            ),
        }
    )
    with local.cwd(repo):
        git("init")
        git("add", ".")
        git("commit", "-m", "Add migrations")
        git("tag", "v0.0.2")
    build_file_tree(
        {
            (repo / "copier.yml"): (
                """\
                _envops:
                    "keep_trailing_newline": True
                project_name: to rule
                author_name: Elaine
                _migrations:
                    -   version: v0.0.1
                        before:
                            - touch before-v0.0.1
                        after:
                            - touch after-v0.0.1
                    -   version: v0.0.2
                        before:
                            - touch before-v0.0.2
                        after:
                            - touch after-v0.0.2
                    -   version: v1.0.0
                        before:
                            - touch before-v1.0.0
                        after:
                            - touch after-v1.0.0
                """
            ),
            (repo / "README.txt.jinja"): (
                """
                Let me introduce myself.

                My name is {{author_name}}.

                My project is {{project_name}}.

                Thanks for your attention.
                """
            ),
        }
    )
    with local.cwd(repo):
        git("init")
        git("add", ".")
        git("commit", "-m", "Elaine wants to rule")
        git("bundle", "create", bundle, "--all")
        last_commit = git("describe", "--tags").strip()
    # Generate repo bundle
    target = dst / "target"
    readme = target / "README.txt"
    answers = target / ".copier-answers.yml"
    commit = git["commit", "--all"]
    # Run copier 1st time, with specific tag
    CopierApp.run(
        [
            "copier",
            "copy",
            str(bundle),
            str(target),
            "--defaults",
            "--overwrite",
            "--vcs-ref=v0.0.1",
        ],
        exit=False,
    )
    # Check it's copied OK
    assert answers.read_text() == dedent(
        f"""\
        # Changes here will be overwritten by Copier
        _commit: v0.0.1
        _src_path: {bundle}
        author_name: Guybrush
        project_name: to become a pirate\n
        """
    )
    assert readme.read_text() == dedent(
        """
        Let me introduce myself.

        My name is Guybrush, and my project is to become a pirate.

        Thanks for your attention.
        """
    )
    # Init destination as a new independent git repo
    with local.cwd(target):
        git("init")
        # Configure git in case you're running in CI
        git("config", "user.name", "Copier Test")
        git("config", "user.email", "test@copier")
        # Commit changes
        git("add", ".")
        commit("-m", "hello world")
        # Emulate the user modifying the README by hand
        readme.write_text(
            dedent(
                """
                Let me introduce myself.

                My name is Guybrush, and my project is to become a pirate.

                Thanks for your grog.
                """
            )
        )
        commit("-m", "I prefer grog")
        # Update target to latest tag and check it's updated in answers file
        CopierApp.run(["copier", "update", "--defaults", "--UNSAFE"], exit=False)
        assert answers.read_text() == dedent(
            f"""\
            # Changes here will be overwritten by Copier
            _commit: v0.0.2
            _src_path: {bundle}
            author_name: Guybrush
            project_name: to become a pirate\n
            """
        )
        # Check migrations were executed properly
        assert not (target / "before-v0.0.1").is_file()
        assert not (target / "after-v0.0.1").is_file()
        assert (target / "before-v0.0.2").is_file()
        assert (target / "after-v0.0.2").is_file()
        (target / "before-v0.0.2").unlink()
        (target / "after-v0.0.2").unlink()
        assert not (target / "before-v1.0.0").is_file()
        assert not (target / "after-v1.0.0").is_file()
        commit("-m", "Update template to v0.0.2")
        # Update target to latest commit, which is still untagged
        CopierApp.run(
            ["copier", "update", "--defaults", "--vcs-ref=HEAD"],
            exit=False,
        )
        # Check no new migrations were executed
        assert not (target / "before-v0.0.1").is_file()
        assert not (target / "after-v0.0.1").is_file()
        assert not (target / "before-v0.0.2").is_file()
        assert not (target / "after-v0.0.2").is_file()
        assert not (target / "before-v1.0.0").is_file()
        assert not (target / "after-v1.0.0").is_file()
        # Check it's updated OK
        assert answers.read_text() == dedent(
            f"""\
            # Changes here will be overwritten by Copier
            _commit: {last_commit}
            _src_path: {bundle}
            author_name: Guybrush
            project_name: to become a pirate\n
            """
        )
        assert readme.read_text() == dedent(
            """
            Let me introduce myself.

            My name is Guybrush.

            My project is to become a pirate.

            Thanks for your grog.
            """
        )
        commit("-m", f"Update template to {last_commit}")
        assert not git("status", "--porcelain")
        # No more updates exist, so updating again should change nothing
        CopierApp.run(
            ["copier", "update", "--defaults", "--vcs-ref=HEAD"],
            exit=False,
        )
        assert not git("status", "--porcelain")
        # If I change an option, it updates properly
        run_update(
            data={"author_name": "Largo LaGrande", "project_name": "to steal a lot"},
            defaults=True,
            overwrite=True,
            vcs_ref="HEAD",
        )
        assert readme.read_text() == dedent(
            """
            Let me introduce myself.

            My name is Largo LaGrande.

            My project is to steal a lot.

            Thanks for your grog.
            """
        )
        commit("-m", "Subproject evolved")
        # Reapply template ignoring subproject evolution
        Worker(
            data={"author_name": "Largo LaGrande", "project_name": "to steal a lot"},
            defaults=True,
            overwrite=True,
            vcs_ref="HEAD",
        ).run_copy()
        assert readme.read_text() == dedent(
            """
            Let me introduce myself.

            My name is Largo LaGrande.

            My project is to steal a lot.

            Thanks for your attention.
            """
        )


# This fails on Windows because there's some problem while detecting
# the diff. It seems like an older Git version were being used, while
# that's not the case...
# FIXME Some generous Windows power user please fix this test!
@pytest.mark.xfail(
    condition=platform.system() == "Windows", reason="Git broken on Windows?"
)
@pytest.mark.impure
def test_commit_hooks_respected(tmp_path_factory: pytest.TempPathFactory) -> None:
    """Commit hooks are taken into account when producing the update diff."""
    # Prepare source template v1
    src, dst1, dst2 = map(tmp_path_factory.mktemp, ("src", "dst1", "dst2"))
    with local.cwd(src):
        build_file_tree(
            {
                "copier.yml": (
                    f"""
                    _envops: {BRACKET_ENVOPS_JSON}
                    _templates_suffix: {SUFFIX_TMPL}
                    _tasks:
                        - git init
                        - pre-commit install -t pre-commit -t commit-msg
                        - pre-commit run -a || true
                    what: grog
                    """
                ),
                "[[ _copier_conf.answers_file ]].tmpl": (
                    """
                    [[ _copier_answers|to_nice_yaml ]]
                    """
                ),
                ".pre-commit-config.yaml": (
                    r"""
                    repos:
                    -   repo: https://github.com/pre-commit/mirrors-prettier
                        rev: v2.0.4
                        hooks:
                        -   id: prettier
                    -   repo: https://github.com/commitizen-tools/commitizen
                        rev: v3.12.0
                        hooks:
                        -   id: commitizen
                    -   repo: local
                        hooks:
                        -   id: forbidden-files
                            name: forbidden files
                            entry: found forbidden files; remove them
                            language: fail
                            files: "\\.rej$"
                    """
                ),
                "life.yml.tmpl": (
                    """
                    # Following code should be reformatted by pre-commit after copying
                    Line 1:      hello
                    Line 2:      [[ what ]]
                    Line 3:      bye
                    """
                ),
            }
        )
        git("init")
        git("add", ".")
        git("commit", "-m", "feat: commit 1")
        git("tag", "v1")
    # Copy source template
    run_copy(
        src_path=str(src), dst_path=dst1, defaults=True, overwrite=True, unsafe=True
    )
    with local.cwd(dst1):
        life = Path("life.yml")
        git("add", ".")
        # 1st commit fails because pre-commit reformats life.yml
        git("commit", "-am", "feat: failed commit", retcode=1)
        # 2nd commit works because it's already formatted
        git("commit", "-am", "feat: copied v1")
        assert life.read_text() == dedent(
            """\
            # Following code should be reformatted by pre-commit after copying
            Line 1: hello
            Line 2: grog
            Line 3: bye
            """
        )
    # Evolve source template to v2
    with local.cwd(src):
        build_file_tree(
            {
                "life.yml.tmpl": (
                    """\
                    # Following code should be reformatted by pre-commit after copying
                    Line 1:     hello world
                    Line 2:     grow up
                    Line 3:     [[ what ]]
                    Line 4:     grow old
                    Line 5:     bye bye world
                    """
                ),
            }
        )
        git("init")
        git("add", ".")
        git("commit", "-m", "feat: commit 2")
        git("tag", "v2")
    # Update subproject to v2
    run_update(
        dst_path=dst1,
        defaults=True,
        overwrite=True,
        conflict="rej",
        context_lines=1,
        unsafe=True,
    )
    with local.cwd(dst1):
        git("commit", "-am", "feat: copied v2")
        assert life.read_text() == dedent(
            """\
            # Following code should be reformatted by pre-commit after copying
            Line 1: hello world
            Line 2: grow up
            Line 3: grog
            Line 4: grow old
            Line 5: bye bye world
            """
        )
        # No .rej files created (update diff was smart)
        assert not git("status", "--porcelain")
        # Subproject evolves
        life.write_text(
            dedent(
                """\
                Line 1: hello world
                Line 2: grow up
                Line 2.5: make friends
                Line 3: grog
                Line 4: grow old
                Line 4.5: no more work
                Line 5: bye bye world
                """
            )
        )
        git("commit", "-am", "chore: subproject is evolved")
    # A new subproject appears, which is a shallow clone of the 1st one.
    # Using file:// prefix to allow local shallow clones.
    git("clone", "--depth=1", f"file://{dst1}", dst2)
    with local.cwd(dst2):
        # Subproject re-updates just to change some values
        run_update(
            data={"what": "study"},
            defaults=True,
            overwrite=True,
            conflict="rej",
            context_lines=1,
            unsafe=True,
        )
        git("commit", "-am", "chore: re-updated to change values after evolving")
        # Subproject evolution was respected up to sane possibilities.
        # In an ideal world, this file would be exactly the same as what's written
        # a few lines above, just changing "grog" for "study". However, that's nearly
        # impossible to achieve, because each change hunk needs at least 1 line of
        # context to let git apply that patch smartly, and that context couldn't be
        # found because we changed data when updating, so the sanest thing we can
        # do is to provide a .rej file to notify those
        # unresolvable diffs. OTOH, some other changes are be applied.
        # If some day you are able to produce that ideal result, you should be
        # happy to modify these asserts.
        assert life.read_text() == dedent(
            """\
            Line 1: hello world
            Line 2: grow up
            Line 3: study
            Line 4: grow old
            Line 4.5: no more work
            Line 5: bye bye world
            """
        )
        # This time a .rej file is unavoidable
        assert Path(f"{life}.rej").is_file()


def test_update_from_tagged_to_head(tmp_path_factory: pytest.TempPathFactory) -> None:
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))
    # Build a template
    with local.cwd(src):
        build_file_tree(
            {
                "{{ _copier_conf.answers_file }}.jinja": "{{ _copier_answers|to_nice_yaml }}",  # noqa: E501
                "example": "1",
            }
        )
        git("init")
        git("add", "-A")
        git("commit", "-m1")
        # Publish v1 release
        git("tag", "v1")
        # New commit, no release
        build_file_tree({"example": "2"})
        git("commit", "-am2")
        sha = git("rev-parse", "--short", "HEAD").strip()
    # Copy it without specifying version
    run_copy(src_path=str(src), dst_path=dst)
    example = dst / "example"
    answers_file = dst / ".copier-answers.yml"
    assert example.read_text() == "1"
    assert yaml.safe_load(answers_file.read_text())["_commit"] == "v1"
    # Build repo on copy
    with local.cwd(dst):
        git("init")
        git("add", "-A")
        git("commit", "-m3")
    # Update project, it must let us do it
    run_update(dst, vcs_ref="HEAD", defaults=True, overwrite=True)
    assert example.read_text() == "2"
    assert yaml.safe_load(answers_file.read_text())["_commit"] == f"v1-1-g{sha}"


def test_skip_update(tmp_path_factory: pytest.TempPathFactory) -> None:
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))
    with local.cwd(src):
        build_file_tree(
            {
                "copier.yaml": "_skip_if_exists: [skip_me]",
                "{{ _copier_conf.answers_file }}.jinja": "{{ _copier_answers|to_yaml }}",  # noqa: E501
                "skip_me": "1",
            }
        )
        git("init")
        git("add", ".")
        git("commit", "-m1")
        git("tag", "1.0.0")
    run_copy(str(src), dst, defaults=True, overwrite=True)
    skip_me = dst / "skip_me"
    answers_file = dst / ".copier-answers.yml"
    answers = yaml.safe_load(answers_file.read_text())
    assert skip_me.read_text() == "1"
    assert answers["_commit"] == "1.0.0"
    skip_me.write_text("2")
    with local.cwd(dst):
        git("init")
        git("add", ".")
        git("commit", "-m1")
    with local.cwd(src):
        build_file_tree({"skip_me": "3"})
        git("commit", "-am2")
        git("tag", "2.0.0")
    run_update(dst, defaults=True, overwrite=True)
    answers = yaml.safe_load(answers_file.read_text())
    assert skip_me.read_text() == "2"
    assert answers["_commit"] == "2.0.0"
    assert not (dst / "skip_me.rej").exists()


@pytest.mark.parametrize(
    "answers_file", [None, ".copier-answers.yml", ".custom.copier-answers.yaml"]
)
def test_overwrite_answers_file_always(
    tmp_path_factory: pytest.TempPathFactory, answers_file: str | None
) -> None:
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))
    with local.cwd(src):
        build_file_tree(
            {
                "copier.yaml": "question_1: true",
                "{{ _copier_conf.answers_file }}.jinja": "{{ _copier_answers|to_yaml }}",  # noqa: E501
                "answer_1.jinja": "{{ question_1 }}",
            }
        )
        git("init")
        git("add", ".")
        git("commit", "-m1")
        git("tag", "1")
        build_file_tree({"copier.yaml": "question_1: false"})
        git("commit", "-am2")
        git("tag", "2")
    # When copying, there's nothing to overwrite, overwrite=False shouldn't hang
    run_copy(str(src), dst, vcs_ref="1", defaults=True, answers_file=answers_file)
    with local.cwd(dst):
        git("init")
        git("add", ".")
        git("commit", "-m1")
        # When updating, the only thing to overwrite is the copier answers file,
        # which shouldn't ask, so also this shouldn't hang with overwrite=False
        run_update(defaults=True, overwrite=True, answers_file=answers_file)
    answers = yaml.safe_load(
        (dst / (answers_file or ".copier-answers.yml")).read_bytes()
    )
    assert answers["question_1"] is True
    assert answers["_commit"] == "2"
    assert (dst / "answer_1").read_text() == "True"


def test_file_removed(tmp_path_factory: pytest.TempPathFactory) -> None:
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))
    # Add a file in the template repo
    with local.cwd(src):
        build_file_tree(
            {
                "{{ _copier_conf.answers_file }}.jinja": "{{ _copier_answers|to_yaml }}",  # noqa: E501
                "1.txt": "content 1",
                Path("dir 2", "2.txt"): "content 2",
                Path("dir 3", "subdir 3", "3.txt"): "content 3",
                Path("dir 4", "subdir 4", "4.txt"): "content 4",
                Path("dir 5", "subdir 5", "5.txt"): "content 5",
                "toignore.txt": "should survive update",
            }
        )
        git("init")
        git("add", "-A")
        git("commit", "-m1")
        git("tag", "1")
    # Copy in subproject
    with local.cwd(dst):
        git("init")
        run_copy(str(src))
        # Subproject has an extra file
        build_file_tree(
            {
                "I.txt": "content I",
                Path("dir II", "II.txt"): "content II",
                Path("dir 3", "subdir III", "III.txt"): "content III",
                Path("dir 4", "subdir 4", "IV.txt"): "content IV",
            }
        )
        git("add", "-A")
        git("commit", "-m2")
    # All files exist
    assert (dst / ".copier-answers.yml").is_file()
    assert (dst / "1.txt").is_file()
    assert (dst / "dir 2" / "2.txt").is_file()
    assert (dst / "dir 3" / "subdir 3" / "3.txt").is_file()
    assert (dst / "dir 4" / "subdir 4" / "4.txt").is_file()
    assert (dst / "dir 5" / "subdir 5" / "5.txt").is_file()
    assert (dst / "toignore.txt").is_file()
    assert (dst / "I.txt").is_file()
    assert (dst / "dir II" / "II.txt").is_file()
    assert (dst / "dir 3" / "subdir III" / "III.txt").is_file()
    assert (dst / "dir 4" / "subdir 4" / "IV.txt").is_file()
    # Template removes file 1
    with local.cwd(src):
        Path("1.txt").unlink()
        rmtree("dir 2")
        rmtree("dir 3")
        rmtree("dir 4")
        rmtree("dir 5")
        build_file_tree({"6.txt": "content 6"})
        git("add", "-A")
        git("commit", "-m3")
        git("tag", "2")
    # Subproject updates
    with local.cwd(dst):
        Path(".gitignore").write_text("toignore.txt")
        git("add", ".gitignore")
        git("commit", "-m", "ignore file")
        with pytest.raises(
            UserMessageError, match="Enable overwrite to update a subproject."
        ):
            run_update(conflict="rej")
        run_update(conflict="rej", overwrite=True)
    # Check what must still exist
    assert (dst / ".copier-answers.yml").is_file()
    assert (dst / "I.txt").is_file()
    assert (dst / "dir II" / "II.txt").is_file()
    assert (dst / "dir 3" / "subdir III" / "III.txt").is_file()
    assert (dst / "dir 4" / "subdir 4" / "IV.txt").is_file()
    assert (dst / "6.txt").is_file()
    assert (dst / "toignore.txt").is_file()
    # Check what must not exist
    assert not (dst / "1.txt").exists()
    assert not (dst / "dir 2").exists()
    assert not (dst / "dir 3" / "subdir 3").exists()
    assert not (dst / "dir 4" / "subdir 4" / "4.txt").exists()
    assert not (dst / "dir 5").exists()


@pytest.mark.parametrize("interactive", [True, False])
def test_update_inline_changed_answers_and_questions(
    tmp_path_factory: pytest.TempPathFactory, interactive: bool, spawn: Spawn
) -> None:
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))
    with local.cwd(src):
        build_file_tree(
            {
                "{{ _copier_conf.answers_file }}.jinja": "{{ _copier_answers|to_yaml }}",  # noqa: E501
                "copier.yml": "b: false",
                "content.jinja": """\
                    aaa
                    {%- if b %}
                    bbb
                    {%- endif %}
                    zzz
                    """,
            }
        )
        git("init")
        git("add", "-A")
        git("commit", "-m1")
        git("tag", "1")
        build_file_tree(
            {
                "copier.yml": dedent(
                    """\
                    b: false
                    c: false
                    """
                ),
                "content.jinja": """\
                    aaa
                    {%- if b %}
                    bbb
                    {%- endif %}
                    {%- if c %}
                    ccc
                    {%- endif %}
                    zzz
                    """,
            }
        )
        git("commit", "-am2")
        git("tag", "2")
    # Init project
    if interactive:
        tui = spawn(COPIER_PATH + ("copy", "-r1", str(src), str(dst)), timeout=10)
        tui.expect_exact("b (bool)")
        tui.expect_exact("(y/N)")
        tui.send("y")
        tui.expect_exact(pexpect.EOF)
    else:
        run_copy(str(src), dst, data={"b": True}, vcs_ref="1")
    assert "ccc" not in (dst / "content").read_text()
    with local.cwd(dst):
        git("init")
        git("add", "-A")
        git("commit", "-m1")
        # Project evolution
        Path("content").write_text(
            dedent(
                """\
                aaa
                bbb
                jjj
                zzz
                """
            )
        )
        git("commit", "-am2")
        # Update from template, inline, with answer changes
        if interactive:
            tui = spawn(COPIER_PATH + ("update", "--conflict=inline"), timeout=10)
            tui.expect_exact("b (bool)")
            tui.expect_exact("(Y/n)")
            tui.sendline()
            tui.expect_exact("c (bool)")
            tui.expect_exact("(y/N)")
            tui.send("y")
            tui.expect_exact(pexpect.EOF)
        else:
            run_update(
                data={"c": True}, defaults=True, overwrite=True, conflict="inline"
            )
        assert Path("content").read_text() == dedent(
            """\
            aaa
            bbb
            <<<<<<< before updating
            jjj
            =======
            ccc
            >>>>>>> after updating
            zzz
            """
        )


@pytest.mark.parametrize("conflict", ["rej", "inline"])
def test_update_in_repo_subdirectory(
    tmp_path_factory: pytest.TempPathFactory, conflict: Literal["rej", "inline"]
) -> None:
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))
    subdir = Path("subdir")

    with local.cwd(src):
        build_file_tree(
            {
                "{{ _copier_conf.answers_file }}.jinja": "{{ _copier_answers|to_yaml }}",  # noqa: E501
                "version.txt": "v1",
            }
        )
        git("init")
        git("add", ".")
        git("commit", "-m1")
        git("tag", "v1")

    run_copy(str(src), dst / subdir)

    with local.cwd(dst):
        git("init")
        git("add", ".")
        git("commit", "-m1")

    assert (dst / subdir / ".copier-answers.yml").is_file()
    assert (dst / subdir / "version.txt").is_file()
    assert (dst / subdir / "version.txt").read_text() == "v1"

    with local.cwd(dst):
        build_file_tree({subdir / "version.txt": "v1 edited"})
        git("add", ".")
        git("commit", "-m1e")

    with local.cwd(src):
        build_file_tree({"version.txt": "v2"})
        git("add", ".")
        git("commit", "-m2")
        git("tag", "v2")

    run_update(dst / subdir, overwrite=True, conflict=conflict)

    assert (dst / subdir / ".copier-answers.yml").is_file()
    assert (dst / subdir / "version.txt").is_file()
    if conflict == "rej":
        assert (dst / subdir / "version.txt").read_text() == "v2"
        assert (dst / subdir / "version.txt.rej").is_file()
    else:
        assert (dst / subdir / "version.txt").read_text() == dedent(
            """\
            <<<<<<< before updating
            v1 edited
            =======
            v2
            >>>>>>> after updating
            """
        )


@pytest.mark.parametrize(
    "context_lines",
    [
        pytest.param(
            1,
            marks=pytest.mark.xfail(
                raises=AssertionError,
                reason="Not enough context lines to resolve the conflict.",
                strict=True,
            ),
        ),
        pytest.param(
            2,
            marks=pytest.mark.xfail(
                raises=AssertionError,
                reason="Not enough context lines to resolve the conflict.",
                strict=True,
            ),
        ),
        3,
    ],
)
@pytest.mark.parametrize("api", [True, False])
def test_update_needs_more_context(
    tmp_path_factory: pytest.TempPathFactory, context_lines: int, api: bool
) -> None:
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))
    # Create a template where some code blocks are similar
    with local.cwd(src):
        build_file_tree(
            {
                "{{ _copier_conf.answers_file }}.jinja": "{{ _copier_answers|to_yaml }}",  # noqa: E501
                "sample.py": dedent(
                    """\
                    def function_one():
                        print("This line is equal to the next one.")
                        print("This line is equal to the next one.")
                        print("This line is equal to the next one.")
                        print("This line is equal to the next one.")
                        print("Previous line lied.")

                    def function_two():
                        print("This line is equal to the next one.")
                        print("This line is equal to the next one.")
                        print("This line is equal to the next one.")
                        print("This line is equal to the next one.")
                        print("Previous line lied.")
                    """
                ),
            }
        )
        git("init")
        git("add", ".")
        git("commit", "-m1")
        git("tag", "v1")
    # Render and evolve that project
    with local.cwd(dst):
        if api:
            run_copy(str(src), ".")
        else:
            CopierApp.run(["copier", "copy", str(src), "."], exit=False)
        git("init")
        git("add", ".")
        git("commit", "-m1")
        build_file_tree(
            {
                "sample.py": dedent(
                    """\
                    def function_one():
                        print("This line is equal to the next one.")
                        print("This line is equal to the next one.")
                        print("This line is equal to the next one.")
                        print("This line is equal to the next one.")
                        print("Previous line lied.")

                    def function_two():
                        print("This line is equal to the next one.")
                        print("This line is equal to the next one.")
                        print("This line is new.")
                        print("This line is equal to the next one.")
                        print("This line is equal to the next one.")
                        print("Previous line lied.")
                    """
                )
            }
        )
        git("commit", "-am2")
    # Evolve the template
    with local.cwd(src):
        build_file_tree(
            {
                "sample.py": dedent(
                    """\
                    def function_zero():
                        print("This line is equal to the next one.")
                        print("This line is equal to the next one.")
                        print("This line is equal to the next one.")
                        print("This line is equal to the next one.")
                        print("Previous line lied.")

                    def function_one():
                        print("This line is equal to the next one.")
                        print("This line is equal to the next one.")
                        print("This line is equal to the next one.")
                        print("This line is equal to the next one.")
                        print("Previous line lied.")

                    def function_two():
                        print("This line is equal to the next one.")
                        print("This line is equal to the next one.")
                        print("This line is equal to the next one.")
                        print("This line is equal to the next one.")
                        print("Previous line lied.")
                    """
                )
            }
        )
        git("commit", "-am3")
        git("tag", "v2")
    # Update the project
    if api:
        run_update(dst, overwrite=True, conflict="inline", context_lines=context_lines)
    else:
        COPIER_CMD(
            "update",
            str(dst),
            "--conflict=inline",
            f"--context-lines={context_lines}",
        )
    # Check the update result
    assert (dst / "sample.py").read_text() == dedent(
        """\
        def function_zero():
            print("This line is equal to the next one.")
            print("This line is equal to the next one.")
            print("This line is equal to the next one.")
            print("This line is equal to the next one.")
            print("Previous line lied.")

        def function_one():
            print("This line is equal to the next one.")
            print("This line is equal to the next one.")
            print("This line is equal to the next one.")
            print("This line is equal to the next one.")
            print("Previous line lied.")

        def function_two():
            print("This line is equal to the next one.")
            print("This line is equal to the next one.")
            print("This line is new.")
            print("This line is equal to the next one.")
            print("This line is equal to the next one.")
            print("Previous line lied.")
        """
    )


@pytest.mark.parametrize(
    "filename",
    [
        "README.md",
        "spa ces",
        # Double quotes are not supported in file names on Windows.
        "qu`o'tes" if platform.system() == "Windows" else 'qu`o"tes',
        "m4â4ñ4a",
    ],
)
def test_conflicted_files_are_marked_unmerged(
    tmp_path_factory: pytest.TempPathFactory,
    filename: str,
) -> None:
    # Template in v1 has a file with a single line;
    # in v2 it changes that line.
    # Meanwhile, downstream project appended contents to the first line.
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))

    # First, create the template with an initial file
    build_file_tree(
        {
            (src / filename): "upstream version 1",
            (src / "{{_copier_conf.answers_file}}.jinja"): (
                "{{_copier_answers|to_nice_yaml}}"
            ),
        }
    )
    with local.cwd(src):
        git_init("hello template")
        git("tag", "v1")

    # Generate the project a first time, assert the file exists
    run_copy(str(src), dst, defaults=True, overwrite=True)
    assert (dst / filename).exists()
    assert "_commit: v1" in (dst / ".copier-answers.yml").read_text()

    # Start versioning the generated project
    with local.cwd(dst):
        git_init("hello project")

        # After first commit, change the file, commit again
        Path(filename).write_text("upstream version 1 + downstream")
        git("commit", "-am", "updated file")

    # Now change the template
    with local.cwd(src):
        # Update the file
        Path(filename).write_text("upstream version 2")

        # Commit the changes
        git("add", ".", "-A")
        git("commit", "-m", "change line in file")
        git("tag", "v2")

    # Finally, update the generated project
    run_update(dst_path=dst, defaults=True, overwrite=True, conflict="inline")
    assert "_commit: v2" in (dst / ".copier-answers.yml").read_text()

    # Assert that the file still exists, has inline markers,
    # and is reported as "unmerged" by Git.
    assert (dst / filename).exists()

    expected_contents = dedent(
        """\
        <<<<<<< before updating
        upstream version 1 + downstream
        =======
        upstream version 2
        >>>>>>> after updating
        """
    )
    assert (dst / filename).read_text().splitlines() == expected_contents.splitlines()
    assert not (dst / f"{filename}.rej").exists()

    with local.cwd(dst):
        lines = git("status", "--porcelain=v1").strip().splitlines()
        assert any(
            line.startswith("UU") and normalize_git_path(line[3:]) == filename
            for line in lines
        )
