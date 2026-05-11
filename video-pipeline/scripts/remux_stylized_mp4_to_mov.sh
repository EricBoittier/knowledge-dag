#!/usr/bin/env bash
# Transcode stylized H.264/AAC MP4 → DaVinci mezzanine MOV (DNxHR HQ + PCM), matching normalize_clips / README.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
OUT_DIR="${OUT_DIR:-${REPO_ROOT}/video-pipeline/output/style_transfer}"
SKIP_EXISTING="${SKIP_EXISTING:-1}"

shopt -s nullglob
mapfile -t SRCS < <(find "${OUT_DIR}" -maxdepth 1 -type f -name '*.stylized.mp4' | sort)

if [[ ${#SRCS[@]} -eq 0 ]]; then
  echo "No *.stylized.mp4 under ${OUT_DIR}" >&2
  exit 1
fi

for src in "${SRCS[@]}"; do
  dst="${src%.mp4}.mov"
  if [[ -f "${dst}" ]] && [[ "${SKIP_EXISTING}" == "1" ]]; then
    echo "Skip (exists): ${dst}"
    continue
  fi
  echo "Mezzanine MOV: ${src} -> ${dst}"
  "${PYTHON_BIN}" "${REPO_ROOT}/video-pipeline/scripts/mezzanine_transcode_cli.py" \
    "${src}" "${dst}" --fps probe
done

echo "Done. MOVs in: ${OUT_DIR}"
