"""User settings models and helper functions."""

from __future__ import annotations

import os
import re
import warnings
from os.path import expanduser
from pathlib import Path
from typing import Any

import yaml
from platformdirs import user_config_path
from pydantic import BaseModel, Field, field_validator, model_validator

from .errors import MissingSettingsWarning

ENV_VAR = "COPIER_SETTINGS_PATH"

RE_REF = re.compile(r"^(?P<url>.+?)@(?P<ref>[^:]+)$")


class Shortcut(BaseModel):
    """Shortcut model."""

    url: str = Field(description="Prefix url to replace the prefix with.")
    suffix: bool = Field(default=True, description="Whether to add a `.git` suffix.")

    @model_validator(mode="before")
    @classmethod
    def handle_string(cls, value: Any) -> Any:
        """Allow short syntax using string only."""
        if isinstance(value, str):
            return {"url": value}
        return value

    @field_validator("url", mode="after")
    @classmethod
    def inject_trailing_slash(cls, value: str) -> str:
        """Always add a trailing slash."""
        if not value.endswith("/"):
            value += "/"
        return value


DEFAULT_SHORTCUTS = {
    "gh": Shortcut(url="https://github.com/"),
    "gl": Shortcut(url="https://gitlab.com/"),
}


class Settings(BaseModel):
    """User settings model."""

    defaults: dict[str, Any] = Field(
        default_factory=dict, description="Default values for questions"
    )
    shortcuts: dict[str, Shortcut] = Field(
        DEFAULT_SHORTCUTS, description="URL shortcuts"
    )
    trust: set[str] = Field(
        default_factory=set, description="List of trusted repositories or prefixes"
    )

    @classmethod
    def from_file(cls, settings_path: Path | None = None) -> Settings:
        """Load settings from a file."""
        env_path = os.getenv(ENV_VAR)
        if settings_path is None:
            if env_path:
                settings_path = Path(env_path)
            else:
                settings_path = user_config_path("copier") / "settings.yml"
        if settings_path.is_file():
            data = yaml.safe_load(settings_path.read_text())
            return cls.model_validate(data)
        elif env_path:
            warnings.warn(
                f"Settings file not found at {env_path}", MissingSettingsWarning
            )
        return cls()

    @field_validator("shortcuts", mode="after")
    @classmethod
    def inject_defaults(cls, value: dict[str, Shortcut]) -> dict[str, Shortcut]:
        """Ensure default are always present unless overridden."""
        return {**DEFAULT_SHORTCUTS, **value}

    def is_trusted(self, repository: str) -> bool:
        """Check if a repository is trusted."""
        return any(
            self.normalize(repository).startswith(self.normalize(trusted))
            if trusted.endswith("/")
            else self.normalize(repository) == self.normalize(trusted)
            for trusted in self.trust
        )

    def normalize(self, url: str) -> str:
        """Normalize an URL using user settings."""
        url, ref = url.removeprefix("git+"), None
        if m := RE_REF.match(url):
            url = m.group("url")
            ref = m.group("ref")
        for prefix, shortcut in self.shortcuts.items():
            prefix = f"{prefix}:"
            if url.startswith(prefix):
                # Inject shortcut
                url = url.replace(prefix, shortcut.url)
                # Remove double slash if any
                url = url.replace(f"{shortcut.url}/", shortcut.url)
            if url.startswith(shortcut.url):
                if not url.endswith((".git", "/")):
                    url += ".git" if shortcut.suffix else "/"
                break
        if url.startswith("~"):  # Only expand on str to avoid messing with URLs
            url = expanduser(url)
        if ref:
            url = f"{url}@{ref}"
        return url
