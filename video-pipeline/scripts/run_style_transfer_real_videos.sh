#!/usr/bin/env bash
set -euo pipefail

# Run style transfer on real, existing clips in this repository.
# Usage:
#   bash video-pipeline/scripts/run_style_transfer_real_videos.sh
# Optional env overrides:
#   QUALITY_PRESET=fast|quality  — quality uses full-res stylize (scale=1.0); fast uses STYLIZE_SCALE below
#   STYLIZE_SCALE=0.65  — fraction of source resolution for extraction/stylize (1.0 = native; higher = more VRAM/time)
#   FPS=8 STYLIZE_NTH=4 PROMPT="..." NEGATIVE_PROMPT="..."
#   STYLIZE_ENGINE=flux2_klein|zimage  (default: flux2_klein)
#   FLUX_STEPS=4 FLUX_GUIDANCE_SCALE=1.0 FLUX_MODEL_ID=black-forest-labs/FLUX.2-klein-4B
#   For Z-Image: STYLIZE_ENGINE=zimage ZIMAGE_STEPS=2 ZIMAGE_MODEL_ID=...
#   POST_CLEAN_PASS=1  — second FFmpeg pass (hqdn3d + atadenoise) to tame flicker
#   STYLIZE_NTH=1 or INTERPOLATE_MODE=framerate — if streaks remain, full-rate stylize or softer blends
#   POST_CLEAN_VF='hqdn3d=2:1:3:2'  — optional custom -vf for that pass
#   NORMALIZED_DIR=...  — folder of source .mov/.mp4 (default: ai-director-app/output/normalized)
#   SKIP_EXISTING=0     — re-stylize even when output already exists (default: 1)
#   STYLIZE_OUTPUT_EXT=mov|mp4 — final container (default: mov; DaVinci/FCPXML often expect QuickTime MOV)
#   If only legacy *.stylized.mp4 exists, the batch remuxes to *.stylized.mov before skip/stylize.
#   STYLIZE_SKIP_MOV_SIBLING=1 — when output is .mp4, skip DNxHR MOV sibling (Python path)
#   STYLIZE_SKIP_DNXHR_MOV=1 — when output is .mov, keep H.264/AAC in MOV (skip DNxHR+PCM mezzanine)

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"

# Presets:
# - fast: much faster throughput, lower temporal/style fidelity
# - quality: slower, better fidelity
QUALITY_PRESET="${QUALITY_PRESET:-fast}"

if [[ "${QUALITY_PRESET}" == "quality" ]]; then
  FPS_DEFAULT=12
  STYLIZE_NTH_DEFAULT=1
  FLUX_STEPS_DEFAULT=4
  ZIMAGE_STEPS_DEFAULT=4
  SCENE_CUT_AWARE_DEFAULT=1
  STYLIZE_SCALE_DEFAULT=1.0
else
  FPS_DEFAULT=8
  STYLIZE_NTH_DEFAULT=4
  FLUX_STEPS_DEFAULT=4
  ZIMAGE_STEPS_DEFAULT=4
  SCENE_CUT_AWARE_DEFAULT=0
  # Stylize at ~2/3 linear res vs old 0.35 (~4× pixels); use QUALITY_PRESET=quality or STYLIZE_SCALE=1.0 for full.
  STYLIZE_SCALE_DEFAULT=0.65
fi

