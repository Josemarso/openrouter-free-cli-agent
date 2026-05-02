# This helps run your program locally with the same environment as when it's run in production.
#It also ensures that any errors will cause the script to exit immediately, which can help with debugging.

set -e

SCRIPT_DIR="$(dirname "$0")"
PYTHONSAFEPATH=1 PYTHONPATH="$SCRIPT_DIR" exec uv run \
  --project "$SCRIPT_DIR" \
  --quiet \
  -m app.main \
  "$@"
