"""Smoke tests for installation, CLI help, and Python requirements."""

import importlib
from importlib import metadata
from pathlib import Path
import subprocess
import sys
import tomllib


def test_package_can_be_imported():
    package = importlib.import_module("csv_validator")
    assert package.__name__ == "csv_validator"
    assert package.__file__ is not None


def test_cli_help_exits_successfully():
    result = subprocess.run(
        [sys.executable, "-m", "csv_validator.cli", "--help"],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout.lower()
    assert "--help" in result.stdout
    assert "not implemented yet" in result.stdout
    assert result.stderr == ""


def test_python_requirement_matches_installed_metadata():
    project_root = Path(__file__).resolve().parents[1]
    with (project_root / "pyproject.toml").open("rb") as file:
        config = tomllib.load(file)

    requirement = config["project"]["requires-python"]
    installed = metadata.metadata(config["project"]["name"])

    assert requirement == ">=3.12"
    assert installed["Requires-Python"] == requirement
    assert sys.version_info >= (3, 12)
