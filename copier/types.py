"""Complex types, annotations, validators."""

import sys
from pathlib import Path
from typing import (
    Annotated,
    Any,
    Dict,
    Literal,
    Mapping,
    NewType,
    Optional,
    Sequence,
    TypeVar,
    Union,
)

from pydantic import AfterValidator

if sys.version_info >= (3, 10):
    from typing import ParamSpec as ParamSpec
else:
    from typing_extensions import ParamSpec as ParamSpec

# simple types
StrOrPath = Union[str, Path]
AnyByStrDict = Dict[str, Any]

# sequences
IntSeq = Sequence[int]
PathSeq = Sequence[Path]

# optional types
OptBool = Optional[bool]
OptStrOrPath = Optional[StrOrPath]

# miscellaneous
T = TypeVar("T")
JSONSerializable = (dict, list, str, int, float, bool, type(None))
VCSTypes = Literal["git"]
Env = Mapping[str, str]
MissingType = NewType("MissingType", object)
MISSING = MissingType(object())
Operation = Literal["copy", "update"]


# Validators
def path_is_absolute(value: Path) -> Path:
    """Require absolute paths in an argument."""
    if not value.is_absolute():
        from .errors import PathNotAbsoluteError

        raise PathNotAbsoluteError(path=value)
    return value


def path_is_relative(value: Path) -> Path:
    """Require relative paths in an argument."""
    if value.is_absolute():
        from .errors import PathNotRelativeError

        raise PathNotRelativeError(path=value)
    return value


AbsolutePath = Annotated[Path, AfterValidator(path_is_absolute)]
RelativePath = Annotated[Path, AfterValidator(path_is_relative)]
