"""Validate CSV records and convert schema columns to Python values."""

import csv
import math
from os import PathLike
from pathlib import Path
import re

from csv_validator.csv_reader import (
    CSVHeaderError,
    open_csv_reader,
    read_header_record,
    validate_headers,
)
from csv_validator.schema import validate_schema


_INT_PATTERN = re.compile(r"[+-]?[0-9]+")
_FLOAT_PATTERN = re.compile(
    r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?"
)
CellValue = int | float | str | None


class CSVRowError(ValueError):
    """A CSV record failed parsing, shape validation, or cell conversion."""

    def __init__(
        self,
        path: str | PathLike[str],
        line: int,
        reason: str,
        *,
        column: str | None = None,
        raw_value: str | None = None,
        expected_type: str | None = None,
    ):
        self.path = Path(path)
        self.line = line
        self.column = column
        self.raw_value = raw_value
        self.expected_type = expected_type
        detail = f"{self.path}: line {line}: "
        if column is not None:
            detail += (
                f"column {column!r}, raw value {raw_value!r}, "
                f"expected {expected_type}: "
            )
        super().__init__(detail + reason)


def _convert_cell(raw: str, type_name: str, required: bool) -> CellValue:
    token = raw.strip()
    if not token:
        if required:
            raise ValueError("required cell is empty or whitespace-only")
        return None
    if type_name == "str":
        return raw
    if type_name == "int":
        if not _INT_PATTERN.fullmatch(token):
            raise ValueError("expected an ASCII decimal integer with optional sign")
        return int(token)
    # Schema validation guarantees the remaining type is float.
    if not _FLOAT_PATTERN.fullmatch(token):
        raise ValueError("expected a decimal number with optional exponent")
    value = float(token)
    if not math.isfinite(value):
        raise ValueError("float result must be finite")
    return value


def convert_csv(
    path: str | PathLike[str], schema: dict
) -> list[dict[str, CellValue]]:
    """Validate schema, headers, and all records; return results only on success."""
    schema = validate_schema(schema)
    source = Path(path)
    results = []
    with open_csv_reader(source) as reader:
        headers = read_header_record(reader, source)
        try:
            validate_headers(headers, schema)
        except CSVHeaderError as exc:
            raise CSVHeaderError(f"{source}: {exc}") from exc
        positions = {name: index for index, name in enumerate(headers)}

        while True:
            start_line = reader.line_num + 1
            try:
                row = next(reader)
            except StopIteration:
                break
            except UnicodeDecodeError as exc:
                raise CSVRowError(
                    source, start_line, f"invalid UTF-8 in CSV record: {exc.reason}"
                ) from exc
            except csv.Error as exc:
                raise CSVRowError(
                    source, start_line, f"malformed CSV record: {exc}"
                ) from exc
            except OSError as exc:
                raise CSVRowError(
                    source, start_line, f"cannot read CSV record: {exc}"
                ) from exc

            if len(row) != len(headers):
                raise CSVRowError(
                    source, start_line,
                    f"expected {len(headers)} fields, got {len(row)}",
                )

            converted = {}
            for name, config in schema["columns"].items():
                if name not in positions:
                    # Header validation already rejected missing required columns.
                    converted[name] = None
                    continue
                raw = row[positions[name]]
                try:
                    converted[name] = _convert_cell(
                        raw, config["type"], config["required"]
                    )
                except ValueError as exc:
                    raise CSVRowError(
                        source, start_line, str(exc),
                        column=name, raw_value=raw, expected_type=config["type"],
                    ) from exc
            results.append(converted)
    return results
