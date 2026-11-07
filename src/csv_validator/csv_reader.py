"""Read CSV records and validate headers against a schema."""

from collections.abc import Iterable, Iterator
from contextlib import contextmanager
import csv
from os import PathLike
from pathlib import Path

from csv_validator.schema import validate_schema


class CSVHeaderError(ValueError):
    """A CSV header could not be read or does not meet the header contract."""


def _strict_utf8_lines(lines: Iterable[str]) -> Iterator[str]:
    # TextIO may decode ahead into later records. Preserve invalid bytes until
    # their physical line is consumed, then strictly decode that line so the
    # caller can attribute the error to the record currently being read.
    for line in lines:
        yield line.encode("utf-8", errors="surrogateescape").decode("utf-8")


@contextmanager
def open_csv_reader(path: str | PathLike[str]):
    """Own one file and strict CSV reader; close it on success or failure."""
    source = Path(path)
    try:
        file = source.open(
            "r", encoding="utf-8", errors="surrogateescape", newline=""
        )
    except OSError as exc:
        raise CSVHeaderError(f"{source}: cannot read CSV: {exc}") from exc
    with file:
        yield csv.reader(_strict_utf8_lines(file), delimiter=",", strict=True)


def read_header_record(
    reader: Iterator[list[str]], path: str | PathLike[str]
) -> list[str]:
    """Consume the header from an existing reader without reopening the file."""
    try:
        return next(reader)
    except StopIteration as exc:
        raise CSVHeaderError(f"{path}: empty CSV file; no header record") from exc
    except UnicodeDecodeError as exc:
        raise CSVHeaderError(
            f"{path}: invalid UTF-8 in CSV input: {exc.reason}"
        ) from exc
    except csv.Error as exc:
        raise CSVHeaderError(f"{path}: malformed CSV header: {exc}") from exc
    except OSError as exc:
        raise CSVHeaderError(f"{path}: cannot read CSV: {exc}") from exc


def read_csv_header(path: str | PathLike[str]) -> list[str]:
    """Read the first record as UTF-8 CSV; schema checks are separate."""
    with open_csv_reader(path) as reader:
        return read_header_record(reader, path)


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
