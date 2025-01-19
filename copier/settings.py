"""User settings models and helper functions."""
from __future__ import annotations

import os
import warnings
from pathlib import Path
from typing import Any

import yaml
from platformdirs import user_config_path
from pydantic import BaseModel, Field

from .errors import MissingSettingsWarning

ENV_VAR = "COPIER_SETTINGS_PATH"


class Settings(BaseModel):
    """User settings model."""

    defaults: dict[str, Any] = Field(default_factory=dict)

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
