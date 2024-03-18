"""Objects to interact with subprojects.

A *subproject* is a project that gets rendered and/or updated with Copier.
"""

from __future__ import annotations

from dataclasses import field
from functools import cached_property
from pathlib import Path
from typing import Callable

import yaml
from plumbum.machines import local
from pydantic.dataclasses import dataclass

from .template import Template
from .types import AbsolutePath, AnyByStrDict, VCSTypes
from .vcs import get_git, is_in_git_repo


@dataclass
class Subproject:
    """Object that represents the subproject and its current state.

    Attributes:
        local_abspath:
            Absolute path on local disk pointing to the subproject root folder.

        answers_relpath:
            Relative path to [the answers file][the-copier-answersyml-file].
    """

    local_abspath: AbsolutePath
    answers_relpath: Path = Path(".copier-answers.yml")

    _cleanup_hooks: list[Callable] = field(default_factory=list, init=False)

    def is_dirty(self) -> bool:
        """Indicate if the local template root is dirty.

        Only applicable for VCS-tracked templates.
        """
        if self.vcs == "git":
            with local.cwd(self.local_abspath):
                return bool(get_git()("status", "--porcelain").strip())
        return False

    def _cleanup(self):
        """Remove temporary files and folders created by the subproject."""
        for method in self._cleanup_hooks:
            method()

    @property
    def _raw_answers(self) -> AnyByStrDict:
        """Get last answers, loaded raw as yaml."""
        try:
            return yaml.safe_load(
                (self.local_abspath / self.answers_relpath).read_text()
            )
        except OSError:
            return {}

    @cached_property
    def last_answers(self) -> AnyByStrDict:
        """Last answers, excluding private ones (except _src_path and _commit)."""
        return {
            key: value
            for key, value in self._raw_answers.items()
            if key in {"_src_path", "_commit"} or not key.startswith("_")
        }

    @cached_property
    def template(self) -> Template | None:
        """Template, as it was used the last time."""
        last_url = self.last_answers.get("_src_path")
        last_ref = self.last_answers.get("_commit")
        if last_url:
            result = Template(url=last_url, ref=last_ref)
            self._cleanup_hooks.append(result._cleanup)
            return result

    @cached_property
    def vcs(self) -> VCSTypes | None:
        """VCS type of the subproject."""
        if is_in_git_repo(self.local_abspath):
            return "git"
