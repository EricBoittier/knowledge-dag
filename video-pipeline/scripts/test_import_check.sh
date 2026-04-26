#!/usr/bin/env bash
set -euo pipefail

TARGET_DIR="${1:-./output/normalized}"

if ! command -v ffprobe >/dev/null 2>&1; then
  echo "ffprobe not found in PATH"
  exit 1
fi

if [ ! -d "$TARGET_DIR" ]; then
  echo "Directory not found: $TARGET_DIR"
  exit 1
fi

echo "Checking normalized media in: $TARGET_DIR"

fail=0
count=0

shopt -s nullglob
for f in "$TARGET_DIR"/*.mov; do
  count=$((count + 1))
  has_video="$(ffprobe -v error -select_streams v:0 -show_entries stream=codec_name -of csv=p=0 "$f" || true)"
  has_audio="$(ffprobe -v error -select_streams a:0 -show_entries stream=codec_name -of csv=p=0 "$f" || true)"
  sr="$(ffprobe -v error -select_streams a:0 -show_entries stream=sample_rate -of csv=p=0 "$f" || true)"
  ch="$(ffprobe -v error -select_streams a:0 -show_entries stream=channels -of csv=p=0 "$f" || true)"

  if [[ -z "$has_video" || -z "$has_audio" ]]; then
    echo "FAIL: $f (missing video or audio stream)"
    fail=1
    continue
  fi

  if [[ "$sr" != "48000" || "$ch" != "2" ]]; then
    echo "FAIL: $f (audio policy mismatch: sample_rate=$sr channels=$ch)"
    fail=1
    continue
  fi

  echo "PASS: $f (v=$has_video a=$has_audio sr=$sr ch=$ch)"
done
shopt -u nullglob

if [[ "$count" -eq 0 ]]; then
  echo "No .mov files found in $TARGET_DIR"
  exit 1
fi

if [[ "$fail" -ne 0 ]]; then
  echo "Import precheck: FAILED"
  exit 1
fi

echo "Import precheck: PASSED"
