from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Mapping, Protocol, Union

import pexpect
import pytest
import yaml
from pexpect.popen_spawn import PopenSpawn
from plumbum import local
from plumbum.cmd import git

from copier.types import StrOrPath

from .helpers import (
    BRACKET_ENVOPS,
    BRACKET_ENVOPS_JSON,
    COPIER_PATH,
    SUFFIX_TMPL,
    Keyboard,
    Spawn,
    build_file_tree,
    expect_prompt,
    git_save,
)

try:
    from typing import TypeAlias  # type: ignore[attr-defined]
except ImportError:
    from typing_extensions import TypeAlias


MARIO_TREE: Mapping[StrOrPath, str | bytes] = {
    "copier.yml": (
        f"""\
        _templates_suffix: {SUFFIX_TMPL}
        _envops: {BRACKET_ENVOPS_JSON}
        in_love:
            type: bool
            default: yes
        your_name:
            type: str
            default: Mario
            help: If you have a name, tell me now.
        your_enemy:
            type: str
            default: Bowser
            secret: yes
            help: Secret enemy name
        what_enemy_does:
            type: str
            default: "[[ your_enemy ]] hates [[ your_name ]]"
        """
    ),
    "[[ _copier_conf.answers_file ]].tmpl": "[[_copier_answers|to_nice_yaml]]",
}

MARIO_TREE_WITH_NEW_FIELD: Mapping[StrOrPath, str | bytes] = {
    "copier.yml": (
        f"""\
        _templates_suffix: {SUFFIX_TMPL}
        _envops: {BRACKET_ENVOPS_JSON}
        in_love:
            type: bool
            default: yes
        your_name:
            type: str
            default: Mario
            help: If you have a name, tell me now.
        your_enemy:
            type: str
            default: Bowser
            secret: yes
            help: Secret enemy name
        your_sister:
            type: str
            default: Luigi
            help: Your sister's name
        what_enemy_does:
            type: str
            default: "[[ your_enemy ]] hates [[ your_name ]]"
        """
    ),
    "[[ _copier_conf.answers_file ]].tmpl": "[[_copier_answers|to_nice_yaml]]",
}


@pytest.mark.parametrize(
    "name, args",
    [
        ("Mario", ()),  # Default name in the template
        ("Luigi", ("--data=your_name=Luigi",)),
        ("None", ("--data=your_name=None",)),
    ],
)
def test_copy_default_advertised(
    tmp_path_factory: pytest.TempPathFactory,
    spawn: Spawn,
    name: str,
    args: tuple[str, ...],
) -> None:
    """Test that the questions for the user are OK."""
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))
    with local.cwd(src):
        build_file_tree(MARIO_TREE)
        git_save(tag="v1")
        git("commit", "--allow-empty", "-m", "v2")
        git("tag", "v2")
    with local.cwd(dst):
        # Copy the v1 template
        tui = spawn(
            COPIER_PATH + ("copy", str(src), ".", "--vcs-ref=v1") + args, timeout=10
        )
        # Check what was captured
        expect_prompt(tui, "in_love", "bool")
        tui.expect_exact("(Y/n)")
        tui.sendline()
        tui.expect_exact("Yes")
        if not args:
            expect_prompt(
                tui, "your_name", "str", help="If you have a name, tell me now."
            )
            tui.expect_exact(name)
            tui.sendline()
        expect_prompt(tui, "your_enemy", "str", help="Secret enemy name")
        tui.expect_exact("******")
        tui.sendline()
        expect_prompt(tui, "what_enemy_does", "str")
        tui.expect_exact(f"Bowser hates {name}")
        tui.sendline()
        tui.expect_exact(pexpect.EOF)
        assert "_commit: v1" in Path(".copier-answers.yml").read_text()
        # Update subproject
        git_save()
        assert "_commit: v1" in Path(".copier-answers.yml").read_text()
        tui = spawn(COPIER_PATH + ("update",), timeout=30)
        # Check what was captured
        expect_prompt(tui, "in_love", "bool")
        tui.expect_exact("(Y/n)")
        tui.sendline()
        expect_prompt(tui, "your_name", "str", help="If you have a name, tell me now.")
        tui.expect_exact(name)
        tui.sendline()
        expect_prompt(tui, "your_enemy", "str", help="Secret enemy name")
        tui.expect_exact("******")
        tui.sendline()
        expect_prompt(tui, "what_enemy_does", "str")
        tui.expect_exact(f"Bowser hates {name}")
        tui.sendline()
        tui.expect_exact(pexpect.EOF)
        assert "_commit: v2" in Path(".copier-answers.yml").read_text()