FPS="${FPS:-${FPS_DEFAULT}}"
STYLIZE_NTH="${STYLIZE_NTH:-${STYLIZE_NTH_DEFAULT}}"
INTERPOLATE_MODE="${INTERPOLATE_MODE:-minterpolate}"
PROMPT="${PROMPT:-studio ghibli penguins cute cinematic}"
NEGATIVE_PROMPT="${NEGATIVE_PROMPT:-blurry, low detail, watermark}"
STYLE_IMAGE="${STYLE_IMAGE:-}"
STYLIZE_ENGINE="${STYLIZE_ENGINE:-flux2_klein}"
ZIMAGE_DEVICE="${ZIMAGE_DEVICE:-auto}"
FLUX_MODEL_ID="${FLUX_MODEL_ID:-black-forest-labs/FLUX.2-klein-4B}"
FLUX_STEPS="${FLUX_STEPS:-${FLUX_STEPS_DEFAULT}}"
FLUX_GUIDANCE_SCALE="${FLUX_GUIDANCE_SCALE:-1.0}"
ZIMAGE_MODEL_ID="${ZIMAGE_MODEL_ID:-Tongyi-MAI/Z-Image-Turbo}"
ZIMAGE_STEPS="${ZIMAGE_STEPS:-${ZIMAGE_STEPS_DEFAULT}}"
ZIMAGE_GUIDANCE_SCALE="${ZIMAGE_GUIDANCE_SCALE:-0.0}"
ZIMAGE_SEED="${ZIMAGE_SEED:-42}"
STYLIZE_SCALE="${STYLIZE_SCALE:-${STYLIZE_SCALE_DEFAULT}}"
UPSCALE_TO_INPUT="${UPSCALE_TO_INPUT:-1}"
# Temporal defaults tuned to reduce streaking / smear (especially with FLUX Klein).
# Increase PREV_FRAME_INPUT_BLEND or enable OPTICAL_FLOW_WARP if you need stronger lock.
TEMPORAL_CONDITIONING="${TEMPORAL_CONDITIONING:-1}"
TEMPORAL_BLEND="${TEMPORAL_BLEND:-0.06}"
REFERENCE_BLEND="${REFERENCE_BLEND:-0.5}"
PREV_FRAME_INPUT_BLEND="${PREV_FRAME_INPUT_BLEND:-0.08}"
OPTICAL_FLOW_WARP="${OPTICAL_FLOW_WARP:-0}"
FLOW_PYR_SCALE="${FLOW_PYR_SCALE:-0.5}"
FLOW_LEVELS="${FLOW_LEVELS:-3}"
FLOW_WINSIZE="${FLOW_WINSIZE:-15}"
POST_CLEAN_PASS="${POST_CLEAN_PASS:-0}"
POST_CLEAN_VF="${POST_CLEAN_VF:-}"
POST_CLEAN_CRF="${POST_CLEAN_CRF:--1}"
PACK_GRID="${PACK_GRID:-off}"
PACK_PADDING="${PACK_PADDING:-16}"
KEYFRAME_INTERVAL="${KEYFRAME_INTERVAL:-1}"
KEYFRAME_SCENE_CUTS="${KEYFRAME_SCENE_CUTS:-1}"
KEYFRAME_SCENE_THRESHOLD="${KEYFRAME_SCENE_THRESHOLD:-0.3}"
SCENE_CUT_AWARE="${SCENE_CUT_AWARE:-${SCENE_CUT_AWARE_DEFAULT}}"

OUT_DIR="${REPO_ROOT}/video-pipeline/output/style_transfer"
WORK_DIR_BASE="${REPO_ROOT}/video-pipeline/output/style_transfer/work"
NORMALIZED_DIR="${NORMALIZED_DIR:-${REPO_ROOT}/ai-director-app/output/normalized}"
SKIP_EXISTING="${SKIP_EXISTING:-1}"
STYLIZE_OUTPUT_EXT="${STYLIZE_OUTPUT_EXT:-mov}"
case "${STYLIZE_OUTPUT_EXT}" in
  mov|mp4) ;;
  *)
    echo "STYLIZE_OUTPUT_EXT must be mov or mp4, got: ${STYLIZE_OUTPUT_EXT}" >&2
    exit 1
    ;;
esac
mkdir -p "${OUT_DIR}" "${WORK_DIR_BASE}"

declare -a INPUT_VIDEOS=()
while IFS= read -r -d '' f; do
  INPUT_VIDEOS+=("$f")
done < <(find "${NORMALIZED_DIR}" -maxdepth 1 -type f \( -iname '*.mov' -o -iname '*.mp4' \) -print0 | sort -z)

