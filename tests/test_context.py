import json
from pathlib import Path

import pytest
from plumbum import local

import copier

from .helpers import build_file_tree, git_save


def test_exclude_templating_with_operation(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """
    Ensure it's possible to create one-off boilerplate files that are not
    managed during updates via `_exclude` using the `_operation` context variable.
    """
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))

    template = "{% if _operation == 'update' %}copy-only{% endif %}"
    with local.cwd(src):
        build_file_tree(
            {
                "copier.yml": f'_exclude:\n - "{template}"',
                "{{ _copier_conf.answers_file }}.jinja": "{{ _copier_answers|to_yaml }}",
                "copy-only": "foo",
                "copy-and-update": "foo",
            }
        )
        git_save(tag="1.0.0")
        build_file_tree(
            {
                "copy-only": "bar",
                "copy-and-update": "bar",
            }
        )
        git_save(tag="2.0.0")
    copy_only = dst / "copy-only"
    copy_and_update = dst / "copy-and-update"

    copier.run_copy(str(src), dst, defaults=True, overwrite=True, vcs_ref="1.0.0")
    for file in (copy_only, copy_and_update):
        assert file.exists()
        assert file.read_text() == "foo"

    with local.cwd(dst):
        git_save()

    copier.run_update(str(dst), overwrite=True)
    assert copy_only.read_text() == "foo"
    assert copy_and_update.read_text() == "bar"


def test_task_templating_with_operation(
    tmp_path_factory: pytest.TempPathFactory, tmp_path: Path
) -> None:
    """
    Ensure that it is possible to define tasks that are only executed when copying.
    """
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))
    # Use a file outside the Copier working directories to ensure accurate tracking
    task_counter = tmp_path / "task_calls.txt"
    with local.cwd(src):
        build_file_tree(
            {
                "copier.yml": (
                    f"""\
                    _tasks:
                        -   command: echo {{{{ _operation }}}} >> {json.dumps(str(task_counter))}
                            when: "{{{{ _operation == 'copy' }}}}"
                    """
                ),
                "{{ _copier_conf.answers_file }}.jinja": "{{ _copier_answers|to_yaml }}",
            }
        )
        git_save(tag="1.0.0")

    copier.run_copy(str(src), dst, defaults=True, overwrite=True, unsafe=True)
    assert task_counter.exists()
    assert len(task_counter.read_text().splitlines()) == 1

    with local.cwd(dst):
        git_save()

    copier.run_recopy(dst, defaults=True, overwrite=True, unsafe=True)
    assert len(task_counter.read_text().splitlines()) == 2

    copier.run_update(dst, defaults=True, overwrite=True, unsafe=True)
    assert len(task_counter.read_text().splitlines()) == 2
