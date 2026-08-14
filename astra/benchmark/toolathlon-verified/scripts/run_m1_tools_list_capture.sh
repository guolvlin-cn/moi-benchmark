#!/usr/bin/env bash
set -Eeuo pipefail

umask 077

MODE=${1:-run}
if [[ ${MODE} != run && ${MODE} != --preflight-only ]]; then
  echo "Usage: sudo $0 [--preflight-only]" >&2
  exit 2
fi

if [[ ${EUID} -ne 0 ]]; then
  echo "ERROR: run this script with sudo so it can read root-only frozen credentials and use Docker." >&2
  exit 2
fi

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd -- "${SCRIPT_DIR}/../../../.." && pwd)
SOURCE_ROOT=${TOOLATHLON_SOURCE_ROOT:-/home/vagrant/dataset/Toolathlon}
FREEZE_ROOT=${REPO_ROOT}/astra/benchmark/toolathlon-verified/freeze
RUNTIME_ROOT=${REPO_ROOT}/astra/benchmark/toolathlon-verified/runtime
WORK_ROOT=${TOOLATHLON_M1_OUTPUT_ROOT:-${REPO_ROOT}/astra/work/toolathlon-verified/m1-live/tool-schemas}
REQUIREMENTS=${FREEZE_ROOT}/task-requirements.json
CREDENTIAL_MANIFEST=${FREEZE_ROOT}/credential-manifest.json
APP_MANIFEST=${FREEZE_ROOT}/m1-app-state-live.json
IMAGE=docker.io/lockon0927/toolathlon-task-image@sha256:4d04fe4e0a6fdb4946f51bb05120cb44a0eef980231c11252f93b62897afcb9f
EXPECTED_IMAGE_ID=sha256:4d04fe4e0a6fdb4946f51bb05120cb44a0eef980231c11252f93b62897afcb9f
EXPECTED_COMMIT=2aed2468858f15818acafa178518390cc4b0f5cb

CAPTURED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)
RUN_ID=$(date -u +%Y%m%dT%H%M%SZ)-$$
CONTAINER_NAME=toolathlon-m1-tools-list-${RUN_ID}
STAGING_ROOT=$(mktemp -d /tmp/toolathlon-m1-tools-list.XXXXXX)
FINAL_ROOT=${WORK_ROOT}/${RUN_ID}
TARGET_UID=${SUDO_UID:-0}
TARGET_GID=${SUDO_GID:-0}

cleanup() {
  docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
  case "${STAGING_ROOT}" in
    /tmp/toolathlon-m1-tools-list.*) rm -rf -- "${STAGING_ROOT}" ;;
    *) echo "WARNING: refused to remove unexpected staging path: ${STAGING_ROOT}" >&2 ;;
  esac
}
trap cleanup EXIT INT TERM

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

[[ -d ${SOURCE_ROOT} ]] || fail "Toolathlon source is missing: ${SOURCE_ROOT}"
[[ -f ${REQUIREMENTS} ]] || fail "frozen task requirements are missing"
[[ -f ${CREDENTIAL_MANIFEST} ]] || fail "credential manifest is missing"
[[ -f ${APP_MANIFEST} ]] || fail "local application manifest is missing"

SOURCE_COMMIT=$(git -C "${SOURCE_ROOT}" rev-parse HEAD)
[[ ${SOURCE_COMMIT} == "${EXPECTED_COMMIT}" ]] || fail "Toolathlon source commit mismatch"

IMAGE_ID=$(docker image inspect --format '{{.Id}}' "${IMAGE}")
[[ ${IMAGE_ID} == "${EXPECTED_IMAGE_ID}" ]] || fail "frozen task image ID mismatch"

jq -e '.toolathlon_application_credentials.state == "GO" and .secret_values_recorded == false' \
  "${CREDENTIAL_MANIFEST}" >/dev/null || fail "Toolathlon credential fingerprint gate is not GO"
jq -e '.local_applications.state == "GO" and .local_applications.successful_replays == 1' \
  "${APP_MANIFEST}" >/dev/null || fail "local application reset-replay gate is not GO"
jq -e '.source_commit == "2aed2468858f15818acafa178518390cc4b0f5cb" and (.tasks | length) == 108' \
  "${REQUIREMENTS}" >/dev/null || fail "frozen task universe is not exactly 108 tasks"

CREDENTIAL_COUNT=0
while IFS=$'\t' read -r EXPECTED_SHA RELATIVE_PATH; do
  case "${RELATIVE_PATH}" in
    /*|../*|*/../*|*/..) fail "unsafe credential path in manifest" ;;
  esac
  CREDENTIAL_PATH=${SOURCE_ROOT}/${RELATIVE_PATH}
  [[ -f ${CREDENTIAL_PATH} ]] || fail "credential file is missing: ${RELATIVE_PATH}"
  ACTUAL_SHA=$(sha256sum "${CREDENTIAL_PATH}")
  ACTUAL_SHA=${ACTUAL_SHA%% *}
  [[ ${ACTUAL_SHA} == "${EXPECTED_SHA}" ]] || fail "credential fingerprint drift: ${RELATIVE_PATH}"
  CREDENTIAL_COUNT=$((CREDENTIAL_COUNT + 1))
