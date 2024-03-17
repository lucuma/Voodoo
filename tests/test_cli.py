import subprocess
import sys
from pathlib import Path
from typing import Callable, Generator

import pytest
import yaml
from plumbum import local
from plumbum.cmd import git

from copier.cli import CopierApp

from .helpers import COPIER_CMD, build_file_tree


@pytest.fixture(scope="module")
def template_path(tmp_path_factory: pytest.TempPathFactory) -> str:
    root = tmp_path_factory.mktemp("template")
    build_file_tree({
        (root / "{{ _copier_conf.answers_file }}.jinja"): (
            """\
                # Changes here will be overwritten by Copier
                {{ _copier_answers|to_nice_yaml }}
                """
        ),
        (root / "a.txt"): "EXAMPLE_CONTENT",
    })
    return str(root)


@pytest.fixture(scope="module")
def template_path_with_dot_config(
    tmp_path_factory: pytest.TempPathFactory,
) -> Generator[Callable[[str], str], str, None]:
    def _template_path_with_dot_config(config_folder: str) -> str:
        root = tmp_path_factory.mktemp("template")
        build_file_tree({
            root / config_folder / "{{ _copier_conf.answers_file }}.jinja": """\
                    # Changes here will be overwritten by Copier
                    {{ _copier_answers|to_nice_yaml }}
                    """,
            root / "a.txt": "EXAMPLE_CONTENT",
        })
        return str(root)

    yield _template_path_with_dot_config


def test_good_cli_run(template_path: str, tmp_path: Path) -> None:
    run_result = CopierApp.run(
        [
            "copier",
            "copy",
            "--quiet",
            "-a",
            "altered-answers.yml",
            template_path,
            str(tmp_path),
        ],
        exit=False,
    )
    a_txt = tmp_path / "a.txt"
    assert run_result[1] == 0
    assert a_txt.exists()
    assert a_txt.is_file()
    assert a_txt.read_text() == "EXAMPLE_CONTENT"
    answers = yaml.safe_load((tmp_path / "altered-answers.yml").read_text())
    assert answers["_src_path"] == template_path


@pytest.mark.parametrize(
    "type_, answer, expected",
    [
        ("str", "string", "string"),
        ("str", "1", "1"),
        ("str", "1.2", "1.2"),
        ("str", "true", "true"),
        ("str", "null", "null"),
        ("str", '["string", 1, 1.2, true, null]', '["string", 1, 1.2, true, null]'),
        ("int", "1", 1),
        ("float", "1.2", 1.2),
        ("bool", "true", True),
        ("bool", "false", False),
        ("yaml", '"string"', "string"),
        ("yaml", "1", 1),
        ("yaml", "1.2", 1.2),
        ("yaml", "true", True),
        ("yaml", "null", None),
        ("yaml", '["string", 1, 1.2, true, null]', ["string", 1, 1.2, True, None]),
        ("json", '"string"', "string"),
        ("json", "1", 1),
        ("json", "1.2", 1.2),
        ("json", "true", True),
        ("json", "null", None),
        ("json", '["string", 1, 1.2, true, null]', ["string", 1, 1.2, True, None]),
    ],
)
def test_cli_data_parsed_by_question_type(
    tmp_path_factory: pytest.TempPathFactory, type_, answer, expected
) -> None:
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))
    build_file_tree({
        (src / "copier.yml"): (
            f"""\
                question:
                    type: {type_}
                """
        ),
        (src / "{{ _copier_conf.answers_file }}.jinja"): (
            """\
                # Changes here will be overwritten by Copier
                {{ _copier_answers|to_nice_yaml }}
                """
        ),
    })
    run_result = CopierApp.run(
        ["copier", "copy", f"--data=question={answer}", str(src), str(dst), "--quiet"],
        exit=False,
    )
    assert run_result[1] == 0
    answers = yaml.safe_load((dst / ".copier-answers.yml").read_text())
    assert answers["_src_path"] == str(src)
    assert answers["question"] == expected


