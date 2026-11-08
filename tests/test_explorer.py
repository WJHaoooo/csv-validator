"""W1 preview extension and static delivery; W0 resource fixtures are reused."""

from contextlib import contextmanager

import pytest

from csv_validator import web
from tests.test_web import client, resources  # noqa: F401


def upload(client, content, filename="customers.csv"):
    return client.post("/api/csv/inspect", files={"file": (filename, content, "text/csv")})


def test_original_names_order_strings_and_first_five_records(client):
    content = b"phone, name ,id\n001, Amy ,0001\n002,Bob,0002\n003,Cam,0003\n004,Dan,0004\n005,Eve,0005\n006,Fox,0006\n"
    data = upload(client, content).json()
    assert data == {
        "status": "ok", "filename": "customers.csv",
        "columns": ["phone", " name ", "id"],
        "preview": [["001", " Amy ", "0001"], ["002", "Bob", "0002"],
                    ["003", "Cam", "0003"], ["004", "Dan", "0004"], ["005", "Eve", "0005"]],
        "preview_count": 5,
    }


def test_header_only_has_empty_preview(client):
    response = upload(client, b"id,name\n")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok", "filename": "customers.csv",
        "columns": ["id", "name"], "preview": [], "preview_count": 0,
    }


def test_quotes_empty_cells_and_multiline_are_not_normalized(client):
    response = upload(client, b'"full,name",note,value\r\n"Amy, Hao","line1\r\nline2",\r\n"say ""hello""",,001\r\n')
    assert response.status_code == 200
    assert response.json()["columns"] == ["full,name", "note", "value"]
    assert response.json()["preview"] == [
        ["Amy, Hao", "line1\r\nline2", ""], ['say "hello"', "", "001"],
    ]


@pytest.mark.parametrize(("content", "reason"), [
    (b"id,id\n1,2\n", "duplicate CSV header"),
    (b"id,name,extra,extra\n", "duplicate CSV header"),
    (b"id,\n", "blank CSV header"),
    (b"id, \t\n", "blank CSV header"),
])
def test_blank_or_duplicate_header_rejected(client, content, reason):
    response = upload(client, content)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_CSV"
    assert reason in response.json()["error"]["message"]
    assert "csv-validator-upload-" not in response.text


def test_csv_reader_does_not_consume_sixth_record(client, monkeypatch):
    original_reader = web.open_csv_reader
    consumed = []

    @contextmanager
    def bounded_reader(path):
        with original_reader(path) as reader:
            def guarded():
                for index, row in enumerate(reader):
                    if index > 5:
                        pytest.fail("CSV parser consumed beyond the five-record preview")
                    consumed.append(index)
                    yield row
            yield guarded()

    monkeypatch.setattr(web, "open_csv_reader", bounded_reader)
    result = upload(client, b"id\n1\n2\n3\n4\n5\n6\n7\n")
    assert result.status_code == 200
    assert result.json()["preview_count"] == 5
    assert consumed == [0, 1, 2, 3, 4, 5]


def test_later_csv_syntax_is_not_certified_but_full_utf8_still_checked(client):
    prefix = b"id\n1\n2\n3\n4\n5\n"
    assert upload(client, prefix + b'"unterminated').status_code == 200
    invalid_utf8 = upload(client, prefix + b"\xff\n")
    assert invalid_utf8.status_code == 422
    assert invalid_utf8.json()["error"]["code"] == "INVALID_UTF8"


def test_filename_is_display_only_and_markup_stays_plain_data(client):
    response = upload(client, b'<img src=x onerror=alert(1)>\n"<script>alert(1)</script>"\n', "../../customers.csv")
    assert response.status_code == 200
    assert response.json()["filename"] == "customers.csv"
    assert response.json()["columns"] == ["<img src=x onerror=alert(1)>"]
    assert response.json()["preview"] == [["<script>alert(1)</script>"]]


def test_explorer_and_static_assets_are_served(client):
    page = client.get("/")
    assert page.status_code == 200
    assert "CSV Explorer" in page.text
    assert 'id="csv-file"' in page.text and 'id="next-step"' in page.text
    for name, content_type in [("style.css", "text/css"), ("app.js", "javascript")]:
        response = client.get("/static/" + name)
        assert response.status_code == 200
        assert content_type in response.headers["content-type"]
