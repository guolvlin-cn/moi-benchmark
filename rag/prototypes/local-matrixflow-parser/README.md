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

The CLI also exposes two official MinerU cloud pipelines:

| Pipeline | Official route | Token | Output consumed locally |
| --- | --- | --- | --- |
| `precision` | `/api/v4/file-urls/batch` | `MINERU_API_TOKEN` | ZIP `full.md` |
| `agent` | `/api/v1/agent/parse/file` | none | Markdown CDN URL |

Both routes upload the local file using the signed URL returned by MinerU,
poll the documented result endpoint, and normalize the returned Markdown into
MatrixFlow standard documents. They do not use 302.AI.

Result downloads use Go's HTTP client first. Some MinerU CDN edges terminate
Go/LibreSSL TLS handshakes on macOS; when that transport fails, the parser
automatically uses `wget` from `PATH`. The fallback is invoked without a shell,
does not inherit API-key environment variables, and retains the same HTTPS and
download-size checks. `result.json` records `mineru.download_via` as
`go-http` or `wget`. Install the fallback on macOS with `brew install wget`.

## Dependency planning

```sh
go run ./cmd/local-matrixflow-parser plan --input /path/to/document.pdf
```

The JSON plan reports MinerU for PDF, document conversion plus MinerU for the
web-default Office route, OpenXML for native DOCX/PPTX/XLSX, VLM for
image/visual enrichment, and Paddle when `enable_paddle_preprocess=true`.
OpenXML and TaaS VLM become `online` when their settings are present; other
unavailable product backends remain explicit instead of silently falling back.

## Current format status

| Input | MatrixFlow product route | Status | Offline |
| --- | --- | --- | --- |
| TXT, CSV, JSON, JSONL | `plainBlockSource` | configured and smoke-tested | yes |
| Markdown | `markdownBlockSource` | configured and smoke-tested | yes |
| HTML | `htmlBlockSource` | configured and smoke-tested | yes |
| text-layer PDF | `pdfiumNativeBlockSource` | configured and smoke-tested | yes |
| scanned/image PDF | official MinerU precision or Agent pipeline | configured; precision benchmark has run | no |
| DOCX | OpenXML layout + tagged PDF + geometry aligner | configured and smoke-tested | yes |
| PPTX | OpenXML native layout | configured and smoke-tested | yes |
| XLSX | OpenXML rich spreadsheet parser | configured and smoke-tested | yes |
| DOC, PPT, XLS | soffice up-conversion followed by OpenXML | configured and smoke-tested | yes |
| PNG/JPG/WebP and other raster images | TaaS `qwen3-vl-plus` | configured and smoke-tested | no |
| audio/video | ASR | intentionally not configured | no |

PDF uses MatrixFlow's embedded PDFium Native path. No MatrixOne, Catalog,
MinerU, VLM, Paddle, Mowl, or MatrixFlow web deployment is required.

For Office formats use `--profile v3-native`. For scanned PDFs use
`--pipeline precision` or `--pipeline agent`; for raster document images use
`--pipeline vlm`. Audio/video remain outside this deployment scope.

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

Store the official MinerU token here:

```text
/Users/muuushroom/gitrepos/moi-benchmark/rag/.env
```

The file is ignored by Git. Add this line without quotes or with shell-style
quotes:

```dotenv
MINERU_API_TOKEN=your-official-mineru-token
OPENXML_BASE_URL=http://127.0.0.1:8080
SOFFICE_BIN=/absolute/path/to/soffice
MOI_DOCX_GEOMETRY_ALIGNER=/absolute/path/to/docx-geometry-aligner
TAAS_BASE_URL=https://api-taas.moi.matrixorigin.cn/v1
TAAS_VL_MODEL=qwen3-vl-plus
TAAS_API_KEY=your-taas-api-key
```

The CLI searches the current directory and its parents for `.env`. An explicit
path can be supplied with `--env-file`. Process environment variables take
precedence over the file.

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

Build and start the local OpenXML service:

```sh
cd /Users/muuushroom/gitrepos/matrixflow/openxml_service
docker build -t openxml-parser:local -f OpenXMLParser.Api/Dockerfile .
docker run -d --name moi-openxml-parser --restart unless-stopped \
  -p 127.0.0.1:8080:8080 openxml-parser:local
curl --fail http://127.0.0.1:8080/healthz
```

DOCX additionally requires the geometry aligner. Build its managed runtime
with MatrixFlow's canonical deployment script:

```sh
cd /Users/muuushroom/gitrepos/matrixflow
LOCAL_DEPLOY_UV_BIN=/path/to/uv-0.11.17 \
LOCAL_DEPLOY_SOFFICE_BIN=/absolute/path/to/soffice \
  bash skills/local-deploy/scripts/prepare-docx-geometry-aligner.sh \
  /Users/muuushroom/gitrepos/matrixflow \
  /Users/muuushroom/gitrepos/moi-benchmark/rag/tmp/local-parser-runtime
```

The current machine is already configured with the generated soffice wrapper
and aligner paths in `/Users/muuushroom/gitrepos/moi-benchmark/rag/.env`.

Parse native Office files through OpenXML:

```sh
go run ./cmd/local-matrixflow-parser parse \
  --input /absolute/path/document.docx \
  --profile v3-native \
  --env-file /Users/muuushroom/gitrepos/moi-benchmark/rag/.env \
  --run runs/openxml-docx
```

Use TaaS `qwen3-vl-plus` as the explicit lightweight OCR/VLM pipeline for a
document image:

```sh
go run ./cmd/local-matrixflow-parser parse \
  --input /absolute/path/page.png \
  --pipeline vlm \
  --env-file /Users/muuushroom/gitrepos/moi-benchmark/rag/.env \
  --run runs/taas-vlm
```

The VLM route sends the image as an inline data URL to TaaS
`/v1/chat/completions`, stores the returned Markdown, then normalizes that
Markdown through MatrixFlow's native Markdown block source. It uses only
`TAAS_API_KEY`; MinerU continues to use only `MINERU_API_TOKEN`.

Official MinerU precision parsing:

```sh
go run ./cmd/local-matrixflow-parser parse \
  --input /absolute/path/document.pdf \
  --pipeline precision \
  --env-file /Users/muuushroom/gitrepos/moi-benchmark/rag/.env \
  --run runs/mineru-precision
```

Official MinerU Agent lightweight parsing (no Token):

```sh
go run ./cmd/local-matrixflow-parser parse \
  --input /absolute/path/document.pdf \
  --pipeline agent \
  --page-selector 1-10 \
  --run runs/mineru-agent
```

The Agent API has lower file/page limits, returns Markdown only, and its page
selector accepts one page or one contiguous range; comma-separated ranges are
rejected locally. Precision mode uses the official VLM model and retains the
ZIP result contract. Neither route is labeled as an exact execution of
MatrixFlow's pinned web deployment.

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
