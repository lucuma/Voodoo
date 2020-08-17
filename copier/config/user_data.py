"""Functions used to load user data."""

import json
import re
import sys
from collections import ChainMap
from functools import partial
from pathlib import Path
from typing import Any, Callable, Dict

import yaml
from iteration_utilities import deepflatten
from jinja2 import UndefinedError
from jinja2.sandbox import SandboxedEnvironment
from plumbum.cli.terminal import ask, choose
from plumbum.colors import bold, info, italics, reverse, warn
from prompt_toolkit import prompt
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.lexers import PygmentsLexer
from prompt_toolkit.validation import Validator
from pygments.lexers.data import JsonLexer, YamlLexer
from yamlinclude import YamlIncludeConstructor

from ..tools import force_str_end, get_jinja_env, printf_exception, to_nice_yaml
from ..types import AnyByStrDict, Choices, OptStr, OptStrOrPath, PathSeq, StrOrPath
from .objects import DEFAULT_DATA, EnvOps, UserMessageError

__all__ = ("load_config_data", "query_user_data")


class ConfigFileError(ValueError):
    pass


class InvalidConfigFileError(ConfigFileError):
    def __init__(self, conf_path: Path, quiet: bool):
        msg = str(conf_path)
        printf_exception(self, "INVALID CONFIG FILE", msg=msg, quiet=quiet)
        super().__init__(msg)


class MultipleConfigFilesError(ConfigFileError):
    def __init__(self, conf_paths: PathSeq, quiet: bool):
        msg = str(conf_paths)
        printf_exception(self, "MULTIPLE CONFIG FILES", msg=msg, quiet=quiet)
        super().__init__(msg)


class InvalidTypeError(TypeError):
    pass


def ask_interactively(
    question: str,
    type_name: str,
    type_fn: Callable,
    secret: bool = False,
    placeholder: OptStr = None,
    default: Any = None,
    choices: Any = None,
    extra_help: OptStr = None,
) -> Any:
    """Ask one question interactively to the user."""
    # Generate message to ask the user
    message = ""
    if extra_help:
        message = force_str_end(f"\n{info & italics | extra_help}{message}")
    emoji = "🕵️" if secret else "🎤"
    message += f"{bold | question}? Format: {type_name}\n{emoji} "
    lexer_map = {"json": JsonLexer, "yaml": YamlLexer}
    lexer = lexer_map.get(type_name)
    # HACK https://github.com/prompt-toolkit/python-prompt-toolkit/issues/1071
    # FIXME When fixed, use prompt toolkit too for choices and bools
    # Use the correct method to ask
    if type_name == "bool":
        return ask(message, default)
    if choices:
        return choose(message, choices, default)
    # Hints for the multiline input user
    multiline = lexer is not None
    if multiline:
        message += f"- Finish with {reverse | 'Esc, ↵'} or {reverse | 'Meta + ↵'}\n"
    # Convert default to string
    to_str_map: Dict[str, Callable[[Any], str]] = {
        "json": lambda obj: json.dumps(obj, indent=2),
        "yaml": to_nice_yaml,
    }
    to_str_fn = to_str_map.get(type_name, str)
    # Allow placeholder YAML comments
    default_str = to_str_fn(default)
    if placeholder and type_name == "yaml":
        prefixed_default_str = force_str_end(placeholder) + default_str
        if yaml.safe_load(prefixed_default_str) == default:
            default_str = prefixed_default_str
        else:
            print(warn | "Placeholder text alters value!", file=sys.stderr)
    return prompt(
        ANSI(message),
        default=default_str,
        is_password=secret,
        lexer=lexer and PygmentsLexer(lexer),
        mouse_support=True,
        multiline=multiline,
        validator=Validator.from_callable(abstract_validator(type_fn)),
    )


def abstract_validator(type_fn: Callable) -> Callable:
    """Produce a validator for the given type.

    Params:
        type_fn: A callable that converts text into the expected type.
    """

    def _validator(text: str):
        try:
            type_fn(text)
            return True
        except Exception:
            return False

    return _validator


def load_yaml_data(conf_path: Path, quiet: bool = False) -> AnyByStrDict:
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
    YamlIncludeConstructor.add_to_loader_class(
        loader_class=yaml.FullLoader, base_dir=conf_path.parent
    )

    try:
        with open(conf_path) as f:
            flattened_result = deepflatten(
                yaml.load_all(f, Loader=yaml.FullLoader), depth=2, types=(list,),
            )
            # HACK https://bugs.python.org/issue32792#msg311822
            # I'd use ChainMap, but it doesn't respect order in Python 3.6
            result = {}
            for part in flattened_result:
                result.update(part)
            return result
    except yaml.parser.ParserError as e:
        raise InvalidConfigFileError(conf_path, quiet) from e


