import crypto from "node:crypto";
import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

function argument(name) {
  const index = process.argv.indexOf(name);
  if (index < 0 || index + 1 >= process.argv.length) throw new Error(`Missing ${name}`);
  return process.argv[index + 1];
}

const resultsPath = argument("--results");
const workbookPath = argument("--workbook");
const markdownPath = argument("--markdown");
const previewDir = argument("--preview-dir");
const summaryPath = argument("--summary");
const results = JSON.parse(await fs.readFile(resultsPath, "utf8"));
if (!results.complete && !process.argv.includes("--allow-partial")) {
  throw new Error(`Refusing to record incomplete results: ${results.missing_runs.join(", ")}`);
}

const input = await FileBlob.load(workbookPath);
const workbook = await SpreadsheetFile.importXlsx(input);
const runByExperiment = new Map(results.runs.map((run) => [run.experiment_id, run]));

function setCell(sheet, row, col, value) {
  sheet.getCell(row, col).values = [[value ?? null]];
}

const matrix = workbook.worksheets.getItem("实验矩阵");
const matrixRange = matrix.getUsedRange();
const matrixValues = matrixRange.values;
const matrixHeaderRow = matrixValues.findIndex((row) => row[0] === "实验ID");
if (matrixHeaderRow < 0) throw new Error("实验矩阵 header not found");
const matrixHeaders = matrixValues[matrixHeaderRow];
const matrixColumns = Object.fromEntries(matrixHeaders.map((header, index) => [header, index]));
const requiredMatrixColumns = ["实验ID", "指标", "实验结果", "分子", "分母", "N/A原因", "Run ID"];
for (const name of requiredMatrixColumns) {
  if (matrixColumns[name] === undefined) throw new Error(`实验矩阵 missing column ${name}`);
}

let updatedMetricRows = 0;
for (let row = matrixHeaderRow + 1; row < matrixValues.length; row += 1) {
  const experimentId = matrixValues[row][matrixColumns["实验ID"]];
  const metricName = matrixValues[row][matrixColumns["指标"]];
  const run = runByExperiment.get(experimentId);
  const metric = run?.metrics?.[metricName];
  if (!metric) continue;
  setCell(matrix, row, matrixColumns["实验结果"], metric.value);
  setCell(matrix, row, matrixColumns["分子"], metric.numerator);
  setCell(matrix, row, matrixColumns["分母"], metric.denominator);
  setCell(matrix, row, matrixColumns["N/A原因"], metric.na_reason);
  setCell(matrix, row, matrixColumns["Run ID"], run.run_id);
  const resultCell = matrix.getCell(row, matrixColumns["实验结果"]);
  if (["Accepted-page rate", "Gold Evidence Preservation", "Run completeness"].includes(metricName)) {
    resultCell.format.numberFormat = "0.00%";
  } else if (metricName === "Normalized Edit Distance") {
    resultCell.format.numberFormat = "0.000000";
  } else if (["CDM", "TEDS"].includes(metricName)) {
    resultCell.format.numberFormat = "0.00";
  }
  updatedMetricRows += 1;
}

const ledger = workbook.worksheets.getItem("Run Ledger");
const ledgerRange = ledger.getUsedRange();
const ledgerValues = ledgerRange.values;
const ledgerHeaderRow = ledgerValues.findIndex((row) => row[0] === "计划实验ID");
if (ledgerHeaderRow < 0) throw new Error("Run Ledger header not found");
const ledgerHeaders = ledgerValues[ledgerHeaderRow];
const ledgerColumns = Object.fromEntries(ledgerHeaders.map((header, index) => [header, index]));
const ledgerMapping = {
  "Run ID": "run_id",
  "Batch ID": "batch_id",
  "Dataset revision/hash": "dataset_revision_hash",
  "Code commit": "code_commit",
  "Product version": "product_version",
  Parser: "parser",
  "开始时间": "started_at",
  "结束时间": "ended_at",
  "Planned attempts": "planned_attempts",
  "Actual attempts": "actual_attempts",
};
let updatedLedgerRows = 0;
for (let row = ledgerHeaderRow + 1; row < ledgerValues.length; row += 1) {
  const experimentId = ledgerValues[row][ledgerColumns["计划实验ID"]];
  const run = runByExperiment.get(experimentId);
  if (!run) continue;
  for (const [columnName, key] of Object.entries(ledgerMapping)) {
    if (ledgerColumns[columnName] !== undefined) {
      setCell(ledger, row, ledgerColumns[columnName], run.ledger[key]);
      if (["开始时间", "结束时间"].includes(columnName)) {
        ledger.getCell(row, ledgerColumns[columnName]).format.numberFormat = "yyyy-mm-dd hh:mm:ss";
      }
    }
  }
  updatedLedgerRows += 1;
}

