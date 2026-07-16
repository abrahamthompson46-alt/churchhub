#!/usr/bin/env bash
set -o errexit
set -o pipefail

# Resolve Python binary (Render provides python3; some images only have python)
if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "ERROR: Neither python3 nor python found in PATH" >&2
  exit 1
fi

echo "==> Using interpreter: $($PY -c 'import sys; print(sys.executable, sys.version)')"

echo "==> Installing dependencies"
$PY -m pip install --upgrade pip
$PY -m pip install -r requirements.txt

echo "==> Collecting static files"
$PY manage.py collectstatic --noinput

echo "==> Build complete"
