import pexpect
import pytest
from plumbum import local
from plumbum.cmd import git
from pytest import TempPathFactory

import copier

from .helpers import COPIER_PATH, Spawn, build_file_tree, expect_prompt


def test_render_conditional(tmp_path_factory: TempPathFactory) -> None:
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))
    build_file_tree(
        {
            (src / "{% if conditional %}file.txt{% endif %}.jinja"): (
                "This is {{ conditional.variable }}."
            ),
        }
    )
    copier.run_copy(str(src), dst, data={"conditional": {"variable": True}})
    assert (dst / "file.txt").read_text() == "This is True."


def test_dont_render_conditional(tmp_path_factory: TempPathFactory) -> None:
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))
    build_file_tree(
        {
            (src / "{% if conditional %}file.txt{% endif %}.jinja"): (
                "This is {{ conditional.variable }}."
            ),
        }
    )
    copier.run_copy(str(src), dst)
    assert not (dst / "file.txt").exists()


def test_render_conditional_subdir(tmp_path_factory: TempPathFactory) -> None:
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))
    build_file_tree(
        {
            (src / "subdir" / "{% if conditional %}file.txt{% endif %}.jinja"): (
                "This is {{ conditional.variable }}."
            ),
        }
    )
    copier.run_copy(str(src), dst, data={"conditional": {"variable": True}})
    assert (dst / "subdir" / "file.txt").read_text() == "This is True."


def test_dont_render_conditional_subdir(tmp_path_factory: TempPathFactory) -> None:
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))
    build_file_tree(
        {
            (src / "subdir" / "{% if conditional %}file.txt{% endif %}.jinja"): (
                "This is a {{ conditional.variable }}."
            ),
        }
    )
    copier.run_copy(str(src), dst)
    assert not (dst / "subdir" / "file.txt").exists()


@pytest.mark.parametrize("interactive", [False, True])
def test_answer_changes(
    tmp_path_factory: TempPathFactory, spawn: Spawn, interactive: bool
) -> None:
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))

    with local.cwd(src):
        build_file_tree(
            {
                "{{ _copier_conf.answers_file }}.jinja": "{{ _copier_answers|to_nice_yaml }}",  # noqa: E501
                "copier.yml": """
                    condition:
                        type: bool
                """,
                "{% if condition %}file.txt{% endif %}.jinja": "",
            }
        )
        git("init")
        git("add", ".")
        git("commit", "-mv1")
        git("tag", "v1")

    if interactive:
        tui = spawn(COPIER_PATH + ("copy", str(src), str(dst)), timeout=10)
        expect_prompt(tui, "condition", "bool")
        tui.expect_exact("(y/N)")
        tui.sendline("y")
        tui.expect_exact("Yes")
        tui.expect_exact(pexpect.EOF)
    else:
        copier.run_copy(str(src), dst, data={"condition": True})

    assert (dst / "file.txt").exists()

    with local.cwd(dst):
        git("init")
        git("add", ".")
        git("commit", "-mv1")

    if interactive:
        tui = spawn(COPIER_PATH + ("update", str(dst)), timeout=10)
        expect_prompt(tui, "condition", "bool")
        tui.expect_exact("(Y/n)")
        tui.sendline("n")
        tui.expect_exact("No")
        tui.expect_exact(pexpect.EOF)
    else:
        copier.run_update(dst_path=dst, data={"condition": False}, overwrite=True)

    assert not (dst / "file.txt").exists()