const temporaryWorkbookPath = `${workbookPath}.recording.tmp.xlsx`;
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(temporaryWorkbookPath);
await fs.rename(temporaryWorkbookPath, workbookPath);

function escapeCell(value) {
  if (value === null || value === undefined) return "";
  return String(value).replaceAll("|", "\\|").replaceAll("\n", "<br>");
}

function displayResult(metricName, metric) {
  if (metric.na_reason) return "";
  if (typeof metric.value !== "number") return metric.value ?? "";
  if (["Accepted-page rate", "Gold Evidence Preservation", "Run completeness"].includes(metricName)) {
    return `${(metric.value * 100).toFixed(2)}%`;
  }
  if (metricName === "Normalized Edit Distance") return metric.value.toFixed(6);
  return metric.value.toFixed(2);
}

const odbLines = [];
odbLines.push("<!-- ODB_RESULTS_START -->");
odbLines.push(
  results.complete
    ? `本表已于 ${results.generated_at} 从官方 scorer 与本地运行 ledger 自动回填。复用页保留 \`reused=true\` / \`reused_from\`，不计为新请求。`
    : "本表为自动回填测试，仅包含当前已经完整结束的运行。"
);
odbLines.push("");
odbLines.push("| 实验 ID | 样本 | Pipeline | 指标 | 方向 | 单位 | 计算方法 | 实验结果 | 分子 | 分母 | N/A 原因 | Run ID |");
odbLines.push("|---|---|---|---|---|---|---|---:|---:|---:|---|---|");
for (let row = matrixHeaderRow + 1; row < matrixValues.length; row += 1) {
  const experimentId = matrixValues[row][matrixColumns["实验ID"]];
  const run = runByExperiment.get(experimentId);
  if (!run) continue;
  const metricName = matrixValues[row][matrixColumns["指标"]];
  const metric = run.metrics[metricName];
  if (!metric) continue;
  const fields = [
    experimentId,
    matrixValues[row][matrixColumns["Split/样本"]],
    matrixValues[row][matrixColumns["Pipeline/模型"]],
    metricName,
    matrixValues[row][matrixColumns["方向"]],
    matrixValues[row][matrixColumns["单位"]],
    matrixValues[row][matrixColumns["计算方法"]],
    displayResult(metricName, metric),
    metric.numerator,
    metric.denominator,
    metric.na_reason,
    run.run_id,
  ];
  odbLines.push(`| ${fields.map(escapeCell).join(" | ")} |`);
}
odbLines.push("<!-- ODB_RESULTS_END -->");

let markdown = await fs.readFile(markdownPath, "utf8");
function replaceSection(source, start, end, replacement) {
  const begin = source.indexOf(start);
  const finish = source.indexOf(end);
  if (begin < 0 || finish < begin) throw new Error(`Markdown markers not found: ${start}, ${end}`);
  return `${source.slice(0, begin)}${replacement}${source.slice(finish + end.length)}`;
}
markdown = replaceSection(markdown, "<!-- ODB_RESULTS_START -->", "<!-- ODB_RESULTS_END -->", odbLines.join("\n"));

