import json
from collections import deque
from pathlib import Path
from textwrap import dedent

import pexpect
import pytest
import yaml
from pexpect.popen_spawn import PopenSpawn
from plumbum import local
from plumbum.cmd import git

from copier import run_copy, run_update
from copier.types import OptStr

from .helpers import (
    BRACKET_ENVOPS,
    BRACKET_ENVOPS_JSON,
    COPIER_PATH,
    SUFFIX_TMPL,
    Keyboard,
    Spawn,
    build_file_tree,
    expect_prompt,
)

BLK_START = BRACKET_ENVOPS["block_start_string"]
BLK_END = BRACKET_ENVOPS["block_end_string"]


@pytest.fixture(scope="module")
def template_path(tmp_path_factory: pytest.TempPathFactory) -> str:
    root = tmp_path_factory.mktemp("template")
    build_file_tree(
        {
            (root / "copier.yml"): (
                f"""\
                _templates_suffix: {SUFFIX_TMPL}
                _envops: {BRACKET_ENVOPS_JSON}
                love_me:
                    help: I need to know it. Do you love me?
                    type: bool
                your_name:
                    help: Please tell me your name.
                    type: str
                your_age:
                    help: How old are you?
                    type: int
                    validator: |-
                        [% if your_age <= 0 %]
                            Must be +
                        [% endif %]
                your_height:
                    help: What's your height?
                    type: float
                more_json_info:
                    multiline: true
                    type: json
                anything_else:
                    multiline: true
                    help: Wanna give me any more info?

                # In choices, the user will always write the choice index (1, 2, 3...)
                choose_list:
                    help: You see the value of the list items
                    default: first
                    choices:
                        - first
                        - second
                        - third
                choose_tuple:
                    help: You see the 1st tuple item, but I get the 2nd item as a result
                    default: second
                    choices:
                        - [one, first]
                        - [two, second]
                        - [three, third]
                choose_dict:
                    help: You see the dict key, but I get the dict value
                    default: third
                    choices:
                        one: first
                        two: second
                        three: third
                choose_number:
                    help: This must be a number
                    default: -1.1
                    type: float
                    choices:
                        - -1.1
                        - 0
                        - 1

                # Simplified format is still supported
                minutes_under_water: 10
                optional_value: null
                """
            ),
            (root / "results.txt.tmpl"): (
                """\
                love_me: [[love_me|tojson]]
                your_name: [[your_name|tojson]]
                your_age: [[your_age|tojson]]
                your_height: [[your_height|tojson]]
                more_json_info: [[more_json_info|tojson]]
                anything_else: [[anything_else|tojson]]
                choose_list: [[choose_list|tojson]]
                choose_tuple: [[choose_tuple|tojson]]
                choose_dict: [[choose_dict|tojson]]
                choose_number: [[choose_number|tojson]]
                minutes_under_water: [[minutes_under_water|tojson]]
                optional_value: [[optional_value|tojson]]
            """
            ),
        }
    )
    return str(root)


def check_invalid(
    tui: PopenSpawn,
    name: str,
    format: str,
    invalid_value: str,
    help: OptStr = None,
    err: str = "Invalid input",
) -> None:
    """Check that invalid input is reported correctly."""
    expect_prompt(tui, name, format, help)
    tui.sendline(invalid_value)
    tui.expect_exact(invalid_value)
    tui.expect_exact(err)


def test_api(template_path: str, tmp_path: Path) -> None:
    """Test copier correctly processes advanced questions and answers through API."""
    run_copy(
        template_path,
        tmp_path,
        {
            "love_me": False,
            "your_name": "LeChuck",
            "your_age": 220,
            "your_height": 1.9,
            "more_json_info": ["bad", "guy"],
            "anything_else": {"hates": "all"},
        },
        defaults=True,
        overwrite=True,
    )
    assert (tmp_path / "results.txt").read_text() == dedent(
        """\
            love_me: false
            your_name: "LeChuck"
            your_age: 220
            your_height: 1.9
            more_json_info: ["bad", "guy"]
            anything_else: {"hates": "all"}
            choose_list: "first"
            choose_tuple: "second"
            choose_dict: "third"
            choose_number: -1.1
            minutes_under_water: 10
            optional_value: null
        """
    )


