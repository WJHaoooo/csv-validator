"""Web explorer: bounded upload inspection and raw CSV preview."""

from contextlib import asynccontextmanager
import csv
from http import HTTPStatus
import logging
from itertools import islice
from pathlib import Path
import tempfile
from typing import BinaryIO

from fastapi import APIRouter, FastAPI, Request
from anyio import CancelScope, fail_after
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException
from starlette.formparsers import MultiPartException, MultiPartParser
from starlette.staticfiles import StaticFiles

from csv_validator.csv_reader import (
    CSVHeaderError,
    open_csv_reader,
    read_header_record,
    validate_header_names,
)


from csv_validator.web_security import SecurityBoundary, SecuritySettings

from csv_validator.web_service import (
    APIError,
    MAX_SCHEMA_BYTES,
    copy_csv,
    convert_upload,
    read_schema,
)


MAX_UPLOAD_BYTES = 5 * 1024 * 1024
CHUNK_BYTES = 64 * 1024
# The CSV limit is exact; this separate cap also bounds multipart overhead.
MAX_REQUEST_BYTES = MAX_UPLOAD_BYTES + CHUNK_BYTES
_BODY_LIMIT_MESSAGE = "Upload request exceeds the size limit."
logger = logging.getLogger(__name__)
router = APIRouter()
STATIC_DIRECTORY = Path(__file__).with_name("static")


@router.get("/", include_in_schema=False)
async def explorer_page():
    return FileResponse(STATIC_DIRECTORY / "index.html")


class _CompleteMultipartParser(MultiPartParser):
    """Track the public completion callback without replacing multipart parsing."""

    finished = False

    def on_end(self) -> None:
        self.finished = True
        super().on_end()


def _error(status: int, code: str, message: str, details: dict | None = None) -> JSONResponse:
    error = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    return JSONResponse(status_code=status, content={"error": error})


async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    return _error(exc.status, exc.code, exc.message, exc.details)


async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return _error(exc.status_code, "HTTP_ERROR", HTTPStatus(exc.status_code).phrase)


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return _error(422, "INVALID_REQUEST", "Invalid request.")


async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    # Exception text/tracebacks may contain uploaded values or temporary paths.
    logger.error("Unexpected CSV web request failure.")
    return _error(500, "INTERNAL_ERROR", "Unable to process the request.")


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


def _inspect_file(upload: BinaryIO) -> dict[str, object]:
    """Copy bounded chunks to a server-owned path and inspect without a schema."""
    with tempfile.TemporaryDirectory(prefix="csv-validator-upload-") as directory:
        path = Path(directory) / "upload.csv"
        copy_csv(upload, path, limit=MAX_UPLOAD_BYTES, chunk_bytes=CHUNK_BYTES)

        try:
            with open_csv_reader(path) as reader:
                headers = read_header_record(reader, path)
                if not headers:
                    raise APIError(422, "INVALID_CSV", "Unable to read a CSV header.")
                try:
                    validate_header_names(headers)
                except CSVHeaderError as exc:
                    raise APIError(422, "INVALID_CSV", str(exc)) from exc
                # UTF-8 was checked for the entire file above. Parse no more
                # than five data records; later CSV syntax is not certified.
                preview = list(islice(reader, 5))
                return {
                    "columns": headers,
                    "preview": preview,
                    "preview_count": len(preview),
                }
        except CSVHeaderError as exc:
            if isinstance(exc.__cause__, OSError):
                # Storage failures are server errors, not bad user CSV.
                raise
            raise APIError(422, "INVALID_CSV", "Unable to parse the CSV file.") from exc
        except csv.Error as exc:
            raise APIError(422, "INVALID_CSV", "Unable to parse the CSV file.") from exc


@router.post(
    "/api/csv/inspect",
    openapi_extra={"requestBody": {
        "required": True,
        "content": {"multipart/form-data": {"schema": {
            "type": "object", "required": ["file"],
            "properties": {"file": {"type": "string", "format": "binary"}},
        }}},
    }},
)
async def inspect_csv(request: Request) -> dict[str, object]:
    return await _safe_request(_inspect_csv(request))


async def _safe_request(operation):
    try:
        return await operation
    except APIError:
        raise
    except Exception:
        logger.error("Unexpected CSV web request failure.")
        raise APIError(500, "INTERNAL_ERROR", "Unable to process the request.") from None