const mirrorLines = [];
mirrorLines.push("<!-- EXCEL_FULL_MIRROR_START -->");
mirrorLines.push("## 9. Excel 工作表字段级全量镜像");
mirrorLines.push("");
mirrorLines.push("本节按单元格同步 Excel 的 7 个工作表；实验结果以 Excel 为主记录，并由同一自动收尾步骤同步到本节。");
mirrorLines.push("");
for (const sheetName of ["说明", "实验矩阵", "模型与Pipeline", "指标口径", "数据集清单", "论文基线摘录", "Run Ledger"]) {
  const sheet = workbook.worksheets.getItem(sheetName);
  const used = sheet.getUsedRange();
  const rows = used.values;
  const width = Math.max(...rows.map((row) => row.length));
  const letters = Array.from({ length: width }, (_, index) => {
    let n = index + 1;
    let label = "";
    while (n > 0) {
      n -= 1;
      label = String.fromCharCode(65 + (n % 26)) + label;
      n = Math.floor(n / 26);
    }
    return label;
  });
  mirrorLines.push(`<details><summary>${sheetName}（${used.address}）</summary>`);
  mirrorLines.push("");
  mirrorLines.push(`| Excel 行 | ${letters.join(" | ")} |`);
  mirrorLines.push(`|---:|${letters.map(() => "---").join("|")}|`);
  rows.forEach((row, index) => {
    const cells = Array.from({ length: width }, (_, col) => escapeCell(row[col]));
    mirrorLines.push(`| ${index + 1} | ${cells.join(" | ")} |`);
  });
  mirrorLines.push("");
  mirrorLines.push("</details>");
  mirrorLines.push("");
}
mirrorLines.push("<!-- EXCEL_FULL_MIRROR_END -->");
markdown = replaceSection(
  markdown,
  "<!-- EXCEL_FULL_MIRROR_START -->",
  "<!-- EXCEL_FULL_MIRROR_END -->",
  mirrorLines.join("\n")
);
await fs.writeFile(markdownPath, markdown);

const keyCheck = await workbook.inspect({
  kind: "region",
  sheetId: "实验矩阵",
  range: "A4:W32",
  include: "values,formulas",
  tableMaxRows: 32,
  tableMaxCols: 23,
  maxChars: 14000,
});
console.log(keyCheck.ndjson);
const ledgerCheck = await workbook.inspect({
  kind: "region",
  sheetId: "Run Ledger",
  range: "A4:Z9",
  include: "values,formulas",
  tableMaxRows: 10,
  tableMaxCols: 26,
  maxChars: 8000,
});
console.log(ledgerCheck.ndjson);
const formulaErrors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
  maxChars: 4000,
});
console.log(formulaErrors.ndjson);

await fs.mkdir(previewDir, { recursive: true });
for (const sheetName of ["说明", "实验矩阵", "模型与Pipeline", "指标口径", "数据集清单", "论文基线摘录", "Run Ledger"]) {
  const preview = await workbook.render({ sheetName, autoCrop: "all", scale: 0.8, format: "png" });
  await fs.writeFile(`${previewDir}/${sheetName}.png`, new Uint8Array(await preview.arrayBuffer()));
}

const digest = async (path) => crypto.createHash("sha256").update(await fs.readFile(path)).digest("hex");
await fs.writeFile(
  summaryPath,
  `${JSON.stringify(
    {
      schema_version: "moi-omnidocbench-recording-v1",
      recorded_at: new Date().toISOString(),
      complete: results.complete,
      updated_metric_rows: updatedMetricRows,
      updated_ledger_rows: updatedLedgerRows,
      workbook: workbookPath,
      workbook_sha256: await digest(workbookPath),
      markdown: markdownPath,
      markdown_sha256: await digest(markdownPath),
      results_source: resultsPath,
    },
    null,
    2
  )}\n`
);
await fs.rm(`${temporaryWorkbookPath}.inspect.ndjson`, { force: true });
await fs.rm(`${workbookPath}.inspect.ndjson`, { force: true });
console.log(`updated_metric_rows=${updatedMetricRows} updated_ledger_rows=${updatedLedgerRows}`);