def test_cli_interactive(template_path: str, tmp_path: Path, spawn: Spawn) -> None:
    """Test copier correctly processes advanced questions and answers through CLI."""
    tui = spawn(COPIER_PATH + ("copy", template_path, str(tmp_path)), timeout=10)
    expect_prompt(tui, "love_me", "bool", help="I need to know it. Do you love me?")
    tui.send("y")
    expect_prompt(tui, "your_name", "str", help="Please tell me your name.")
    tui.sendline("Guybrush Threpwood")
    check_invalid(tui, "your_age", "int", "wrong your_age", help="How old are you?")
    tui.send((Keyboard.Alt + Keyboard.Backspace) * 2)
    tui.send("-1")
    tui.expect_exact("Must be +")
    tui.send(Keyboard.Backspace * 2)
    tui.sendline("22")
    check_invalid(
        tui, "your_height", "float", "wrong your_height", help="What's your height?"
    )
    tui.send((Keyboard.Alt + Keyboard.Backspace) * 2)
    tui.sendline("1.56")
    check_invalid(tui, "more_json_info", "json", '{"objective":')
    tui.sendline('"be a pirate"}')
    tui.send(Keyboard.Esc + Keyboard.Enter)
    expect_prompt(tui, "anything_else", "yaml", help="Wanna give me any more info?")
    tui.sendline("- Want some grog?")
    tui.sendline("- I'd love it")
    tui.send(Keyboard.Esc + Keyboard.Enter)
    expect_prompt(tui, "choose_list", "str", help="You see the value of the list items")
    deque(
        map(
            tui.expect_exact,
            [
                "first",
                "second",
                "third",
            ],
        )
    )
    tui.sendline()
    expect_prompt(
        tui,
        "choose_tuple",
        "str",
        help="You see the 1st tuple item, but I get the 2nd item as a result",
    )
    deque(
        map(
            tui.expect_exact,
            [
                "one",
                "two",
                "three",
            ],
        )
    )
    tui.sendline()
    expect_prompt(
        tui, "choose_dict", "str", help="You see the dict key, but I get the dict value"
    )
    deque(
        map(
            tui.expect_exact,
            [
                "one",
                "two",
                "three",
            ],
        )
    )
    tui.sendline()
    expect_prompt(tui, "choose_number", "float", help="This must be a number")
    deque(
        map(
            tui.expect_exact,
            ["-1.1", "0", "1"],
        )
    )
    tui.sendline()
    expect_prompt(tui, "minutes_under_water", "int")
    tui.expect_exact("10")
    tui.send(Keyboard.Backspace)
    tui.sendline()
    expect_prompt(tui, "optional_value", "yaml")
    tui.sendline()
    tui.expect_exact(pexpect.EOF)
    assert (tmp_path / "results.txt").read_text() == dedent(
        """\
            love_me: true
            your_name: "Guybrush Threpwood"
            your_age: 22
            your_height: 1.56
            more_json_info: {"objective": "be a pirate"}
            anything_else: ["Want some grog?", "I\\u0027d love it"]
            choose_list: "first"
            choose_tuple: "second"
            choose_dict: "third"
            choose_number: -1.1
            minutes_under_water: 1
            optional_value: null
        """
    )


def test_api_str_data(template_path: str, tmp_path: Path) -> None:
    """Test copier when all data comes as a string.

    This happens i.e. when using the --data CLI argument.
    """
    run_copy(
        template_path,
        tmp_path,
        data={
            "love_me": "false",
            "your_name": "LeChuck",
            "your_age": "220",
            "your_height": "1.9",
            "more_json_info": '["bad", "guy"]',
            "anything_else": "{'hates': 'all'}",
            "choose_number": "0",
        },
        defaults=True,
        overwrite=True,
    )
    assert (tmp_path / "results.txt").read_text() == dedent(
        """\
            love_me: false
            your_name: "LeChuck"
            your_age: 220
            your_height: 1.9
            more_json_info: ["bad", "guy"]
            anything_else: {"hates": "all"}
            choose_list: "first"
            choose_tuple: "second"
            choose_dict: "third"
            choose_number: 0.0
            minutes_under_water: 10
            optional_value: null
        """
    )


