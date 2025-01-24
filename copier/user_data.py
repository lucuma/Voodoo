"""Functions used to load user data."""

from __future__ import annotations

import json
import warnings
from collections import ChainMap
from dataclasses import field
from datetime import datetime
from functools import cached_property
from hashlib import sha512
from os import urandom
from pathlib import Path
from typing import Any, Callable, Literal, Mapping, Sequence

import yaml
from jinja2 import UndefinedError
from jinja2.sandbox import SandboxedEnvironment
from prompt_toolkit.lexers import PygmentsLexer
from pydantic import ConfigDict, Field, field_validator
from pydantic.dataclasses import dataclass
from pydantic_core.core_schema import ValidationInfo
from pygments.lexers.data import JsonLexer, YamlLexer
from questionary.prompts.common import Choice

from copier.settings import Settings

from .errors import InvalidTypeError, UserMessageError
from .tools import cast_to_bool, cast_to_str, force_str_end
from .types import MISSING, AnyByStrDict, MissingType, OptStrOrPath, StrOrPath


# TODO Remove these two functions as well as DEFAULT_DATA in a future release
def _now() -> datetime:
    warnings.warn(
        "'now' will be removed in a future release of Copier.\n"
        "Please use this instead: {{ '%Y-%m-%d %H:%M:%S' | strftime }}\n"
        "strftime format reference https://strftime.org/",
        FutureWarning,
    )
    return datetime.utcnow()


def _make_secret() -> str:
    warnings.warn(
        "'make_secret' will be removed in a future release of Copier.\n"
        "Please use this instead: {{ 999999999999999999999999999999999|ans_random|hash('sha512') }}\n"
        "random and hash filters documentation: https://docs.ansible.com/ansible/2.3/playbooks_filters.html",
        FutureWarning,
    )
    return sha512(urandom(48)).hexdigest()


DEFAULT_DATA: AnyByStrDict = {
    "now": _now,
    "make_secret": _make_secret,
}


@dataclass
class AnswersMap:
    """Object that gathers answers from different sources.

    Attributes:
        user:
            Answers provided by the user, interactively.

        init:
            Answers provided on init.

            This will hold those answers that come from `--data` in
            CLI mode.

            See [data][].

        metadata:
            Data used to be able to reproduce the template.

            It comes from [copier.template.Template.metadata][].

        last:
            Data from [the answers file][the-copier-answersyml-file].

        user_defaults:
            Default data from the user e.g. previously completed and restored data.

            See [copier.main.Worker][].
    """

    # Private
    hidden: set[str] = field(default_factory=set, init=False)

    # Public
    user: AnyByStrDict = field(default_factory=dict)
    init: AnyByStrDict = field(default_factory=dict)
    metadata: AnyByStrDict = field(default_factory=dict)
    last: AnyByStrDict = field(default_factory=dict)
    user_defaults: AnyByStrDict = field(default_factory=dict)

    @property
    def combined(self) -> Mapping[str, Any]:
        """Answers combined from different sources, sorted by priority."""
        return dict(
            ChainMap(
                self.user,
                self.init,
                self.metadata,
                self.last,
                self.user_defaults,
                DEFAULT_DATA,
            )
        )

    def old_commit(self) -> str | None:
        """Commit when the project was updated from this template the last time."""
        return self.last.get("_commit")

    def hide(self, key: str) -> None:
        """Remove an answer by key."""
        self.hidden.add(key)


