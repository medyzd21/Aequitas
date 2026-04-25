#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$ROOT_DIR/.env"
APP_DIR="$ROOT_DIR/reflex_app"
APP_URL="http://localhost:3000/contracts"

cd "$ROOT_DIR"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
else
  echo "No .env file found at $ENV_FILE"
  echo "Create one from .env.example before the jury demo:"
  echo "  cp .env.example .env"
  exit 1
fi

if [[ "${AEQUITAS_DEVTOOLS:-}" != "1" ]]; then
  echo "AEQUITAS_DEVTOOLS=1 is required for the in-app Developer Tools panel."
  echo "Set it in .env, then run ./run_demo.sh again."
  exit 1
fi

if [[ ! -x "$APP_DIR/.venv/bin/python" ]]; then
  echo "Reflex virtualenv not found at reflex_app/.venv"
  echo "Run the repo setup first, then retry ./run_demo.sh."
  exit 1
fi

echo "Starting Aequitas demo app..."
echo "Developer Tools: enabled"
echo "Local URL: $APP_URL"
echo "Secrets are loaded into the backend environment but are not printed."

if [[ "$(uname -s)" == "Darwin" ]]; then
  (sleep 2 && open "$APP_URL" >/dev/null 2>&1 || true) &
fi

cd "$APP_DIR"
exec ./.venv/bin/python -m reflex run
