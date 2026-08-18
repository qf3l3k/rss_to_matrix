#!/bin/sh

set -eu

PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$PROJECT_ROOT"

PYTHON=${PYTHON:-python3}

"$PYTHON" -m ruff format --check .
"$PYTHON" -m ruff check .
"$PYTHON" -m mypy
"$PYTHON" -m pytest \
    --cov=rss_to_matrix \
    --cov-report=term-missing \
    --cov-report=xml
