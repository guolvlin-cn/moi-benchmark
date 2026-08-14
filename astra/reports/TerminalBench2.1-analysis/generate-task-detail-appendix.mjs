import { readdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { Workbook } from "@oai/artifact-tool";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const repositoryRoot = process.env.MOI_BENCHMARK_ROOT
  ? resolve(process.env.MOI_BENCHMARK_ROOT)
  : resolve(scriptDir, "../../..");
const outputPath = resolve(
  repositoryRoot,
  "astra/reports/TerminalBench2.1-analysis/terminalbench2.1-astra-hermes-pi-task-detail-appendix.csv",
);
const tasksRoot = resolve(
  repositoryRoot,
  "work/terminal-bench-2-1-hermes-prebuilt/tasks",
);

const productOrder = ["Astra", "Hermes", "PI"];
const productConfig = {
  Astra: {
    product_version: "v0.0.5-4-g844473c68",
    model_api_id: "c5bde5de-9805-48d4-a016-1db6e6018fc4",
    model_provider: "BigModel/OpenAI-compatible",
    temperature: "0",
    configured_max_turns: "50",
    observed_max_agent_turns_product: "",
    observed_tasks_gt_50_product: "",
    product_execution_budget: "2x_dataset_agent_timeout_sec",
    token_accounting_note: "main_agent_only_excludes_intent_judge",
  },
  Hermes: {
    product_version: "v2026.7.20",
    model_api_id: "zai/glm-5.2",
    model_provider: "Z.AI",
    temperature: "0",
    configured_max_turns: "90",
    observed_max_agent_turns_product: "47",
    observed_tasks_gt_50_product: "0",
    product_execution_budget: "2x_dataset_agent_timeout_sec",
    token_accounting_note: "reported_hermes_run_usage",
  },
  PI: {
    product_version: "0.73.1",
    model_api_id: "zai/glm-5.2",
    model_provider: "Z.AI",
    temperature: "0",
    configured_max_turns: "",
    observed_max_agent_turns_product: "122",
    observed_tasks_gt_50_product: "9",
    product_execution_budget: "2x_dataset_agent_timeout_sec",
    token_accounting_note: "reported_input_plus_cache_plus_output",
  },
};

const inputSources = [
  {
    product: "Astra",
    path: "work/astra-c0-all-jobs/analysis/v2/output/astra-c0-latest-verified-trials.csv",
  },
  {
    product: "Hermes",
    path: "work/hermes-c0-all-jobs/analysis/v2/output/hermes-c0-latest-verified-trials.csv",
  },
  {
    product: "PI",
    path: "work/pi-c0-all-jobs/analysis/v2/output/pi-c0-latest-verified-trials.csv",
  },
];

const outputFields = [
  "comparison_scope",
  "task_id",
  "author_difficulty",
  "verified_product_count",
  "in_strict_three_way_83",
  "product",
  "attempt_count_for_task",
  "selected_source_root",
  "selected_run_dir",
  "selected_trial_name",
  "selected_trial_path",
  "selected_finished_at",
  "reward",
  "verify_status",
  "normal_e2e_pass",
  "pass_after_timeout",
  "timeout",
  "outcome_bucket",
  "product_terminal_status",
  "product_return_code",
  "product_completion_claim",
  "product_run_state_field",
  "product_run_state",
  "product_error_field",
  "product_error",
  "exception_type",
  "interruption_or_stop_reason",
  "timeout_types",
  "timeout_evidence",
  "stream_transport_failure_classification",
  "stream_transport_interruption_count",
  "gateway_response_truncated_count",
  "gateway_balance_error_line_count",
  "e2e_s",
  "environment_setup_s",
  "agent_setup_s",
  "agent_execution_s",
  "verifier_s",
  "tool_calls_field",
  "tool_calls",
  "tool_calls_failed",
  "tool_call_failure_rate",
  "tool_call_duration_s",
  "tool_breakdown",
  "failed_tool_breakdown",
  "turn_metric_name",
  "turn_metric_value",
  "model_activity_observed",
  "token_input",
  "token_fresh_input",
  "token_cache_read",
  "token_cache_creation",
  "token_cache_reported",
  "token_output",
  "token_total",
  "token_known_minimum",
  "token_source",
  "token_accounting_status",
  "token_accounting_scope_or_note",
  "token_sources_consistent",
  "token_is_lower_bound",
  "token_accounting_note",
  "verifier_tests",
  "verifier_passed",
  "verifier_failed",
  "verifier_skipped",
  "failed_test_names",
  "product_version",
  "model_api_id",
  "model_provider",
  "temperature",
  "configured_max_turns",
  "observed_max_agent_turns_product",
  "observed_tasks_gt_50_product",
  "product_execution_budget",
];

function blank(value) {
  return value === undefined || value === null || value === "";
}

function stringValue(value) {
  return blank(value) ? "" : String(value);
}

function boolValue(value) {
  return value === true || String(value).toLowerCase() === "true";
}

function parseCsv(text) {
  const rows = [];
  let row = [];
  let cell = "";
  let inQuotes = false;
  for (let index = 0; index < text.length; index += 1) {
    const character = text[index];
    if (inQuotes) {
      if (character === '"') {
        if (text[index + 1] === '"') {
          cell += '"';
          index += 1;
        } else {
          inQuotes = false;
        }
      } else {
        cell += character;
      }
    } else if (character === '"') {
      inQuotes = true;
    } else if (character === ",") {
      row.push(cell);
      cell = "";
    } else if (character === "\n" || character === "\r") {
      if (character === "\r" && text[index + 1] === "\n") {
        index += 1;
      }
      row.push(cell);
      rows.push(row);
      row = [];
      cell = "";
    } else {
      cell += character;
    }
  }
  if (cell !== "" || row.length > 0) {
    row.push(cell);
    rows.push(row);
  }
  return rows;
}

function toRowMaps(values) {
  const [header, ...rows] = values;
  const fields = header.map((field) => String(field).replace(/^\uFEFF/, ""));
  return rows.map((row) =>
    Object.fromEntries(fields.map((field, index) => [field, row[index] ?? ""])),
  );
}

async function loadCsv(path) {
  const text = await readFile(path, "utf8");
  const workbook = await Workbook.fromCSV(text, { sheetName: "Data" });
  const artifactValues = workbook.worksheets
    .getItem("Data")
    .getUsedRange(true).values;
  const rawValues = parseCsv(text);
  if (
    artifactValues.length !== rawValues.length ||
    artifactValues[0].length !== rawValues[0].length
  ) {
    throw new Error("Source CSV import validation failed: unexpected shape");
  }
  return toRowMaps(rawValues);
}

async function loadTaskDifficulty() {
  const entries = await readdir(tasksRoot, { withFileTypes: true });
  const difficulty = new Map();
  for (const entry of entries) {
    if (!entry.isDirectory()) {
      continue;
    }
    const taskToml = await readFile(join(tasksRoot, entry.name, "task.toml"), "utf8");
    const match = taskToml.match(/^difficulty\s*=\s*"([^"]+)"/m);
    difficulty.set(entry.name, match?.[1] ?? "");
  }
  return difficulty;
}