def test_cli_interatively_with_flag_data_and_type_casts(
    template_path: str, tmp_path: Path, spawn: Spawn
) -> None:
    """Assert how choices work when copier is invoked with --data interactively."""
    tui = spawn(
        COPIER_PATH
        + (
            "copy",
            "--data=choose_list=second",
            "--data=choose_dict=first",
            "--data=choose_tuple=third",
            "--data=choose_number=1",
            template_path,
            str(tmp_path),
        ),
        timeout=10,
    )
    expect_prompt(tui, "love_me", "bool", help="I need to know it. Do you love me?")
    tui.send("y")
    expect_prompt(tui, "your_name", "str", help="Please tell me your name.")
    tui.sendline("Guybrush Threpwood")
    check_invalid(tui, "your_age", "int", "wrong your_age", help="How old are you?")
    tui.sendline()  # Does nothing, "wrong your_age still on screen"
    tui.send((Keyboard.Alt + Keyboard.Backspace) * 2)
    tui.sendline("22")
    check_invalid(
        tui, "your_height", "float", "wrong your_height", help="What's your height?"
    )
    tui.send((Keyboard.Alt + Keyboard.Backspace) * 2)
    tui.sendline("1.56")
    check_invalid(tui, "more_json_info", "json", '{"objective":')
    tui.sendline('"be a pirate"}')
    tui.send(Keyboard.Esc + Keyboard.Enter)
    expect_prompt(tui, "anything_else", "yaml", help="Wanna give me any more info?")
    tui.sendline("- Want some grog?")
    tui.sendline("- I'd love it")
    tui.send(Keyboard.Esc + Keyboard.Enter)
    expect_prompt(tui, "minutes_under_water", "int")
    tui.expect_exact("10")
    tui.sendline()
    expect_prompt(tui, "optional_value", "yaml")
    tui.sendline()
    tui.expect_exact(pexpect.EOF)
    results_file = tmp_path / "results.txt"
    assert results_file.read_text() == dedent(
        """\
            love_me: true
            your_name: "Guybrush Threpwood"
            your_age: 22
            your_height: 1.56
            more_json_info: {"objective": "be a pirate"}
            anything_else: ["Want some grog?", "I\\u0027d love it"]
            choose_list: "second"
            choose_tuple: "third"
            choose_dict: "first"
            choose_number: 1.0
            minutes_under_water: 10
            optional_value: null
        """
    )


@pytest.mark.parametrize(
    "has_2_owners, owner2", [(True, "example2"), (False, "example")]
)
def test_tui_inherited_default(
    tmp_path_factory: pytest.TempPathFactory,
    spawn: Spawn,
    has_2_owners: bool,
    owner2: str,
) -> None:
    """Make sure a template inherits default as expected."""
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))
    build_file_tree(
        {
            (src / "copier.yaml"): (
                """\
                owner1:
                    type: str
                has_2_owners:
                    type: bool
                    default: false
                owner2:
                    type: str
                    default: "{{ owner1 }}"
                    when: "{{ has_2_owners }}"
                """
            ),
            (src / "{{ _copier_conf.answers_file }}.jinja"): (
                "{{ _copier_answers|to_nice_yaml }}"
            ),
            (src / "answers.json.jinja"): "{{ _copier_answers|to_nice_json }}",
            (src / "context.json.jinja"): '{"owner2": "{{ owner2 }}"}',
        }
    )
    with local.cwd(src):
        git("init")
        git("add", "--all")
        git("commit", "--message", "init template")
        git("tag", "1")
    tui = spawn(COPIER_PATH + ("copy", str(src), str(dst)), timeout=10)
    expect_prompt(tui, "owner1", "str")
    tui.sendline("example")
    expect_prompt(tui, "has_2_owners", "bool")
    tui.expect_exact("(y/N)")
    tui.send("y" if has_2_owners else "n")
    if has_2_owners:
        expect_prompt(tui, "owner2", "str")
        tui.expect_exact("example")
        tui.sendline("2")
    tui.expect_exact(pexpect.EOF)
    result = {
        "_commit": "1",
        "_src_path": str(src),
        "has_2_owners": has_2_owners,
        "owner1": "example",
        **({"owner2": owner2} if has_2_owners else {}),
    }
    assert json.loads((dst / "answers.json").read_text()) == result
    assert json.loads((dst / "context.json").read_text()) == {"owner2": owner2}
    with local.cwd(dst):
        git("init")
        git("add", "--all")
        git("commit", "--message", "init project")
    # After a forced update, answers stay the same
    run_update(dst, defaults=True, overwrite=True)
    assert json.loads((dst / "answers.json").read_text()) == result


def test_tui_typed_default(
    tmp_path_factory: pytest.TempPathFactory, spawn: Spawn
) -> None:
    """Make sure a template defaults are typed as expected."""
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))
    build_file_tree(
        {
            (src / "copier.yaml"): (
                """\
                test1:
                    type: bool
                    default: false
                    when: false
                test2:
                    type: bool
                    default: "{{ 'a' == 'b' }}"
                    when: false
                """
            ),
            (src / "{{ _copier_conf.answers_file }}.jinja"): (
                "{{ _copier_answers|to_nice_yaml }}"
            ),
            (src / "answers.json.jinja"): "{{ _copier_answers|to_nice_json }}",
            (src / "context.json.jinja"): (
                """\
                {"test1": "{{ test1 }}", "test2": "{{ test2 }}"}
                """
            ),
        }
    )
    tui = spawn(COPIER_PATH + ("copy", str(src), str(dst)), timeout=10)
    tui.expect_exact(pexpect.EOF)
    assert json.loads((dst / "answers.json").read_text()) == {"_src_path": str(src)}
    assert json.loads((dst / "context.json").read_text()) == {
        "test1": "False",
        "test2": "False",
    }