@pytest.mark.parametrize(
    "name, args",
    [
        ("Mario", ()),  # Default name in the template
        ("Luigi", ("--data=your_name=Luigi",)),
        ("None", ("--data=your_name=None",)),
    ],
)
@pytest.mark.parametrize("update_action", ("update", "recopy"))
def test_update_skip_answered(
    tmp_path_factory: pytest.TempPathFactory,
    spawn: Spawn,
    name: str,
    update_action: str,
    args: tuple[str, ...],
) -> None:
    """Test that the questions for the user are OK."""
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))
    with local.cwd(src):
        build_file_tree(MARIO_TREE)
        git_save(tag="v1")
        git("commit", "--allow-empty", "-m", "v2")
        git("tag", "v2")
    with local.cwd(dst):
        # Copy the v1 template
        tui = spawn(
            COPIER_PATH + ("copy", str(src), ".", "--vcs-ref=v1") + args, timeout=10
        )
        # Check what was captured
        expect_prompt(tui, "in_love", "bool")
        tui.expect_exact("(Y/n)")
        tui.sendline()
        tui.expect_exact("Yes")
        if not args:
            expect_prompt(
                tui, "your_name", "str", help="If you have a name, tell me now."
            )
            tui.expect_exact(name)
            tui.sendline()
        expect_prompt(tui, "your_enemy", "str", help="Secret enemy name")
        tui.expect_exact("******")
        tui.sendline()
        expect_prompt(tui, "what_enemy_does", "str")
        tui.expect_exact(f"Bowser hates {name}")
        tui.sendline()
        tui.expect_exact(pexpect.EOF)
        assert "_commit: v1" in Path(".copier-answers.yml").read_text()
        # Update subproject
        git_save()
        tui = spawn(
            COPIER_PATH
            + (
                update_action,
                "--skip-answered",
            ),
            timeout=30,
        )
        # Check what was captured
        expect_prompt(tui, "your_enemy", "str", help="Secret enemy name")
        tui.expect_exact("******")
        tui.sendline()
        tui.expect_exact(pexpect.EOF)
        assert "_commit: v2" in Path(".copier-answers.yml").read_text()


@pytest.mark.parametrize(
    "name, args",
    [
        ("Mario", ()),  # Default name in the template
        ("Luigi", ("--data=your_name=Luigi",)),
        ("None", ("--data=your_name=None",)),
    ],
)
def test_update_with_new_field_in_new_version_skip_answered(
    tmp_path_factory: pytest.TempPathFactory,
    spawn: Spawn,
    name: str,
    args: tuple[str, ...],
) -> None:
    """Test that the questions for the user are OK."""
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))
    with local.cwd(src):
        build_file_tree(MARIO_TREE)
        git_save(tag="v1")
        build_file_tree(MARIO_TREE_WITH_NEW_FIELD)
        git_save(tag="v2")
    with local.cwd(dst):
        # Copy the v1 template
        tui = spawn(
            COPIER_PATH + ("copy", str(src), ".", "--vcs-ref=v1") + args, timeout=10
        )
        # Check what was captured
        expect_prompt(tui, "in_love", "bool")
        tui.expect_exact("(Y/n)")
        tui.sendline()
        tui.expect_exact("Yes")
        if not args:
            expect_prompt(
                tui, "your_name", "str", help="If you have a name, tell me now."
            )
            tui.expect_exact(name)
            tui.sendline()
        expect_prompt(tui, "your_enemy", "str", help="Secret enemy name")
        tui.expect_exact("******")
        tui.sendline()
        expect_prompt(tui, "what_enemy_does", "str")
        tui.expect_exact(f"Bowser hates {name}")
        tui.sendline()
        tui.expect_exact(pexpect.EOF)
        assert "_commit: v1" in Path(".copier-answers.yml").read_text()
        # Update subproject
        git_save()
        tui = spawn(
            COPIER_PATH
            + (
                "update",
                "-A",
            ),
            timeout=30,
        )
        # Check what was captured
        expect_prompt(tui, "your_enemy", "str", help="Secret enemy name")
        tui.expect_exact("******")
        tui.sendline()
        expect_prompt(tui, "your_sister", "str", help="Your sister's name")
        tui.expect_exact("Luigi")
        tui.sendline()
        tui.expect_exact(pexpect.EOF)
        assert "_commit: v2" in Path(".copier-answers.yml").read_text()


