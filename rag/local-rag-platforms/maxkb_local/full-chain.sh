#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)
BASE_URL=${MAXKB_BASE_URL:-http://127.0.0.1:8090}
ADMIN_API="$BASE_URL/admin/api"
FIXTURE=${MAXKB_SENTINEL_FIXTURE:-$SCRIPT_DIR/fixtures/unique-sentinel.md}
SENTINEL=${MAXKB_SENTINEL:-MAXKB-SENTINEL-ORCHID-7419}
QUESTION=${MAXKB_SENTINEL_QUESTION:-What is the unique sentinel launch code? Include the full sentinel identifier.}
TOKEN_FILE=${MAXKB_ADMIN_TOKEN_FILE:-$REPO_ROOT/.local-services/maxkb_local/secrets/admin.token}
SECRET_DIR="$REPO_ROOT/.local-services/maxkb_local/secrets"
LOG_ROOT="$REPO_ROOT/.local-services/maxkb_local/logs"
RUN_STAMP=$(date -u +%Y%m%dT%H%M%SZ)
RUN_DIR=${MAXKB_FULL_CHAIN_OUTPUT:-$LOG_ROOT/full-chain-$RUN_STAMP}
CURRENT_STEP=initialization
DIRECT_RETURN=${MAXKB_DIRECT_RETURN:-0}
RUN_OUTCOME=failed
EMBEDDING_PROVIDER=${MAXKB_EMBEDDING_PROVIDER:-}
EMBEDDING_MODEL_NAME=${MAXKB_EMBEDDING_MODEL_NAME:-}
if [[ -z "$EMBEDDING_MODEL_NAME" ]]; then
  case "$EMBEDDING_PROVIDER" in
    *[Mm]aas*) EMBEDDING_MODEL_NAME=${MAAS_EMBEDDING_MODEL:-bge-m3} ;;
    *[Tt]aas*) EMBEDDING_MODEL_NAME=${TAAS_EMBEDDING_MODEL:-bge-m3} ;;
    *) EMBEDDING_MODEL_NAME=${QIANFAN_EMBEDDING_MODEL:-qwen3-embedding-8b} ;;
  esac
fi
EMBEDDING_DIMENSION=${MAXKB_EMBEDDING_DIMENSION:-}
if [[ -z "$EMBEDDING_DIMENSION" ]]; then
  case "$EMBEDDING_PROVIDER" in
    *[Mm]aas*) EMBEDDING_DIMENSION=${MAAS_EMBEDDING_DIMENSION:-1024} ;;
    *[Tt]aas*) EMBEDDING_DIMENSION=${TAAS_EMBEDDING_DIMENSION:-1024} ;;
    *) EMBEDDING_DIMENSION=${QIANFAN_EMBEDDING_DIMENSION:-4096} ;;
  esac
fi
USE_QIANFAN_EMBEDDING=0
if [[ "$EMBEDDING_PROVIDER" == *[Qq]ianfan* || ( -z "$EMBEDDING_PROVIDER" && "$EMBEDDING_MODEL_NAME" == "qwen3-embedding-8b" ) ]]; then
  USE_QIANFAN_EMBEDDING=1
fi

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "missing required command: $1"
}

write_checksums() {
  local file
  while IFS= read -r -d '' file; do
    [[ "$file" == *.sha256 ]] && continue
    shasum -a 256 "$file" >"$file.sha256"
  done < <(find "$RUN_DIR" -maxdepth 1 -type f -print0)
}

finish() {
  local exit_code=$?
  trap - EXIT
  mkdir -p "$RUN_DIR"
  jq -n \
    --arg status "$([[ $exit_code -eq 0 ]] && printf '%s' "$RUN_OUTCOME" || printf failed)" \
    --arg step "$CURRENT_STEP" \
    --argjson exit_code "$exit_code" \
    '{status:$status,last_step:$step,exit_code:$exit_code}' >"$RUN_DIR/run-status.json"
  write_checksums
  exit "$exit_code"
}
trap finish EXIT

api_json() {
  local method=$1 path=$2 request_file=$3 response_file=$4
  HTTP_STATUS=$(curl -sS --max-time 120 -o "$response_file" -w '%{http_code}' \
    -X "$method" -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H 'Content-Type: application/json' --data-binary @"$request_file" \
    "$ADMIN_API$path")
  [[ "$HTTP_STATUS" == 200 ]] || die "$CURRENT_STEP transport status $HTTP_STATUS"
  jq -e '.code == 200' "$response_file" >/dev/null || \
    die "$CURRENT_STEP API error: $(jq -r '.message // "unknown error"' "$response_file")"
}

