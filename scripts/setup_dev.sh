#!/usr/bin/env bash

set -euo pipefail

APP_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PATH="${VENV_PATH:-$APP_ROOT/.venv}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
	echo "Python interpreter '$PYTHON_BIN' was not found." >&2
	exit 1
fi

"$PYTHON_BIN" - <<'PY'
import sys

if sys.version_info < (3, 10):
    raise SystemExit("Python 3.10 or newer is required.")
PY

if [ ! -d "$VENV_PATH" ]; then
	echo "Creating virtual environment at $VENV_PATH"
	"$PYTHON_BIN" -m venv "$VENV_PATH"
fi

# shellcheck disable=SC1090
source "$VENV_PATH/bin/activate"

python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
pre-commit install

cat <<EOF
Development environment is ready.

Virtualenv: $VENV_PATH
Activate with:
  source "$VENV_PATH/bin/activate"

Typical next steps:
  pre-commit run --all-files
  bench --site <site-name> run-tests --app sheet_cutting_layout
EOF