@pytest.mark.parametrize(
    "question_1",
    # All these values evaluate to true
    (
        True,
        1,
        1.1,
        -1,
        -0.001,
        "1",
        "1.1",
        "1st",
        "-1",
        "0.1",
        "00001",
        "000.0001",
        "-0001",
        "-000.001",
        "+001",
        "+000.001",
        "hello! 🤗",
    ),
)
@pytest.mark.parametrize(
    "question_2_when, asks",
    (
        (True, True),
        (False, False),
        ("trUe", True),
        ("faLse", False),
        ("Yes", True),
        ("nO", False),
        ("Y", True),
        ("N", False),
        ("on", True),
        ("off", False),
        ("~", False),
        ("NonE", False),
        ("nulL", False),
        ("[[ question_1 ]]", True),
        ("[[ not question_1 ]]", False),
        ("[% if question_1 %]YES[% endif %]", True),
        ("[% if question_1 %]FALSE[% endif %]", False),
    ),
)
def test_when(
    tmp_path_factory: pytest.TempPathFactory,
    spawn: Spawn,
    question_1: str | int | float | bool,
    question_2_when: bool | str,
    asks: bool,
) -> None:
    """Test that the 2nd question is skipped or not, properly."""
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))
    questions = {
        "_envops": BRACKET_ENVOPS,
        "_templates_suffix": SUFFIX_TMPL,
        "question_1": question_1,
        "question_2": {"default": "something", "type": "yaml", "when": question_2_when},
    }
    build_file_tree(
        {
            (src / "copier.yml"): yaml.dump(questions),
            (src / "[[ _copier_conf.answers_file ]].tmpl"): (
                "[[ _copier_answers|to_nice_yaml ]]"
            ),
            (src / "context.yml.tmpl"): (
                """\
                question_2: [[ question_2 ]]
                """
            ),
        }
    )
    tui = spawn(COPIER_PATH + ("copy", str(src), str(dst)), timeout=10)
    expect_prompt(tui, "question_1", type(question_1).__name__)
    tui.sendline()
    if asks:
        expect_prompt(tui, "question_2", "yaml")
        tui.sendline()
    tui.expect_exact(pexpect.EOF)
    answers = yaml.safe_load((dst / ".copier-answers.yml").read_text())
    assert answers == {
        "_src_path": str(src),
        "question_1": question_1,
        **({"question_2": "something"} if asks else {}),
    }
    context = yaml.safe_load((dst / "context.yml").read_text())
    assert context == {"question_2": "something"}