require_command curl
require_command jq
require_command shasum
[[ -f "$FIXTURE" ]] || die "missing fixture: $FIXTURE"
grep -Fq "$SENTINEL" "$FIXTURE" || die "fixture does not contain sentinel: $SENTINEL"
[[ -f "$TOKEN_FILE" ]] || die "missing admin token file: $TOKEN_FILE"
: "${MAXKB_CHAT_MODEL_ID:?set MAXKB_CHAT_MODEL_ID to a validated chat model}"

mkdir -p "$RUN_DIR" "$SECRET_DIR"
chmod 700 "$SECRET_DIR"
ADMIN_TOKEN=$(cat "$TOKEN_FILE")

if (( USE_QIANFAN_EMBEDDING )); then
  CURRENT_STEP=verify_qianfan_embedding
  : "${QIANFAN_API_KEY:?set QIANFAN_API_KEY in the local provider environment}"
  verify_args=(verify --model-name "$EMBEDDING_MODEL_NAME" --dimension "$EMBEDDING_DIMENSION" \
    --output "$RUN_DIR/qianfan-embedding-verification.json")
  if [[ -n "${MAXKB_EMBEDDING_MODEL_ID:-}" ]]; then
    verify_args+=(--model-id "$MAXKB_EMBEDDING_MODEL_ID")
  fi
  python3 "$SCRIPT_DIR/maxkb_qianfan_embedding.py" "${verify_args[@]}"
  MAXKB_EMBEDDING_MODEL_ID=$(jq -er '.maxkb_model_id' "$RUN_DIR/qianfan-embedding-verification.json")
else
  : "${MAXKB_EMBEDDING_MODEL_ID:?set MAXKB_EMBEDDING_MODEL_ID to a validated embedding model}"
fi

CURRENT_STEP=health
curl -fsS --max-time 15 "$BASE_URL/admin/" >/dev/null

CURRENT_STEP=create_knowledge
jq -n --arg name "maxkb-full-chain-$RUN_STAMP" --arg embedding "$MAXKB_EMBEDDING_MODEL_ID" \
  '{name:$name,folder_id:"default",desc:"Unique sentinel full-chain acceptance",embedding_model_id:$embedding}' \
  >"$RUN_DIR/knowledge-create-request.json"
jq -e --arg embedding "$MAXKB_EMBEDDING_MODEL_ID" \
  '.embedding_model_id == $embedding' "$RUN_DIR/knowledge-create-request.json" >/dev/null || \
  die "knowledge create request lost the selected embedding model id"
api_json POST /workspace/default/knowledge/base \
  "$RUN_DIR/knowledge-create-request.json" "$RUN_DIR/knowledge-create-response.json"
KNOWLEDGE_ID=$(jq -er '.data.id' "$RUN_DIR/knowledge-create-response.json")

CURRENT_STEP=split_document
HTTP_STATUS=$(curl -sS --max-time 120 -o "$RUN_DIR/document-split-response.json" -w '%{http_code}' \
  -H "Authorization: Bearer $ADMIN_TOKEN" -F "file=@$FIXTURE;type=text/markdown" \
  "$ADMIN_API/workspace/default/knowledge/$KNOWLEDGE_ID/document/split")
[[ "$HTTP_STATUS" == 200 ]] || die "split transport status $HTTP_STATUS"
jq -e '.code == 200 and (.data|length == 1)' "$RUN_DIR/document-split-response.json" >/dev/null || \
  die "split did not return exactly one parsed document"
jq '[.data[] | {name,source_file_id,paragraphs:.content}]' \
  "$RUN_DIR/document-split-response.json" >"$RUN_DIR/document-create-request.json"

CURRENT_STEP=create_and_embed_document
api_json PUT "/workspace/default/knowledge/$KNOWLEDGE_ID/document/batch_create" \
  "$RUN_DIR/document-create-request.json" "$RUN_DIR/document-create-response.json"
DOCUMENT_ID=$(jq -er '.data[0].id' "$RUN_DIR/document-create-response.json")

