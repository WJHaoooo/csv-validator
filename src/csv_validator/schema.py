"""Load and validate the project's custom JSON schema (not JSON Schema)."""

import json
from os import PathLike
from pathlib import Path


class SchemaError(ValueError):
    """A schema could not be read, parsed, or validated."""


class _ObjectPairs(list):
    """Preserve JSON object pairs until duplicate keys have been checked."""


def _member_path(path: str, key: str) -> str:
    return f"{path}[{json.dumps(key, ensure_ascii=False)}]"


def _check_duplicate_keys(value: object, path: str = "$") -> object:
    if isinstance(value, _ObjectPairs):
        result = {}
        for key, item in value:
            location = _member_path(path, key)
            if key in result:
                raise SchemaError(f"{location}: duplicate JSON object key")
            result[key] = _check_duplicate_keys(item, location)
        return result
    if isinstance(value, list):
        return [
            _check_duplicate_keys(item, f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    return value


def _reject_constant(value: str) -> None:
    raise SchemaError(f"$: {value} is not a valid JSON constant")


def validate_schema(data: object) -> dict:
    """Validate an already parsed structure and return the same dictionary."""
    if not isinstance(data, dict):
        raise SchemaError("$: expected an object")
    if "columns" not in data:
        raise SchemaError('$["columns"]: missing required property')
    for key in data:
        if key != "columns":
            raise SchemaError(f"{_member_path('$', key)}: unknown property")

    columns = data["columns"]
    if not isinstance(columns, dict):
        raise SchemaError('$["columns"]: expected a non-empty object')
    if not columns:
        raise SchemaError('$["columns"]: expected a non-empty object')

    for name, config in columns.items():
        location = _member_path('$["columns"]', str(name))
        if not isinstance(name, str) or not name.strip():
            raise SchemaError(f"{location}: column name must be a non-blank string")
        if not isinstance(config, dict):
            raise SchemaError(f"{location}: expected an object")
        for key in ("type", "required"):
            if key not in config:
                raise SchemaError(f"{_member_path(location, key)}: missing required property")
        for key in config:
            if key not in ("type", "required"):
                raise SchemaError(f"{_member_path(location, key)}: unknown property")
        if not isinstance(config["type"], str) or config["type"] not in (
            "int", "float", "str"
        ):
            raise SchemaError(
                f'{location}["type"]: expected one of "int", "float", "str"'
            )
        if not isinstance(config["required"], bool):
            raise SchemaError(f'{location}["required"]: expected a JSON boolean')
    return data


def parse_schema(text: str) -> dict:
    """Parse strict JSON, reject duplicate keys, and validate its structure."""
    try:
        data = json.loads(
            text,
            object_pairs_hook=_ObjectPairs,
            parse_constant=_reject_constant,
        )
    except json.JSONDecodeError as exc:
        raise SchemaError(
            f"$: JSON syntax error at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc
    return validate_schema(_check_duplicate_keys(data))


def load_schema(path: str | PathLike[str]) -> dict:
    """Read a UTF-8 schema file and return its validated dictionary."""
    source = Path(path)
    try:
        text = source.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise SchemaError(
            f"{source}: invalid UTF-8 near byte {exc.start}: {exc.reason}"
        ) from exc
    except OSError as exc:
        raise SchemaError(f"{source}: cannot read schema: {exc}") from exc

    try:
        return parse_schema(text)
    except SchemaError as exc:
        raise SchemaError(f"{source}: {exc}") from exc