def test_placeholder(tmp_path_factory: pytest.TempPathFactory, spawn: Spawn) -> None:
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))
    build_file_tree(
        {
            (src / "copier.yml"): yaml.dump(
                {
                    "_envops": BRACKET_ENVOPS,
                    "_templates_suffix": SUFFIX_TMPL,
                    "question_1": "answer 1",
                    "question_2": {
                        "type": "str",
                        "help": "write a list of answers",
                        "placeholder": "Write something like [[ question_1 ]], but better",  # noqa: E501
                    },
                }
            ),
            (src / "[[ _copier_conf.answers_file ]].tmpl"): (
                "[[ _copier_answers|to_nice_yaml ]]"
            ),
        }
    )
    tui = spawn(COPIER_PATH + ("copy", str(src), str(dst)), timeout=10)
    expect_prompt(tui, "question_1", "str")
    tui.expect_exact("answer 1")
    tui.sendline()
    expect_prompt(tui, "question_2", "str", help="write a list of answers")
    tui.expect_exact("Write something like answer 1, but better")
    tui.sendline()
    tui.expect_exact(pexpect.EOF)
    answers = yaml.safe_load((dst / ".copier-answers.yml").read_text())
    assert answers == {
        "_src_path": str(src),
        "question_1": "answer 1",
        "question_2": "",
    }


@pytest.mark.parametrize("type_", ["str", "yaml", "json"])
def test_multiline(
    tmp_path_factory: pytest.TempPathFactory, spawn: Spawn, type_: str
) -> None:
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))
    build_file_tree(
        {
            (src / "copier.yml"): yaml.dump(
                {
                    "_envops": BRACKET_ENVOPS,
                    "_templates_suffix": SUFFIX_TMPL,
                    "question_1": "answer 1",
                    "question_2": {"type": type_},
                    "question_3": {"type": type_, "multiline": True},
                    "question_4": {
                        "type": type_,
                        "multiline": "[[ question_1 == 'answer 1' ]]",
                    },
                    "question_5": {
                        "type": type_,
                        "multiline": "[[ question_1 != 'answer 1' ]]",
                    },
                }
            ),
            (src / "[[ _copier_conf.answers_file ]].tmpl"): (
                "[[ _copier_answers|to_nice_yaml ]]"
            ),
        }
    )
    tui = spawn(COPIER_PATH + ("copy", str(src), str(dst)), timeout=10)
    expect_prompt(tui, "question_1", "str")
    tui.expect_exact("answer 1")
    tui.sendline()
    expect_prompt(tui, "question_2", type_)
    tui.sendline('"answer 2"')
    expect_prompt(tui, "question_3", type_)
    tui.sendline('"answer 3"')
    tui.send(Keyboard.Alt + Keyboard.Enter)
    expect_prompt(tui, "question_4", type_)
    tui.sendline('"answer 4"')
    tui.send(Keyboard.Alt + Keyboard.Enter)
    expect_prompt(tui, "question_5", type_)
    tui.sendline('"answer 5"')
    tui.expect_exact(pexpect.EOF)
    answers = yaml.safe_load((dst / ".copier-answers.yml").read_text())
    if type_ == "str":
        assert answers == {
            "_src_path": str(src),
            "question_1": "answer 1",
            "question_2": '"answer 2"',
            "question_3": ('"answer 3"\n'),
            "question_4": ('"answer 4"\n'),
            "question_5": ('"answer 5"'),
        }
    else:
        assert answers == {
            "_src_path": str(src),
            "question_1": "answer 1",
            "question_2": ("answer 2"),
            "question_3": ("answer 3"),
            "question_4": ("answer 4"),
            "question_5": ("answer 5"),
        }