def test_data_file_parsed_by_question_type(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    src, dst, local = map(tmp_path_factory.mktemp, ("src", "dst", "local"))
    build_file_tree({
        (src / "copier.yml"): (
            """\
                question:
                    type: str
                """
        ),
        (src / "{{ _copier_conf.answers_file }}.jinja"): (
            """\
                # Changes here will be overwritten by Copier
                {{ _copier_answers|to_nice_yaml }}
                """
        ),
        (local / "data.yml"): yaml.dump({"question": "answer"}),
    })

    run_result = CopierApp.run(
        [
            "copier",
            "copy",
            f"--data-file={local / 'data.yml'}",
            str(src),
            str(dst),
            "--quiet",
        ],
        exit=False,
    )
    assert run_result[1] == 0
    answers = yaml.safe_load((dst / ".copier-answers.yml").read_text())
    assert answers["_src_path"] == str(src)
    assert answers["question"] == "answer"


def test_data_cli_takes_precedence_over_data_file(
    tmp_path_factory: pytest.TempPathFactory,
):
    src, dst, local = map(tmp_path_factory.mktemp, ("src", "dst", "local"))
    build_file_tree({
        (src / "copier.yml"): (
            """\
                question:
                    type: str
                another_question:
                    type: str
                yet_another_question:
                    type: str
                """
        ),
        (src / "{{ _copier_conf.answers_file }}.jinja"): (
            """\
                # Changes here will be overwritten by Copier
                {{ _copier_answers|to_nice_yaml }}
                """
        ),
        (local / "data.yml"): yaml.dump({
            "question": "does not matter",
            "another_question": "another answer!",
            "yet_another_question": "sure, one more for you!",
        }),
    })

    answer_override = "fourscore and seven years ago"
    run_result = CopierApp.run(
        [
            "copier",
            "copy",
            f"--data-file={local / 'data.yml'}",
            f"--data=question={answer_override}",
            str(src),
            str(dst),
            "--quiet",
        ],
        exit=False,
    )
    assert run_result[1] == 0
    actual_answers = yaml.safe_load((dst / ".copier-answers.yml").read_text())
    expected_answers = {
        "_src_path": str(src),
        "question": answer_override,
        "another_question": "another answer!",
        "yet_another_question": "sure, one more for you!",
    }
    assert actual_answers == expected_answers


@pytest.mark.parametrize(
    "config_folder",
    map(
        Path,
        ["", ".config/", ".config/subconfig/", ".config/subconfig/deep_nested_config/"],
    ),
)
def test_good_cli_run_dot_config(
    tmp_path: Path,
    template_path_with_dot_config: Callable[[str], str],
    config_folder: Path,
) -> None:
    """Function to test different locations of the answersfile.

    Added based on the discussion: https://github.com/copier-org/copier/discussions/859
    """
    src = template_path_with_dot_config(str(config_folder))

    with local.cwd(src):
        git_commands()

    run_result = CopierApp.run(
        [
            "copier",
            "copy",
            "--quiet",
            "-a",
            str(config_folder / "altered-answers.yml"),
            src,
            str(tmp_path),
        ],
        exit=False,
    )
    a_txt = tmp_path / "a.txt"
    assert run_result[1] == 0
    assert a_txt.exists()
    assert a_txt.is_file()
    assert a_txt.read_text() == "EXAMPLE_CONTENT"
    answers = yaml.safe_load(
        (tmp_path / config_folder / "altered-answers.yml").read_text()
    )
    assert answers["_src_path"] == src

    with local.cwd(str(tmp_path)):
        git_commands()

    run_update = CopierApp.run(
        [
            "copier",
            "update",
            str(tmp_path),
            "--answers-file",
            str(config_folder / "altered-answers.yml"),
            "--quiet",
        ],
        exit=False,
    )
    assert run_update[1] == 0
    assert answers["_src_path"] == src


def git_commands() -> None:
    git("init")
    git("add", "-A")
    git("commit", "-m", "init")


def test_help() -> None:
    _help = COPIER_CMD("--help-all")
    assert "copier copy [SWITCHES] template_src destination_path" in _help
    assert "copier update [SWITCHES] [destination_path=.]" in _help


def test_copy_help() -> None:
    _help = COPIER_CMD("copy", "--help")
    assert "copier copy [SWITCHES] template_src destination_path" in _help


def test_update_help() -> None:
    _help = COPIER_CMD("update", "--help")
    assert "-o, --conflict" in _help
    assert "copier update [SWITCHES] [destination_path=.]" in _help
    assert "--skip-answered" in _help


def test_python_run() -> None:
    cmd = [sys.executable, "-m", "copier", "--help-all"]
    assert subprocess.run(cmd, check=True).returncode == 0


def test_skip_filenotexists(template_path: str, tmp_path: Path) -> None:
    run_result = CopierApp.run(
        [
            "copier",
            "copy",
            "--quiet",
            "-a",
            "altered-answers.yml",
            "--overwrite",
            "--skip=a.txt",
            template_path,
            str(tmp_path),
        ],
        exit=False,
    )
    a_txt = tmp_path / "a.txt"
    assert run_result[1] == 0
    assert a_txt.exists()
    assert a_txt.is_file()
    assert a_txt.read_text() == "EXAMPLE_CONTENT"
    answers = yaml.safe_load((tmp_path / "altered-answers.yml").read_text())
    assert answers["_src_path"] == str(template_path)


def test_skip_fileexists(template_path: str, tmp_path: Path) -> None:
    a_txt = tmp_path / "a.txt"
    a_txt.write_text("PREVIOUS_CONTENT")
    run_result = CopierApp.run(
        [
            "copier",
            "copy",
            "--quiet",
            "-a",
            "altered-answers.yml",
            "--overwrite",
            "--skip=a.txt",
            template_path,
            str(tmp_path),
        ],
        exit=False,
    )
    assert run_result[1] == 0
    assert a_txt.exists()
    assert a_txt.is_file()
    assert a_txt.read_text() == "PREVIOUS_CONTENT"
    answers = yaml.safe_load((tmp_path / "altered-answers.yml").read_text())
    assert answers["_src_path"] == str(template_path)
