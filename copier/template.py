"""Tools related to template management."""
from __future__ import annotations

import re
import sys
from collections import ChainMap, defaultdict
from contextlib import suppress
from dataclasses import field
from functools import cached_property
from pathlib import Path, PurePosixPath
from shutil import rmtree
from typing import Any, Literal, Mapping, Sequence
from warnings import warn

import dunamai
import packaging.version
import yaml
from funcy import lflatten
from packaging.version import Version, parse
from plumbum.machines import local
from pydantic.dataclasses import dataclass

from .errors import (
    InvalidConfigFileError,
    MultipleConfigFilesError,
    OldTemplateWarning,
    UnknownCopierVersionWarning,
    UnsupportedVersionError,
)
from .tools import copier_version, handle_remove_readonly
from .types import AnyByStrDict, Env, VCSTypes
from .vcs import checkout_latest_tag, clone, get_git, get_repo

# Default list of files in the template to exclude from the rendered project
DEFAULT_EXCLUDE: tuple[str, ...] = (
    "copier.yaml",
    "copier.yml",
    "~*",
    "*.py[co]",
    "__pycache__",
    ".git",
    ".DS_Store",
    ".svn",
)

DEFAULT_TEMPLATES_SUFFIX = ".jinja"


def filter_config(data: AnyByStrDict) -> tuple[AnyByStrDict, AnyByStrDict]:
    """Separates config and questions data."""
    config_data: AnyByStrDict = {}
    questions_data = {}
    for k, v in data.items():
        if k.startswith("_"):
            config_data[k[1:]] = v
        else:
            # Transform simplified questions format into complex
            if not isinstance(v, dict):
                v = {"default": v}
            questions_data[k] = v
    return config_data, questions_data


def load_template_config(conf_path: Path, quiet: bool = False) -> AnyByStrDict:
    """Load the `copier.yml` file.

    This is like a simple YAML load, but applying all specific quirks needed
    for [the `copier.yml` file][the-copieryml-file].

    For example, it supports the `!include` tag with glob includes, and
    merges multiple sections.

    Params:
        conf_path: The path to the `copier.yml` file.
        quiet: Used to configure the exception.

    Raises:
        InvalidConfigFileError: When the file is formatted badly.
    """

    class _Loader(yaml.FullLoader):
        """Intermediate class to avoid monkey-patching main loader."""

    def _include(loader: yaml.Loader, node: yaml.Node) -> Any:
        if not isinstance(node, yaml.ScalarNode):
            raise ValueError(f"Unsupported YAML node: {node!r}")
        include_file = str(loader.construct_scalar(node))
        if PurePosixPath(include_file).is_absolute():
            raise ValueError("YAML include file path must be a relative path")
        return [
            yaml.load(path.read_bytes(), Loader=type(loader))
            for path in conf_path.parent.glob(include_file)
        ]

    _Loader.add_constructor("!include", _include)

    with conf_path.open("rb") as f:
        try:
            flattened_result = lflatten(filter(None, yaml.load_all(f, Loader=_Loader)))
        except yaml.parser.ParserError as e:
            raise InvalidConfigFileError(conf_path, quiet) from e

    merged_options = defaultdict(list)
    for option in (
        "_exclude",
        "_jinja_extensions",
        "_secret_questions",
        "_skip_if_exists",
    ):
        for result in flattened_result:
            if option in result:
                merged_options[option].extend(result[option])

    return dict(ChainMap(dict(merged_options), *reversed(flattened_result)))


def verify_copier_version(version_str: str) -> None:
    """Raise an error if the current Copier version is less than the given version.

    Args:
        version_str:
            Minimal copier version for the template.
    """
    installed_version = copier_version()

    # Disable check when running copier as editable installation
    if installed_version == Version("0.0.0"):
        warn(
            "Cannot check Copier version constraint.",
            UnknownCopierVersionWarning,
        )
        return
    parsed_min = Version(version_str)
    if installed_version < parsed_min:
        raise UnsupportedVersionError(
            f"This template requires Copier version >= {version_str}, "
            f"while your version of Copier is {installed_version}."
        )
    if installed_version.major > parsed_min.major:
        warn(
            f"This template was designed for Copier {version_str}, "
            f"but your version of Copier is {installed_version}. "
            f"You could find some incompatibilities.",
            OldTemplateWarning,
        )