@pytest.mark.parametrize(
    "choices",
    (
        [1, 2, 3],
        [["one", 1], ["two", 2], ["three", 3]],
        {"one": 1, "two": 2, "three": 3},
    ),
)
def test_update_choice(
    tmp_path_factory: pytest.TempPathFactory,
    spawn: Spawn,
    choices: list[int] | list[list[str | int]] | dict[str, int],
) -> None:
    """Choices are properly remembered and selected in TUI when updating."""
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))
    # Create template
    build_file_tree(
        {
            (src / "copier.yml"): (
                f"""\
                _templates_suffix: {SUFFIX_TMPL}
                _envops: {BRACKET_ENVOPS_JSON}
                pick_one:
                    type: float
                    default: 3
                    choices: {choices}
                """
            ),
            (src / "[[ _copier_conf.answers_file ]].tmpl"): (
                "[[ _copier_answers|to_nice_yaml ]]"
            ),
        }
    )
    with local.cwd(src):
        git("init")
        git("add", ".")
        git("commit", "-m one")
        git("tag", "v1")
    # Copy
    tui = spawn(COPIER_PATH + ("copy", str(src), str(dst)), timeout=10)
    expect_prompt(tui, "pick_one", "float")
    tui.sendline(Keyboard.Up)
    tui.expect_exact(pexpect.EOF)
    answers = yaml.safe_load((dst / ".copier-answers.yml").read_text())
    assert answers["pick_one"] == 2.0
    with local.cwd(dst):
        git("init")
        git("add", ".")
        git("commit", "-m1")
    # Update
    tui = spawn(
        COPIER_PATH
        + (
            "update",
            str(dst),
        ),
        timeout=10,
    )
    expect_prompt(tui, "pick_one", "float")
    tui.sendline(Keyboard.Down)
    tui.expect_exact(pexpect.EOF)
    answers = yaml.safe_load((dst / ".copier-answers.yml").read_text())
    assert answers["pick_one"] == 3.0


@pytest.mark.skip("TODO: fix this")
def test_multiline_defaults(
    tmp_path_factory: pytest.TempPathFactory, spawn: Spawn
) -> None:
    """Multiline questions with scalar defaults produce multiline defaults."""
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))
    build_file_tree(
        {
            (src / "copier.yaml"): (
                """\
                yaml_single:
                    type: yaml
                    default: &default
                        - one
                        - two
                        - three:
                            - four
                yaml_multi:
                    type: yaml
                    multiline: "{{ 'me' == ('m' + 'e') }}"
                    default: *default
                json_single:
                    type: json
                    default: *default
                json_multi:
                    type: json
                    multiline: yes
                    default: *default
                """
            ),
            (src / "{{ _copier_conf.answers_file }}.jinja"): (
                "{{ _copier_answers|to_nice_yaml }}"
            ),
        }
    )
    tui = spawn(COPIER_PATH + ("copy", str(src), str(dst)), timeout=10)
    expect_prompt(tui, "yaml_single", "yaml")
    # This test will always fail here, because python prompt toolkit gives
    # syntax highlighting to YAML and JSON outputs, encoded into terminal
    # colors and all that stuff.
    # TODO Fix this test some day.
    tui.expect_exact("[one, two, {three: [four]}]")
    tui.send(Keyboard.Enter)
    expect_prompt(tui, "yaml_multi", "yaml")
    tui.expect_exact("> - one\n  - two\n  - three:\n    - four")
    tui.send(Keyboard.Alt + Keyboard.Enter)
    expect_prompt(tui, "json_single", "json")
    tui.expect_exact('["one", "two", {"three": ["four"]}]')
    tui.send(Keyboard.Enter)
    expect_prompt(tui, "json_multi", "json")
    tui.expect_exact(
        '> [\n    "one",\n    "two",\n    {\n      "three": [\n        "four"\n      ]\n    }\n  ]'  # noqa: E501
    )
    tui.send(Keyboard.Alt + Keyboard.Enter)
    tui.expect_exact(pexpect.EOF)
    answers = yaml.safe_load((dst / ".copier-answers.yml").read_text())
    assert (
        answers["yaml_single"]
        == answers["yaml_multi"]
        == answers["json_single"]
        == answers["json_multi"]
        == ["one", "two", {"three": ["four"]}]
    )


def test_partial_interrupt(
    tmp_path_factory: pytest.TempPathFactory,
    spawn: Spawn,
) -> None:
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))
    build_file_tree(
        {
            (src / "copier.yml"): yaml.safe_dump(
                {
                    "question_1": "answer 1",
                    "question_2": "answer 2",
                }
            ),
        }
    )
    tui = spawn(COPIER_PATH + ("copy", str(src), str(dst)), timeout=10)
    expect_prompt(tui, "question_1", "str")
    tui.expect_exact("answer 1")
    # Answer the first question using the default.
    tui.sendline()
    # Send a ctrl-c.
    tui.send(Keyboard.ControlC + Keyboard.Enter)
    # This string (or similar) should show in the output if we've gracefully caught the
    # interrupt.
    # We won't want our custom exception (CopierAnswersInterrupt) propagating
    # to an uncaught stacktrace.
    tui.expect_exact("Execution stopped by user\n")
    tui.expect_exact(pexpect.EOF)


