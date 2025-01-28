from pathlib import Path

import pytest
import yaml
from plumbum import local

from copier import run_copy, run_update
from copier.errors import UnsafeTemplateError, UserMessageError

from .helpers import (
    COPIER_ANSWERS_FILE,
    PROJECT_TEMPLATE,
    build_file_tree,
    git,
    git_save,
)

SRC = Path(f"{PROJECT_TEMPLATE}_migrations").absolute()


def test_basic_migration(tmp_path_factory: pytest.TempPathFactory) -> None:
    """Test a basic migration running on every version"""
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))

    with local.cwd(src):
        build_file_tree(
            {
                **COPIER_ANSWERS_FILE,
                "copier.yml": (
                    """\
                    _migrations:
                        - touch foo
                    """
                ),
            }
        )
        git_save(tag="v1")
    with local.cwd(dst):
        run_copy(src_path=str(src))
        git_save()

    assert not (dst / "foo").exists()  # Migrations don't run on initial copy

    with local.cwd(src):
        git("tag", "v2")
    with local.cwd(dst):
        run_update(defaults=True, overwrite=True, unsafe=True)

    assert (dst / "foo").is_file()


def test_requires_unsafe(tmp_path_factory: pytest.TempPathFactory) -> None:
    """Tests that migrations require the unsafe flag to be passed"""
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))

    with local.cwd(src):
        build_file_tree(
            {
                **COPIER_ANSWERS_FILE,
                "copier.yml": (
                    """\
                    _migrations:
                        - touch foo
                    """
                ),
            }
        )
        git_save(tag="v1")
    with local.cwd(dst):
        run_copy(src_path=str(src))
        git_save()

    assert not (dst / "foo").exists()  # Migrations don't run on initial copy

    with local.cwd(src):
        git("tag", "v2")
    with local.cwd(dst):
        with pytest.raises(UnsafeTemplateError):
            run_update(defaults=True, overwrite=True, unsafe=False)

    assert not (dst / "foo").exists()


def test_version_migration(tmp_path_factory: pytest.TempPathFactory) -> None:
    """Test a migration running on a specific version"""
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))

    with local.cwd(src):
        build_file_tree(
            {
                **COPIER_ANSWERS_FILE,
                "copier.yml": (
                    """\
                    _migrations:
                    -   version: v3
                        command: touch foo
                    """
                ),
            }
        )
        git_save(tag="v1")
    with local.cwd(dst):
        run_copy(src_path=str(src))

    assert not (dst / "foo").exists()  # Migrations don't run on initial copy

    for i in range(2, 5):
        with local.cwd(src):
            git_save(tag=f"v{i}", allow_empty=True)
        with local.cwd(dst):
            git_save()
            run_update(defaults=True, overwrite=True, unsafe=True)

        if i == 3:
            assert (dst / "foo").is_file()
            (dst / "foo").unlink()
        else:
            assert not (dst / "foo").exists()


def test_prerelease_version_migration(tmp_path_factory: pytest.TempPathFactory) -> None:
    """Test if prerelease version migrations work"""
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))

    versions = ["v2.dev0", "v2.dev2", "v2.a1", "v2.a2"]

    with local.cwd(src):
        build_file_tree(
            {
                **COPIER_ANSWERS_FILE,
                "copier.yml": (
                    """\
                    _migrations:
                    -   version: v1.9
                        command: touch v1.9
                    -   version: v2.dev0
                        command: touch v2.dev0
                    -   version: v2.dev2
                        command: touch v2.dev2
                    -   version: v2.a1
                        command: touch v2.a1
                    -   version: v2.a2
                        command: touch v2.a2
                    """
                ),
            }
        )
        git_save(tag="v1")
    with local.cwd(dst):
        run_copy(src_path=str(src))
    with local.cwd(src):
        for version in ["v1.9", *versions]:
            git_save(tag=version, allow_empty=True)

    assert not (dst / "v1.9").exists()
    assert all(not (dst / version).exists() for version in versions)

    with local.cwd(dst):
        git_save()
        # No pre-releases. Should update to v1.9
        run_update(defaults=True, overwrite=True, unsafe=True)

    answers = yaml.safe_load((dst / ".copier-answers.yml").read_text())
    assert answers["_commit"] == "v1.9"
    assert (dst / "v1.9").exists()
    assert all(not (dst / version).exists() for version in versions)

    with local.cwd(dst):
        git_save()
        # With pre-releases. Should update to v2.a2
        run_update(defaults=True, overwrite=True, unsafe=True, use_prereleases=True)

    answers = yaml.safe_load((dst / ".copier-answers.yml").read_text())
    assert answers["_commit"] == "v2.a2"
    assert (dst / "v1.9").exists()
    assert all((dst / version).exists() for version in versions)

    with local.cwd(dst):
        git_save()
        with pytest.raises(UserMessageError):
            # Can't downgrade
            run_update(defaults=True, overwrite=True, unsafe=True)