if [[ ${#INPUT_VIDEOS[@]} -eq 0 ]]; then
  echo "No .mov/.mp4 files in ${NORMALIZED_DIR}" >&2
  exit 1
fi

echo "Found ${#INPUT_VIDEOS[@]} source clip(s) in ${NORMALIZED_DIR}"

for INPUT_VIDEO in "${INPUT_VIDEOS[@]}"; do
  if [[ ! -f "${INPUT_VIDEO}" ]]; then
    echo "Skipping missing input: ${INPUT_VIDEO}"
    continue
  fi

  BASE_NAME="$(basename "${INPUT_VIDEO}")"
  BASE_STEM="${BASE_NAME%.*}"
  OUTPUT_VIDEO="${OUT_DIR}/${BASE_STEM}.stylized.${STYLIZE_OUTPUT_EXT}"
  WORK_DIR="${WORK_DIR_BASE}/${BASE_STEM}"
  LEGACY_STYLIZED_MP4="${OUT_DIR}/${BASE_STEM}.stylized.mp4"

  if [[ "${OUTPUT_VIDEO}" == *.mov ]] && [[ ! -f "${OUTPUT_VIDEO}" ]] && [[ -f "${LEGACY_STYLIZED_MP4}" ]]; then
    echo ""
    echo "==> Transcode legacy stylized MP4 -> mezzanine MOV (DNxHR+PCM): ${LEGACY_STYLIZED_MP4}"
    "${PYTHON_BIN}" "${REPO_ROOT}/video-pipeline/scripts/mezzanine_transcode_cli.py" \
      "${LEGACY_STYLIZED_MP4}" "${OUTPUT_VIDEO}" --fps probe
  fi

  if [[ "${SKIP_EXISTING}" == "1" ]] && [[ -f "${OUTPUT_VIDEO}" ]]; then
    echo ""
    echo "==> Skip (output exists): ${OUTPUT_VIDEO}"
    continue
  fi

  echo ""
  echo "==> Stylizing: ${INPUT_VIDEO}"
  echo "    Output:    ${OUTPUT_VIDEO}"
  echo "    Preset:    ${QUALITY_PRESET} (engine=${STYLIZE_ENGINE}, fps=${FPS}, nth=${STYLIZE_NTH}, flux_steps=${FLUX_STEPS}, zimage_steps=${ZIMAGE_STEPS}, scale=${STYLIZE_SCALE}, pack=${PACK_GRID}, key-interval=${KEYFRAME_INTERVAL}, flow-warp=${OPTICAL_FLOW_WARP}, post-clean=${POST_CLEAN_PASS})"

  CMD=(
    "${PYTHON_BIN}" "${REPO_ROOT}/video-pipeline/scripts/style_transfer_video.py"
    --input "${INPUT_VIDEO}"
    --output "${OUTPUT_VIDEO}"
    --work-dir "${WORK_DIR}"
    --fps "${FPS}"
    --stylize-scale "${STYLIZE_SCALE}"
    --stylize-every-nth-frame "${STYLIZE_NTH}"
    --interpolate-mode "${INTERPOLATE_MODE}"
    --overwrite
    --stylize-engine "${STYLIZE_ENGINE}"
    --flux-model-id "${FLUX_MODEL_ID}"
    --flux-steps "${FLUX_STEPS}"
    --flux-guidance-scale "${FLUX_GUIDANCE_SCALE}"
    --zimage-device "${ZIMAGE_DEVICE}"
    --zimage-model-id "${ZIMAGE_MODEL_ID}"
    --zimage-steps "${ZIMAGE_STEPS}"
    --zimage-guidance-scale "${ZIMAGE_GUIDANCE_SCALE}"
    --zimage-seed "${ZIMAGE_SEED}"
    --temporal-blend "${TEMPORAL_BLEND}"
    --reference-blend "${REFERENCE_BLEND}"
    --prev-frame-input-blend "${PREV_FRAME_INPUT_BLEND}"
    --flow-pyr-scale "${FLOW_PYR_SCALE}"
    --flow-levels "${FLOW_LEVELS}"
    --flow-winsize "${FLOW_WINSIZE}"
    --pack-grid "${PACK_GRID}"
    --pack-padding "${PACK_PADDING}"
    --keyframe-interval "${KEYFRAME_INTERVAL}"
    --keyframe-scene-threshold "${KEYFRAME_SCENE_THRESHOLD}"
    --post-clean-crf "${POST_CLEAN_CRF}"
    --prompt "${PROMPT}"
    --negative-prompt "${NEGATIVE_PROMPT}"
  )

  if [[ "${TEMPORAL_CONDITIONING}" == "1" ]]; then
    CMD+=(--temporal-conditioning)
  fi
  if [[ "${OPTICAL_FLOW_WARP}" == "1" ]]; then
    CMD+=(--optical-flow-warp)
  fi
  if [[ "${POST_CLEAN_PASS}" == "1" ]]; then
    CMD+=(--post-clean-pass)
  fi
  if [[ -n "${POST_CLEAN_VF}" ]]; then
    CMD+=(--post-clean-vf "${POST_CLEAN_VF}")
  fi
  if [[ "${UPSCALE_TO_INPUT}" == "1" ]]; then
    CMD+=(--upscale-to-input)
  fi

  if [[ "${SCENE_CUT_AWARE}" == "1" ]]; then
    CMD+=(--scene-cut-aware)
  fi
  if [[ "${KEYFRAME_SCENE_CUTS}" == "1" ]]; then
    CMD+=(--keyframe-scene-cuts)
  fi

  if [[ -n "${STYLE_IMAGE}" ]]; then
    CMD+=(--style-image "${STYLE_IMAGE}")
  fi

  "${CMD[@]}"
done

echo ""
echo "Done. Stylized outputs are in: ${OUT_DIR}"
echo "Tip: remux any stray MP4s with: bash ${REPO_ROOT}/video-pipeline/scripts/remux_stylized_mp4_to_mov.sh"