@dataclass
class Task:
    """Object that represents a task to execute.

    Attributes:
        cmd:
            Command to execute.

        extra_env:
            Additional environment variables to set while executing the command.
    """

    cmd: str | Sequence[str]
    extra_env: Env = field(default_factory=dict)


@dataclass
class Template:
    """Object that represents a template and its current state.

    See [configuring a template][configuring-a-template].

    Attributes:
        url:
            Absolute origin that points to the template.

            It can be:

            - A local path.
            - A Git url. Note: if something fails, prefix the URL with `git+`.

        ref:
            The tag to checkout in the template.

            Only used if `url` points to a VCS-tracked template.

            If `None`, then it will checkout the latest tag, sorted by PEP440.
            Otherwise it will checkout the reference used here.

            Usually it should be a tag, or `None`.

        use_prereleases:
            When `True`, the template's *latest* release will consider prereleases.

            Only used if:

            - `url` points to a VCS-tracked template
            - `ref` is `None`.

            Helpful if you want to test templates before doing a proper release, but you
            need some features that require a proper PEP440 version identifier.
    """

    url: str
    ref: str | None = None
    use_prereleases: bool = False

    def _cleanup(self) -> None:
        temp_clone = self._temp_clone()
        if temp_clone:
            if sys.version_info >= (3, 12):
                rmtree(
                    temp_clone,
                    ignore_errors=False,
                    onexc=handle_remove_readonly,
                )
            else:
                rmtree(
                    temp_clone,
                    ignore_errors=False,
                    onerror=handle_remove_readonly,
                )

    def _temp_clone(self) -> Path | None:
        """Get the path to the temporary clone of the template.

        If the template hasn't yet been cloned, or if it was a local template,
        then there's no temporary clone and this will return `None`.
        """
        if "local_abspath" not in self.__dict__:
            return None
        clone_path = self.local_abspath
        original_path = Path(self.url).expanduser()
        with suppress(OSError):  # triggered for URLs on Windows
            original_path = original_path.resolve()
        if clone_path != original_path:
            return clone_path
        return None

    @cached_property
    def _raw_config(self) -> AnyByStrDict:
        """Get template configuration, raw.

        It reads [the `copier.yml` file][the-copieryml-file].
        """
        conf_paths = [
            p
            for p in self.local_abspath.glob("copier.*")
            if p.is_file() and re.match(r"\.ya?ml", p.suffix, re.I)
        ]
        if len(conf_paths) > 1:
            raise MultipleConfigFilesError(conf_paths)
        elif len(conf_paths) == 1:
            return load_template_config(conf_paths[0])
        return {}

    @cached_property
    def answers_relpath(self) -> Path:
        """Get the answers file relative path, as specified in the template.

        If not specified, returns the default `.copier-answers.yml`.

        See [answers_file][].
        """
        result = Path(self.config_data.get("answers_file", ".copier-answers.yml"))
        assert not result.is_absolute()
        return result

    @cached_property
    def commit(self) -> str | None:
        """If the template is VCS-tracked, get its commit description."""
        if self.vcs == "git":
            with local.cwd(self.local_abspath):
                return get_git()("describe", "--tags", "--always").strip()
        return None

    @cached_property
    def commit_hash(self) -> str | None:
        """If the template is VCS-tracked, get its commit full hash."""
        if self.vcs == "git":
            return get_git()("-C", self.local_abspath, "rev-parse", "HEAD").strip()
        return None

    @cached_property
    def config_data(self) -> AnyByStrDict:
        """Get config from the template.

        It reads [the `copier.yml` file][the-copieryml-file] to get its
        [settings][available-settings].
        """
        result = filter_config(self._raw_config)[0]
        with suppress(KeyError):
            verify_copier_version(result["min_copier_version"])
        return result

    @cached_property
    def envops(self) -> Mapping[str, Any]:
        """Get the Jinja configuration specified in the template, or default values.

        See [envops][].
        """
        result = self.config_data.get("envops", {})
        if "keep_trailing_newline" not in result:
            # NOTE: we want to keep trailing newlines in templates as this is what a
            #       user will most likely expects as a default.
            #       See https://github.com/copier-org/copier/issues/464
            result["keep_trailing_newline"] = True
        return result

    @cached_property
    def exclude(self) -> tuple[str, ...]:
        """Get exclusions specified in the template, or default ones.

        See [exclude][].
        """
        return tuple(
            self.config_data.get(
                "exclude",
                DEFAULT_EXCLUDE if Path(self.subdirectory) == Path(".") else [],
            )
        )

    @cached_property
    def jinja_extensions(self) -> tuple[str, ...]:
        """Get Jinja2 extensions specified in the template, or `()`.

        See [jinja_extensions][].
        """
        return tuple(self.config_data.get("jinja_extensions", ()))

    @cached_property
    def message_after_copy(self) -> str:
        """Get message to print after copy action specified in the template."""
        return self.config_data.get("message_after_copy", "")

    @cached_property
    def message_after_update(self) -> str:
        """Get message to print after update action specified in the template."""
        return self.config_data.get("message_after_update", "")

    @cached_property
    def message_before_copy(self) -> str:
        """Get message to print before copy action specified in the template."""
        return self.config_data.get("message_before_copy", "")

    @cached_property
    def message_before_update(self) -> str:
        """Get message to print before update action specified in the template."""
        return self.config_data.get("message_before_update", "")

    @cached_property
    def metadata(self) -> AnyByStrDict:
        """Get template metadata.

        This data, if any, should be saved in the answers file to be able to
        restore the template to this same state.
        """
        result: AnyByStrDict = {"_src_path": self.url}
        if self.commit:
            result["_commit"] = self.commit
        return result

    def migration_tasks(
        self, stage: Literal["before", "after"], from_template: Template
    ) -> Sequence[Task]:
        """Get migration objects that match current version spec.

        Versions are compared using PEP 440.

        See [migrations][].

        Args:
            stage: A valid stage name to find tasks for.
            from_template: Original template, from which we are migrating.
        """
        result: list[Task] = []
        if not (self.version and from_template.version):
            return result
        extra_env: Env = {
            "STAGE": stage,
            "VERSION_FROM": str(from_template.commit),
            "VERSION_TO": str(self.commit),
            "VERSION_PEP440_FROM": str(from_template.version),
            "VERSION_PEP440_TO": str(self.version),
        }
        migration: dict[str, Any]
        for migration in self._raw_config.get("_migrations", []):
            current = parse(migration["version"])
            if self.version >= current > from_template.version:
                extra_env = {
                    **extra_env,
                    "VERSION_CURRENT": migration["version"],
                    "VERSION_PEP440_CURRENT": str(current),
                }
                result.extend(
                    Task(cmd=cmd, extra_env=extra_env)
                    for cmd in migration.get(stage, [])
                )
        return result

    @cached_property
    def min_copier_version(self) -> Version | None:
        """Get minimal copier version for the template and validates it.

        See [min_copier_version][].
        """
        try:
            return Version(self.config_data["min_copier_version"])
        except KeyError:
            return None

    @cached_property
    def questions_data(self) -> AnyByStrDict:
        """Get questions from the template.

        See [questions][].
        """
        result = filter_config(self._raw_config)[1]
        for key in set(self.config_data.get("secret_questions", [])):
            if key in result:
                result[key]["secret"] = True
        return result

    @cached_property
    def secret_questions(self) -> set[str]:
        """Get names of secret questions from the template.

        These questions shouldn't be saved into the answers file.
        """
        result = set(self.config_data.get("secret_questions", []))
        for key, value in self.questions_data.items():
            if value.get("secret"):
                result.add(key)
        return result

    @cached_property
    def skip_if_exists(self) -> Sequence[str]:
        """Get skip patterns from the template.

        These files will never be rewritten when rendering the template.

        See [skip_if_exists][].
        """
        return self.config_data.get("skip_if_exists", ())

    @cached_property
    def subdirectory(self) -> str:
        """Get the subdirectory as specified in the template.

        The subdirectory points to the real template code, allowing the
        templater to separate it from other template assets, such as docs,
        tests, etc.

        See [subdirectory][].
        """
        return self.config_data.get("subdirectory", "")

    @cached_property
    def tasks(self) -> Sequence[Task]:
        """Get tasks defined in the template.

        See [tasks][].
        """
        return [
            Task(cmd=cmd, extra_env={"STAGE": "task"})
            for cmd in self.config_data.get("tasks", [])
        ]

    @cached_property
    def pre_copy(self) -> Sequence[Task]:
        """Get pre-copy tasks defined in the template.

        See [pre_copy][].
        """
        return [
            Task(cmd=cmd, extra_env={"STAGE": "pre_copy"})
            for cmd in self.config_data.get("pre_copy", [])
        ]

    @cached_property
    def post_copy(self) -> Sequence[Task]:
        """Get post-copy tasks defined in the template.

        See [post_copy][].
        """
        return [
            Task(cmd=cmd, extra_env={"STAGE": "post_copy"})
            for cmd in self.config_data.get("post_copy", [])
        ]

    @cached_property
    def pre_update(self) -> Sequence[Task]:
        """Get pre-update tasks defined in the template.

        See [pre_update][].
        """
        return [
            Task(cmd=cmd, extra_env={"STAGE": "pre_update"})
            for cmd in self.config_data.get("pre_update", [])
        ]

    @cached_property
    def post_update(self) -> Sequence[Task]:
        """Get post-update tasks defined in the template.

        See [post_update][].
        """
        return [
            Task(cmd=cmd, extra_env={"STAGE": "post_update"})
            for cmd in self.config_data.get("post_update", [])
        ]

    @cached_property
    def templates_suffix(self) -> str:
        """Get the suffix defined for templates.

        By default: `.jinja`.

        See [templates_suffix][].
        """
        result = self.config_data.get("templates_suffix")
        if result is None:
            return DEFAULT_TEMPLATES_SUFFIX
        return result

    @cached_property
    def preserve_symlinks(self) -> bool:
        """Know if Copier should preserve symlinks when rendering the template.

        See [preserve_symlinks][].
        """
        return bool(self.config_data.get("preserve_symlinks", False))

    @cached_property
    def local_abspath(self) -> Path:
        """Get the absolute path to the template on disk.

        This may clone it if `url` points to a VCS-tracked template.
        Dirty changes for local VCS-tracked templates will be copied.
        """
        result = Path(self.url)
        if self.vcs == "git":
            result = Path(clone(self.url_expanded, self.ref))
            if self.ref is None:
                checkout_latest_tag(result, self.use_prereleases)
        if not result.is_dir():
            raise ValueError("Local template must be a directory.")
        with suppress(OSError):
            result = result.resolve()
        return result

    @cached_property
    def url_expanded(self) -> str:
        """Get usable URL.

        `url` can be specified in shortcut
        format, which wouldn't be understood by the underlying VCS system. This
        property returns the expanded version, which should work properly.
        """
        return get_repo(self.url) or self.url

    @cached_property
    def version(self) -> Version | None:
        """PEP440-compliant version object."""
        if self.vcs != "git" or not self.commit:
            return None
        try:
            with local.cwd(self.local_abspath):
                # Leverage dunamai by default; usually it gets best results.
                # `dunamai.Version.from_git` needs `Pattern.DefaultUnprefixed`
                # to be PEP440 compliant on version reading
                return Version(
                    dunamai.Version.from_git(
                        pattern=dunamai.Pattern.DefaultUnprefixed
                    ).serialize(style=dunamai.Style.Pep440)
                )
        except ValueError:
            # A fully descriptive commit can be easily detected converted into a
            # PEP440 version, because it has the format "<tag>-<count>-g<hash>"
            if re.match(r"^.+-\d+-g\w+$", self.commit):
                base, count, git_hash = self.commit.rsplit("-", 2)
                return Version(f"{base}.post{count}+{git_hash}")
        # If we get here, the commit string is a tag
        try:
            return Version(self.commit)
        except packaging.version.InvalidVersion:
            # appears to not be a version
            return None

    @cached_property
    def vcs(self) -> VCSTypes | None:
        """Get VCS system used by the template, if any."""
        if get_repo(self.url):
            return "git"
        return None
