from __future__ import annotations

from pathlib import Path

import pytest

from copier.errors import MissingSettingsWarning
from copier.settings import Settings


def test_default_settings() -> None:
    settings = Settings()

    assert settings.defaults == {}


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
