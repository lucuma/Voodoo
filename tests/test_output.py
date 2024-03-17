import re
from pathlib import Path

import pexpect
import pytest
from plumbum import local
from plumbum.cmd import git

from copier.errors import InvalidTypeError
from copier.main import run_copy, run_recopy, run_update

from .helpers import COPIER_PATH, Spawn, build_file_tree, expect_prompt, render


def test_output(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    render(tmp_path, quiet=False)
    _, err = capsys.readouterr()
    assert re.search(r"create[^\s]*  config\.py", err)
    assert re.search(r"create[^\s]*  pyproject\.toml", err)
    assert re.search(r"create[^\s]*  doc[/\\]images[/\\]nslogo\.gif", err)


def test_output_pretend(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    render(tmp_path, quiet=False, pretend=True)
    _, err = capsys.readouterr()
    assert re.search(r"create[^\s]*  config\.py", err)
    assert re.search(r"create[^\s]*  pyproject\.toml", err)
    assert re.search(r"create[^\s]*  doc[/\\]images[/\\]nslogo\.gif", err)


def test_output_force(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    render(tmp_path)
    capsys.readouterr()
    render(tmp_path, quiet=False, defaults=True, overwrite=True)
    _, err = capsys.readouterr()
    assert re.search(r"conflict[^\s]*  config\.py", err)
    assert re.search(r"overwrite[^\s]*  config\.py", err)
    assert re.search(r"identical[^\s]*  pyproject\.toml", err)
    assert re.search(r"identical[^\s]*  doc[/\\]images[/\\]nslogo\.gif", err)


def test_output_skip(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    render(tmp_path)
    capsys.readouterr()
    render(tmp_path, quiet=False, skip_if_exists=["config.py"])
    _, err = capsys.readouterr()
    assert re.search(r"conflict[^\s]*  config\.py", err)
    assert re.search(r"skip[^\s]*  config\.py", err)
    assert re.search(r"identical[^\s]*  pyproject\.toml", err)
    assert re.search(r"identical[^\s]*  doc[/\\]images[/\\]nslogo\.gif", err)


def test_output_quiet(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    render(tmp_path, quiet=True)
    out, err = capsys.readouterr()
    assert out == ""
    assert err == ""


def test_question_with_invalid_type(tmp_path_factory: pytest.TempPathFactory) -> None:
    src, dst = map(tmp_path_factory.mktemp, ["src", "dst"])
    build_file_tree(
        {
            src / "copier.yaml": """
                bad:
                    type: invalid
                    default: 1
                """
        }
    )
    with pytest.raises(
        InvalidTypeError, match='Unsupported type "invalid" in question "bad"'
    ):
        run_copy(str(src), dst, defaults=True, overwrite=True)


def test_answer_with_invalid_type(tmp_path_factory: pytest.TempPathFactory) -> None:
    src, dst = map(tmp_path_factory.mktemp, ["src", "dst"])
    build_file_tree(
        {
            src / "copier.yaml": """
                bad:
                    type: int
                    default: null
                """
        }
    )
    with pytest.raises(
        InvalidTypeError,
        match=(
            'Invalid answer "None" of type "<class \'NoneType\'>" to question "bad" '
            'of type "int"'
        ),
    ):
        run_copy(str(src), dst, defaults=True, overwrite=True)


@pytest.mark.parametrize("interactive", [False, True])
def test_messages_with_inline_text(
    tmp_path_factory: pytest.TempPathFactory,
    capsys: pytest.CaptureFixture[str],
    spawn: Spawn,
    interactive: bool,
) -> None:
    src, dst = map(tmp_path_factory.mktemp, ["src", "dst"])

    build_file_tree(
        {
            (src / "copier.yaml"): (
                """\
                project_name:
                    type: str

                _message_before_copy: Thank you for using our template on {{ _copier_conf.os }}
                _message_after_copy: Project {{ project_name }} successfully created
                _message_before_update: Updating on {{ _copier_conf.os }}
                _message_after_update: Project {{ project_name }} successfully updated
                """  # noqa: E501
            ),
            (src / "{{ _copier_conf.answers_file }}.jinja"): (
                """\
                # Changes here will be overwritten by Copier
                {{ _copier_answers|to_nice_yaml }}
                """
            ),
            (src / "version.txt"): "v1",
        }
    )
    with local.cwd(src):
        git("init")
        git("add", ".")
        git("commit", "-m1")
        git("tag", "v1")

    build_file_tree(
        {
            (src / "version.txt"): "v2",
        }
    )
    with local.cwd(src):
        git("add", ".")
        git("commit", "-m2")
        git("tag", "v2")

    # clear capture output log
    capsys.readouterr()

    # copy
    if interactive:
        tui = spawn(COPIER_PATH + ("copy", "-r", "v1", str(src), str(dst)), timeout=10)
        expect_prompt(tui, "project_name", "str")
        tui.sendline("myproj")
        tui.expect_exact(pexpect.EOF)
    else:
        run_copy(str(src), dst, data={"project_name": "myproj"}, vcs_ref="v1")

    assert (dst / "version.txt").read_text() == "v1"
    _, err = capsys.readouterr()
    assert re.search(
        r"""
        ^Thank\ you\ for\ using\ our\ template\ on\ (linux|macos|windows).+
        Project\ myproj\ successfully\ created\s*$
        """,
        err,
        flags=re.S | re.X,
    )

    # recopy
    if interactive:
        tui = spawn(COPIER_PATH + ("recopy", "-r", "v1", str(dst)), timeout=10)
        expect_prompt(tui, "project_name", "str")
        tui.sendline("_new")
        tui.expect_exact(pexpect.EOF)
    else:
        run_recopy(dst, data={"project_name": "myproj_new"}, vcs_ref="v1")

    assert (dst / "version.txt").read_text() == "v1"
    _, err = capsys.readouterr()
    assert re.search(
        r"""
        ^Thank\ you\ for\ using\ our\ template\ on\ (linux|macos|windows).+
        Project\ myproj_new\ successfully\ created\s*$
        """,
        err,
        flags=re.S | re.X,
    )

    with local.cwd(dst):
        git("init")
        git("add", ".")
        git("commit", "-m1")

    # clear capture output log
    capsys.readouterr()

    # update
    if interactive:
        tui = spawn(COPIER_PATH + ("update", str(dst)), timeout=10)
        expect_prompt(tui, "project_name", "str")
        tui.sendline("_update")
        tui.expect_exact(pexpect.EOF)
    else:
        run_update(dst, data={"project_name": "myproj_new_update"}, overwrite=True)

    assert (dst / "version.txt").read_text() == "v2"
    _, err = capsys.readouterr()
    assert re.search(
        r"""
        ^Updating\ on\ (linux|macos|windows).+
        Project\ myproj_new_update\ successfully\ updated\s*$
        """,
        err,
        flags=re.S | re.X,
    )


@pytest.mark.parametrize("interactive", [False, True])
def test_messages_with_included_text(
    tmp_path_factory: pytest.TempPathFactory,
    capsys: pytest.CaptureFixture[str],
    spawn: Spawn,
    interactive: bool,
) -> None:
    src, dst = map(tmp_path_factory.mktemp, ["src", "dst"])

    build_file_tree(
        {
            (src / "copier.yaml"): (
                """\
                project_name:
                    type: str

                _exclude: [".git", "*.md"]
                _message_before_copy: "{% include 'message_before_copy.md.jinja' %}"
                _message_after_copy: "{% include 'message_after_copy.md.jinja' %}"
                _message_before_update: "{% include 'message_before_update.md.jinja' %}"
                _message_after_update: "{% include 'message_after_update.md.jinja' %}"
                """
            ),
            (src / "message_before_copy.md.jinja"): (
                """\
                Thank you for using our template on {{ _copier_conf.os }}
                """
            ),
            (src / "message_after_copy.md.jinja"): (
                """\
                Project {{ project_name }} successfully created
                """
            ),
            (src / "message_before_update.md.jinja"): (
                """\
                Updating on {{ _copier_conf.os }}
                """
            ),
            (src / "message_after_update.md.jinja"): (
                """\
                Project {{ project_name }} successfully updated
                """
            ),
            (src / "{{ _copier_conf.answers_file }}.jinja"): (
                """\
                # Changes here will be overwritten by Copier
                {{ _copier_answers|to_nice_yaml }}
                """
            ),
            (src / "version.txt"): "v1",
        }
    )
    with local.cwd(src):
        git("init")
        git("add", ".")
        git("commit", "-m1")
        git("tag", "v1")

    build_file_tree(
        {
            (src / "version.txt"): "v2",
        }
    )
    with local.cwd(src):
        git("add", ".")
        git("commit", "-m2")
        git("tag", "v2")

    # clear capture output log
    capsys.readouterr()

    # copy
    if interactive:
        tui = spawn(COPIER_PATH + ("copy", "-r", "v1", str(src), str(dst)), timeout=10)
        expect_prompt(tui, "project_name", "str")
        tui.sendline("myproj")
        tui.expect_exact(pexpect.EOF)
    else:
        run_copy(str(src), dst, data={"project_name": "myproj"}, vcs_ref="v1")

    assert (dst / "version.txt").read_text() == "v1"
    _, err = capsys.readouterr()
    assert re.search(
        r"""
        ^Thank\ you\ for\ using\ our\ template\ on\ (linux|macos|windows).+
        Project\ myproj\ successfully\ created\s*$
        """,
        err,
        flags=re.S | re.X,
    )

    # recopy
    if interactive:
        tui = spawn(COPIER_PATH + ("recopy", "-r", "v1", str(dst)), timeout=10)
        expect_prompt(tui, "project_name", "str")
        tui.sendline("_new")
        tui.expect_exact(pexpect.EOF)
    else:
        run_recopy(dst, data={"project_name": "myproj_new"}, vcs_ref="v1")

    assert (dst / "version.txt").read_text() == "v1"
    _, err = capsys.readouterr()
    assert re.search(
        r"""
        ^Thank\ you\ for\ using\ our\ template\ on\ (linux|macos|windows).+
        Project\ myproj_new\ successfully\ created\s*$
        """,
        err,
        flags=re.S | re.X,
    )

    with local.cwd(dst):
        git("init")
        git("add", ".")
        git("commit", "-m1")

    # clear capture output log
    capsys.readouterr()

    # update
    if interactive:
        tui = spawn(COPIER_PATH + ("update", str(dst)), timeout=10)
        expect_prompt(tui, "project_name", "str")
        tui.sendline("_update")
        tui.expect_exact(pexpect.EOF)
    else:
        run_update(dst, data={"project_name": "myproj_new_update"}, overwrite=True)

    assert (dst / "version.txt").read_text() == "v2"
    _, err = capsys.readouterr()
    assert re.search(
        r"""
        ^Updating\ on\ (linux|macos|windows).+
        Project\ myproj_new_update\ successfully\ updated\s*$
        """,
        err,
        flags=re.S | re.X,
    )


@pytest.mark.parametrize("interactive", [False, True])
def test_messages_quiet(
    tmp_path_factory: pytest.TempPathFactory,
    capsys: pytest.CaptureFixture[str],
    spawn: Spawn,
    interactive: bool,
) -> None:
    src, dst = map(tmp_path_factory.mktemp, ["src", "dst"])

    build_file_tree(
        {
            (src / "copier.yaml"): (
                """\
                project_name:
                    type: str

                _message_before_copy: Thank you for using our template on {{ _copier_conf.os }}
                _message_after_copy: Project {{ project_name }} successfully created
                _message_before_update: Updating on {{ _copier_conf.os }}
                _message_after_update: Project {{ project_name }} successfully updated
                """  # noqa: E501
            ),
            (src / "{{ _copier_conf.answers_file }}.jinja"): (
                """\
                # Changes here will be overwritten by Copier
                {{ _copier_answers|to_nice_yaml }}
                """
            ),
            (src / "version.txt"): "v1",
        }
    )
    with local.cwd(src):
        git("init")
        git("add", ".")
        git("commit", "-m1")
        git("tag", "v1")

    build_file_tree(
        {
            (src / "version.txt"): "v2",
        }
    )
    with local.cwd(src):
        git("add", ".")
        git("commit", "-m2")
        git("tag", "v2")

    # clear capture output log
    capsys.readouterr()

    # copy
    if interactive:
        tui = spawn(
            COPIER_PATH + ("copy", "--quiet", "-r", "v1", str(src), str(dst)),
            timeout=10,
        )
        expect_prompt(tui, "project_name", "str")
        tui.sendline("myproj")
        tui.expect_exact(pexpect.EOF)
    else:
        run_copy(
            str(src), dst, data={"project_name": "myproj"}, vcs_ref="v1", quiet=True
        )

    assert (dst / "version.txt").read_text() == "v1"
    _, err = capsys.readouterr()
    assert "Thank you for using our template" not in err
    assert "Project myproj successfully created" not in err

    # recopy
    if interactive:
        tui = spawn(
            COPIER_PATH + ("recopy", "--quiet", "-r", "v1", str(dst)), timeout=10
        )
        expect_prompt(tui, "project_name", "str")
        tui.sendline("_new")
        tui.expect_exact(pexpect.EOF)
    else:
        run_recopy(dst, data={"project_name": "myproj_new"}, vcs_ref="v1", quiet=True)

    assert (dst / "version.txt").read_text() == "v1"
    _, err = capsys.readouterr()
    assert "Thank you for using our template" not in err
    assert "Project myproj_new successfully created" not in err

    with local.cwd(dst):
        git("init")
        git("add", ".")
        git("commit", "-m1")

    # clear capture output log
    capsys.readouterr()

    # update
    if interactive:
        tui = spawn(COPIER_PATH + ("update", "--quiet", str(dst)), timeout=10)
        expect_prompt(tui, "project_name", "str")
        tui.sendline("_update")
        tui.expect_exact(pexpect.EOF)
    else:
        run_update(
            dst, data={"project_name": "myproj_new_update"}, overwrite=True, quiet=True
        )

    assert (dst / "version.txt").read_text() == "v2"
    _, err = capsys.readouterr()
    assert "Updating on" not in err
    assert "Project myproj_new_update successfully updated" not in err
