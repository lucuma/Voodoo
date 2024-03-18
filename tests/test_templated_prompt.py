from __future__ import annotations

import json
from datetime import datetime
from typing import Sequence

import pexpect
import pytest
import yaml
from pexpect.popen_spawn import PopenSpawn

from copier import Worker
from copier.errors import InvalidTypeError
from copier.types import AnyByStrDict, OptStr

from .helpers import (
    BRACKET_ENVOPS,
    BRACKET_ENVOPS_JSON,
    COPIER_PATH,
    SUFFIX_TMPL,
    Spawn,
    build_file_tree,
    expect_prompt,
)

main_default = "copier"
main_question = {
    "main": {"default": main_default},
    "_envops": BRACKET_ENVOPS,
    "_templates_suffix": SUFFIX_TMPL,
}


class Prompt:
    def __init__(self, name: str, format: str, help: OptStr = None) -> None:
        self.name = name
        self.format = format
        self.help = help

    def expect(self, tui: PopenSpawn) -> None:
        expect_prompt(tui, self.name, self.format, self.help)


@pytest.mark.parametrize(
    "questions_data, expected_value, expected_outputs",
    [
        (
            {"templated_default": {"default": "[[ main ]]default"}},
            "copierdefault",
            [Prompt("templated_default", "str"), "copierdefault"],
        ),
        (
            {
                "templated_type": {
                    "type": "[% if main == 'copier' %]int[% endif %]",
                    "default": "0",
                },
            },
            0,
            [Prompt("templated_type", "int"), "0"],
        ),
        (
            {
                "templated_help": {
                    "default": main_default,
                    "help": "THIS [[ main ]] HELP IS TEMPLATED",
                },
            },
            main_default,
            [
                Prompt("templated_help", "str", "THIS copier HELP IS TEMPLATED"),
                "copier",
            ],
        ),
        (
            {
                "templated_choices_dict_1": {
                    "default": "[[ main ]]",
                    "choices": {
                        "choice 1": "[[ main ]]",
                        "[[ main ]]": "value 2",
                    },
                },
            },
            main_default,
            ["(Use arrow keys)", "choice 1", "copier"],
        ),
        (
            {
                "templated_choices_dict_2": {
                    "default": "value 2",
                    "choices": {"choice 1": "[[ main ]]", "[[ main ]]": "value 2"},
                },
            },
            "value 2",
            ["(Use arrow keys)", "choice 1", "copier"],
        ),
        (
            {
                "templated_choices_string_list_1": {
                    "default": main_default,
                    "choices": ["[[ main ]]", "choice 2"],
                },
            },
            main_default,
            ["(Use arrow keys)", "copier", "choice 2"],
        ),
        (
            {
                "templated_choices_string_list_2": {
                    "default": "choice 1",
                    "choices": ["choice 1", "[[ main ]]"],
                },
            },
            "choice 1",
            ["(Use arrow keys)", "choice 1", "copier"],
        ),
        (
            {
                "templated_choices_tuple_list_1": {
                    "default": main_default,
                    "choices": [["name 1", "[[ main ]]"], ["[[ main ]]", "value 2"]],
                },
            },
            main_default,
            ["(Use arrow keys)", "name 1", "copier"],
        ),
        (
            {
                "templated_choices_tuple_list_2": {
                    "default": "value 2",
                    "choices": [["name 1", "[[ main ]]"], ["[[ main ]]", "value 2"]],
                },
            },
            "value 2",
            ["name 1", "copier"],
        ),
        (
            {
                "templated_choices_mixed_list": {
                    "default": "value 2",
                    "choices": ["[[ main ]]", ["[[ main ]]", "value 2"]],
                },
            },
            "value 2",
            ["copier", "copier"],
        ),
    ],
)
def test_templated_prompt(
    tmp_path_factory: pytest.TempPathFactory,
    spawn: Spawn,
    questions_data: AnyByStrDict,
    expected_value: str | int,
    expected_outputs: Sequence[str | Prompt],
) -> None:
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))
    questions_combined = {**main_question, **questions_data}
    # There's always only 1 question; get its name
    question_name = next(iter(questions_data))
    build_file_tree(
        {
            (src / "copier.yml"): json.dumps(questions_combined),
            (src / "[[ _copier_conf.answers_file ]].tmpl"): (
                "[[ _copier_answers|to_nice_yaml ]]"
            ),
        }
    )
    tui = spawn(COPIER_PATH + ("copy", str(src), str(dst)), timeout=10)
    expect_prompt(tui, "main", "str")
    tui.expect_exact(main_default)
    tui.sendline()
    for output in expected_outputs:
        if isinstance(output, Prompt):
            output.expect(tui)
        else:
            tui.expect_exact(output)
    tui.sendline()
    tui.expect_exact(pexpect.EOF)
    answers = yaml.safe_load((dst / ".copier-answers.yml").read_text())
    assert answers[question_name] == expected_value