def test_var_name_value_allowed(
    tmp_path_factory: pytest.TempPathFactory, spawn: Spawn
) -> None:
    """Test that a question var name "value" causes no name collision.

    See https://github.com/copier-org/copier/pull/780 for more details.
    """
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))

    # Create template
    build_file_tree(
        {
            (src / "copier.yaml"): (
                """\
                value:
                    type: str
                    default: string
                """
            ),
            (src / "{{ _copier_conf.answers_file }}.jinja"): (
                "{{ _copier_answers|to_nice_yaml }}"
            ),
        }
    )
    # Copy
    tui = spawn(COPIER_PATH + ("copy", str(src), str(dst)), timeout=10)
    expect_prompt(tui, "value", "str")
    tui.expect_exact("string")
    tui.send(Keyboard.Alt + Keyboard.Enter)
    tui.expect_exact(pexpect.EOF)
    # Check answers file
    answers = yaml.safe_load((dst / ".copier-answers.yml").read_text())
    assert answers["value"] == "string"


@pytest.mark.parametrize(
    "type_name, expected_answer",
    [
        ("str", ""),
        ("int", ValueError("Invalid input")),
        ("float", ValueError("Invalid input")),
        ("json", ValueError("Invalid input")),
        ("yaml", None),
    ],
)
def test_required_text_question(
    tmp_path_factory: pytest.TempPathFactory,
    spawn: Spawn,
    type_name: str,
    expected_answer: str | None | ValueError,
) -> None:
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))
    build_file_tree(
        {
            (src / "copier.yml"): yaml.dump(
                {
                    "_envops": BRACKET_ENVOPS,
                    "_templates_suffix": SUFFIX_TMPL,
                    "question": {"type": type_name},
                }
            ),
            (src / "[[ _copier_conf.answers_file ]].tmpl"): (
                "[[ _copier_answers|to_nice_yaml ]]"
            ),
        }
    )
    tui = spawn(COPIER_PATH + ("copy", str(src), str(dst)), timeout=10)
    expect_prompt(tui, "question", type_name)
    tui.expect_exact("")
    tui.sendline()
    if isinstance(expected_answer, ValueError):
        tui.expect_exact(str(expected_answer))
        assert not (dst / ".copier-answers.yml").exists()
    else:
        tui.expect_exact(pexpect.EOF)
        answers = yaml.safe_load((dst / ".copier-answers.yml").read_text())
        assert answers == {
            "_src_path": str(src),
            "question": expected_answer,
        }


def test_required_bool_question(
    tmp_path_factory: pytest.TempPathFactory, spawn: Spawn
) -> None:
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))
    build_file_tree(
        {
            (src / "copier.yml"): yaml.dump(
                {
                    "_envops": BRACKET_ENVOPS,
                    "_templates_suffix": SUFFIX_TMPL,
                    "question": {"type": "bool"},
                }
            ),
            (src / "[[ _copier_conf.answers_file ]].tmpl"): (
                "[[ _copier_answers|to_nice_yaml ]]"
            ),
        }
    )
    tui = spawn(COPIER_PATH + ("copy", str(src), str(dst)), timeout=10)
    expect_prompt(tui, "question", "bool")
    tui.expect_exact("(y/N)")
    tui.sendline()
    tui.expect_exact(pexpect.EOF)
    answers = yaml.safe_load((dst / ".copier-answers.yml").read_text())
    assert answers == {
        "_src_path": str(src),
        "question": False,
    }


