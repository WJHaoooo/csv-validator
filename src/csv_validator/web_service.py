"""Bounded Web adapters around the existing Schema, Converter and JSON core."""

from contextlib import closing
import codecs
from pathlib import Path
import tempfile
from typing import BinaryIO

from csv_validator.converter import CSVRowError, iter_converted_rows
from csv_validator.csv_reader import CSVHeaderError
from csv_validator.schema import SchemaError, parse_schema
from csv_validator.writer import iter_json_text


MAX_SCHEMA_BYTES = 128 * 1024
MAX_OUTPUT_BYTES = 8 * 1024 * 1024
CHUNK_BYTES = 64 * 1024


class APIError(Exception):
    """Expected HTTP error; details must contain only safe public diagnostics."""

    def __init__(self, status: int, code: str, message: str, details: dict | None = None):
        self.status = status
        self.code = code
        self.message = message
        self.details = details
        super().__init__(message)


def copy_csv(upload: BinaryIO, path: Path, *, limit: int, chunk_bytes: int, validate_utf8: bool = True) -> None:
    decoder = codecs.getincrementaldecoder("utf-8")(errors="strict") if validate_utf8 else None
    size = 0
    with path.open("wb") as destination:
        while True:
            chunk = upload.read(min(chunk_bytes, limit + 1 - size))
            if not chunk:
                break
            size += len(chunk)
            if size > limit:
                raise APIError(413, "FILE_TOO_LARGE", "CSV file exceeds 5 MiB.")
            if decoder is not None:
                try:
                    decoder.decode(chunk, final=False)
                except UnicodeDecodeError as exc:
                    raise APIError(422, "INVALID_UTF8", "CSV file must be valid UTF-8.") from exc
            destination.write(chunk)
        if decoder is not None:
            try:
                decoder.decode(b"", final=True)
            except UnicodeDecodeError as exc:
                raise APIError(422, "INVALID_UTF8", "CSV file must be valid UTF-8.") from exc
    if size == 0:
        raise APIError(400, "EMPTY_FILE", "CSV file is empty.")


def read_schema(upload: BinaryIO) -> dict:
    data = bytearray()
    while True:
        chunk = upload.read(min(CHUNK_BYTES, MAX_SCHEMA_BYTES + 1 - len(data)))
        if not chunk:
            break
        data.extend(chunk)
        if len(data) > MAX_SCHEMA_BYTES:
            raise APIError(413, "SCHEMA_TOO_LARGE", "Schema exceeds 128 KiB.")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise APIError(422, "SCHEMA_ERROR", "Schema must be valid UTF-8.") from exc
    try:
        return parse_schema(text)
    except SchemaError as exc:
        raise APIError(422, "SCHEMA_ERROR", str(exc)[:1000]) from exc
    except RecursionError as exc:
        raise APIError(422, "SCHEMA_ERROR", "Schema nesting is too deep.") from exc


def _bounded_json(rows) -> tuple[bytes, int]:
    payload = bytearray(b"[")
    count = 0

    def append(chunk: bytes) -> None:
        if len(payload) + len(chunk) > MAX_OUTPUT_BYTES:
            raise APIError(413, "OUTPUT_TOO_LARGE", "Converted JSON exceeds 8 MiB.")
        payload.extend(chunk)

    for row in rows:
        append(b",\n  " if count else b"\n  ")
        # Share the CLI's strict JSON encoder. Indent each object by the
        # array's additional two spaces without serializing a complete list.
        for text in iter_json_text(row):
            append(text.replace("\n", "\n  ").encode("utf-8"))
        count += 1
    append(b"\n]\n" if count else b"]\n")
    return bytes(payload), count


def convert_upload(upload: BinaryIO, schema: dict, *, csv_limit: int) -> tuple[bytes, int]:
    with tempfile.TemporaryDirectory(prefix="csv-validator-convert-") as directory:
        path = Path(directory) / "upload.csv"
        # Do not pre-validate the entire file's encoding here: the shared
        # converter decodes records in order, preserving CLI Fail Fast priority.
        copy_csv(upload, path, limit=csv_limit, chunk_bytes=CHUNK_BYTES, validate_utf8=False)
        try:
            # close() is essential on early output-limit or conversion errors:
            # release the CSV handle before removing the Windows temp directory.
            with closing(iter_converted_rows(path, schema)) as rows:
                return _bounded_json(rows)
        except CSVRowError as exc:
            if isinstance(exc.__cause__, UnicodeDecodeError):
                raise APIError(422, "INVALID_UTF8", "CSV file must be valid UTF-8.", {"line": exc.line}) from exc
            if isinstance(exc.__cause__, OSError):
                raise
            details = {"line": exc.line}
            if exc.column is not None:
                raw = exc.raw_value or ""
                details.update({
                    "column": exc.column,
                    "raw_value": raw[:256],
                    "raw_value_truncated": len(raw) > 256,
                    "expected_type": exc.expected_type,
                })
            raise APIError(422, "CSV_ROW_ERROR", exc.reason[:1000], details) from exc
        except CSVHeaderError as exc:
            current = exc
            while isinstance(current.__cause__, CSVHeaderError):
                current = current.__cause__
            if isinstance(current.__cause__, UnicodeDecodeError):
                raise APIError(422, "INVALID_UTF8", "CSV file must be valid UTF-8.") from exc
            if isinstance(current.__cause__, OSError):
                raise
            if current.__cause__ is None:
                message = str(current)
            else:
                message = "Unable to parse the CSV header."
            raise APIError(422, "CSV_HEADER_ERROR", message[:1000]) from exc
        except (TypeError, ValueError, OverflowError, RecursionError) as exc:
            # Never return partial bytes or exception text that could expose paths.
            raise APIError(500, "JSON_WRITE_ERROR", "Unable to serialize JSON.") from exc