for attempt in $(seq 1 90); do
  curl -sS --max-time 20 -H "Authorization: Bearer $ADMIN_TOKEN" \
    "$ADMIN_API/workspace/default/knowledge/$KNOWLEDGE_ID/document/$DOCUMENT_ID" \
    >"$RUN_DIR/document-status.json"
  document_status=$(jq -r '.data.status // ""' "$RUN_DIR/document-status.json")
  [[ "$document_status" == *3 ]] && die "document embedding failed with status $document_status"
  [[ "$document_status" == *2 ]] && break
  sleep 1
done
[[ "$document_status" == *2 ]] || die "document embedding did not reach SUCCESS; status=$document_status"

if [[ "$DIRECT_RETURN" == 1 ]]; then
  CURRENT_STEP=configure_direct_return
  jq -n --arg id "$DOCUMENT_ID" \
    '{id_list:[$id],hit_handling_method:"directly_return",directly_return_similarity:0.1}' \
    >"$RUN_DIR/document-hit-handling-request.json"
  api_json PUT "/workspace/default/knowledge/$KNOWLEDGE_ID/document/batch_hit_handling" \
    "$RUN_DIR/document-hit-handling-request.json" "$RUN_DIR/document-hit-handling-response.json"
fi

CURRENT_STEP=admin_hit_test
jq -n --arg question "$QUESTION" \
  '{query_text:$question,top_number:5,similarity:0.0,search_mode:"embedding"}' \
  >"$RUN_DIR/hit-test-request.json"
api_json POST "/workspace/default/knowledge/$KNOWLEDGE_ID/hit_test" \
  "$RUN_DIR/hit-test-request.json" "$RUN_DIR/hit-test-response.json"
jq -e --arg sentinel "$SENTINEL" 'any(.data[]?; .content|contains($sentinel))' \
  "$RUN_DIR/hit-test-response.json" >/dev/null || die "hit_test did not return the sentinel paragraph"

CURRENT_STEP=create_application
jq -n --arg name "maxkb-full-chain-$RUN_STAMP" --arg model "$MAXKB_CHAT_MODEL_ID" \
  --arg knowledge "$KNOWLEDGE_ID" \
  '{name:$name,desc:"Unique sentinel generative RAG acceptance app",folder_id:"default",model_id:$model,
    dialogue_number:3,prologue:"",knowledge_id_list:[$knowledge],
    knowledge_setting:{top_n:5,similarity:0.0,max_paragraph_char_number:5000,search_mode:"embedding",
      no_references_setting:{status:"designated_answer",value:"No matching knowledge."}},
    model_setting:{prompt:"Use only the following retrieved knowledge:\n{data}\n\nQuestion: {question}",system:"Grounded RAG assistant",
      no_references_prompt:"No relevant knowledge was retrieved."},problem_optimization:false,type:"SIMPLE",
    model_params_setting:{temperature:0.1,max_tokens:1024}}' >"$RUN_DIR/application-create-request.json"
jq -e --arg knowledge "$KNOWLEDGE_ID" \
  '.knowledge_id_list | index($knowledge) != null' "$RUN_DIR/application-create-request.json" >/dev/null || \
  die "application create request is not bound to the created knowledge base"
api_json POST /workspace/default/application \
  "$RUN_DIR/application-create-request.json" "$RUN_DIR/application-create-response.json"
APPLICATION_ID=$(jq -er '.data.id' "$RUN_DIR/application-create-response.json")

CURRENT_STEP=publish_application
printf '{}\n' >"$RUN_DIR/application-publish-request.json"
api_json PUT "/workspace/default/application/$APPLICATION_ID/publish" \
  "$RUN_DIR/application-publish-request.json" "$RUN_DIR/application-publish-response.json"
jq -e '.data.is_publish == true' "$RUN_DIR/application-publish-response.json" >/dev/null || \
  die "application was not published"

CURRENT_STEP=create_application_key
key_secret_file="$SECRET_DIR/full-chain-$RUN_STAMP-application-key.json"
HTTP_STATUS=$(curl -sS --max-time 30 -o "$key_secret_file" -w '%{http_code}' -X POST \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  "$ADMIN_API/workspace/default/application/$APPLICATION_ID/application_key")
chmod 600 "$key_secret_file"
[[ "$HTTP_STATUS" == 200 ]] || die "application key transport status $HTTP_STATUS"
jq -e '.code == 200 and ((.data.secret_key // "")|length > 0)' "$key_secret_file" >/dev/null || \
  die "application key creation failed"