def test_selection_type_cast(
    tmp_path_factory: pytest.TempPathFactory, spawn: Spawn
) -> None:
    """Selection question with different types, properly casted."""
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))
    build_file_tree(
        {
            (src / "copier.yaml"): (
                """\
                postgres1: &pg
                    type: yaml
                    default: 10
                    help: Which PostgreSQL version do you want to deploy?
                    choices:
                        I will use an external PostgreSQL server: null
                        "9.6": 9.6
                        "10": 10
                postgres2: *pg
                postgres3: *pg
                nulls1: &nulls
                    type: yaml
                    choices:
                        - [same as key, null]
                        - [yaml-casted to a real null, "null"]
                        - [becomes array, "[one, 2, -3.0]"]
                nulls2: *nulls
                nulls3: *nulls
                """
            ),
            (src / "answers.json.jinja"): "{{ _copier_answers|to_json }}",
        }
    )
    tui = spawn(COPIER_PATH + ("copy", str(src), str(dst)), timeout=10)
    expect_prompt(
        tui, "postgres1", "yaml", help="Which PostgreSQL version do you want to deploy?"
    )
    tui.sendline(Keyboard.Down)
    expect_prompt(
        tui, "postgres2", "yaml", help="Which PostgreSQL version do you want to deploy?"
    )
    tui.sendline(Keyboard.Up)
    expect_prompt(
        tui, "postgres3", "yaml", help="Which PostgreSQL version do you want to deploy?"
    )
    tui.sendline()
    expect_prompt(tui, "nulls1", "yaml")
    tui.sendline()
    expect_prompt(tui, "nulls2", "yaml")
    tui.sendline(Keyboard.Down)
    expect_prompt(tui, "nulls3", "yaml")
    tui.sendline(Keyboard.Down + Keyboard.Down)
    tui.expect_exact(pexpect.EOF)
    assert json.loads((dst / "answers.json").read_bytes()) == {
        "_src_path": str(src),
        "nulls1": "same as key",
        "nulls2": None,
        "nulls3": ["one", 2, -3.0],
        "postgres1": "I will use an external PostgreSQL server",
        "postgres2": 9.6,
        "postgres3": 10,
    }


def test_multi_template_answers(tmp_path_factory: pytest.TempPathFactory) -> None:
    tpl1, tpl2, dst = map(tmp_path_factory.mktemp, map(str, range(3)))
    # Build 2 templates with different questions and answers file defaults
    build_file_tree(
        {
            (tpl1 / "copier.yml"): "q1: a1",
            (tpl1 / "{{ _copier_conf.answers_file }}.jinja"): (
                "{{ _copier_answers|to_nice_yaml }}"
            ),
            (tpl2 / "copier.yml"): "{_answers_file: two.yml, q2: a2}",
            (tpl2 / "{{ _copier_conf.answers_file }}.jinja"): (
                "{{ _copier_answers|to_nice_yaml }}"
            ),
        }
    )
    # Make them git-tracked
    for tpl in (tpl1, tpl2):
        with local.cwd(tpl):
            git("init")
            git("add", "-A")
            git("commit", "-m1")
    with local.cwd(dst):
        # Apply template 1
        run_copy(str(tpl1), overwrite=True, defaults=True)
        git("init")
        git("add", "-A")
        git("commit", "-m1")
        # Apply template 2
        run_copy(str(tpl2), overwrite=True, defaults=True)
        git("init")
        git("add", "-A")
        git("commit", "-m2")
        # Check contents
        answers1 = yaml.safe_load(Path(".copier-answers.yml").read_text())
        assert answers1["_src_path"] == str(tpl1)
        assert answers1["q1"] == "a1"
        assert "q2" not in answers1
        answers2 = yaml.safe_load(Path("two.yml").read_text())
        assert answers2["_src_path"] == str(tpl2)
        assert answers2["q2"] == "a2"
        assert "q1" not in answers2


def test_omit_answer_for_skipped_question(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))
    build_file_tree(
        {
            (src / "copier.yml"): (
                """\
                disabled:
                    type: str
                    when: false

                disabled_with_default:
                    type: str
                    default: hello
                    when: false
                """
            ),
            (src / "{{ _copier_conf.answers_file }}.jinja"): (
                "{{ _copier_answers|to_nice_yaml }}"
            ),
            (src / "context.yml.jinja"): yaml.safe_dump(
                {
                    "disabled": "{{ disabled }}",
                    "disabled_with_default": "{{ disabled_with_default }}",
                }
            ),
        }
    )
    run_copy(str(src), dst, defaults=True, data={"disabled": "hello"})
    answers = yaml.safe_load((dst / ".copier-answers.yml").read_text())
    assert answers == {"_src_path": str(src)}
    context = yaml.safe_load((dst / "context.yml").read_text())
    assert context == {"disabled": "hello", "disabled_with_default": "hello"}