@pytest.mark.parametrize(
    "type_name, choices, expected_answer",
    [
        ("str", ["one", "two", "three"], "one"),
        ("int", [1, 2, 3], 1),
        ("float", [1.0, 2.0, 3.0], 1.0),
        ("json", ["[1]", "[2]", "[3]"], [1]),
        ("yaml", ["- 1", "- 2", "- 3"], [1]),
    ],
)
def test_required_choice_question(
    tmp_path_factory: pytest.TempPathFactory,
    spawn: Spawn,
    type_name: str,
    choices: list[Any],
    expected_answer: Any,
) -> None:
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))
    build_file_tree(
        {
            (src / "copier.yml"): yaml.dump(
                {
                    "_envops": BRACKET_ENVOPS,
                    "_templates_suffix": SUFFIX_TMPL,
                    "question": {
                        "type": type_name,
                        "choices": choices,
                    },
                }
            ),
            (src / "[[ _copier_conf.answers_file ]].tmpl"): (
                "[[ _copier_answers|to_nice_yaml ]]"
            ),
        }
    )
    tui = spawn(COPIER_PATH + ("copy", str(src), str(dst)), timeout=10)
    expect_prompt(tui, "question", type_name)
    tui.sendline()
    tui.expect_exact(pexpect.EOF)
    answers = yaml.safe_load((dst / ".copier-answers.yml").read_text())
    assert answers == {
        "_src_path": str(src),
        "question": expected_answer,
    }


QuestionType: TypeAlias = str
QuestionChoices: TypeAlias = Union[List[Any], Dict[str, Any]]
ParsedValues: TypeAlias = List[Any]

_CHOICES: dict[str, tuple[QuestionType, QuestionChoices, ParsedValues]] = {
    "str": ("str", ["one", "two", "three"], ["one", "two", "three"]),
    "int": ("int", [1, 2, 3], [1, 2, 3]),
    "int-label-list": ("int", [["one", 1], ["two", 2], ["three", 3]], [1, 2, 3]),
    "int-label-dict": ("int", {"1. one": 1, "2. two": 2, "3. three": 3}, [1, 2, 3]),
    "float": ("float", [1.0, 2.0, 3.0], [1.0, 2.0, 3.0]),
    "json": ("json", ["[1]", "[2]", "[3]"], [[1], [2], [3]]),
    "yaml": ("yaml", ["- 1", "- 2", "- 3"], [[1], [2], [3]]),
}
CHOICES = [pytest.param(*specs, id=id) for id, specs in _CHOICES.items()]


class QuestionTreeFixture(Protocol):
    def __call__(self, **kwargs) -> tuple[Path, Path]: ...


@pytest.fixture
def question_tree(tmp_path_factory: pytest.TempPathFactory) -> QuestionTreeFixture:
    def builder(**question) -> tuple[Path, Path]:
        src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))
        build_file_tree(
            {
                (src / "copier.yml"): yaml.dump(
                    {
                        "_envops": BRACKET_ENVOPS,
                        "_templates_suffix": SUFFIX_TMPL,
                        "question": question,
                    }
                ),
                (src / "[[ _copier_conf.answers_file ]].tmpl"): (
                    "[[ _copier_answers|to_nice_yaml ]]"
                ),
            }
        )
        return src, dst

    return builder


class CopierFixture(Protocol):
    def __call__(self, *args, **kwargs) -> PopenSpawn: ...


@pytest.fixture
def copier(spawn: Spawn) -> CopierFixture:
    """Multiple choices are properly remembered and selected in TUI when updating."""

    def fixture(*args, **kwargs) -> PopenSpawn:
        return spawn(COPIER_PATH + args, **kwargs)

    return fixture


@pytest.mark.parametrize("type_name, choices, values", CHOICES)
def test_multiselect_choices_question_single_answer(
    question_tree: QuestionTreeFixture,
    copier: CopierFixture,
    type_name: QuestionType,
    choices: QuestionChoices,
    values: ParsedValues,
) -> None:
    src, dst = question_tree(type=type_name, choices=choices, multiselect=True)
    tui = copier("copy", str(src), str(dst), timeout=10)
    expect_prompt(tui, "question", type_name)
    tui.send(" ")  # select 1
    tui.sendline()
    tui.expect_exact(pexpect.EOF)
    answers = yaml.safe_load((dst / ".copier-answers.yml").read_text())
    assert answers["question"] == values[:1]


