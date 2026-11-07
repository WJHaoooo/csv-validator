"""Real filesystem publication tests plus targeted I/O fault injection."""

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import threading

import pytest

from csv_validator import writer
from csv_validator.writer import JSONWriteError, check_output_path, write_json


def test_json_utf8_types_order_and_format(tmp_path):
    output = tmp_path / "output.json"
    data = [{"id": 1, "name": "小明", "score": None}, {"id": 2, "name": "Amy", "score": 80.0}]
    assert write_json(data, output) == output
    text = output.read_text(encoding="utf-8")
    assert json.loads(text) == data
    assert list(json.loads(text)[0]) == ["id", "name", "score"]
    assert "小明" in text and "\\u5c0f" not in text
    assert '"score": null' in text
    assert '\n  {\n    "id": 1' in text
    assert text.endswith("\n")
    assert list(tmp_path.iterdir()) == [output]


@pytest.mark.parametrize("data", [[{"value": float("nan")}], [float("inf")], [float("-inf")], {1, 2}, ["\ud800"]])
def test_serialization_failure_precedes_temp_creation(tmp_path, data, monkeypatch):
    def unexpected_temp(*args, **kwargs):
        pytest.fail("serialization must complete before any temporary file is created")

    monkeypatch.setattr(writer.tempfile, "NamedTemporaryFile", unexpected_temp)
    output = tmp_path / "out.json"
    with pytest.raises(JSONWriteError, match="JSON serialization failed") as error:
        write_json(data, output)
    assert str(output) in str(error.value)
    assert list(tmp_path.iterdir()) == []


def test_existing_output_is_preserved(tmp_path):
    output = tmp_path / "out.json"
    output.write_bytes(b"original output")
    with pytest.raises(JSONWriteError, match="already exists"):
        write_json([{"id": 1}], output)
    assert output.read_bytes() == b"original output"
    assert list(tmp_path.iterdir()) == [output]


@pytest.mark.parametrize("name", ["input.csv", "schema.json"])
def test_input_output_alias_rejected(tmp_path, name):
    source = tmp_path / name
    source.write_bytes(b"original input")
    nested = tmp_path / "nested"
    nested.mkdir()
    alias = nested / ".." / name
    with pytest.raises(JSONWriteError, match="conflicts with input"):
        write_json([], alias, input_paths=[source])
    assert source.read_bytes() == b"original input"


def test_missing_output_directory_is_not_created(tmp_path):
    output = tmp_path / "missing" / "out.json"
    with pytest.raises(JSONWriteError, match="output directory"):
        write_json([], output)
    assert not output.parent.exists()


@pytest.mark.parametrize("failure", ["create", "create_collision", "write", "flush", "sync", "publish"])
def test_io_failure_cleans_temp_and_never_publishes(tmp_path, monkeypatch, failure):
    original_temp = writer.tempfile.NamedTemporaryFile
    output = tmp_path / "out.json"

    def denied(*args, **kwargs):
        if failure == "create_collision":
            raise FileExistsError("simulated temporary name collision")
        raise PermissionError(f"simulated {failure} failure")

    if failure in ("create", "create_collision"):
        monkeypatch.setattr(writer.tempfile, "NamedTemporaryFile", denied)
    elif failure in ("write", "flush"):
        def broken_temp(*args, **kwargs):
            file = original_temp(*args, **kwargs)
            original_write = file.write

            def partial_write(payload):
                original_write(payload[:4])
                raise OSError("simulated partial write failure")

            if failure == "write":
                file.write = partial_write
            else:
                file.flush = denied
            return file

        monkeypatch.setattr(writer.tempfile, "NamedTemporaryFile", broken_temp)
    elif failure == "sync":
        monkeypatch.setattr(writer.os, "fsync", denied)
    else:
        def failed_publish(temporary, target):
            assert json.loads(temporary.read_text(encoding="utf-8")) == [{"id": 1}]
            assert temporary.parent == target.parent
            assert not target.exists()
            denied()

        monkeypatch.setattr(writer, "_publish_no_replace", failed_publish)

    with pytest.raises(JSONWriteError) as error:
        write_json([{"id": 1}], output)
    assert str(output) in str(error.value)
    assert "simulated" in str(error.value)
    assert isinstance(error.value.__cause__, OSError)
    if failure == "create_collision":
        assert "cannot create/write temporary JSON" in str(error.value)
        assert "output already exists" not in str(error.value)
    assert list(tmp_path.iterdir()) == []


def test_destination_created_during_publication_is_not_overwritten(tmp_path, monkeypatch):
    output = tmp_path / "out.json"
    original_publish = writer._publish_no_replace

    def competing_writer(temporary, target):
        target.write_bytes(b"competitor content")
        original_publish(temporary, target)

    monkeypatch.setattr(writer, "_publish_no_replace", competing_writer)
    with pytest.raises(JSONWriteError, match="already exists"):
        write_json([{"id": 1}], output)
    assert output.read_bytes() == b"competitor content"
    assert list(tmp_path.iterdir()) == [output]


def test_two_real_writers_publish_exactly_once(tmp_path, monkeypatch):
    output = tmp_path / "out.json"
    barrier = threading.Barrier(2)
    original_publish = writer._publish_no_replace

    def simultaneous_publish(temporary, target):
        barrier.wait(timeout=10)
        original_publish(temporary, target)

    monkeypatch.setattr(writer, "_publish_no_replace", simultaneous_publish)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(write_json, [{"id": value}], output) for value in (1, 2)]
        successes = []
        errors = []
        for future in futures:
            try:
                successes.append(future.result(timeout=15))
            except JSONWriteError as exc:
                errors.append(exc)
    assert successes == [output]
    assert len(errors) == 1
    assert "already exists" in str(errors[0])
    assert json.loads(output.read_text(encoding="utf-8")) in ([{"id": 1}], [{"id": 2}])
    assert list(tmp_path.iterdir()) == [output]


def test_cleanup_failure_warns_without_hiding_publication_failure(tmp_path, monkeypatch):
    output = tmp_path / "out.json"

    def failed_publish(*args):
        raise OSError("publication denied")

    def failed_cleanup(*args, **kwargs):
        raise PermissionError("cleanup denied")

    monkeypatch.setattr(writer, "_publish_no_replace", failed_publish)
    monkeypatch.setattr(Path, "unlink", failed_cleanup)
    with pytest.warns(RuntimeWarning, match="temporary cleanup failed"):
        with pytest.raises(JSONWriteError, match="publication denied"):
            write_json([], output)
    assert not output.exists()
    temporary = list(tmp_path.iterdir())
    assert len(temporary) == 1 and temporary[0].suffix == ".tmp"


def test_case_alias_is_rejected_on_windows(tmp_path):
    import os
    if os.name != "nt":
        pytest.skip("Windows case-insensitive path comparison")
    source = tmp_path / "Input.csv"
    source.write_bytes(b"original")
    with pytest.raises(JSONWriteError, match="conflicts with input"):
        check_output_path(tmp_path / "INPUT.CSV", input_paths=[source])
    assert source.read_bytes() == b"original"
