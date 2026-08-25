#!/usr/bin/env bash
# Build the fan-out snapshot — one command, reproducible.
#
#   bash scripts/fanout/build_snapshot.sh [--name NAME] [--push]
#
# Produces a Daytona snapshot containing the repo, its deps, headless PyBoy,
# and the tapes capture sidecar. It contains no ROM and no credentials: both
# are supplied per sandbox at launch, so this image is safe to keep around and
# a rotated key never forces a rebuild.
#
# Requires: docker, daytona CLI, and DAYTONA_API_KEY in the environment.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DOCKERFILE="${REPO_ROOT}/docker/fanout/Dockerfile"

# Tag by commit, never `latest`: Daytona rejects mutable tags outright, and a
# race is only comparable if every arm demonstrably ran the same code.
GIT_SHA="$(git -C "${REPO_ROOT}" rev-parse --short HEAD)"
SNAPSHOT_NAME="pokemon-fanout-${GIT_SHA}"
LOCAL_TAG="pokemon-fanout:${GIT_SHA}"
PUSH=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --name) SNAPSHOT_NAME="$2"; shift 2 ;;
        --push) PUSH=true; shift ;;
        -h|--help) sed -n '2,12p' "${BASH_SOURCE[0]}"; exit 0 ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done

if ! command -v docker >/dev/null 2>&1; then
    echo "[build] docker not found — required to build the snapshot image" >&2
    exit 1
fi

if [[ -n "$(git -C "${REPO_ROOT}" status --porcelain)" ]]; then
    # Not fatal, but the snapshot name claims a commit it does not match.
    echo "[build] WARNING: working tree is dirty; ${SNAPSHOT_NAME} will not match ${GIT_SHA} exactly" >&2
fi

echo "[build] building ${LOCAL_TAG} (linux/amd64)"
# --platform is mandatory, not defensive: Daytona runs AMD64, and on Apple
# Silicon the default build would produce an arm64 image that fails at launch.
docker build \
    --platform=linux/amd64 \
    -f "${DOCKERFILE}" \
    -t "${LOCAL_TAG}" \
    "${REPO_ROOT}"

echo "[build] verifying no game ROM entered the image"
# Scoped to /workspace and excluding site-packages: PyBoy ships its own
# default_rom.gb, which is the library's and must not trip this guard. What
# must never appear is a commercial ROM copied out of the build context.
FOUND_ROM="$(docker run --rm --platform=linux/amd64 --entrypoint sh "${LOCAL_TAG}" \
    -c 'find /workspace \( -name "*.gb" -o -name "*.gbc" \) -not -path "*/site-packages/*" 2>/dev/null | head -1')"
if [[ -n "${FOUND_ROM}" ]]; then
    echo "[build] FATAL: a ROM is present in the image (${FOUND_ROM}) — refusing to publish" >&2
    echo "[build] check docker/fanout/Dockerfile.dockerignore; patterns need '**/' to match nested paths" >&2
    exit 1
fi
echo "[build] clean: no game ROM in image"

if [[ "${PUSH}" != "true" ]]; then
    echo "[build] built ${LOCAL_TAG}. Re-run with --push to create the Daytona snapshot."
    exit 0
fi

if [[ -z "${DAYTONA_API_KEY:-}" ]]; then
    echo "[build] DAYTONA_API_KEY is not set — cannot create the snapshot" >&2
    exit 1
fi

if command -v daytona >/dev/null 2>&1; then
    echo "[build] pushing snapshot ${SNAPSHOT_NAME} via daytona CLI"
    daytona snapshot push "${LOCAL_TAG}" --name "${SNAPSHOT_NAME}"
else
    # No CLI (it is not in Homebrew): build server-side through the SDK from a
    # git-clean staged context instead. Same outcome, and the staging is
    # provably ROM- and secret-free because gitignore excludes both.
    echo "[build] daytona CLI not found — building ${SNAPSHOT_NAME} via the SDK"
    uv run --group fanout python "${REPO_ROOT}/scripts/fanout/sdk_build.py" "${SNAPSHOT_NAME}"
fi

echo "[build] done: ${SNAPSHOT_NAME}"
echo "[build] race against it with:"
echo "    uv run scripts/fanout/cli.py --backend daytona --snapshot ${SNAPSHOT_NAME} --rom <rom>"