@pytest.mark.parametrize("type_name, choices, values", CHOICES)
def test_multiselect_choices_question_multiple_answers(
    question_tree: QuestionTreeFixture,
    copier: CopierFixture,
    type_name: QuestionType,
    choices: QuestionChoices,
    values: ParsedValues,
) -> None:
    src, dst = question_tree(type=type_name, choices=choices, multiselect=True)
    tui = copier("copy", str(src), str(dst), timeout=10)
    expect_prompt(tui, "question", type_name)
    tui.send(" ")  # select 0
    tui.send(Keyboard.Down)
    tui.send(" ")  # select 1
    tui.sendline()
    tui.expect_exact(pexpect.EOF)
    answers = yaml.safe_load((dst / ".copier-answers.yml").read_text())
    assert answers["question"] == values[:2]


@pytest.mark.parametrize("type_name, choices, values", CHOICES)
def test_multiselect_choices_question_with_default(
    question_tree: QuestionTreeFixture,
    copier: CopierFixture,
    type_name: QuestionType,
    choices: QuestionChoices,
    values: ParsedValues,
) -> None:
    src, dst = question_tree(
        type=type_name, choices=choices, multiselect=True, default=values
    )
    tui = copier("copy", str(src), str(dst), timeout=10)
    expect_prompt(tui, "question", type_name)
    tui.send(" ")  # toggle first
    tui.sendline()
    tui.expect_exact(pexpect.EOF)
    answers = yaml.safe_load((dst / ".copier-answers.yml").read_text())
    assert answers["question"] == values[1:]


@pytest.mark.parametrize("type_name, choices, values", CHOICES)
def test_update_multiselect_choices(
    question_tree: QuestionTreeFixture,
    copier: CopierFixture,
    type_name: QuestionType,
    choices: QuestionChoices,
    values: ParsedValues,
) -> None:
    """Multiple choices are properly remembered and selected in TUI when updating."""
    src, dst = question_tree(
        type=type_name, choices=choices, multiselect=True, default=values
    )

    with local.cwd(src):
        git("init")
        git("add", ".")
        git("commit", "-m one")
        git("tag", "v1")

    # Copy
    tui = copier("copy", str(src), str(dst), timeout=10)
    expect_prompt(tui, "question", type_name)
    tui.send(" ")  # toggle first
    tui.sendline()
    tui.expect_exact(pexpect.EOF)
    answers = yaml.safe_load((dst / ".copier-answers.yml").read_text())
    assert answers["question"] == values[1:]

    with local.cwd(dst):
        git("init")
        git("add", ".")
        git("commit", "-m1")

    # Update
    tui = copier("update", str(dst), timeout=10)
    expect_prompt(tui, "question", type_name)
    tui.send(" ")  # toggle first
    tui.sendline()
    tui.expect_exact(pexpect.EOF)
    answers = yaml.safe_load((dst / ".copier-answers.yml").read_text())
    assert answers["question"] == values


def test_multiselect_choices_validator(
    question_tree: QuestionTreeFixture, copier: CopierFixture
) -> None:
    """Multiple choices are validated."""
    src, dst = question_tree(
        type="str",
        choices=["one", "two", "three"],
        multiselect=True,
        validator=("[%- if not question -%]At least one choice required[%- endif -%]"),
    )

    tui = copier("copy", str(src), str(dst), timeout=10)
    expect_prompt(tui, "question", "str")
    tui.sendline()
    tui.expect_exact("At least one choice required")
    tui.send(" ")  # select "one"
    tui.sendline()
    tui.expect_exact(pexpect.EOF)
    answers = yaml.safe_load((dst / ".copier-answers.yml").read_text())
    assert answers["question"] == ["one"]
