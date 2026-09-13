#!/usr/bin/env bash
# Publish packages/uwuchat-auth-core to the private
# Capsize-Games/uwuchat-auth-core repository.
#
# The canonical source of the published package lives in this repo at
# packages/uwuchat-auth-core/ so the published artifact is reviewable and
# regenerable.  This script mirrors that tree into a clean checkout of the
# target repo, refuses to publish if any application reference leaked in,
# and (optionally) runs the package's own test suite standalone first.
#
# Usage:
#   scripts/publish-auth-core.sh                 # verify + publish
#   scripts/publish-auth-core.sh --dry-run       # verify, stop before push
#   scripts/publish-auth-core.sh --verify        # run the standalone suite too
#   scripts/publish-auth-core.sh --skip-verify   # publish without the grep gate
#
# Env overrides:
#   AUTH_CORE_REMOTE    target clone URL
#                       (default: git@github.com:Capsize-Games/uwuchat-auth-core.git)
#   AUTH_CORE_BRANCH    target branch (default: main)
#   AUTH_CORE_WORK_DIR  scratch checkout (default: .headlesscode/scratch/uwuchat-auth-core)
#   AUTH_CORE_GIT_NAME / AUTH_CORE_GIT_EMAIL  commit identity
#   AUTH_CORE_TEST_IMAGE  container used by --verify (default: python:3.12-slim)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${ROOT}/packages/uwuchat-auth-core"
REMOTE="${AUTH_CORE_REMOTE:-git@github.com:Capsize-Games/uwuchat-auth-core.git}"
BRANCH="${AUTH_CORE_BRANCH:-main}"
WORK="${AUTH_CORE_WORK_DIR:-${ROOT}/.headlesscode/scratch/uwuchat-auth-core}"
TEST_IMAGE="${AUTH_CORE_TEST_IMAGE:-python:3.12-slim}"

# The one token that must never appear in the published tree.  Written as
# two adjacent literals so this script itself does not contain it either
# (the repo-wide grep for leaked application references must stay clean).
FORBIDDEN="airunner""_services"

DRY_RUN=0
RUN_TESTS=0
CHECK_ISOLATION=1
for arg in "$@"; do
    case "${arg}" in
        --dry-run) DRY_RUN=1 ;;
        --verify) RUN_TESTS=1 ;;
        --skip-verify) CHECK_ISOLATION=0 ;;
        -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
        *) echo "unknown argument: ${arg}" >&2; exit 2 ;;
    esac
done

if [[ ! -d "${SRC}" ]]; then
    echo "publish-auth-core: source tree missing: ${SRC}" >&2
    exit 2
fi

# ── Gate 1: no application reference may exist in the tree ───────────
if [[ "${CHECK_ISOLATION}" -eq 1 ]]; then
    if grep -rn "${FORBIDDEN}" "${SRC}" >/dev/null 2>&1; then
        echo "publish-auth-core: refusing to publish — '${FORBIDDEN}'" \
             "referenced in the package tree:" >&2
        grep -rn "${FORBIDDEN}" "${SRC}" >&2
        exit 1
    fi
    echo "ok: '${FORBIDDEN}' not referenced anywhere in the package tree"
fi

# ── Gate 2 (optional): the package's own suite must pass standalone ──
if [[ "${RUN_TESTS}" -eq 1 ]]; then
    echo "running the package test suite standalone (${TEST_IMAGE})..."
    docker run --rm -v "${SRC}:/src:ro" -w /work "${TEST_IMAGE}" sh -c \
        "cp -r /src /work/pkg && cd /work/pkg \
         && pip install -q -e '.[test]' \
         && python -m pytest -q -p no:cacheprovider"
fi

# ── Mirror the tree into a clean checkout of the target repo ─────────
rm -rf "${WORK}"
mkdir -p "$(dirname "${WORK}")"
# A freshly created remote is empty, so the clone leaves HEAD on an
# unborn branch (git's default name, not necessarily ${BRANCH}).
git clone --quiet "${REMOTE}" "${WORK}" \
    || { echo "publish-auth-core: could not clone ${REMOTE}" >&2; exit 1; }

# The package's own .gitignore travels with it; the excludes here keep
# local build artifacts from ever reaching the target repo.
rsync -a --delete \
    --exclude '.git/' \
    --exclude '__pycache__/' \
    --exclude '*.py[cod]' \
    --exclude '*.egg-info/' \
    --exclude '.pytest_cache/' \
    "${SRC}/" "${WORK}/"

cd "${WORK}"
git add -A

if git diff --cached --quiet; then
    echo "publish-auth-core: nothing to publish — ${BRANCH} is up to date"
    exit 0
fi

echo "--- changes to publish ---"
git diff --cached --stat

if [[ "${DRY_RUN}" -eq 1 ]]; then
    echo "publish-auth-core: --dry-run, stopping before commit/push"
    exit 0
fi

NAME="${AUTH_CORE_GIT_NAME:-$(git config user.name 2>/dev/null || true)}"
EMAIL="${AUTH_CORE_GIT_EMAIL:-$(git config user.email 2>/dev/null || true)}"
NAME="${NAME:-headlesscode}"
EMAIL="${EMAIL:-headlesscode@users.noreply.github.com}"

git -c user.name="${NAME}" -c user.email="${EMAIL}" commit --quiet \
    -m "chore: publish uwuchat-auth-core (airunnerweb#213)" \
    -m "Extracted, standalone auth core: JWT, argon2 password hashing/policy,
password-reset tokens, Google/Twitch OAuth, geoblock, rate limiting and
the JWT middleware, all behind the AuthStorageBackend seam.  Includes the
Fernet data-encryption keyring and DEK cache, a README describing the
storage contract, and the package's own standalone test suite."

# The clone of an empty remote has no branch yet — name it explicitly so
# the push target always exists regardless of the local default.
git branch -M "${BRANCH}"
git push --quiet --set-upstream origin "${BRANCH}"
echo "publish-auth-core: pushed to ${REMOTE} (${BRANCH})"
