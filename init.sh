#!/usr/bin/env bash
# init.sh — environment + harness sanity check for thesis-agents-python
# Must finish with exit code 0 before any work session starts,
# and again before any feature is declared `done`.

set -u
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

ok()   { printf "${GREEN}[OK]${NC}   %s\n" "$1"; }
warn() { printf "${YELLOW}[WARN]${NC} %s\n" "$1"; }
fail() { printf "${RED}[FAIL]${NC} %s\n" "$1"; }

EXIT_CODE=0

# Resolve a python interpreter (Windows ships `python`, Unix often `python3`)
PY=""
for candidate in python python3; do
  if command -v "$candidate" >/dev/null 2>&1; then
    PY="$candidate"
    break
  fi
done

echo "── 1. Checking environment ─────────────────────────────"
if [ -z "$PY" ]; then
  fail "Python is not installed or not on PATH."
  exit 1
fi
ok "python -> $($PY --version 2>&1)"

# Lower bound; pyproject.toml's requires-python is the authoritative pin.
PY_VERSION_OK=$($PY -c 'import sys; print(int(sys.version_info >= (3, 11)))')
if [ "$PY_VERSION_OK" != "1" ]; then
  fail "Python >= 3.11 is required."
  exit 1
fi
ok "Python version compatible"

if command -v uv >/dev/null 2>&1; then
  ok "uv -> $(uv --version)"
else
  fail "uv is not installed (https://docs.astral.sh/uv/) — all Python tooling runs through uv."
  EXIT_CODE=1
fi

echo ""
echo "── 2. Checking harness files ───────────────────────────"

for f in AGENTS.md CLAUDE.md CHECKPOINTS.md feature_list.json progress/current.md progress/history.md \
         .claude/rules/architecture.md .claude/rules/conventions.md .claude/rules/verification.md; do
  if [ ! -f "$f" ]; then
    fail "Missing harness file: $f"
    EXIT_CODE=1
  else
    ok "Exists $f"
  fi
done

echo ""
echo "── 3. Validating feature_list.json ─────────────────────"

$PY - <<'PYEOF'
import json, sys

try:
    data = json.load(open("feature_list.json", encoding="utf-8"))
except Exception as exc:
    print(f"[FAIL] feature_list.json is not valid JSON: {exc}")
    sys.exit(1)

features = data["features"]
valid = set(data["rules"]["valid_status"])
ids = [f["id"] for f in features]
by_id = {f["id"]: f for f in features}
errors = []

if len(ids) != len(set(ids)):
    errors.append("Duplicate feature ids")

in_progress = [f["id"] for f in features if f["status"] == "in_progress"]
if len(in_progress) > 1:
    errors.append(f"{len(in_progress)} features in_progress (max 1): {in_progress}")

for f in features:
    if f["status"] not in valid:
        errors.append(f"Feature {f['id']}: invalid status '{f['status']}'")
    for dep in f.get("depends_on", []):
        if dep not in by_id:
            errors.append(f"Feature {f['id']}: depends_on references unknown id {dep}")
        elif dep == f["id"]:
            errors.append(f"Feature {f['id']}: depends on itself")
    if f["status"] in ("in_progress", "done"):
        not_done = [d for d in f.get("depends_on", []) if by_id.get(d, {}).get("status") != "done"]
        if not_done:
            errors.append(
                f"Feature {f['id']} is '{f['status']}' but dependencies {not_done} are not done"
            )

if errors:
    for e in errors:
        print(f"[FAIL] {e}")
    sys.exit(1)

done = sum(1 for f in features if f["status"] == "done")
print(f"[OK]   feature_list.json valid ({len(features)} features, {done} done, {len(in_progress)} in progress)")
PYEOF
if [ $? -ne 0 ]; then EXIT_CODE=1; fi

echo ""
echo "── 4. Running tests ────────────────────────────────────"

if [ "${SKIP_TESTS:-0}" = "1" ]; then
  warn "SKIP_TESTS=1 — test execution delegated to the caller."
elif [ -d "tests" ] && [ -n "$(find tests -name 'test_*.py' -print -quit 2>/dev/null)" ]; then
  if [ -f "pyproject.toml" ]; then
    TEST_RUNNER="uv run pytest"
  else
    TEST_RUNNER="$PY -m pytest"
  fi
  if $TEST_RUNNER tests -q -m "not integration" 2>&1; then
    ok "Unit tests passed (integration tests excluded; run them with: pytest -m integration)"
  else
    fail "Test suite is red"
    EXIT_CODE=1
  fi
else
  warn "No tests found yet in tests/ — expected only before the first feature lands."
fi

echo ""
echo "── 5. Review ───────────────────────────────────────────"

if [ $EXIT_CODE -eq 0 ]; then
  ok "Environment ready. You can start working."
else
  fail "Environment not ready. Resolve all errors before continuing."
fi

exit $EXIT_CODE
