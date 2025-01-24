from __future__ import annotations

from pathlib import Path

import pytest

from copier.errors import MissingSettingsWarning
from copier.settings import DEFAULT_SHORTCUTS, Settings, Shortcut


def test_default_settings() -> None:
    settings = Settings()

    assert settings.defaults == {}
    assert settings.trust == set()
    assert settings.shortcuts == DEFAULT_SHORTCUTS


def test_settings_from_default_location(settings_path: Path) -> None:
    settings_path.write_text("defaults:\n  foo: bar")

    settings = Settings.from_file()

    assert settings.defaults == {"foo": "bar"}


@pytest.mark.usefixtures("config_path")
def test_settings_from_default_location_dont_exists() -> None:
    settings = Settings.from_file()

    assert settings.defaults == {}


def test_settings_from_env_location(
    settings_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings_path.write_text("defaults:\n  foo: bar")

    settings_from_env_path = tmp_path / "settings.yml"
    settings_from_env_path.write_text("defaults:\n  foo: baz")

    monkeypatch.setenv("COPIER_SETTINGS_PATH", str(settings_from_env_path))

    settings = Settings.from_file()

    assert settings.defaults == {"foo": "baz"}


def test_settings_from_param(
    settings_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings_path.write_text("defaults:\n  foo: bar")

    settings_from_env_path = tmp_path / "settings.yml"
    settings_from_env_path.write_text("defaults:\n  foo: baz")

    monkeypatch.setenv("COPIER_SETTINGS_PATH", str(settings_from_env_path))

    file_path = tmp_path / "file.yml"
    file_path.write_text("defaults:\n  from: file")

    settings = Settings.from_file(file_path)

    assert settings.defaults == {"from": "file"}


def test_settings_defined_but_missing(
    settings_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COPIER_SETTINGS_PATH", str(settings_path))

    with pytest.warns(MissingSettingsWarning):
        Settings.from_file()


@pytest.mark.parametrize(
    ("repository", "trust", "is_trusted"),
    [
        ("https://github.com/user/repo.git", set(), False),
        (
            "https://github.com/user/repo.git",
            {"https://github.com/user/repo.git"},
            True,
        ),
        ("https://github.com/user/repo", {"https://github.com/user/repo.git"}, True),
        ("https://github.com/user/repo.git", {"https://github.com/user/"}, True),
        ("https://github.com/user/repo.git", {"https://github.com/user/repo"}, True),
        ("https://github.com/user/repo.git", {"https://github.com/user"}, False),
        ("https://github.com/user/repo.git", {"https://github.com/"}, True),
        ("https://github.com/user/repo.git", {"https://github.com"}, False),
        (f"{Path.home()}/template", set(), False),
        (f"{Path.home()}/template", {f"{Path.home()}/template"}, True),
        (f"{Path.home()}/template", {"~/template"}, True),
        ("~/template", {f"{Path.home()}/template"}, True),
        (f"{Path.home()}/path/to/template", {"~/path/to/template"}, True),
        (f"{Path.home()}/path/to/template", {"~/path/to/"}, True),
        (f"{Path.home()}/path/to/template", {"~/path/to"}, False),
        ("https://github.com/user/repo.git", {"gh:user/"}, True),
        ("https://github.com/user/repo.git", {"gh:user/repo"}, True),
        ("https://github.com/user/repo.git", {"gh:user/rep"}, False),
    ],
)
def test_is_trusted(repository: str, trust: set[str], is_trusted: bool) -> None:
    settings = Settings(trust=trust)

    assert settings.is_trusted(repository) == is_trusted


@pytest.mark.parametrize(
    "provided,expected",
    [
        ({}, DEFAULT_SHORTCUTS),
        # Default shortcuts are always provided
        (
            {"some": {"url": "https://somewhere.com/", "suffix": False}},
            {
                "some": Shortcut(url="https://somewhere.com/", suffix=False),
                **DEFAULT_SHORTCUTS,
            },
        ),
        # Trailing slash is always appended
        (
            {"some": {"url": "https://somewhere.com"}},
            {
                "some": Shortcut(url="https://somewhere.com/"),
                **DEFAULT_SHORTCUTS,
            },
        ),
        # strings are properly handled
        (
            {"some": "https://somewhere.com/"},
            {
                "some": Shortcut(url="https://somewhere.com/"),
                **DEFAULT_SHORTCUTS,
            },
        ),
        # Default are overridable
        (
            {"gh": "https://somewhere.com/"},
            {
                "gh": Shortcut(url="https://somewhere.com/"),
                "gl": Shortcut(url="https://gitlab.com/"),
            },
        ),
    ],
)
def test_shortcuts_parsing(
    provided: dict[str, str | Shortcut], expected: dict[str, Shortcut]
) -> None:
    settings = Settings(shortcuts=provided)

    assert settings.shortcuts == expected


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://github.com/user/repo", "https://github.com/user/repo.git"),
        ("gh:user/repo", "https://github.com/user/repo.git"),
        ("gl:user/repo", "https://gitlab.com/user/repo.git"),
        ("gh:/user/repo", "https://github.com/user/repo.git"),
        ("gh:user/repo.git", "https://github.com/user/repo.git"),
        ("gh:/user/repo.git", "https://github.com/user/repo.git"),
        ("gh:user/", "https://github.com/user/"),
        ("gh:/user/", "https://github.com/user/"),
        ("gh:user", "https://github.com/user.git"),
        ("local:", f"{Path.home()}/projects/"),
        ("local:/", f"{Path.home()}/projects/"),
        ("local:dir", f"{Path.home()}/projects/dir/"),
        ("local:/dir", f"{Path.home()}/projects/dir/"),
        ("local:dir/", f"{Path.home()}/projects/dir/"),
        ("~/projects", f"{Path.home()}/projects"),
        (
            "git://git.myproject.org/MyProject.git@master",
            "git://git.myproject.org/MyProject.git@master",
        ),
        (
            "git://git.myproject.org/MyProject@master",
            "git://git.myproject.org/MyProject.git@master",
        ),
        (
            "git://git.myproject.org/MyProject.git@v1.0",
            "git://git.myproject.org/MyProject.git@v1.0",
        ),
        (
            "git://git.myproject.org/MyProject.git@da39a3ee5e6b4b0d3255bfef956018",
            "git://git.myproject.org/MyProject.git@da39a3ee5e6b4b0d3255bfef956018",
        ),
        (
            "project:MyProject@master",
            "git://git.myproject.org/MyProject.git@master",
        ),
        ("project:MyProject.git@v1.0", "git://git.myproject.org/MyProject.git@v1.0"),
        (
            "project:MyProject@da39a3ee5e6b4b0d3255bfef956018",
            "git://git.myproject.org/MyProject.git@da39a3ee5e6b4b0d3255bfef956018",
        ),
        ("git+https://github.com/user/repo", "https://github.com/user/repo.git"),
        (
            "git@git.myproject.org:MyProject@master",
            "git@git.myproject.org:MyProject@master",
        ),
    ],
)
def test_normalize(url: str, expected: str) -> None:
    settings = Settings(
        shortcuts={
            "local": Shortcut(url="~/projects", suffix=False),
            "project": Shortcut(url="git://git.myproject.org/"),
        }
    )

    assert settings.normalize(url) == expected
