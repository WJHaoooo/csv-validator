"""Serialize validated data and publish complete JSON without overwriting."""

from collections.abc import Iterable
import json
import os
from os import PathLike
from pathlib import Path
import tempfile
import warnings


class JSONWriteError(ValueError):
    """JSON serialization, output safety checks, or publication failed."""


def check_output_path(
    path: str | PathLike[str],
    *,
    input_paths: Iterable[str | PathLike[str]] = (),
) -> Path:
    """Reject input aliases, existing destinations, and missing directories."""
    # Keep the final path component intact: never follow an output symlink
    # when publishing. Resolution below is only for input-alias comparison.
    target = Path(os.path.abspath(path))
    try:
        resolved = target.resolve()
        for source in input_paths:
            if resolved == Path(source).resolve():
                raise JSONWriteError(
                    f"{target}: output path conflicts with input path {source}"
                )
        if os.path.lexists(target):
            raise JSONWriteError(f"{target}: output already exists; refusing to overwrite")
        if not target.parent.is_dir():
            raise JSONWriteError(f"{target}: output directory does not exist or is not a directory")
    except (OSError, RuntimeError) as exc:
        raise JSONWriteError(f"{target}: cannot check output path: {exc}") from exc
    return target


def _publish_no_replace(temporary: Path, target: Path) -> None:
    """Publish in one no-replace operation, even if another writer wins a race."""
    if os.name == "nt":
        # Windows rename always rejects an existing destination.
        os.rename(temporary, target)
    else:
        # POSIX rename would overwrite. link creates a new name or fails.
        # No overwrite-capable fallback if this filesystem lacks hard links.
        os.link(temporary, target)


def write_json(
    data: object,
    path: str | PathLike[str],
    *,
    input_paths: Iterable[str | PathLike[str]] = (),
) -> Path:
    """Serialize fully, write a sibling temporary file, then publish safely.

    A cleanup warning after publication means the complete output exists but
    an extra temporary name could not be removed. It is not a partial output.
    """
    target = check_output_path(path, input_paths=input_paths)
    try:
        payload = (
            json.dumps(data, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise JSONWriteError(f"{target}: JSON serialization failed: {exc}") from exc

    temporary = None
    stage = "create/write temporary JSON"
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=target.parent,
            prefix=f".{target.name}.", suffix=".tmp", delete=False,
        ) as file:
            temporary = Path(file.name)
            file.write(payload)
            file.flush()
            os.fsync(file.fileno())
        stage = "publish JSON"
        _publish_no_replace(temporary, target)
    except OSError as exc:
        if stage == "publish JSON" and isinstance(exc, FileExistsError):
            reason = "output already exists; refusing to overwrite"
        else:
            reason = f"cannot {stage}: {exc}"
        raise JSONWriteError(f"{target}: {reason}") from exc
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError as exc:
                warnings.warn(
                    f"{temporary}: temporary cleanup failed: {exc}",
                    RuntimeWarning, stacklevel=2,
                )
    return target