def test_migration_working_directory(tmp_path_factory: pytest.TempPathFactory) -> None:
    """Test the working directory attribute of migrations"""
    src, dst, workdir = map(tmp_path_factory.mktemp, ("src", "dst", "workdir"))

    with local.cwd(src):
        build_file_tree(
            {
                **COPIER_ANSWERS_FILE,
                "copier.yml": (
                    f"""\
                    _migrations:
                    -   command: touch foo
                        working_directory: {workdir}
                    """
                ),
            }
        )
        git_save(tag="v1")
    with local.cwd(dst):
        run_copy(src_path=str(src))
        git_save()

    assert not (workdir / "foo").exists()  # Migrations don't run on initial copy

    with local.cwd(src):
        git("tag", "v2")
    with local.cwd(dst):
        run_update(defaults=True, overwrite=True, unsafe=True)

    assert not (dst / "foo").exists()
    assert (workdir / "foo").is_file()


@pytest.mark.parametrize("condition", (True, False))
def test_migration_condition(
    tmp_path_factory: pytest.TempPathFactory, condition: bool
) -> None:
    """Test the `when` argument of migrations"""
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))

    with local.cwd(src):
        build_file_tree(
            {
                **COPIER_ANSWERS_FILE,
                "copier.yml": (
                    f"""\
                    _migrations:
                    -   command: touch foo
                        when: {'true' if condition else 'false'}
                    """
                ),
            }
        )
        git_save(tag="v1")
    with local.cwd(dst):
        run_copy(src_path=str(src))
        git_save()

    assert not (dst / "foo").exists()  # Migrations don't run on initial copy

    with local.cwd(src):
        git("tag", "v2")
    with local.cwd(dst):
        run_update(defaults=True, overwrite=True, unsafe=True)

    assert (dst / "foo").is_file() == condition


def test_pretend_migration(tmp_path_factory: pytest.TempPathFactory) -> None:
    """Test that migrations aren't run in pretend mode"""
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))

    with local.cwd(src):
        build_file_tree(
            {
                **COPIER_ANSWERS_FILE,
                "copier.yml": (
                    """\
                    _migrations:
                    -   touch foo
                    """
                ),
            }
        )
        git_save(tag="v1")
    with local.cwd(dst):
        run_copy(src_path=str(src))
        git_save()

    assert not (dst / "foo").exists()  # Migrations don't run on initial copy

    with local.cwd(src):
        git("tag", "v2")
    with local.cwd(dst):
        run_update(defaults=True, overwrite=True, unsafe=True, pretend=True)

    assert not (dst / "foo").exists()  # In pretend mode the command shouldn't run


def test_skip_migration(tmp_path_factory: pytest.TempPathFactory) -> None:
    """Test that migrations aren't run in pretend mode"""
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))

    with local.cwd(src):
        build_file_tree(
            {
                **COPIER_ANSWERS_FILE,
                "copier.yml": (
                    """\
                    _migrations:
                    -   touch foo
                    """
                ),
            }
        )
        git_save(tag="v1")
    with local.cwd(dst):
        run_copy(src_path=str(src))
        git_save()

    assert not (dst / "foo").exists()  # Migrations don't run on initial copy

    with local.cwd(src):
        git("tag", "v2")
    with local.cwd(dst):
        run_update(defaults=True, overwrite=True, unsafe=True, skip_tasks=True)

    assert (dst / "foo").exists()  # Migrations are not skipped by skip_tasks


def test_migration_run_before(tmp_path_factory: pytest.TempPathFactory) -> None:
    """Test running migrations in the before upgrade step"""
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))

    with local.cwd(src):
        build_file_tree(
            {
                **COPIER_ANSWERS_FILE,
                # We replace an answer in the before step, so it will be used during update
                "copier.yml": (
                    """
                    hello:
                        default: World
                    _migrations:
                    -   command:
                        -   "{{ _copier_python }}"
                        -   -c
                        -   |
                            import yaml
                            with open(".copier-answers.yml", "r") as f:
                                v = yaml.safe_load(f)
                            v["hello"] = "Copier"
                            with open(".copier-answers.yml", "w") as f:
                                yaml.safe_dump(v, f)
                        when: \"{{ _stage == 'before' }}\"
                    """
                ),
                "foo.jinja": "Hello {{ hello }}",
            }
        )
        git_save(tag="v1")
    with local.cwd(dst):
        run_copy(src_path=str(src), defaults=True)
        git_save()

    assert (dst / "foo").is_file()
    assert (dst / "foo").read_text() == "Hello World"

    with local.cwd(src):
        build_file_tree({"foo": ""})
        git_save(tag="v2")
    with local.cwd(dst):
        run_update(defaults=True, overwrite=True, unsafe=True)

    assert (dst / "foo").is_file()
    assert (dst / "foo").read_text() == "Hello Copier"