@asynccontextmanager
async def _multipart_form(
    request: Request, *, max_files: int = 1, max_body: int = MAX_REQUEST_BYTES
):
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
            if received > max_body:
                raise MultiPartException(_BODY_LIMIT_MESSAGE)
            yield chunk
        if parser is not None and not parser.finished:
            raise MultiPartException("Incomplete multipart upload.")

    parser = _CompleteMultipartParser(
        request.headers, bounded_stream(), max_files=max_files, max_fields=0
    )
    form = None
    try:
        try:
            # This bounds async body reception/parsing only, not CPU work.
            with fail_after(request.app.state.security.upload_timeout_seconds):
                form = await parser.parse()
        except TimeoutError as exc:
            raise APIError(408, "UPLOAD_TIMEOUT", "Upload reception timed out.") from exc
        yield form
    except MultiPartException as exc:
        if exc.message == _BODY_LIMIT_MESSAGE:
            raise APIError(413, "FILE_TOO_LARGE", "Upload request exceeds the size limit.") from exc
        raise APIError(400, "INVALID_UPLOAD", "Invalid multipart upload.") from exc
    finally:
        if form is not None:
            # A disconnected/cancelled caller must not skip spool cleanup.
            with CancelScope(shield=True):
                await form.close()


def _required_file(form, field: str) -> UploadFile:
    file = form.get(field)
    if file is None:
        if field == "file":
            raise APIError(400, "MISSING_FILE", "Provide one CSV file in the 'file' field.")
        raise APIError(400, "MISSING_SCHEMA", "Provide one JSON file in the 'schema' field.")
    if not isinstance(file, UploadFile) or len(form.getlist(field)) != 1:
        raise APIError(400, "INVALID_UPLOAD", "Provide exactly one file per upload field.")
    return file


async def _inspect_csv(request: Request) -> dict[str, object]:
    async with _multipart_form(request) as form:
        file = _required_file(form, "file")
        if set(form) != {"file"}:
            raise APIError(400, "INVALID_UPLOAD", "Provide exactly one uploaded CSV file.")
        inspection = await run_in_threadpool(_inspect_file, file.file)
        filename = Path((file.filename or "upload.csv").replace("\\", "/")).name or "upload.csv"
    return {"status": "ok", "filename": filename, **inspection}


@router.post("/api/schema/validate", openapi_extra={"requestBody": {
    "required": True, "content": {"multipart/form-data": {"schema": {
        "type": "object", "required": ["file"],
        "properties": {"file": {"type": "string", "format": "binary"}},
    }}},
}})
async def validate_uploaded_schema(request: Request) -> dict:
    return await _safe_request(_validate_schema_upload(request))


async def _validate_schema_upload(request: Request) -> dict:
    async with _multipart_form(
        request, max_body=MAX_SCHEMA_BYTES + CHUNK_BYTES
    ) as form:
        file = _required_file(form, "file")
        if set(form) != {"file"}:
            raise APIError(400, "INVALID_UPLOAD", "Provide exactly one uploaded Schema file.")
        schema = await run_in_threadpool(read_schema, file.file)
    return {"status": "ok", "schema": schema, "column_order": list(schema["columns"])}


@router.post("/api/csv/convert", openapi_extra={"requestBody": {
    "required": True, "content": {"multipart/form-data": {"schema": {
        "type": "object", "required": ["file", "schema"],
        "properties": {
            "file": {"type": "string", "format": "binary"},
            "schema": {"type": "string", "format": "binary"},
        },
    }}},
}})
async def convert_csv_upload(request: Request) -> Response:
    return await _safe_request(_convert_csv_upload(request))


async def _convert_csv_upload(request: Request) -> Response:
    async with _multipart_form(
        request, max_files=2,
        max_body=MAX_UPLOAD_BYTES + MAX_SCHEMA_BYTES + CHUNK_BYTES,
    ) as form:
        file = _required_file(form, "file")
        schema_file = _required_file(form, "schema")
        if set(form) != {"file", "schema"}:
            raise APIError(400, "INVALID_UPLOAD", "Only 'file' and 'schema' uploads are accepted.")
        # Schema processing precedes any CSV validation/conversion.
        schema = await run_in_threadpool(read_schema, schema_file.file)
        payload, row_count = await run_in_threadpool(
            convert_upload, file.file, schema, csv_limit=MAX_UPLOAD_BYTES
        )
    return Response(
        payload, media_type="application/json",
        headers={
            "Content-Disposition": 'attachment; filename="converted.json"',
            "X-Row-Count": str(row_count),
            "X-Column-Count": str(len(schema["columns"])),
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


def create_app(settings: SecuritySettings | None = None) -> FastAPI:
    """Create an explicitly configured worker; production docs stay disabled."""
    application = FastAPI(
        title="CSV Validator Web", version="0.2.0", debug=False,
        docs_url=None, redoc_url=None, openapi_url=None,
    )
    application.state.security = settings or SecuritySettings.from_environment()
    application.add_exception_handler(APIError, api_error_handler)
    application.add_exception_handler(HTTPException, http_error_handler)
    application.add_exception_handler(RequestValidationError, validation_error_handler)
    application.add_exception_handler(Exception, unexpected_error_handler)
    application.include_router(router)
    application.mount("/static", StaticFiles(directory=STATIC_DIRECTORY), name="static")
    application.add_middleware(SecurityBoundary, settings=application.state.security)
    return application


app = create_app()
