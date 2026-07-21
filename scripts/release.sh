#!/usr/bin/env bash
set -euo pipefail

# ── Color helpers ──────────────────────────────────────────────────────────────
BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

info()  { echo -e "${BOLD}${CYAN}==>${NC} ${BOLD}$1${NC}"; }
ok()    { echo -e "  ${GREEN}✓${NC} $1"; }
warn()  { echo -e "  ${YELLOW}⚠${NC} $1"; }

# ── Resolve version ────────────────────────────────────────────────────────────
VERSION="${1:-}"
if [ -z "$VERSION" ]; then
  CURRENT="$(python3 -c "import re; print(re.search(r'^version = \"(.+)\"', open('pyproject.toml').read(), re.M).group(1))")"
  VERSION="$(echo "$CURRENT" | awk -F. '{print $1"."$2"."($3+1)}')"
  info "Auto-incremented: ${CURRENT} → ${VERSION}"
else
  info "Using specified version: ${VERSION}"
fi

SKIP_DEPLOY="${SKIP_DEPLOY:-0}"

echo ""

# ── Step 1: Bump version in pyproject.toml ─────────────────────────────────────
info "Step 1/4: Bumping version in pyproject.toml"
python3 -c "
import re, pathlib
p = pathlib.Path('pyproject.toml')
p.write_text(re.sub(r'^version = \".*\"', 'version = \"$VERSION\"', p.read_text(), count=1, flags=re.MULTILINE))
"
ok "pyproject.toml updated to version ${VERSION}"

echo ""

# ── Step 2: Sync lockfile ──────────────────────────────────────────────────────
info "Step 2/4: Syncing lockfile"
uv lock --quiet
ok "uv.lock synchronized"

echo ""

# ── Step 3: Commit + tag ───────────────────────────────────────────────────────
info "Step 3/4: Creating commit and tag"

git add pyproject.toml uv.lock
ok "Staged pyproject.toml and uv.lock"

git commit --quiet -m "chore: bump version to $VERSION"
ok "Committed with message: chore: bump version to ${VERSION}"

git tag "v$VERSION"
ok "Tagged as v${VERSION}"

echo ""

# ── Step 4: Push ───────────────────────────────────────────────────────────────
info "Step 4/4: Pushing commit and tags to remote"

git push --quiet
ok "Commit pushed to remote"

git push --quiet --tags
ok "Tag v${VERSION} pushed to remote"

echo ""
echo -e "${BOLD}${GREEN}✔ Release v${VERSION} complete!${NC}"
