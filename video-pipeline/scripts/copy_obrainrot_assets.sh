#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${1:-https://github.com/harvestingmoon/OBrainRot.git}"
REF="${2:-master}"
DEST_DIR="${3:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/input/assets/obrainrot}"
PINNED_COMMIT="${PINNED_COMMIT:-}"

if ! command -v git >/dev/null 2>&1; then
  echo "Error: git is required but not installed." >&2
  exit 1
fi

if ! command -v rsync >/dev/null 2>&1; then
  echo "Error: rsync is required but not installed." >&2
  exit 1
fi

tmp_dir="$(mktemp -d)"
cleanup() {
  rm -rf "${tmp_dir}"
}
trap cleanup EXIT

echo "Cloning ${REPO_URL} (${REF}) with sparse checkout..."
git clone --depth 1 --branch "${REF}" --filter=blob:none --sparse "${REPO_URL}" "${tmp_dir}/repo"
git -C "${tmp_dir}/repo" sparse-checkout set assets
if [[ -n "${PINNED_COMMIT}" ]]; then
  git -C "${tmp_dir}/repo" fetch --depth 1 origin "${PINNED_COMMIT}"
  git -C "${tmp_dir}/repo" checkout "${PINNED_COMMIT}"
fi

RESOLVED_SHA="$(git -C "${tmp_dir}/repo" rev-parse HEAD)"

mkdir -p "${DEST_DIR}"
echo "Syncing assets -> ${DEST_DIR}"
rsync -a --delete "${tmp_dir}/repo/assets/" "${DEST_DIR}/"

PROVENANCE_PATH="${DEST_DIR}/.source-provenance.json"
SYNC_TS="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
cat > "${PROVENANCE_PATH}" <<EOF
{
  "source_repo": "${REPO_URL}",
  "ref": "${REF}",
  "resolved_sha": "${RESOLVED_SHA}",
  "sync_timestamp_utc": "${SYNC_TS}"
}
EOF

echo "Done. Copied OBrainRot assets to: ${DEST_DIR}"
