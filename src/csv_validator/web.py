"""W0 HTTP boundary: bounded upload inspection, separate from CLI/core rules."""

import codecs
import csv
from http import HTTPStatus
import logging
from pathlib import Path
import tempfile
from typing import BinaryIO

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException
from starlette.formparsers import MultiPartException, MultiPartParser

from csv_validator.csv_reader import (
    CSVHeaderError,
    open_csv_reader,
    read_header_record,
)


MAX_UPLOAD_BYTES = 5 * 1024 * 1024
CHUNK_BYTES = 64 * 1024
# The CSV limit is exact; this separate cap also bounds multipart overhead.
MAX_REQUEST_BYTES = MAX_UPLOAD_BYTES + CHUNK_BYTES
_BODY_LIMIT_MESSAGE = "Upload request exceeds the size limit."
logger = logging.getLogger(__name__)
app = FastAPI(title="CSV Validator Web", version="0.1.0")


class APIError(Exception):
    """Expected HTTP error with a safe, stable public message."""

    def __init__(self, status: int, code: str, message: str):
        self.status = status
        self.code = code
        self.message = message
        super().__init__(message)


class _CompleteMultipartParser(MultiPartParser):
    """Track the public completion callback without replacing multipart parsing."""

    finished = False

    def on_end(self) -> None:
        self.finished = True
        super().on_end()


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message}},
    )


@app.exception_handler(APIError)
async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    return _error(exc.status, exc.code, exc.message)


@app.exception_handler(HTTPException)
async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return _error(exc.status_code, "HTTP_ERROR", HTTPStatus(exc.status_code).phrase)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return _error(422, "INVALID_REQUEST", "Invalid request.")


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    # Exception text/tracebacks may contain uploaded values or temporary paths.
    logger.error("Unexpected CSV web request failure.")
    return _error(500, "INTERNAL_ERROR", "Unable to process the request.")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


def _inspect_file(upload: BinaryIO) -> None:
    """Copy bounded chunks to a server-owned path and inspect without a schema."""
    with tempfile.TemporaryDirectory(prefix="csv-validator-upload-") as directory:
        path = Path(directory) / "upload.csv"
        decoder = codecs.getincrementaldecoder("utf-8")(errors="strict")
        size = 0
        with path.open("wb") as destination:
            while True:
                # Read at most one byte over the CSV limit, never read(-1).
                chunk = upload.read(min(CHUNK_BYTES, MAX_UPLOAD_BYTES + 1 - size))
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise APIError(413, "FILE_TOO_LARGE", "CSV file exceeds 5 MiB.")
                try:
                    decoder.decode(chunk, final=False)
                except UnicodeDecodeError as exc:
                    raise APIError(422, "INVALID_UTF8", "CSV file must be valid UTF-8.") from exc
                destination.write(chunk)
            try:
                decoder.decode(b"", final=True)
            except UnicodeDecodeError as exc:
                raise APIError(422, "INVALID_UTF8", "CSV file must be valid UTF-8.") from exc
        if size == 0:
            raise APIError(400, "EMPTY_FILE", "CSV file is empty.")

        try:
            with open_csv_reader(path) as reader:
                headers = read_header_record(reader, path)
                if not headers:
                    raise APIError(422, "INVALID_CSV", "Unable to read a CSV header.")
                # Syntax inspection only: no row preview, schema, width or types.
                for _ in reader:
                    pass
        except CSVHeaderError as exc:
            if isinstance(exc.__cause__, OSError):
                # Storage failures are server errors, not bad user CSV.
                raise
            raise APIError(422, "INVALID_CSV", "Unable to parse the CSV file.") from exc
        except csv.Error as exc:
            raise APIError(422, "INVALID_CSV", "Unable to parse the CSV file.") from exc


@app.post(
    "/api/csv/inspect",
    openapi_extra={"requestBody": {
        "required": True,
        "content": {"multipart/form-data": {"schema": {
            "type": "object", "required": ["file"],
            "properties": {"file": {"type": "string", "format": "binary"}},
        }}},
    }},
)
async def inspect_csv(request: Request) -> dict[str, str]:
    try:
        return await _inspect_csv(request)
    except APIError:
        raise
    except Exception:
        # Handle at the upload boundary: an Exception handler alone is not
        # enough, because ServerErrorMiddleware re-raises to the ASGI server,
        # which may log exception text containing uploaded values.
        logger.error("Unexpected CSV inspection failure.")
        raise APIError(500, "INTERNAL_ERROR", "Unable to process the request.") from None


async def _inspect_csv(request: Request) -> dict[str, str]:
    media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if not media_type:
        raise APIError(400, "MISSING_FILE", "Provide one CSV file in the 'file' field.")
    if media_type != "multipart/form-data":
        raise APIError(400, "INVALID_UPLOAD", "Use multipart/form-data with one 'file' field.")

    received = 0
    parser = None

    async def bounded_stream():
        nonlocal received
        async for chunk in request.stream():
            received += len(chunk)
            if received > MAX_REQUEST_BYTES:
                raise MultiPartException(_BODY_LIMIT_MESSAGE)
            yield chunk
        # python-multipart.finalize() does not reject truncated forms itself.
        # Raise while the parser still owns the stream so it closes partial files.
        if parser is not None and not parser.finished:
            raise MultiPartException("Incomplete multipart upload.")

    parser = _CompleteMultipartParser(
        request.headers, bounded_stream(), max_files=1, max_fields=0
    )
    try:
        form = await parser.parse()
        try:
            file = form.get("file")
            if file is None:
                raise APIError(400, "MISSING_FILE", "Provide one CSV file in the 'file' field.")
            if not isinstance(file, UploadFile) or len(form) != 1:
                raise APIError(400, "INVALID_UPLOAD", "Provide exactly one uploaded CSV file.")
            await run_in_threadpool(_inspect_file, file.file)
        finally:
            await form.close()
    except MultiPartException as exc:
        if exc.message == _BODY_LIMIT_MESSAGE:
            raise APIError(413, "FILE_TOO_LARGE", "Upload request exceeds the size limit.") from exc
        raise APIError(400, "INVALID_UPLOAD", "Invalid multipart upload.") from exc
    return {"status": "ok"}
