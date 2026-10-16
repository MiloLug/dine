#!/usr/bin/env bash
# ART run-tests on the local dalvikvm (-Xint). Suite: dine-art/tests/runtime; engine: tests/harness.
# Usage: scripts/test-runtime.sh [fetch|build|run|all] [-f REGEX] [-j N] [--update-expectations] ...
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../env.sh"
exec python3 "$DINE_ROOT/tests/harness" "$@"
