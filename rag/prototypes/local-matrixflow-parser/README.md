# Local MatrixFlow product parser

This standalone module owns the document-parsing stage of the local MatrixFlow
RAG pipeline. Its default `web-default` profile mirrors the `standard_rag` V2
routing boundary and reports every external parser backend that is
intentionally not configured. For locally executable text, Markdown, and HTML
inputs it uses MatrixFlow's V3 Native source as an explicitly labeled
compatibility route.

The module's interface is one operation:

```go
result, err := localparser.New().ParseFile(ctx, path, options)
```

Behind that interface it constructs MatrixFlow
`parser.UnifiedParseService`, pins `parser_version=v3` and
`parse_tier=native`, provides a bounded local-file adapter, runs the product
`SourceRouter`, and returns MatrixFlow standard documents.

Use `Profile: "v3-native"` for that strictly local behavior. The CLI defaults
to `--profile web-default`.

## Dependency planning

```sh
go run ./cmd/local-matrixflow-parser plan --input /path/to/document.pdf
```

The JSON plan reports MinerU for PDF, document conversion plus MinerU for
Office files, OpenXML for spreadsheets, VLM for image/visual enrichment, and
Paddle when `enable_paddle_preprocess=true`. Paddle is optional and disabled
by the web default. These adapters deliberately remain `not_configured` in
`provider.go`.

## What runs fully locally

| Input | MatrixFlow product route |
| --- | --- |
| TXT, CSV, JSON, JSONL | `plainBlockSource` |
| Markdown | `markdownBlockSource` |
| HTML | `htmlBlockSource` |
| PDF | `pdfiumNativeBlockSource` |

PDF uses MatrixFlow's embedded PDFium Native path. No MatrixOne, Catalog,
MinerU, VLM, Paddle, Mowl, or MatrixFlow web deployment is required.

The following formats are deliberately rejected with an explicit dependency
error in local-native mode:

- DOC/DOCX and PPT/PPTX, which need OpenXML or conversion/MinerU;
- XLS/XLSX, which need the OpenXML spreadsheet parser;
- images, which need OCR/VLM for meaningful content;
- audio/video, which need ASR.

## Important product boundary

MatrixFlow's current built-in web knowledge-base `standard_rag` template uses
the legacy `moi:document.parse` V2 workflow. That workflow depends on Catalog,
Mowl, MinerU, document converters, and optional Paddle/VLM services.

This module extracts the fully local product parser seam, Parse V3 Native. It
is useful for isolated parser correctness and latency tests, but it must not
be labeled as an exact execution of the web knowledge-base V2/Standard
pipeline. An exact V2 run requires those owned services or a deployed
MatrixFlow parser endpoint.

## Repository layout

The `replace` directives expect:

```text
gitrepos/
├── matrixflow/
└── moi-benchmark/
    └── rag/prototypes/local-matrixflow-parser/
```

Changing the sibling MatrixFlow checkout changes the product implementation
under test.

## Run

```sh
cd /Users/muuushroom/gitrepos/moi-benchmark/rag/prototypes/local-matrixflow-parser

go run ./cmd/local-matrixflow-parser parse \
  --input data/sample.md \
  --profile web-default \
  --run runs/markdown-smoke
```

Local PDF example:

```sh
go run ./cmd/local-matrixflow-parser parse \
  --input /absolute/path/document.pdf \
  --profile v3-native \
  --page-selector 1-3 \
  --run runs/pdf-native
```

`--run` is an artifact root. Every invocation creates and prints a new
timestamped child directory, so previous results are never overwritten.

## Artifacts

```text
runs/markdown-smoke/
└── 20260731-141416.518/
    ├── result.json         # complete product ParseOutput projection
    ├── documents.jsonl     # one standard MatrixFlow document per line
    ├── plain-text.txt      # emitted when the product parser returns it
    ├── summary.json        # counts, backend, version, tier, latency
    └── product-artifacts/  # product-uploaded markdown/layout/debug artifacts
```

The summary records `backend_used`, `parser_version`, `tier_requested`, and
`tier_effective`, making accidental fallback or a different parsing route
visible.

## Validate

```sh
go test ./...
go vet ./...
go test -race ./...
```