@pytest.mark.parametrize("explicit", (True, False))
def test_migration_run_after(
    tmp_path_factory: pytest.TempPathFactory, explicit: bool
) -> None:
    """
    Test running migrations in the before upgrade step
    Also checks that this is the default behaviour if no `when` is given.
    """
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))

    with local.cwd(src):
        build_file_tree(
            {
                **COPIER_ANSWERS_FILE,
                "copier.yml": (
                    # Python < 3.11 don't support escapes in f-string expressions, so
                    # we use .format instead
                    """\
                    _migrations:
                    -   command: mv foo bar
                        {}
                    """.format("when: \"{{ _stage == 'after' }}\"" if explicit else "")
                ),
            }
        )
        git_save(tag="v1")
    with local.cwd(dst):
        run_copy(src_path=str(src))
        git_save()

    with local.cwd(src):
        build_file_tree({"foo": ""})
        git_save(tag="v2")
    with local.cwd(dst):
        run_update(defaults=True, overwrite=True, unsafe=True)

    assert not (dst / "foo").exists()
    assert (dst / "bar").is_file()


@pytest.mark.parametrize("with_version", [True, False])
def test_migration_env_variables(
    tmp_path_factory: pytest.TempPathFactory, with_version: bool
) -> None:
    """Test that environment variables are passed to the migration commands"""
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))

    variables = {
        "STAGE": "after",
        "VERSION_FROM": "v1",
        "VERSION_TO": "v3",
        "VERSION_PEP440_FROM": "1",
        "VERSION_PEP440_TO": "3",
    }
    current_only_variables = {
        "VERSION_CURRENT": "v2",
        "VERSION_PEP440_CURRENT": "2",
    }

    with local.cwd(src):
        build_file_tree(
            {
                **COPIER_ANSWERS_FILE,
                "copier.yml": (
                    f"""\
                    _migrations:
                    -   command: env > env.txt
                        {"version: v2" if with_version else ""}
                    """
                ),
            }
        )
        git_save(tag="v1")
    with local.cwd(dst):
        run_copy(src_path=str(src))
        git_save()

    assert not (dst / "foo").exists()  # Migrations don't run on initial copy

    with local.cwd(src):
        build_file_tree({"version": "v2"})
        git_save(tag="v2")
    with local.cwd(src):
        build_file_tree({"version": "v3"})
        git_save(tag="v3")
    with local.cwd(dst):
        run_update(defaults=True, overwrite=True, unsafe=True)

    assert (dst / "env.txt").is_file()
    env = (dst / "env.txt").read_text().split("\n")
    for variable, value in variables.items():
        assert f"{variable}={value}" in env

    for variable, value in current_only_variables.items():
        assert (f"{variable}={value}" in env) == with_version


@pytest.mark.parametrize("with_version", [True, False])
def test_migration_jinja_variables(
    tmp_path_factory: pytest.TempPathFactory, with_version: bool
) -> None:
    """Test that environment variables are passed to the migration commands"""
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))

    variables = {
        "_stage": "after",
        "_version_from": "v1",
        "_version_to": "v3",
        "_version_pep440_from": "1",
        "_version_pep440_to": "3",
    }
    current_only_variables = {
        "_version_current": "v2",
        "_version_pep440_current": "2",
    }
    all_variables = {**variables, **current_only_variables}

    command = "&&".join(
        f"echo {var}={{{{ {var} }}}} >> vars.txt" for var in all_variables
    )

    with local.cwd(src):
        build_file_tree(
            {
                **COPIER_ANSWERS_FILE,
                "copier.yml": (
                    f"""\
                    _migrations:
                    -   command: {command}
                        {"version: v2" if with_version else ""}
                    """
                ),
            }
        )
        git_save(tag="v1")
    with local.cwd(dst):
        run_copy(src_path=str(src))
        git_save()

    assert not (dst / "foo").exists()  # Migrations don't run on initial copy

    with local.cwd(src):
        build_file_tree({"version": "v2"})
        git_save(tag="v2")
    with local.cwd(src):
        build_file_tree({"version": "v3"})
        git_save(tag="v3")
    with local.cwd(dst):
        run_update(defaults=True, overwrite=True, unsafe=True)

    assert (dst / "vars.txt").is_file()
    raw_vars = (dst / "vars.txt").read_text().split("\n")
    vars = map(lambda x: x.strip(), raw_vars)
    for variable, value in variables.items():
        assert f"{variable}={value}" in vars

    for variable, value in current_only_variables.items():
        if with_version:
            assert f"{variable}={value}" in vars
        else:
            assert f"{variable}=" in vars


def test_copier_phase_variable(tmp_path_factory: pytest.TempPathFactory) -> None:
    """Test that the Phase variable is properly set."""
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))

    with local.cwd(src):
        build_file_tree(
            {
                **COPIER_ANSWERS_FILE,
                "copier.yml": (
                    """\
                    _migrations:
                        - touch {{ _copier_phase }}
                    """
                ),
            }
        )
        git_save(tag="v1")
    with local.cwd(dst):
        run_copy(src_path=str(src))
        git_save()

    with local.cwd(src):
        git("tag", "v2")
    with local.cwd(dst):
        run_update(defaults=True, overwrite=True, unsafe=True)

    assert (dst / "migrate").is_file()
