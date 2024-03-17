from __future__ import annotations

from pathlib import Path
from textwrap import dedent
from typing import Any, Callable

import pytest
from plumbum import local
from plumbum.cmd import git
from pydantic import ValidationError

import copier
from copier.errors import InvalidConfigFileError, MultipleConfigFilesError
from copier.template import DEFAULT_EXCLUDE, Task, Template, load_template_config
from copier.types import AnyByStrDict

from .helpers import BRACKET_ENVOPS_JSON, SUFFIX_TMPL, build_file_tree

GOOD_ENV_OPS = {
    "autoescape": True,
    "block_start_string": "<%",
    "block_end_string": "%>",
    "variable_start_string": "<<",
    "variable_end_string": ">>",
    "keep_trailing_newline": False,
    "i_am_not_a_member": None,
    "comment_end_string": "#>",
    "comment_start_string": "<#",
}


def git_init(message="hello world") -> None:
    git("init")
    git("config", "user.name", "Copier Test")
    git("config", "user.email", "test@copier")
    git("add", ".")
    git("commit", "-m", message)


def test_config_data_is_loaded_from_file() -> None:
    tpl = Template("tests/demo_data")
    assert tpl.exclude == ("exclude1", "exclude2")
    assert tpl.skip_if_exists == ["skip_if_exists1", "skip_if_exists2"]
    assert tpl.tasks == [
        Task(cmd="touch 1", extra_env={"STAGE": "task"}),
        Task(cmd="touch 2", extra_env={"STAGE": "task"}),
    ]


def test_config_data_is_merged_from_files() -> None:
    tpl = Template("tests/demo_merge_options_from_answerfiles")
    assert list(tpl.skip_if_exists) == [
        "skip_if_exists0",
        "skip_if_exists1",
        "skip_if_exists2",
    ]
    assert list(tpl.exclude) == ["exclude1", "exclude21", "exclude22"]
    assert list(tpl.jinja_extensions) == ["jinja2.ext.0", "jinja2.ext.2"]
    assert list(tpl.secret_questions) == ["question1"]


@pytest.mark.parametrize("config_suffix", ["yaml", "yml"])
def test_read_data(
    tmp_path_factory: pytest.TempPathFactory, config_suffix: str
) -> None:
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))
    build_file_tree({
        (src / f"copier.{config_suffix}"): (
            f"""\
                # This is a comment
                _envops: {BRACKET_ENVOPS_JSON}
                a_string: lorem ipsum
                a_number: 12345
                a_boolean: true
                a_list:
                    - one
                    - two
                    - three
                """
        ),
        (src / "user_data.txt.jinja"): (
            """\
                A string: [[ a_string ]]
                A number: [[ a_number ]]
                A boolean: [[ a_boolean ]]
                A list: [[ ", ".join(a_list) ]]
                """
        ),
    })
    copier.run_copy(str(src), dst, defaults=True, overwrite=True)
    assert (dst / "user_data.txt").read_text() == dedent(
        """\
        A string: lorem ipsum
        A number: 12345
        A boolean: True
        A list: one, two, three
        """
    )


def test_invalid_yaml(capsys: pytest.CaptureFixture[str]) -> None:
    conf_path = Path("tests", "demo_invalid", "copier.yml")
    with pytest.raises(InvalidConfigFileError):
        load_template_config(conf_path)
    _, err = capsys.readouterr()
    assert "INVALID CONFIG FILE" in err
    assert str(conf_path) in err


@pytest.mark.parametrize(
    "conf_path, check_err",
    [
        ("tests/demo_invalid", lambda x: "INVALID" in x),
        # test key collision between including and included file
        ("tests/demo_transclude_invalid/demo", None),
        # test key collision between two included files
        ("tests/demo_transclude_invalid_multi/demo", None),
    ],
)
def test_invalid_config_data(
    capsys: pytest.CaptureFixture[str],
    conf_path: str,
    check_err: Callable[[str], bool] | None,
) -> None:
    template = Template(conf_path)
    with pytest.raises(InvalidConfigFileError):
        template.config_data  # noqa: B018
    if check_err:
        _, err = capsys.readouterr()
        assert check_err(err)


def test_valid_multi_section(tmp_path: Path) -> None:
    """Including multiple files works fine merged with multiple sections."""
    with local.cwd(tmp_path):
        build_file_tree({
            "exclusions.yml": "_exclude: ['*.yml']",
            "common_jinja.yml": (
                f"""\
                    _templates_suffix: {SUFFIX_TMPL}
                    _envops:
                        block_start_string: "[%"
                        block_end_string: "%]"
                        comment_start_string: "[#"
                        comment_end_string: "#]"
                        variable_start_string: "[["
                        variable_end_string: "]]"
                        keep_trailing_newline: true
                    """
            ),
            "common_questions.yml": (
                """\
                    your_age:
                        type: int
                    your_name:
                        type: yaml
                        help: your name from common questions
                    """
            ),
            "copier.yml": (
                """\
                    ---
                    !include 'common_*.yml'
                    ---
                    !include exclusions.yml
                    ---
                    your_name:
                        type: str
                        help: your name from latest section
                    """
            ),
        })
    template = Template(str(tmp_path))
    assert template.exclude == ("*.yml",)
    assert template.envops == {
        "block_end_string": "%]",
        "block_start_string": "[%",
        "comment_end_string": "#]",
        "comment_start_string": "[#",
        "keep_trailing_newline": True,
        "variable_end_string": "]]",
        "variable_start_string": "[[",
    }
    assert template.questions_data == {
        "your_age": {"type": "int"},
        "your_name": {"type": "str", "help": "your name from latest section"},
    }