def parse_yaml_string(string: str) -> Any:
    """Parse a YAML string and raise a ValueError if parsing failed.

    This method is needed because :meth:`prompt` requires a ``ValueError``
    to repeat falied questions.
    """
    try:
        return yaml.safe_load(string)
    except yaml.error.YAMLError as error:
        raise ValueError(str(error))


def load_config_data(
    src_path: StrOrPath, quiet: bool = False, _warning: bool = True
) -> AnyByStrDict:
    """Try to load the content from a `copier.yml` or a `copier.yaml` file.
    """
    conf_paths = [
        p
        for p in Path(src_path).glob("copier.*")
        if p.is_file() and re.match(r"\.ya?ml", p.suffix, re.I)
    ]

    if len(conf_paths) > 1:
        raise MultipleConfigFilesError(conf_paths, quiet=quiet)
    elif len(conf_paths) == 1:
        return load_yaml_data(conf_paths[0], quiet=quiet)
    else:
        return {}


def load_answersfile_data(
    dst_path: StrOrPath, answers_file: OptStrOrPath = None,
) -> AnyByStrDict:
    """Load answers data from a `$dst_path/$answers_file` file if it exists."""
    try:
        with open(Path(dst_path) / (answers_file or ".copier-answers.yml")) as fd:
            return yaml.safe_load(fd)
    except FileNotFoundError:
        return {}


def cast_answer_type(answer: Any, type_fn: Callable) -> Any:
    """Cast answer to expected type."""
    # Skip casting None into "None"
    if type_fn is str and answer is None:
        return answer
    # Parse correctly bools as 1, true, yes...
    if type_fn is bool and isinstance(answer, str):
        return parse_yaml_string(answer)
    try:
        return type_fn(answer)
    except (TypeError, AttributeError):
        # JSON or YAML failed because it wasn't a string; no need to convert
        return answer


def render_value(value: Any, env: SandboxedEnvironment, context: AnyByStrDict) -> str:
    """Render a single templated value using Jinja.

    If the value cannot be used as a template, it will be returned as is.
    """
    try:
        template = env.from_string(value)
    except TypeError:
        # value was not a string
        return value
    try:
        return template.render(**context)
    except UndefinedError as error:
        raise UserMessageError(str(error)) from error


def render_choices(
    choices: Choices, env: SandboxedEnvironment, context: AnyByStrDict
) -> Choices:
    """Render a list or dictionary of templated choices using Jinja."""
    render = partial(render_value, env=env, context=context)
    if isinstance(choices, dict):
        choices = {render(k): render(v) for k, v in choices.items()}
    elif isinstance(choices, list):
        for i, choice in enumerate(choices):
            if isinstance(choice, (tuple, list)) and len(choice) == 2:
                choices[i] = (render(choice[0]), render(choice[1]))
            else:
                choices[i] = render(choice)
    return choices


def query_user_data(
    questions_data: AnyByStrDict,
    last_answers_data: AnyByStrDict,
    forced_answers_data: AnyByStrDict,
    ask_user: bool,
    envops: EnvOps,
) -> AnyByStrDict:
    """Query the user for questions given in the config file."""
    type_maps: Dict[str, Callable] = {
        "bool": bool,
        "float": float,
        "int": int,
        "json": json.loads,
        "str": str,
        "yaml": parse_yaml_string,
    }
    env = get_jinja_env(envops=envops)
    result: AnyByStrDict = {}
    defaults: AnyByStrDict = {}
    _render_value = partial(
        render_value,
        env=env,
        context=ChainMap(result, forced_answers_data, defaults, DEFAULT_DATA),
    )
    _render_choices = partial(
        render_choices,
        env=env,
        context=ChainMap(result, forced_answers_data, defaults, DEFAULT_DATA),
    )

    for question, details in questions_data.items():
        # Get question type; by default let YAML decide it
        type_name = _render_value(details.get("type", "yaml"))
        try:
            type_fn = type_maps[type_name]
        except KeyError:
            raise InvalidTypeError()
        # Get default answer
        ask_this = ask_user
        default = cast_answer_type(_render_value(details.get("default")), type_fn)
        defaults[question] = default
        try:
            # Use forced answer
            answer = forced_answers_data[question]
            ask_this = False
        except KeyError:
            # Get default answer
            answer = last_answers_data.get(question, default)
        if ask_this:
            extra_help = details.get("help")
            if extra_help:
                extra_help = _render_value(extra_help)
            answer = ask_interactively(
                question,
                type_name,
                type_fn,
                details.get("secret", False),
                _render_value(details.get("placeholder")),
                answer,
                _render_choices(details.get("choices")),
                _render_value(details.get("help")),
            )
        if answer != details.get("default", default):
            result[question] = cast_answer_type(answer, type_fn)
    return result
