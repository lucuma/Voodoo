from __future__ import annotations

from pathlib import Path
from typing import Literal

import pytest
import yaml

import copier
from copier.cli import CopierApp

from .helpers import BRACKET_ENVOPS_JSON, SUFFIX_TMPL, build_file_tree


@pytest.fixture(scope="module")
def template_path(tmp_path_factory: pytest.TempPathFactory) -> str:
    root = tmp_path_factory.mktemp("demo_tasks")
    build_file_tree(
        {
            (root / "copier.yaml"): (
                f"""\
                _templates_suffix: {SUFFIX_TMPL}
                _envops: {BRACKET_ENVOPS_JSON}

                other_file: bye
                condition: true

                # This tests two things:
                # 1. That the tasks are being executed in the destination folder; and
                # 2. That the tasks are being executed in order, one after another
                _tasks:
                    -   mkdir hello
                    -   command: touch world
                        working_directory: ./hello
                    -   touch [[ other_file ]]
                    -   ["[[ _copier_python ]]", "-c", "open('pyfile', 'w').close()"]
                    -   command: touch true
                        when: "[[ condition ]]"
                    -   command: touch false
                        when: "[[ not condition ]]"
                """
            )
        }
    )
    return str(root)


def test_render_tasks(template_path: str, tmp_path: Path) -> None:
    copier.run_copy(
        template_path,
        tmp_path,
        data={"other_file": "custom", "condition": "true"},
        unsafe=True,
    )
    assert (tmp_path / "custom").is_file()


def test_copy_tasks(template_path: str, tmp_path: Path) -> None:
    copier.run_copy(
        template_path, tmp_path, quiet=True, defaults=True, overwrite=True, unsafe=True
    )
    assert (tmp_path / "hello").exists()
    assert (tmp_path / "hello").is_dir()
    assert (tmp_path / "hello" / "world").exists()
    assert (tmp_path / "bye").is_file()
    assert (tmp_path / "pyfile").is_file()
    assert (tmp_path / "true").is_file()
    assert not (tmp_path / "false").exists()


def test_copy_skip_tasks(template_path: str, tmp_path: Path) -> None:
    copier.run_copy(
        template_path,
        tmp_path,
        quiet=True,
        defaults=True,
        overwrite=True,
        skip_tasks=True,
    )
    assert not (tmp_path / "hello").exists()
    assert not (tmp_path / "hello").is_dir()
    assert not (tmp_path / "hello" / "world").exists()
    assert not (tmp_path / "bye").is_file()
    assert not (tmp_path / "pyfile").is_file()


@pytest.mark.parametrize("skip_tasks", [False, True])
def test_copy_cli_skip_tasks(
    tmp_path_factory: pytest.TempPathFactory,
    skip_tasks: bool,
) -> None:
    src, dst = map(tmp_path_factory.mktemp, ["src", "dst"])
    build_file_tree(
        {(src / "copier.yaml"): yaml.safe_dump({"_tasks": ["touch task.txt"]})}
    )
    _, retcode = CopierApp.run(
        [
            "copier",
            "copy",
            "--UNSAFE",
            *(["--skip-tasks"] if skip_tasks else []),
            str(src),
            str(dst),
        ],
        exit=False,
    )
    assert retcode == 0
    assert (dst / "task.txt").exists() is (not skip_tasks)


def test_pretend_mode(tmp_path_factory: pytest.TempPathFactory) -> None:
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))
    build_file_tree(
        {
            (src / "copier.yml"): (
                """
                _tasks:
                    - touch created-by-task.txt
                """
            )
        }
    )
    copier.run_copy(str(src), dst, pretend=True, unsafe=True)
    assert not (dst / "created-by-task.txt").exists()


@pytest.mark.parametrize(
    "os, filename",
    [
        ("linux", "linux.txt"),
        ("macos", "macos.txt"),
        ("windows", "windows.txt"),
        (None, "unsupported.txt"),
    ],
)
def test_os_specific_tasks(
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
    os: Literal["linux", "macos", "windows"] | None,
    filename: str,
) -> None:
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))
    build_file_tree(
        {
            (src / "copier.yml"): (
                """\
                _tasks:
                -   >-
                    {% if _copier_conf.os == 'linux' %}
                    touch linux.txt
                    {% elif _copier_conf.os == 'macos' %}
                    touch macos.txt
                    {% elif _copier_conf.os == 'windows' %}
                    touch windows.txt
                    {% elif _copier_conf.os is none %}
                    touch unsupported.txt
                    {% else %}
                    touch never.txt
                    {% endif %}
                """
            )
        }
    )
    monkeypatch.setattr("copier.main.OS", os)
    copier.run_copy(str(src), dst, unsafe=True)
    assert (dst / filename).exists()


def test_copier_phase_variable(tmp_path_factory: pytest.TempPathFactory) -> None:
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))
    build_file_tree(
        {
            (src / "copier.yml"): (
                """
                _tasks:
                    - touch {{ _copier_phase }}
                """
            )
        }
    )
    copier.run_copy(str(src), dst, unsafe=True)
    assert (dst / "tasks").exists()
