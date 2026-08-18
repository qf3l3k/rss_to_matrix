#!/bin/sh

set -eu

: "${CI_PROJECT_DIR:?CI_PROJECT_DIR is required}"
: "${MINIMUM_PYTHON:?MINIMUM_PYTHON is required}"

PYTHON_COMMAND=${PYTHON_COMMAND:-python3}
CI_VENV="${CI_PROJECT_DIR}/.ci-venv"
PIP_CACHE_DIR=${PIP_CACHE_DIR:-"${CI_PROJECT_DIR}/.cache/pip"}

if ! command -v "$PYTHON_COMMAND" >/dev/null 2>&1; then
    printf 'Required interpreter not found on runner: %s\n' "$PYTHON_COMMAND" >&2
    exit 1
fi

actual_version=$(
    "$PYTHON_COMMAND" -c \
        'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")'
)

if ! "$PYTHON_COMMAND" -c \
    'import sys
minimum = tuple(map(int, sys.argv[1].split(".")))
raise SystemExit(sys.version_info[:len(minimum)] < minimum)' \
    "$MINIMUM_PYTHON"
then
    printf \
        'Runner provided Python %s; this project requires Python %s or newer.\n' \
        "$actual_version" \
        "$MINIMUM_PYTHON" \
        >&2
    exit 1
fi

"$PYTHON_COMMAND" -m venv "$CI_VENV"
"$CI_VENV/bin/python" -m pip install \
    --cache-dir "$PIP_CACHE_DIR" \
    -e "${CI_PROJECT_DIR}[dev]"