jq '{code,message,data:(.data|del(.secret_key))}' "$key_secret_file" \
  >"$RUN_DIR/application-key-response-redacted.json"
APPLICATION_KEY=$(jq -r '.data.secret_key' "$key_secret_file")

CURRENT_STEP=public_openai_qa
jq -n --arg question "$QUESTION" \
  '{model:"maxkb",messages:[{role:"user",content:$question}],stream:false}' \
  >"$RUN_DIR/public-qa-request.json"
HTTP_STATUS=$(curl -sS --max-time 120 -o "$RUN_DIR/public-qa-response.json" -w '%{http_code}' \
  -H "Authorization: Bearer $APPLICATION_KEY" -H 'Content-Type: application/json' \
  --data-binary @"$RUN_DIR/public-qa-request.json" \
  "$BASE_URL/chat/api/$APPLICATION_ID/chat/completions")
printf '%s\n' "$HTTP_STATUS" >"$RUN_DIR/public-qa-http-status.txt"
[[ "$HTTP_STATUS" == 200 ]] || die "public QA transport status $HTTP_STATUS"
jq -e --arg sentinel "$SENTINEL" \
  '(.choices[0].message.content // "")|contains($sentinel)' "$RUN_DIR/public-qa-response.json" >/dev/null || \
  die "public QA answer did not contain the sentinel"
if [[ "$DIRECT_RETURN" != 1 ]]; then
  jq -e '(.usage.total_tokens // 0) > 0' "$RUN_DIR/public-qa-response.json" >/dev/null || \
    die "generative public QA has zero/missing token usage"
fi

CURRENT_STEP=write_manifest
jq -n \
  --arg version "v2.10.4-lts" \
  --arg knowledge_id "$KNOWLEDGE_ID" --arg document_id "$DOCUMENT_ID" \
  --arg application_id "$APPLICATION_ID" --arg sentinel "$SENTINEL" \
  --arg embedding_model_id "$MAXKB_EMBEDDING_MODEL_ID" \
  --arg embedding_model_name "$EMBEDDING_MODEL_NAME" \
  --arg embedding_dimension "$EMBEDDING_DIMENSION" \
  --arg embedding_provider "${MAXKB_EMBEDDING_PROVIDER:-unspecified}" \
  --arg chat_provider "${MAXKB_CHAT_PROVIDER:-unspecified}" \
  --arg mode "$([[ "$DIRECT_RETURN" == 1 ]] && printf direct-return || printf generative)" \
  --arg outcome "$([[ "$DIRECT_RETURN" == 1 ]] && printf partial || printf success)" \
  '{maxkb_version:$version,knowledge_id:$knowledge_id,document_id:$document_id,
    application_id:$application_id,sentinel:$sentinel,
    embedding:{provider:$embedding_provider,model_id:$embedding_model_id,model_name:$embedding_model_name,
      dimension:($embedding_dimension|tonumber),registration_contract:"model_openai_provider with empty model_params_form"},
    dataset_binding:{knowledge_id:$knowledge_id,embedding_model_id:$embedding_model_id},
    application_binding:{application_id:$application_id,knowledge_id:$knowledge_id},
    providers:{embedding:$embedding_provider,chat:$chat_provider},
    vector_space_policy:"single embedding model per knowledge base",
    document_embedding_status:"SUCCESS (2)",admin_hit_test:"supported and passed",
    qa_mode:$mode,outcome:$outcome,
    public_openai_qa:(if $mode == "generative" then "passed with nonzero token usage" else "partial: retrieval-backed direct return; generation model bypassed" end),
    public_direct_retrieval:"unsupported; admin hit_test is diagnostic"}' \
  >"$RUN_DIR/manifest.json"

CURRENT_STEP=complete
RUN_OUTCOME=$([[ "$DIRECT_RETURN" == 1 ]] && printf partial || printf success)
printf '%s run_dir=%s knowledge_id=%s document_id=%s application_id=%s\n' \
  "$([[ "$DIRECT_RETURN" == 1 ]] && printf PARTIAL || printf PASS)" \
  "$RUN_DIR" "$KNOWLEDGE_ID" "$DOCUMENT_ID" "$APPLICATION_ID"