done < <(jq -r '.toolathlon_application_credentials.files[] | [.sha256, .path] | @tsv' "${CREDENTIAL_MANIFEST}")
[[ ${CREDENTIAL_COUNT} -eq 99 ]] || fail "expected 99 credential files, observed ${CREDENTIAL_COUNT}"

if [[ ${MODE} == --preflight-only ]]; then
  echo "GO: image, source, 108-task universe, local reset replay, and 99 credential fingerprints passed preflight."
  exit 0
fi

mkdir -p "${STAGING_ROOT}/output" "${STAGING_ROOT}/work" "${WORK_ROOT}"
[[ ! -e ${FINAL_ROOT} ]] || fail "run output already exists: ${FINAL_ROOT}"

docker create \
  --name "${CONTAINER_NAME}" \
  --network host \
  --cpus 8 \
  --memory 8g \
  --memory-swap 16g \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  --tmpfs /tmp:rw,nosuid,nodev,size=1g \
  --mount type=bind,src="${RUNTIME_ROOT}",dst=/m1-runtime,readonly \
  --mount type=bind,src="${REQUIREMENTS}",dst=/m1-input/task-requirements.json,readonly \
  --mount type=bind,src="${STAGING_ROOT}",dst=/qualification \
  --env PYTHONHASHSEED=0 \
  --workdir /workspace \
  --entrypoint /bin/sh \
  "${IMAGE}" -c 'sleep infinity' >/dev/null
docker start "${CONTAINER_NAME}" >/dev/null

# Copy only fingerprinted application credentials into this ephemeral container.
# They are never copied into the output mount and the container is always removed by the trap.
while IFS= read -r RELATIVE_PATH; do
  TARGET_DIR=/workspace/${RELATIVE_PATH%/*}
  docker exec "${CONTAINER_NAME}" mkdir -p "${TARGET_DIR}"
  docker cp "${SOURCE_ROOT}/${RELATIVE_PATH}" "${CONTAINER_NAME}:/workspace/${RELATIVE_PATH}"
  docker exec "${CONTAINER_NAME}" chmod 600 "/workspace/${RELATIVE_PATH}"
done < <(jq -r '.toolathlon_application_credentials.files[].path' "${CREDENTIAL_MANIFEST}")

echo "Starting serial real Gateway tools/list capture for 108 tasks."
echo "Container: ${CONTAINER_NAME}"
echo "Captured at: ${CAPTURED_AT}"

set +e
docker exec \
  --workdir /workspace \
  --env PYTHONHASHSEED=0 \
  --env PYTHONPATH=/workspace:/m1-runtime \
  "${CONTAINER_NAME}" \
  /workspace/.venv/bin/python \
  /m1-runtime/capture_live_tool_schemas.py \
  --source /workspace \
  --requirements /m1-input/task-requirements.json \
  --output /qualification/output \
  --work-root /qualification/work \
  --captured-at "${CAPTURED_AT}" \
  --task-timeout 600
CAPTURE_RC=$?
set -e

mkdir -p "${FINAL_ROOT}"
cp -a "${STAGING_ROOT}/output/." "${FINAL_ROOT}/"
chown -R "${TARGET_UID}:${TARGET_GID}" "${FINAL_ROOT}"

if [[ ${CAPTURE_RC} -ne 0 ]]; then
  echo "Capture returned NO_GO; sanitized evidence was retained at ${FINAL_ROOT}" >&2
  exit "${CAPTURE_RC}"
fi

MANIFEST=${FINAL_ROOT}/tool-schema-manifest.json
[[ -f ${MANIFEST} ]] || fail "capture completed without a root manifest"
jq -e '
  .state == "GO"
  and .qualification_scope == "all_108"
  and .observed_task_count == 108
  and .failed_task_count == 0
  and (.tasks | length) == 108
  and ([.tasks[].state] | all(. == "GO"))
' "${MANIFEST}" >/dev/null || fail "captured Schema root did not pass the 108-task gate"

TASK_FILE_COUNT=$(find "${FINAL_ROOT}/tasks" -maxdepth 1 -type f -name '*.json' | wc -l)
[[ ${TASK_FILE_COUNT} -eq 108 ]] || fail "expected 108 task Schema files, observed ${TASK_FILE_COUNT}"

ROOT_SHA=$(jq -r '.task_schema_root_sha256' "${MANIFEST}")
echo "GO: 108/108 real tools/list results captured."
echo "Output: ${FINAL_ROOT}"
echo "Schema root: ${ROOT_SHA}"
