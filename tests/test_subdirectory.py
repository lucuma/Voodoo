from pathlib import Path
from textwrap import dedent
from typing import Literal

import pytest
import yaml
from plumbum import local
from plumbum.cmd import git

import copier

from .helpers import BRACKET_ENVOPS_JSON, SUFFIX_TMPL, build_file_tree, git_init


@pytest.fixture(scope="module")
def template_path(tmp_path_factory: pytest.TempPathFactory) -> str:
    root = tmp_path_factory.mktemp("template")
    build_file_tree(
        {
            (root / "api_project" / "api_readme.md"): "",
            (root / "api_project" / "[[ _copier_conf.answers_file ]].tmpl"): (
                "[[ _copier_answers|to_nice_yaml ]]"
            ),
            (root / "conf_project" / "conf_readme.md"): (
                """\
                # Demo subdirectory

                Generated using previous answers `_subdirectory` value.
                """
            ),
            (root / "conf_project" / "[[ _copier_conf.answers_file ]].tmpl"): (
                "[[ _copier_answers|to_nice_yaml ]]"
            ),
            (root / "copier.yml"): (
                f"""\
                _templates_suffix: {SUFFIX_TMPL}
                _envops: {BRACKET_ENVOPS_JSON}
                choose_subdir:
                    type: str
                    default: conf_project
                    choices:
                        - api_project
                        - conf_project
                _subdirectory: "[[ choose_subdir ]]"
                """
            ),
        }
    )
    with local.cwd(root):
        git_init()
    return str(root)


def test_copy_subdirectory_api_option(template_path: str, tmp_path: Path) -> None:
    copier.run_copy(
        template_path,
        tmp_path,
        defaults=True,
        overwrite=True,
        data={"choose_subdir": "api_project"},
    )
    assert (tmp_path / "api_readme.md").exists()
    assert not (tmp_path / "conf_readme.md").exists()


def test_copy_subdirectory_config(template_path: str, tmp_path: Path) -> None:
    copier.run_copy(template_path, tmp_path, defaults=True, overwrite=True)
    assert (tmp_path / "conf_readme.md").exists()
    assert not (tmp_path / "api_readme.md").exists()


def test_update_subdirectory(template_path: str, tmp_path: Path) -> None:
    copier.run_copy(template_path, tmp_path, defaults=True, overwrite=True)

    with local.cwd(tmp_path):
        git_init()

    copier.run_update(dst_path=tmp_path, defaults=True, overwrite=True)
    assert not (tmp_path / "conf_project").exists()
    assert not (tmp_path / "api_project").exists()
    assert not (tmp_path / "api_readme.md").exists()
    assert (tmp_path / "conf_readme.md").exists()


def test_update_subdirectory_from_root_path(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))
    with local.cwd(src):
        build_file_tree(
            {
                "copier.yaml": (
                    """\
                    q1:
                        type: str
                        default: a1
                    """
                ),
                "file1.jinja": (
                    """\
                    version 1
                    hello
                    {{ q1 }}
                    bye
                    """
                ),
                "{{ _copier_conf.answers_file }}.jinja": "{{ _copier_answers|to_nice_yaml }}",  # noqa: E501
            }
        )
        git("init")
        git("add", ".")
        git("commit", "-m1")
        git("tag", "1")
        build_file_tree(
            {
                "file1.jinja": (
                    """\
                    version 2
                    hello
                    {{ q1 }}
                    bye
                    """
                ),
            }
        )
        git("commit", "-am2")
        git("tag", "2")
    with local.cwd(dst):
        build_file_tree({"dst_top_file": "one"})
        git("init")
        git("add", ".")
        git("commit", "-m0")
    copier.run_copy(
        str(src),
        dst / "subfolder",
        vcs_ref="1",
        defaults=True,
        overwrite=True,
        answers_file=".custom.copier-answers.yaml",
    )
    assert (dst / "subfolder" / "file1").read_text() == "version 1\nhello\na1\nbye\n"
    with local.cwd(dst):
        git("add", ".")
        git("commit", "-m1")
        copier.run_update(
            "subfolder",
            defaults=True,
            overwrite=True,
            answers_file=".custom.copier-answers.yaml",
        )
    answers = yaml.safe_load(
        (dst / "subfolder" / ".custom.copier-answers.yaml").read_bytes()
    )
    assert answers["_commit"] == "2"
    assert (dst / "subfolder" / "file1").read_text() == "version 2\nhello\na1\nbye\n"