def test_empty_section(tmp_path: Path) -> None:
    """Empty sections are ignored."""
    build_file_tree({
        (tmp_path / "copier.yml"): (
            """\
                ---
                ---

                ---
                your_age:
                    type: int
                your_name:
                    type: str
                ---
                """
        ),
    })
    template = Template(str(tmp_path))
    assert template.questions_data == {
        "your_age": {"type": "int"},
        "your_name": {"type": "str"},
    }


def test_include_path_must_be_relative(tmp_path: Path) -> None:
    """Include path must not be a relative path."""
    build_file_tree({
        (tmp_path / "copier.yml"): (
            """\
                !include /absolute/path/to/common.yml
                """
        ),
    })
    template = Template(str(tmp_path))
    with pytest.raises(
        ValueError, match="YAML include file path must be a relative path"
    ):
        template.config_data  # noqa: B018


@pytest.mark.parametrize("include_value", ["[]", "{}"])
def test_include_value_must_be_scalar_node(tmp_path: Path, include_value: str) -> None:
    """Include value must be a YAML scalar node."""
    build_file_tree({
        (tmp_path / "copier.yml"): (
            f"""\
                !include {include_value}
                """
        ),
    })
    template = Template(str(tmp_path))
    with pytest.raises(ValueError, match=r"^Unsupported YAML node:"):
        template.config_data  # noqa: B018


def test_config_data_empty() -> None:
    template = Template("tests/demo_config_empty")
    assert template.config_data == {}
    assert template.questions_data == {}


def test_multiple_config_file_error() -> None:
    template = Template("tests/demo_multi_config")
    with pytest.raises(MultipleConfigFilesError):
        template.config_data  # noqa: B018


# ConfigData
@pytest.mark.parametrize(
    "data",
    (
        {"pretend": "not_a_bool"},
        {"quiet": "not_a_bool"},
        {"overwrite": "not_a_bool"},
        {"cleanup_on_error": "not_a_bool"},
        {"overwrite": True, "skip_if_exists": True},
    ),
)
def test_flags_bad_data(data: AnyByStrDict) -> None:
    with pytest.raises(ValidationError):
        copier.Worker(**data)


def test_flags_extra_fails() -> None:
    with pytest.raises(ValidationError):
        copier.Worker(  # type: ignore[call-arg]
            src_path="..",
            dst_path=Path("."),
            i_am_not_a_member="and_i_do_not_belong_here",
        )


def test_missing_template(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        copier.run_copy("./i_do_not_exist", tmp_path)


def is_subdict(small: dict[Any, Any], big: dict[Any, Any]) -> bool:
    return {**big, **small} == big


def test_worker_good_data(tmp_path: Path) -> None:
    # This test is probably useless, as it tests the what and not the how
    conf = copier.Worker("./tests/demo_data", tmp_path)
    assert conf._render_context()["_folder_name"] == tmp_path.name
    assert conf.all_exclusions == ("exclude1", "exclude2")
    assert conf.template.skip_if_exists == ["skip_if_exists1", "skip_if_exists2"]
    assert conf.template.tasks == [
        Task(cmd="touch 1", extra_env={"STAGE": "task"}),
        Task(cmd="touch 2", extra_env={"STAGE": "task"}),
    ]


@pytest.mark.parametrize(
    "test_input, expected_exclusions",
    [
        # func_args > defaults
        (
            {"src_path": ".", "exclude": ["aaa"]},
            tuple(DEFAULT_EXCLUDE) + ("aaa",),
        ),
        # func_args > user_data
        (
            {"src_path": "tests/demo_data", "exclude": ["aaa"]},
            ("exclude1", "exclude2", "aaa"),
        ),
    ],
)
def test_worker_config_precedence(
    tmp_path: Path, test_input: AnyByStrDict, expected_exclusions: tuple[str, ...]
) -> None:
    conf = copier.Worker(dst_path=tmp_path, vcs_ref="HEAD", **test_input)
    assert expected_exclusions == conf.all_exclusions


def test_config_data_transclusion() -> None:
    config = copier.Worker("tests/demo_transclude/demo")
    assert config.all_exclusions == ("exclude1", "exclude2")


@pytest.mark.parametrize(
    "user_defaults, data, expected",
    [
        # Nothing overridden.
        (
            {},
            {},
            dedent(
                """\
                A string: lorem ipsum
                A number: 12345
                A boolean: True
                A list: one, two, three
                """
            ),
        ),
        # User defaults provided.
        (
            {
                "a_string": "foo",
                "a_number": 42,
                "a_boolean": False,
                "a_list": ["four", "five", "six"],
            },
            {},
            dedent(
                """\
                A string: foo
                A number: 42
                A boolean: False
                A list: four, five, six
                """
            ),
        ),
        # User defaults + data provided.
        (
            {
                "a_string": "foo",
                "a_number": 42,
                "a_boolean": False,
                "a_list": ["four", "five", "six"],
            },
            {
                "a_string": "yosemite",
            },
            dedent(
                """\
                A string: yosemite
                A number: 42
                A boolean: False
                A list: four, five, six
                """
            ),
        ),
    ],
)
def test_user_defaults(
    tmp_path_factory: pytest.TempPathFactory,
    user_defaults: AnyByStrDict,
    data: AnyByStrDict,
    expected: str,
) -> None:
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))
    build_file_tree({
        (src / "copier.yaml"): (
            """\
                a_string:
                    default: lorem ipsum
                    type: str
                a_number:
                    default: 12345
                    type: int
                a_boolean:
                    default: true
                    type: bool
                a_list:
                    default:
                        - one
                        - two
                        - three
                    type: json
                """
        ),
        (src / "user_data.txt.jinja"): (
            """\
                A string: {{ a_string }}
                A number: {{ a_number }}
                A boolean: {{ a_boolean }}
                A list: {{ ", ".join(a_list) }}
                """
        ),
        (src / "{{ _copier_conf.answers_file }}.jinja"): (
            """\
                # Changes here will be overwritten by Copier
                {{ _copier_answers|to_nice_yaml }}
                """
        ),
    })
    copier.run_copy(
        str(src),
        dst,
        defaults=True,
        overwrite=True,
        user_defaults=user_defaults,
        data=data,
    )
    assert (dst / "user_data.txt").read_text() == expected


