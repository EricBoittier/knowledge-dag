#!/usr/bin/env bash
set -euo pipefail

# Build MP4 + GIF preview from a directory of images.
# Handles mixed encodings/content by normalizing images to a clean PNG sequence first.
#
# Usage:
#   bash video-pipeline/scripts/build_preview_from_images.sh \
#     --input-dir "/path/to/images" \
#     --output-prefix "/home/ericb/Documents/knowledge-dag/output/style_transfer_preview"
#
# Optional:
#   --fps 8
#   --gif-width 768

INPUT_DIR=""
OUTPUT_PREFIX=""
FPS="8"
GIF_WIDTH="768"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --input-dir)
      INPUT_DIR="$2"
      shift 2
      ;;
    --output-prefix)
      OUTPUT_PREFIX="$2"
      shift 2
      ;;
    --fps)
      FPS="$2"
      shift 2
      ;;
    --gif-width)
      GIF_WIDTH="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ -z "${INPUT_DIR}" || -z "${OUTPUT_PREFIX}" ]]; then
  echo "Usage: $0 --input-dir <dir> --output-prefix <path-without-ext> [--fps 8] [--gif-width 768]" >&2
  exit 1
fi

if [[ ! -d "${INPUT_DIR}" ]]; then
  echo "Input directory not found: ${INPUT_DIR}" >&2
  exit 1
fi

OUTPUT_DIR="$(dirname "${OUTPUT_PREFIX}")"
OUTPUT_BASE="$(basename "${OUTPUT_PREFIX}")"
CLEAN_DIR="${OUTPUT_DIR}/${OUTPUT_BASE}_frames_clean"
mkdir -p "${OUTPUT_DIR}" "${CLEAN_DIR}"

python3 - <<'PY' "${INPUT_DIR}" "${CLEAN_DIR}"
from pathlib import Path
from PIL import Image
import sys

src = Path(sys.argv[1])
dst = Path(sys.argv[2])

for p in sorted(dst.glob("*.png")):
    p.unlink()

# Accept common image extensions, keep deterministic ordering.
image_paths = []
for ext in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
    image_paths.extend(src.glob(ext))
image_paths = sorted(image_paths)

base_size = None
count = 0
for i, path in enumerate(image_paths, start=1):
    try:
        im = Image.open(path).convert("RGB")
    except Exception:
        continue
    if base_size is None:
        base_size = im.size
    if im.size != base_size:
        im = im.resize(base_size, Image.Resampling.LANCZOS)
    out = dst / f"{i:06d}.png"
    im.save(out, format="PNG")
    count += 1

if count == 0:
    raise SystemExit("No readable images found in input directory.")
print(f"Normalized {count} frames to {dst}")
PY

MP4_OUT="${OUTPUT_PREFIX}.mp4"
GIF_OUT="${OUTPUT_PREFIX}.gif"

ffmpeg -y \
  -framerate "${FPS}" \
  -i "${CLEAN_DIR}/%06d.png" \
  -vf "format=yuv420p" \
  "${MP4_OUT}"

ffmpeg -y \
  -framerate "${FPS}" \
  -i "${CLEAN_DIR}/%06d.png" \
  -vf "fps=${FPS},scale=${GIF_WIDTH}:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse" \
  "${GIF_OUT}"

echo "Created:"
echo "  ${MP4_OUT}"
echo "  ${GIF_OUT}"
