"""Read the first CSV record and validate its header against a schema."""

import csv
from os import PathLike
from pathlib import Path

from csv_validator.schema import validate_schema


class CSVHeaderError(ValueError):
    """A CSV header could not be read or does not meet the header contract."""


def read_csv_header(path: str | PathLike[str]) -> list[str]:
    """Read the first record as UTF-8 CSV; schema checks are separate."""
    source = Path(path)
    try:
        with source.open("r", encoding="utf-8", newline="") as file:
            return next(csv.reader(file, delimiter=",", strict=True))
    except StopIteration as exc:
        raise CSVHeaderError(f"{source}: empty CSV file; no header record") from exc
    except UnicodeDecodeError as exc:
        raise CSVHeaderError(
            f"{source}: invalid UTF-8 in CSV input: {exc.reason}"
        ) from exc
    except csv.Error as exc:
        raise CSVHeaderError(f"{source}: malformed CSV header: {exc}") from exc
    except OSError as exc:
        raise CSVHeaderError(f"{source}: cannot read CSV: {exc}") from exc


def validate_headers(headers: list[str], schema: dict) -> list[str]:
    """Check header names and required columns, returning the unchanged list."""
    schema = validate_schema(schema)
    if not headers:
        raise CSVHeaderError("blank CSV header record; no column names")

    seen = set()
    for name in headers:
        if not name.strip():
            raise CSVHeaderError(f"blank CSV header name: {name!r}")
        if name in seen:
            raise CSVHeaderError(f"duplicate CSV header: {name!r}")
        seen.add(name)

    for name, config in schema["columns"].items():
        if config["required"] and name not in seen:
            raise CSVHeaderError(f"missing required column: {name!r}")
    return headers


def load_csv_header(path: str | PathLike[str], schema: dict) -> list[str]:
    """Validate schema before opening CSV, then read and validate its header.

    Prefer this entry point for file-based processing. The lower-level reader
    only parses CSV; it does not certify header names or schema compatibility.
    """
    schema = validate_schema(schema)
    headers = read_csv_header(path)
    try:
        return validate_headers(headers, schema)
    except CSVHeaderError as exc:
        raise CSVHeaderError(f"{path}: {exc}") from exc
