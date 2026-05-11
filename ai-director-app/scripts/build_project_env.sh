#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   ./scripts/build_project_env.sh [env_file]
# Defaults to ./.env.video if present.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${1:-${APP_ROOT}/.env.video}"

if [[ -f "${ENV_FILE}" ]]; then
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
fi

PROJECT_DIR="${PROJECT_DIR:-${APP_ROOT}/projects/walrus-dfs}"
FROM_STAGE="${FROM_STAGE:-source}"
TO_STAGE="${TO_STAGE:-render}"
DRY_RUN="${DRY_RUN:-0}"
SKIP_UPLOAD="${SKIP_UPLOAD:-1}"
CHEAP_VOICES="${CHEAP_VOICES:-1}"
CONCEPT="${CONCEPT:-}"
FORCE_REBUILD_DAG="${FORCE_REBUILD_DAG:-0}"
DEFAULT_SEGMENT_DURATION_SEC="${DEFAULT_SEGMENT_DURATION_SEC:-14}"
VARIANT="${VARIANT:-default}"

cd "${APP_ROOT}"

if [[ "${CHEAP_VOICES}" == "1" ]]; then
  export VOICEOVER_ENGINE="espeak"
fi

if [[ -n "${CONCEPT}" ]]; then
  python3 "${APP_ROOT}/scripts/bootstrap_dag_from_concept.py" \
    --project-dir "${PROJECT_DIR}" \
    --concept "${CONCEPT}" \
    --default-duration-sec "${DEFAULT_SEGMENT_DURATION_SEC}" \
    $([[ "${FORCE_REBUILD_DAG}" == "1" ]] && echo "--force")
fi

npm run build

CMD=(
  node ./dist/core/src/cli/build-project.js
  --project "${PROJECT_DIR}"
  --from-stage "${FROM_STAGE}"
  --to-stage "${TO_STAGE}"
  --variant "${VARIANT}"
)

if [[ "${DRY_RUN}" == "1" ]]; then
  CMD+=(--dry-run)
fi
if [[ "${SKIP_UPLOAD}" == "1" ]]; then
  CMD+=(--skip-upload)
fi

echo "Running: ${CMD[*]}"
"${CMD[@]}"