function normalizeRow(product, raw, difficulty, verifiedProductCount) {
  const get = (field) => stringValue(raw[field]);
  const config = productConfig[product];
  const verifyStatus = get("verify_status");
  const timeout = boolValue(raw.timeout);
  const pass = verifyStatus === "pass";

  const productFields =
    product === "Astra"
      ? {
          selected_source_root: get("selected_source_root"),
          product_run_state_field: "astra_final_state",
          product_run_state: get("astra_final_state"),
          product_error_field: "product_error_type",
          product_error: get("product_error_type"),
          exception_type: get("harbor_exception_type"),
          interruption_or_stop_reason: get("interruption_kind"),
          timeout_types: get("timeout_types"),
          timeout_evidence: get("timeout_evidence"),
          stream_transport_failure_classification: get(
            "stream_transport_failure_classification",
          ),
          stream_transport_interruption_count: get(
            "stream_transport_interruption_count",
          ),
          gateway_response_truncated_count: "",
          gateway_balance_error_line_count: "",
          tool_calls_field: "tool_calls_terminal",
          tool_calls: get("tool_calls_terminal"),
          tool_call_duration_s: get("tool_call_duration_sum_s"),
          turn_metric_name: "agentic_steps",
          turn_metric_value: get("agentic_steps"),
          token_fresh_input: get("token_fresh_input"),
          token_cache_read: get("token_cache_read"),
          token_cache_creation: get("token_cache_creation"),
          token_cache_reported: "",
          token_known_minimum: get("token_known_minimum"),
          token_accounting_scope_or_note: get("token_accounting_scope"),
          token_is_lower_bound: get("token_is_lower_bound"),
        }
      : product === "Hermes"
        ? {
            selected_source_root: "",
            product_run_state_field: "run_status",
            product_run_state: get("run_status"),
            product_error_field: "run_error",
            product_error: get("run_error"),
            exception_type: "",
            interruption_or_stop_reason: "",
            timeout_types: "",
            timeout_evidence: "",
            stream_transport_failure_classification: "",
            stream_transport_interruption_count: "",
            gateway_response_truncated_count: get(
              "gateway_response_truncated_count",
            ),
            gateway_balance_error_line_count: get(
              "gateway_balance_error_line_count",
            ),
            tool_calls_field: "tool_calls",
            tool_calls: get("tool_calls"),
            tool_call_duration_s: get("tool_duration_s"),
            turn_metric_name: "session_messages",
            turn_metric_value: get("session_messages"),
            token_fresh_input: "",
            token_cache_read: "",
            token_cache_creation: "",
            token_cache_reported: "",
            token_known_minimum: "",
            token_accounting_scope_or_note: config.token_accounting_note,
            token_is_lower_bound: "",
          }
        : {
            selected_source_root: "",
            product_run_state_field: "pi_final_stop_reason",
            product_run_state: get("pi_final_stop_reason"),
            product_error_field: "",
            product_error: "",
            exception_type: "",
            interruption_or_stop_reason: get("pi_final_stop_reason"),
            timeout_types: "",
            timeout_evidence: "",
            stream_transport_failure_classification: "",
            stream_transport_interruption_count: "",
            gateway_response_truncated_count: "",
            gateway_balance_error_line_count: get(
              "gateway_balance_error_line_count",
            ),
            tool_calls_field: "tool_calls",
            tool_calls: get("tool_calls"),
            tool_call_duration_s: "",
            turn_metric_name: "assistant_messages",
            turn_metric_value: get("assistant_messages"),
            token_fresh_input: "",
            token_cache_read: "",
            token_cache_creation: "",
            token_cache_reported: get("token_cache"),
            token_known_minimum: "",
            token_accounting_scope_or_note: config.token_accounting_note,
            token_is_lower_bound: "",
          };

  return {
    comparison_scope:
      verifiedProductCount === 3
        ? "strict_three_way_83"
        : "latest_verified_nonpaired",
    task_id: get("task_id"),
    author_difficulty: difficulty,
    verified_product_count: String(verifiedProductCount),
    in_strict_three_way_83: String(verifiedProductCount === 3),
    product,
    attempt_count_for_task: get("attempt_count_for_task"),
    ...productFields,
    selected_run_dir: get("selected_run_dir"),
    selected_trial_name: get("selected_trial_name"),
    selected_trial_path: get("selected_trial_path"),
    selected_finished_at: get("selected_finished_at"),
    reward: get("reward"),
    verify_status: verifyStatus,
    normal_e2e_pass: String(pass && !timeout),
    pass_after_timeout: String(pass && timeout),
    timeout: String(timeout),
    outcome_bucket: get("outcome_bucket"),
    product_terminal_status: get("product_terminal_status"),
    product_return_code: get("product_return_code"),
    product_completion_claim: get("product_completion_claim"),
    e2e_s: get("e2e_s"),
    environment_setup_s: get("environment_setup_s"),
    agent_setup_s: get("agent_setup_s"),
    agent_execution_s: get("agent_execution_s"),
    verifier_s: get("verifier_s"),
    tool_calls_failed: get("tool_calls_failed"),
    tool_call_failure_rate: get("tool_call_failure_rate"),
    tool_breakdown: get("tool_breakdown"),
    failed_tool_breakdown: get("failed_tool_breakdown"),
    model_activity_observed: get("model_activity_observed"),
    token_input: get("token_input"),
    token_output: get("token_output"),
    token_total: get("token_total"),
    token_source: get("token_source"),
    token_accounting_status: get("token_accounting_status"),
    token_sources_consistent: get("token_sources_consistent"),
    token_accounting_note: config.token_accounting_note,
    verifier_tests: get("verifier_tests"),
    verifier_passed: get("verifier_passed"),
    verifier_failed: get("verifier_failed"),
    verifier_skipped: get("verifier_skipped"),
    failed_test_names: get("failed_test_names"),
    ...config,
  };
}

