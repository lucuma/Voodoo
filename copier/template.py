"""Tools related to template management."""
from contextlib import suppress
from pathlib import Path
from typing import List, Mapping, Optional, Sequence, Set, Tuple

from packaging import version
from packaging.version import parse
from plumbum.cmd import git
from plumbum.machines import local
from pydantic.dataclasses import dataclass

from .errors import UnsupportedVersionError
from .types import AnyByStrDict, OptStr, StrSeq, VCSTypes
from .user_data import load_config_data
from .vcs import checkout_latest_tag, clone, get_repo

try:
    from functools import cached_property
except ImportError:
    from backports.cached_property import cached_property

# Default list of files in the template to exclude from the rendered project
DEFAULT_EXCLUDE: Tuple[str, ...] = (
    "copier.yaml",
    "copier.yml",
    "~*",
    "*.py[co]",
    "__pycache__",
    ".git",
    ".DS_Store",
    ".svn",
)

DEFAULT_TEMPLATES_SUFFIX = ".tmpl"


def filter_config(data: AnyByStrDict) -> Tuple[AnyByStrDict, AnyByStrDict]:
    """Separates config and questions data."""
    conf_data: AnyByStrDict = {"secret_questions": set()}
    questions_data = {}
    for k, v in data.items():
        if k == "_secret_questions":
            conf_data["secret_questions"].update(v)
        elif k.startswith("_"):
            conf_data[k[1:]] = v
        else:
            # Transform simplified questions format into complex
            if not isinstance(v, dict):
                v = {"default": v}
            questions_data[k] = v
            if v.get("secret"):
                conf_data["secret_questions"].add(k)
    return conf_data, questions_data


def verify_minimum_version(version_str: str) -> None:
    """Raise an error if the current Copier version is less than the given version."""
    # Importing __version__ at the top of the module creates a circular import
    # ("cannot import name '__version__' from partially initialized module 'copier'"),
    # so instead we do a lazy import here
    from . import __version__

    # Disable check when running copier as editable installation
    if __version__ == "0.0.0":
        return

    if version.parse(__version__) < version.parse(version_str):
        raise UnsupportedVersionError(
            f"This template requires Copier version >= {version_str}, "
            f"while your version of Copier is {__version__}."
        )


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
    ref: OptStr = None
    use_prereleases: bool = False

    @cached_property
    def _raw_config(self) -> AnyByStrDict:
        """Get template configuration, raw.

        It reads [the `copier.yml` file][the-copieryml-file].
        """
        result = load_config_data(self.local_abspath)
        with suppress(KeyError):
            verify_minimum_version(result["_min_copier_version"])
        return result

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
    def commit(self) -> OptStr:
        """If the template is VCS-tracked, get its commit description."""
        if self.vcs == "git":
            with local.cwd(self.local_abspath):
                return git("describe", "--tags", "--always").strip()

    @cached_property
    def config_data(self) -> AnyByStrDict:
        """Get config from the template.

        It reads [the `copier.yml` file][the-copieryml-file] to get its
        [settings][available-settings].
        """
        return filter_config(self._raw_config)[0]

    @cached_property
    def default_answers(self) -> AnyByStrDict:
        """Get default answers for template's questions."""
        return {key: value.get("default") for key, value in self.questions_data.items()}

    @cached_property
    def envops(self) -> Mapping:
        """Get the Jinja configuration specified in the template, or default values.

        See [envops][].
        """
        # TODO Use Jinja defaults
        result = {
            "autoescape": False,
            "block_end_string": "%]",
            "block_start_string": "[%",
            "comment_end_string": "#]",
            "comment_start_string": "[#",
            "keep_trailing_newline": True,
            "variable_end_string": "]]",
            "variable_start_string": "[[",
        }
        result.update(self.config_data.get("envops", {}))
        return result

    @cached_property
    def exclude(self) -> Tuple[str, ...]:
        """Get exclusions specified in the template, or default ones.

        See [exclude][].
        """
        return tuple(self.config_data.get("exclude", DEFAULT_EXCLUDE))

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

    def migration_tasks(self, stage: str, from_: str, to: str) -> Sequence[Mapping]:
        """Get migration objects that match current version spec.

        Versions are compared using PEP 440.

        See [migrations][].
        """
        result: List[dict] = []
        if not from_ or not to:
            return result
        parsed_from = parse(from_)
        parsed_to = parse(to)
        extra_env = {
            "STAGE": stage,
            "VERSION_FROM": from_,
            "VERSION_TO": to,
        }
        migration: dict
        for migration in self._raw_config.get("_migrations", []):
            if parsed_to >= parse(migration["version"]) > parsed_from:
                extra_env = dict(extra_env, VERSION_CURRENT=str(migration["version"]))
                result += [
                    {"task": task, "extra_env": extra_env}
                    for task in migration.get(stage, [])
                ]
        return result

    @cached_property
    def questions_data(self) -> AnyByStrDict:
        """Get questions from the template.

        See [questions][].
        """
        return filter_config(self._raw_config)[1]

    @cached_property
    def secret_questions(self) -> Set[str]:
        """Get names of secret questions from the template.

        These questions shouldn't be saved into the answers file.
        """
        result = set(self.config_data.get("secret_questions", {}))
        for key, value in self.questions_data.items():
            if value.get("secret"):
                result.add(key)
        return result

    @cached_property
    def skip_if_exists(self) -> StrSeq:
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
    def tasks(self) -> Sequence:
        """Get tasks defined in the template.

        See [tasks][].
        """
        return self.config_data.get("tasks", [])

    @cached_property
    def templates_suffix(self) -> str:
        """Get the suffix defined for templates.

        By default: `.tmpl`.

        See [templates_suffix][].
        """
        return self.config_data.get("templates_suffix", DEFAULT_TEMPLATES_SUFFIX)

    @cached_property
    def local_abspath(self) -> Path:
        """Get the absolute path to the template on disk.

        This may clone it if `url` points to a
        VCS-tracked template.
        """
        result = Path(self.url)
        if self.vcs == "git":
            result = Path(clone(self.url_expanded, self.ref))
            if self.ref is None:
                checkout_latest_tag(result, self.use_prereleases)
        if not result.is_dir():
            raise ValueError("Local template must be a directory.")
        return result.absolute()

    @cached_property
    def url_expanded(self) -> str:
        """Get usable URL.

        `url` can be specified in shortcut
        format, which wouldn't be understood by the underlying VCS system. This
        property returns the expanded version, which should work properly.
        """
        return get_repo(self.url) or self.url

    @cached_property
    def vcs(self) -> Optional[VCSTypes]:
        """Get VCS system used by the template, if any."""
        if get_repo(self.url):
            return "git"