@dataclass(config=ConfigDict(arbitrary_types_allowed=True))
class Question:
    """One question asked to the user.

    All attributes are init kwargs.

    Attributes:
        choices:
            Selections available for the user if the question requires them.
            Can be templated.

        multiselect:
            Indicates if the question supports multiple answers.
            Only supported by choices type.

        default:
            Default value presented to the user to make it easier to respond.
            Can be templated.

        help:
            Additional text printed to the user, explaining the purpose of
            this question. Can be templated.

        multiline:
            Indicates if the question should allow multiline input. Defaults
            to `True` for JSON and YAML questions, and to `False` otherwise.
            Only meaningful for str-based questions. Can be templated.

        placeholder:
            Text that appears if there's nothing written in the input field,
            but disappears as soon as the user writes anything. Can be templated.

        secret:
            Indicates if the question should be removed from the answers file.
            If the question type is str, it will hide user input on the screen
            by displaying asterisks: `****`.

        type_name:
            The type of question. Affects the rendering, validation and filtering.
            Can be templated.

        var_name:
            Question name in the answers dict.

        validator:
            Jinja template with which to validate the user input. This template
            will be rendered with the combined answers as variables; it should
            render *nothing* if the value is valid, and an error message to show
            to the user otherwise.

        when:
            Condition that, if `False`, skips the question. Can be templated.
            If it is a boolean, it is used directly. If it is a str, it is
            converted to boolean using a parser similar to YAML, but only for
            boolean values.
    """

    var_name: str
    answers: AnswersMap
    jinja_env: SandboxedEnvironment
    settings: Settings = field(default_factory=Settings)
    choices: Sequence[Any] | dict[Any, Any] | str = field(default_factory=list)
    multiselect: bool = False
    default: Any = MISSING
    help: str = ""
    multiline: str | bool = False
    placeholder: str = ""
    secret: bool = False
    type: str = Field(default="", validate_default=True)
    validator: str = ""
    when: str | bool = True

    @field_validator("var_name")
    @classmethod
    def _check_var_name(cls, v: str) -> str:
        if v in DEFAULT_DATA:
            raise ValueError("Invalid question name")
        return v

    @field_validator("type")
    @classmethod
    def _check_type(cls, v: str, info: ValidationInfo) -> str:
        if v == "":
            default_type_name = type(info.data.get("default")).__name__
            v = default_type_name if default_type_name in CAST_STR_TO_NATIVE else "yaml"
        return v

    @field_validator("secret")
    @classmethod
    def _check_secret_question_default_value(
        cls, v: bool, info: ValidationInfo
    ) -> bool:
        if v and info.data["default"] is MISSING:
            raise ValueError("Secret question requires a default value")
        return v

    def cast_answer(self, answer: Any) -> Any:
        """Cast answer to expected type."""
        type_name = self.get_type_name()
        type_fn = CAST_STR_TO_NATIVE[type_name]
        # Only JSON or YAML questions support `None` as an answer
        if answer is None and type_name not in {"json", "yaml"}:
            raise InvalidTypeError(
                f'Invalid answer "{answer}" of type "{type(answer)}" '
                f'to question "{self.var_name}" of type "{type_name}"'
            )
        try:
            if self.multiselect and isinstance(answer, list):
                return [type_fn(item) for item in answer]
            return type_fn(answer)
        except (TypeError, AttributeError) as error:
            # JSON or YAML failed because it wasn't a string; no need to convert
            if type_name in {"json", "yaml"}:
                return answer
            raise InvalidTypeError from error

    def get_default(self) -> Any:
        """Get the default value for this question, casted to its expected type."""
        try:
            result = self.answers.init[self.var_name]
        except KeyError:
            try:
                result = self.answers.last[self.var_name]
            except KeyError:
                try:
                    result = self.answers.user_defaults[self.var_name]
                except KeyError:
                    if self.default is MISSING:
                        return MISSING
                    result = self.render_value(
                        self.settings.defaults.get(self.var_name, self.default)
                    )
        result = self.cast_answer(result)
        return result

    def get_default_rendered(self) -> bool | str | Choice | None | MissingType:
        """Get default answer rendered for the questionary lib.

        The questionary lib expects some specific data types, and returns
        it when the user answers. Sometimes you need to compare the response
        to the rendered one, or viceversa.

        This helper allows such usages.
        """
        default = self.get_default()
        if default is MISSING:
            return MISSING
        # If there are choices, return the one that matches the expressed default
        if self.choices:
            # questionary checkbox use Choice.checked for multiple default
            if not self.multiselect:
                for choice in self._formatted_choices:
                    if choice.value == default:
                        return choice
            return None
        # Yes/No questions expect and return bools
        if isinstance(default, bool) and self.get_type_name() == "bool":
            return default
        # Emptiness is expressed as an empty str
        if default is None:
            return ""
        # JSON and YAML dumped depending on multiline setting
        if self.get_type_name() == "json":
            return json.dumps(default, indent=2 if self.get_multiline() else None)
        if self.get_type_name() == "yaml":
            return yaml.safe_dump(
                default, default_flow_style=not self.get_multiline(), width=2147483647
            ).strip()
        # All other data has to be str
        return str(default)

    @cached_property
    def _formatted_choices(self) -> Sequence[Choice]:
        """Obtain choices rendered and properly formatted."""
        result = []
        choices = self.choices
        default = self.get_default()
        if isinstance(choices, str):
            choices = parse_yaml_string(self.render_value(self.choices))
        if isinstance(choices, dict):
            choices = list(choices.items())
        for choice in choices:
            # If a choice is a value pair
            if isinstance(choice, (tuple, list)):
                name, value = choice
            # If a choice is a single value
            else:
                name = value = choice
            # The name must always be a str
            name = str(self.render_value(name))
            # Extract the extended syntax for dict-like (dict-style or
            # tuple-style) choices if applicable
            disabled = ""
            if isinstance(choice, (tuple, list)) and isinstance(value, dict):
                if "value" not in value:
                    raise KeyError("Property 'value' is required")
                if "validator" in value and not isinstance(value["validator"], str):
                    raise ValueError("Property 'validator' must be a string")

                disabled = self.render_value(value.get("validator", ""))
                value = value["value"]
            # The value can be templated
            value = self.render_value(value)
            checked = (
                self.multiselect
                and isinstance(default, list)
                and self.cast_answer(value) in default
                or None
            )
            c = Choice(name, value, disabled=disabled, checked=checked)
            # Try to cast the value according to the question's type to raise
            # an error in case the value is incompatible.
            self.cast_answer(c.value)
            result.append(c)
        return result

    def get_message(self) -> str:
        """Get the message that will be printed to the user."""
        if self.help:
            if rendered_help := self.render_value(self.help):
                return force_str_end(rendered_help) + "  "
        # Otherwise, there's no help message defined.
        message = self.var_name
        if (answer_type := self.get_type_name()) != "str":
            message += f" ({answer_type})"
        return message + "\n  "

    def get_placeholder(self) -> str:
        """Render and obtain the placeholder."""
        return self.render_value(self.placeholder)

    def get_questionary_structure(self) -> AnyByStrDict:  # noqa: C901
        """Get the question in a format that the questionary lib understands."""

        def _validate(answer: str) -> str | Literal[True]:
            try:
                ans = self.parse_answer(answer)
            except Exception:
                return "Invalid input"
            return self.validate_answer(ans) or True

        lexer = None
        result: AnyByStrDict = {
            "filter": self.cast_answer,
            "message": self.get_message(),
            "mouse_support": True,
            "name": self.var_name,
            "qmark": "🕵️" if self.secret else "🎤",
            "when": lambda _: self.get_when(),
        }
        default = self.get_default_rendered()
        if default is not MISSING:
            result["default"] = default
        questionary_type = "input"
        type_name = self.get_type_name()
        if type_name == "bool":
            questionary_type = "confirm"
            # For backwards compatibility
            if default is MISSING:
                result["default"] = False
        if self.choices:
            questionary_type = "checkbox" if self.multiselect else "select"
            result["choices"] = self._formatted_choices
        if questionary_type == "input":
            if self.secret:
                questionary_type = "password"
            elif type_name == "yaml":
                lexer = PygmentsLexer(YamlLexer)
            elif type_name == "json":
                lexer = PygmentsLexer(JsonLexer)
            if lexer:
                result["lexer"] = lexer
            result["multiline"] = self.get_multiline()
            if placeholder := self.get_placeholder():
                result["placeholder"] = placeholder
        if questionary_type in {"input", "checkbox", "password"}:
            result["validate"] = _validate
        result.update({"type": questionary_type})
        return result

    def get_type_name(self) -> str:
        """Render the type name and return it."""
        type_name = self.render_value(self.type)
        if type_name not in CAST_STR_TO_NATIVE:
            raise InvalidTypeError(
                f'Unsupported type "{type_name}" in question "{self.var_name}"'
            )
        return type_name

    def get_multiline(self) -> bool:
        """Get the value for multiline."""
        return cast_to_bool(self.render_value(self.multiline))

    def validate_answer(self, answer: Any) -> str:
        """Validate user answer."""
        try:
            err_msg = self.render_value(self.validator, {self.var_name: answer}).strip()
        except Exception as error:
            return str(error)
        if err_msg:
            return err_msg
        return ""

    def get_when(self) -> bool:
        """Get skip condition for question."""
        return cast_to_bool(self.render_value(self.when))

    def render_value(
        self, value: Any, extra_answers: AnyByStrDict | None = None
    ) -> Any:
        """Render a single templated value using Jinja.

        If the value cannot be used as a template, it will be returned as is.
        `extra_answers` are combined self `self.answers.combined` when rendering
        the template.
        """
        try:
            template = self.jinja_env.from_string(value)
        except TypeError:
            # value was not a string
            return (
                [self.render_value(item) for item in value]
                if isinstance(value, list)
                else value
            )
        try:
            return template.render({**self.answers.combined, **(extra_answers or {})})
        except UndefinedError as error:
            raise UserMessageError(str(error)) from error

    def parse_answer(self, answer: Any) -> Any:
        """Parse the answer according to the question's type."""
        if self.multiselect:
            answer = [self._parse_answer(a) for a in answer]
            choices = (
                self.cast_answer(choice.value) for choice in self._formatted_choices
            )
            return [choice for choice in choices if choice in answer]
        return self._parse_answer(answer)

    def _parse_answer(self, answer: Any) -> Any:
        """Parse a single answer according to the question's type."""
        ans = self.cast_answer(answer)
        choices = self._formatted_choices
        if not choices:
            return ans
        choice_error = ""
        for choice in choices:
            if ans == self.cast_answer(choice.value):
                if not choice.disabled:
                    return ans
                if not choice_error:
                    choice_error = choice.disabled
        raise ValueError(
            f"Invalid choice: {choice_error}" if choice_error else "Invalid choice"
        )


def parse_yaml_string(string: str) -> Any:
    """Parse a YAML string and raise a ValueError if parsing failed.

    This method is needed because :meth:`prompt` requires a ``ValueError``
    to repeat failed questions.
    """
    try:
        return yaml.safe_load(string)
    except yaml.error.YAMLError as error:
        raise ValueError(str(error))


def load_answersfile_data(
    dst_path: StrOrPath,
    answers_file: OptStrOrPath = None,
) -> AnyByStrDict:
    """Load answers data from a `$dst_path/$answers_file` file if it exists."""
    try:
        with open(Path(dst_path) / (answers_file or ".copier-answers.yml")) as fd:
            return yaml.safe_load(fd)
    except FileNotFoundError:
        return {}


CAST_STR_TO_NATIVE: Mapping[str, Callable[[str], Any]] = {
    "bool": cast_to_bool,
    "float": float,
    "int": int,
    "json": json.loads,
    "str": cast_to_str,
    "yaml": parse_yaml_string,
}