def test_templated_prompt_custom_envops(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))
    build_file_tree(
        {
            (src / "copier.yml"): (
                """\
                _envops:
                    block_start_string: "<%"
                    block_end_string: "%>"
                    comment_start_string: "<#"
                    comment_end_string: "#>"
                    variable_start_string: "<<"
                    variable_end_string: ">>"

                powerlevel:
                    type: int
                    default: 9000

                sentence:
                    type: str
                    default: "<% if powerlevel >= 9000 %>It's over 9000!<% else %>It's only << powerlevel >>...<% endif %>"
                """  # noqa: E501
            ),
            (src / "result.jinja"): "<<sentence>>",
        }
    )
    worker1 = Worker(str(src), dst, defaults=True, overwrite=True)
    worker1.run_copy()
    assert (dst / "result").read_text() == "It's over 9000!"

    worker2 = Worker(
        str(src), dst, data={"powerlevel": 1}, defaults=True, overwrite=True
    )
    worker2.run_copy()
    assert (dst / "result").read_text() == "It's only 1..."


def test_templated_prompt_builtins(tmp_path_factory: pytest.TempPathFactory) -> None:
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))
    build_file_tree(
        {
            (src / "copier.yaml"): (
                f"""\
                _templates_suffix: {SUFFIX_TMPL}
                _envops: {BRACKET_ENVOPS_JSON}
                question1:
                    default: "[[ now() ]]"
                question2:
                    default: "[[ make_secret() ]]"
                """
            ),
            src / "now.tmpl": "[[ question1 ]]",
            src / "make_secret.tmpl": "[[ question2 ]]",
        }
    )
    Worker(str(src), dst, defaults=True, overwrite=True).run_copy()
    that_now = datetime.fromisoformat((dst / "now").read_text())
    assert that_now <= datetime.utcnow()
    assert len((dst / "make_secret").read_text()) == 128


@pytest.mark.parametrize(
    "questions, raises, returns",
    (
        ({"question": {"default": "{{ not_valid }}"}}, None, ""),
        ({"question": {"help": "{{ not_valid }}"}}, None, "None"),
        ({"question": {"type": "{{ not_valid }}"}}, InvalidTypeError, "None"),
        ({"question": {"choices": ["{{ not_valid }}"]}}, None, "None"),
    ),
)
def test_templated_prompt_invalid(
    tmp_path_factory: pytest.TempPathFactory,
    questions: AnyByStrDict,
    raises: type[BaseException] | None,
    returns: str,
) -> None:
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))
    build_file_tree(
        {
            src / "copier.yml": yaml.safe_dump(questions),
            src / "result.jinja": "{{question}}",
        }
    )
    worker = Worker(str(src), dst, data={"question": ""}, overwrite=True)
    if raises:
        with pytest.raises(raises):
            worker.run_copy()
    else:
        worker.run_copy()
        assert (dst / "result").read_text() == returns


@pytest.mark.parametrize(
    "cloud, iac_choices",
    [
        (
            "Any",
            [
                "Terraform",
                "Cloud Formation (Requires AWS)",
                "Azure Resource Manager (Requires Azure)",
                "Deployment Manager (Requires GCP)",
            ],
        ),
        (
            "AWS",
            [
                "Terraform",
                "Cloud Formation",
                "Azure Resource Manager (Requires Azure)",
                "Deployment Manager (Requires GCP)",
            ],
        ),
        (
            "Azure",
            [
                "Terraform",
                "Cloud Formation (Requires AWS)",
                "Azure Resource Manager",
                "Deployment Manager (Requires GCP)",
            ],
        ),
        (
            "GCP",
            [
                "Terraform",
                "Cloud Formation (Requires AWS)",
                "Azure Resource Manager (Requires Azure)",
                "Deployment Manager",
            ],
        ),
    ],
)
def test_templated_prompt_with_conditional_choices(
    tmp_path_factory: pytest.TempPathFactory,
    spawn: Spawn,
    cloud: str,
    iac_choices: str,
) -> None:
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))
    build_file_tree(
        {
            (src / "copier.yml"): (
                """\
                cloud:
                    type: str
                    help: Which cloud provider do you use?
                    choices:
                        - Any
                        - AWS
                        - Azure
                        - GCP

                iac:
                    type: str
                    help: Which IaC tool do you use?
                    choices:
                        Terraform: tf
                        Cloud Formation:
                            value: cf
                            validator: "{% if cloud != 'AWS' %}Requires AWS{% endif %}"
                        Azure Resource Manager:
                            value: arm
                            validator: "{% if cloud != 'Azure' %}Requires Azure{% endif %}"
                        Deployment Manager:
                            value: dm
                            validator: "{% if cloud != 'GCP' %}Requires GCP{% endif %}"
                """  # noqa: E501
            ),
            (src / "result.jinja"): "{{question}}",
        }
    )
    tui = spawn(
        COPIER_PATH + ("copy", f"--data=cloud={cloud}", str(src), str(dst)),
        timeout=10,
    )
    expect_prompt(tui, "iac", "str", help="Which IaC tool do you use?")
    for iac in iac_choices:
        tui.expect_exact(iac)
    tui.sendline()