function escapeCsv(value) {
  const text = stringValue(value);
  return /[",\n\r]/.test(text) ? '"' + text.replaceAll('"', '""') + '"' : text;
}

const difficultyByTask = await loadTaskDifficulty();
const rawByProduct = new Map();
for (const source of inputSources) {
  rawByProduct.set(
    source.product,
    await loadCsv(resolve(repositoryRoot, source.path)),
  );
}

const productsByTask = new Map();
for (const [product, rows] of rawByProduct) {
  for (const row of rows) {
    const taskId = stringValue(row.task_id);
    if (!productsByTask.has(taskId)) {
      productsByTask.set(taskId, new Set());
    }
    productsByTask.get(taskId).add(product);
  }
}

const detailRows = [];
for (const product of productOrder) {
  for (const raw of rawByProduct.get(product) ?? []) {
    const taskId = stringValue(raw.task_id);
    const difficulty = difficultyByTask.get(taskId);
    if (!difficulty) {
      throw new Error("No author difficulty found for task: " + taskId);
    }
    detailRows.push(
      normalizeRow(product, raw, difficulty, productsByTask.get(taskId).size),
    );
  }
}

detailRows.sort(
  (left, right) =>
    left.task_id.localeCompare(right.task_id) ||
    productOrder.indexOf(left.product) - productOrder.indexOf(right.product),
);

const csv =
  [
    outputFields.join(","),
    ...detailRows.map((row) =>
      outputFields.map((field) => escapeCsv(row[field])).join(","),
    ),
  ].join("\n") + "\n";
await writeFile(outputPath, csv, "utf8");

const validationWorkbook = await Workbook.fromCSV(csv, { sheetName: "Appendix" });
const validationValues = validationWorkbook.worksheets
  .getItem("Appendix")
  .getUsedRange(true).values;
const inspection = await validationWorkbook.inspect({
  kind: "table",
  range: "Appendix!A1:Q5",
  include: "values",
  table_max_rows: 5,
  table_max_cols: 17,
});

if (
  validationValues.length !== detailRows.length + 1 ||
  validationValues[0].length !== outputFields.length
) {
  throw new Error("CSV validation failed: unexpected row or column count");
}

console.log(
  JSON.stringify({
    output_path: outputPath,
    rows: detailRows.length,
    strict_three_way_rows: detailRows.filter(
      (row) => row.in_strict_three_way_83 === "true",
    ).length,
    nonpaired_rows: detailRows.filter(
      (row) => row.in_strict_three_way_83 === "false",
    ).length,
    columns: outputFields.length,
    preview: inspection.ndjson,
  }),
);