@pytest.mark.parametrize(
    "conflict, readme, expect_reject",
    [
        (
            "rej",
            "upstream version 2\n",
            True,
        ),
        (
            "inline",
            dedent(
                """\
                <<<<<<< before updating
                downstream version 1
                =======
                upstream version 2
                >>>>>>> after updating
                """
            ),
            False,
        ),
    ],
)
def test_new_version_uses_subdirectory(
    tmp_path_factory: pytest.TempPathFactory,
    conflict: Literal["rej", "inline"],
    readme: str,
    expect_reject: bool,
) -> None:
    # Template in v1 doesn't have a _subdirectory;
    # in v2 it moves all things into a subdir and adds that key to copier.yml.
    # Some files change. Downstream project has evolved too. Does that work as expected?
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))

    # First, create the template with an initial README
    build_file_tree(
        {
            (src / "README.md"): "upstream version 1",
            (src / "{{_copier_conf.answers_file}}.jinja"): (
                "{{_copier_answers|to_nice_yaml}}"
            ),
        }
    )
    with local.cwd(src):
        git_init("hello template")
        git("tag", "v1")

    # Generate the project a first time, assert the README exists
    copier.run_copy(str(src), dst, defaults=True, overwrite=True)
    assert (dst / "README.md").exists()
    assert "_commit: v1" in (dst / ".copier-answers.yml").read_text()

    # Start versioning the generated project
    with local.cwd(dst):
        git_init("hello project")

        # After first commit, change the README, commit again
        Path("README.md").write_text("downstream version 1")
        git("commit", "-am", "updated readme")

    # Now change the template
    with local.cwd(src):
        # Update the README
        Path("README.md").write_text("upstream version 2")

        # Create a subdirectory, move files into it
        subdir = Path("subdir")
        subdir.mkdir()
        Path("README.md").rename(subdir / "README.md")
        Path("{{_copier_conf.answers_file}}.jinja").rename(
            subdir / "{{_copier_conf.answers_file}}.jinja"
        )

        # Add the subdirectory option to copier.yml
        Path("copier.yml").write_text(f"_subdirectory: {subdir}")

        # Commit the changes
        git("add", ".", "-A")
        git("commit", "-m", "use a subdirectory now")
        git("tag", "v2")

    # Finally, update the generated project
    copier.run_update(dst_path=dst, defaults=True, overwrite=True, conflict=conflict)
    assert "_commit: v2" in (dst / ".copier-answers.yml").read_text()

    # Assert that the README still exists, and the conflicts were handled
    # correctly.
    assert (dst / "README.md").exists()

    assert (dst / "README.md").read_text().splitlines() == readme.splitlines()
    assert (dst / "README.md.rej").exists() == expect_reject

    # Also assert the subdirectory itself was not rendered
    assert not (dst / subdir).exists()


def test_new_version_changes_subdirectory(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    # Template in v3 changes from one subdirectory to another.
    # Some file evolves also. Sub-project evolves separately.
    # Sub-project is updated. Does that work as expected?
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))

    # First, create the template with an initial subdirectory and README inside it
    build_file_tree(
        {
            (src / "copier.yml"): "_subdirectory: subdir1\n",
            (src / "subdir1" / "[[_copier_conf.answers_file]].tmpl"): (
                "[[_copier_answers|to_nice_yaml]]\n"
            ),
            (src / "subdir1" / "README.md"): "upstream version 1\n",
        }
    )
    with local.cwd(src):
        git_init("hello template")

    # Generate the project a first time, assert the README exists
    copier.run_copy(str(src), dst, defaults=True, overwrite=True)
    assert (dst / "README.md").exists()

    # Start versioning the generated project
    with local.cwd(dst):
        git_init("hello project")

        # After first commit, change the README, commit again
        Path("README.md").write_text("downstream version 1\n")
        git("commit", "-am", "updated readme")

    # Now change the template
    with local.cwd(src):
        # Update the README
        Path("subdir1", "README.md").write_text("upstream version 2\n")

        # Rename the subdirectory
        Path("subdir1").rename("subdir2")

        # Update copier.yml to reflect this change
        Path("copier.yml").write_text("_subdirectory: subdir2\n")

        # Commit the changes
        git("add", ".", "-A")
        git("commit", "-m", "changed from subdir1 to subdir2")

    # Finally, update the generated project
    copier.run_copy(
        str(src), dst, defaults=True, overwrite=True, skip_if_exists=["README.md"]
    )

    # Assert that the README still exists, and was NOT force updated
    assert (dst / "README.md").exists()
    assert (dst / "README.md").read_text() == "downstream version 1\n"

    # Also assert the subdirectories themselves were not rendered
    assert not (dst / "subdir1").exists()
    assert not (dst / "subdir2").exists()
