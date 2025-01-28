"""Custom exceptions used by Copier."""

from pathlib import Path
from typing import TYPE_CHECKING, Sequence

from .tools import printf_exception
from .types import PathSeq

if TYPE_CHECKING:  # always false
    from .template import Template
    from .user_data import AnswersMap, Question


# Errors
class CopierError(Exception):
    """Base class for all other Copier errors."""


class UserMessageError(CopierError):
    """Exit the program giving a message to the user."""


class UnsupportedVersionError(UserMessageError):
    """Copier version does not support template version."""


class ConfigFileError(ValueError, CopierError):
    """Parent class defining problems with the config file."""


class InvalidConfigFileError(ConfigFileError):
    """Indicates that the config file is wrong."""

    def __init__(self, conf_path: Path, quiet: bool):
        msg = str(conf_path)
        printf_exception(self, "INVALID CONFIG FILE", msg=msg, quiet=quiet)
        super().__init__(msg)


class MultipleConfigFilesError(ConfigFileError):
    """Both copier.yml and copier.yaml found, and that's an error."""

    def __init__(self, conf_paths: "PathSeq"):
        msg = str(conf_paths)
        printf_exception(self, "MULTIPLE CONFIG FILES", msg=msg)
        super().__init__(msg)


class InvalidTypeError(TypeError, CopierError):
    """The question type is not among the supported ones."""


class PathError(CopierError, ValueError):
    """The path is invalid in the given context."""


class PathNotAbsoluteError(PathError):
    """The path is not absolute, but it should be."""

    def __init__(self, *, path: Path) -> None:
        super().__init__(f'"{path}" is not an absolute path')


class PathNotRelativeError(PathError):
    """The path is not relative, but it should be."""

    def __init__(self, *, path: Path) -> None:
        super().__init__(f'"{path}" is not a relative path')


class ExtensionNotFoundError(UserMessageError):
    """Extensions listed in the configuration could not be loaded."""


class CopierAnswersInterrupt(CopierError, KeyboardInterrupt):
    """CopierAnswersInterrupt is raised during interactive question prompts.

    It typically follows a KeyboardInterrupt (i.e. ctrl-c) and provides an
    opportunity for the caller to conduct additional cleanup, such as writing
    the partially completed answers to a file.

    Attributes:
        answers:
            AnswersMap that contains the partially completed answers object.

        last_question:
            Question representing the last_question that was asked at the time
            the interrupt was raised.

        template:
            Template that was being processed for answers.

    """

    def __init__(
        self, answers: "AnswersMap", last_question: "Question", template: "Template"
    ) -> None:
        self.answers = answers
        self.last_question = last_question
        self.template = template


class UnsafeTemplateError(CopierError):
    """Unsafe Copier template features are used without explicit consent."""

    def __init__(self, features: Sequence[str]):
        assert features
        s = "s" if len(features) > 1 else ""
        super().__init__(
            f"Template uses potentially unsafe feature{s}: {', '.join(features)}.\n"
            "If you trust this template, consider adding the `--trust` option when running `copier copy/update`."
        )


class YieldTagInFileError(CopierError):
    """A yield tag is used in the file content, but it is not allowed."""


class MultipleYieldTagsError(CopierError):
    """Multiple yield tags are used in one path name, but it is not allowed."""


# Warnings
class CopierWarning(Warning):
    """Base class for all other Copier warnings."""


class UnknownCopierVersionWarning(UserWarning, CopierWarning):
    """Cannot determine installed Copier version."""


class OldTemplateWarning(UserWarning, CopierWarning):
    """Template was designed for an older Copier version."""


class DirtyLocalWarning(UserWarning, CopierWarning):
    """Changes and untracked files present in template."""


class ShallowCloneWarning(UserWarning, CopierWarning):
    """The template repository is a shallow clone."""


class MissingSettingsWarning(UserWarning, CopierWarning):
    """Settings path has been defined but file is missing."""
