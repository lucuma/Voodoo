from pathlib import Path
from typing import Literal, Optional

import pytest

import copier

from .helpers import BRACKET_ENVOPS_JSON, SUFFIX_TMPL, build_file_tree


@pytest.fixture(scope="module")
def template_path(tmp_path_factory: pytest.TempPathFactory) -> str:
    root = tmp_path_factory.mktemp("demo_pre_copy")
    build_file_tree(
        {
            (root / "copier.yaml"): (
                f"""\
                _templates_suffix: {SUFFIX_TMPL}
                _envops: {BRACKET_ENVOPS_JSON}

                other_file: bye

                # This tests two things:
                # 1. That the tasks are being executed in the destination folder; and
                # 2. That the tasks are being executed in order, one after another
                _pre_copy:
                    - mkdir hello
                    - cd hello && touch world
                    - touch [[ other_file ]]
                    - ["[[ _copier_python ]]", "-c", "open('pyfile', 'w').close()"]
                """
            )
        }
    )
    return str(root)


def test_render_tasks(template_path: str, tmp_path: Path) -> None:
    copier.run_copy(template_path, tmp_path, data={"other_file": "custom"}, unsafe=True)
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


def test_pretend_mode(tmp_path_factory: pytest.TempPathFactory) -> None:
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))
    build_file_tree(
        {
            (src / "copier.yml"): (
                """
                _pre_copy:
                    - touch created-by-pre-copy.txt
                """
            )
        }
    )
    copier.run_copy(str(src), dst, pretend=True, unsafe=True)
    assert not (dst / "created-by-pre-copy.txt").exists()


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
    os: Optional[Literal["linux", "macos", "windows"]],
    filename: str,
) -> None:
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))
    build_file_tree(
        {
            (src / "copier.yml"): (
                """\
                _pre_copy:
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
