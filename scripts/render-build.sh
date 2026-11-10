#!/usr/bin/env bash
set -eu
# Pin the installer to support --build-constraint on any native Render image.
python -m pip install --disable-pip-version-check pip==26.2.1
python -m pip install --disable-pip-version-check --build-constraint requirements/build.txt -c requirements/render.txt ".[web]"
python -m pip check
