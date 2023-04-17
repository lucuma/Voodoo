from pathlib import Path, PurePosixPath
from platform import system
from typing import Any, Optional
from urllib.parse import urldefrag, urlparse
from urllib.request import url2pathname, urlopen

import jsonschema
import yaml

from .errors import PathNotRelativeError


class JsonSchemaFilter:
    """Jinja filter for validating data against a JSON Schema document.

    Args:
        template_root:
            The absolute path to the template on disk.
    """

    _template_root: Path

    def __init__(self, template_root: Path) -> None:
        self._template_root = template_root

    def __call__(
        self, instance: Any, schema_uri: str
    ) -> Optional[jsonschema.ValidationError]:
        if schema_uri.startswith(("http://", "https://")):
            schema = {"$ref": schema_uri}
        else:
            schema_file, fragment = urldefrag(schema_uri)
            schema_file_relpath = PurePosixPath(schema_file)
            if schema_file_relpath.is_absolute():
                raise PathNotRelativeError(path=Path(schema_file_relpath))
            schema_file_abspath = (self._template_root / schema_file_relpath).resolve()
            # HACK https://github.com/python-jsonschema/jsonschema/issues/98#issuecomment-105475109
            scheme = "file:///" if system() == "Windows" else "file://"
            schema = {"$ref": f"{scheme}{schema_file_abspath.as_posix()}#{fragment}"}
        try:
            return jsonschema.validate(
                instance,
                schema,
                resolver=jsonschema.RefResolver(
                    "",
                    {},
                    handlers={
                        "file": self._resolve_local_schema,
                        "http": self._resolve_remote_schema,
                        "https": self._resolve_remote_schema,
                    },
                ),
            )
        except jsonschema.ValidationError as exc:
            return exc

    def _resolve_local_schema(self, uri: str) -> Any:
        schema_file_abspath = Path(url2pathname(urlparse(uri).path)).resolve()
        try:
            schema_file_abspath.relative_to(self._template_root)
        except ValueError as exc:
            raise ValueError(
                f'Schema file path "{schema_file_abspath}" must resolve to a path '
                f'under the template root "{self._template_root}"'
            ) from exc
        with schema_file_abspath.open() as f:
            schema = yaml.safe_load(f)
        return schema

    def _resolve_remote_schema(self, uri: str) -> Any:
        with urlopen(uri) as response:
            raw_schema = response.read().decode("utf-8")
        return yaml.safe_load(raw_schema)