@pytest.mark.parametrize(
    (
        "user_defaults_initial",
        "user_defaults_updated",
        "data_initial",
        "data_updated",
        "expected_initial",
        "expected_updated",
    ),
    [
        # Initial user defaults and updated used defaults. The output
        # should remain unchanged following the update operation.
        (
            {
                "a_string": "foo",
            },
            {
                "a_string": "foobar",
            },
            {},
            {},
            dedent(
                """\
                A string: foo
                """
            ),
            dedent(
                """\
                A string: foo
                """
            ),
        ),
        # User defaults + data provided. Provided data should take precedence
        # and the resulting content unchanged post-update.
        (
            {
                "a_string": "foo",
            },
            {
                "a_string": "foobar",
            },
            {
                "a_string": "yosemite",
            },
            {},
            dedent(
                """\
                A string: yosemite
                """
            ),
            dedent(
                """\
                A string: yosemite
                """
            ),
        ),
        # User defaults + secondary defaults + data overrides. `data_updated` should
        # override user and template defaults.
        (
            {
                "a_string": "foo",
            },
            {
                "a_string": "foobar",
            },
            {
                "a_string": "yosemite",
            },
            {
                "a_string": "red rocks",
            },
            dedent(
                """\
                A string: yosemite
                """
            ),
            dedent(
                """\
                A string: red rocks
                """
            ),
        ),
    ],
)
def test_user_defaults_updated(
    tmp_path_factory: pytest.TempPathFactory,
    user_defaults_initial: AnyByStrDict,
    user_defaults_updated: AnyByStrDict,
    data_initial: AnyByStrDict,
    data_updated: AnyByStrDict,
    expected_initial: str,
    expected_updated: str,
) -> None:
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))
    with local.cwd(src):
        build_file_tree({
            (src / "copier.yaml"): (
                """\
                    a_string:
                        default: lorem ipsum
                        type: str
                    """
            ),
            (src / "user_data.txt.jinja"): (
                """\
                    A string: {{ a_string }}
                    """
            ),
            (src / "{{ _copier_conf.answers_file }}.jinja"): (
                """\
                    # Changes here will be overwritten by Copier
                    {{ _copier_answers|to_nice_yaml }}
                    """
            ),
        })
        git_init()

    copier.run_copy(
        str(src),
        dst,
        defaults=True,
        overwrite=True,
        user_defaults=user_defaults_initial,
        data=data_initial,
    )
    assert (dst / "user_data.txt").read_text() == expected_initial

    with local.cwd(dst):
        git_init()

    copier.run_update(
        dst,
        defaults=True,
        overwrite=True,
        user_defaults=user_defaults_updated,
        data=data_updated,
    )
    assert (dst / "user_data.txt").read_text() == expected_updated


@pytest.mark.parametrize(
    "config",
    [
        """\
        question:
            type: str
            secret: true
        """,
        """\
        question:
            type: str

        _secret_questions:
            - question
        """,
    ],
)
def test_secret_question_requires_default_value(
    tmp_path_factory: pytest.TempPathFactory, config: str
) -> None:
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))
    build_file_tree({src / "copier.yml": config})
    with pytest.raises(ValueError, match="Secret question requires a default value"):
        copier.run_copy(str(src), dst)
