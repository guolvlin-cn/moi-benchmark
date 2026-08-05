package localparser

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/matrixflow/moi-core/workers/go-worker/pkg/runtime"
	productparser "github.com/matrixflow/moi-core/workers/go-worker/pkg/workitems/parser"
	"github.com/matrixflow/moi-core/workers/go-worker/pkg/workitems/parser/clients"
	"github.com/matrixflow/moi-core/workers/go-worker/pkg/workitems/parser/types"
)

const (
	SchemaVersion         = "matrixflow-product-parser-local-v2"
	EngineV3Native        = "matrixflow-parse-v3-native"
	EngineWebDefaultV2    = "matrixflow-standard-rag-v2"
	EngineMinerUPrecision = "mineru-official-precision"
	EngineMinerUAgent     = "mineru-official-agent"
	EngineTaaSVLM         = "taas-vlm"
	ProfileWebDefault     = "web-default"
	ProfileV3Native       = "v3-native"
	PipelineLocal         = "local"
	PipelinePrecision     = "precision"
	PipelineAgent         = "agent"
	PipelineVLM           = "vlm"
)

type OpenXMLOptions struct {
	BaseURL string
}

type VLMOptions struct {
	APIKey  string
	BaseURL string
	Model   string
}

type SofficeOptions struct {
	Binary string
}

type Options struct {
	FileType     string
	Profile      string
	PageSelector string
	Debug        bool
	WorkspaceID  string
	UserID       string
	ArtifactDir  string
	Additional   map[string]any
	Pipeline     string
	MinerU       MinerUOptions
	OpenXML      OpenXMLOptions
	VLM          VLMOptions
	Soffice      SofficeOptions
}

type Result struct {
	SchemaVersion string                      `json:"schema_version"`
	Engine        string                      `json:"engine"`
	SourcePath    string                      `json:"source_path"`
	FileType      string                      `json:"file_type"`
	DurationMS    float64                     `json:"duration_ms"`
	Documents     []types.Document            `json:"documents"`
	PlainText     string                      `json:"plain_text,omitempty"`
	LayoutFileID  string                      `json:"layout_file_id,omitempty"`
	MDFileID      string                      `json:"md_file_id,omitempty"`
	TextRepair    *types.TextRepairSummary    `json:"text_repair,omitempty"`
	Metadata      productparser.ParseMetadata `json:"metadata"`
	Conformance   Conformance                 `json:"conformance"`
	Dependencies  []ExternalDependency        `json:"external_dependencies,omitempty"`
	Remote        *MinerURunMetadata          `json:"mineru,omitempty"`
	VLM           *VLMRunMetadata             `json:"vlm,omitempty"`
}

type Conformance struct {
	Profile       string `json:"profile"`
	WebEquivalent bool   `json:"web_equivalent"`
	Route         string `json:"route"`
	Reason        string `json:"reason,omitempty"`
}

type ExternalDependency struct {
	Name     string `json:"name"`
	Required bool   `json:"required"`
	Status   string `json:"status"`
	UsedFor  string `json:"used_for"`
}

type Parser struct{}

func New() *Parser {
	return &Parser{}
}

func (p *Parser) ParseFile(ctx context.Context, sourcePath string, opts Options) (*Result, error) {
	if p == nil {
		return nil, errors.New("parser is nil")
	}
	absolutePath, err := filepath.Abs(strings.TrimSpace(sourcePath))
	if err != nil {
		return nil, fmt.Errorf("resolve source path: %w", err)
	}
	info, err := os.Stat(absolutePath)
	if err != nil {
		return nil, fmt.Errorf("stat source: %w", err)
	}
	if info.IsDir() {
		return nil, fmt.Errorf("source must be a file: %s", absolutePath)
	}
	fileType := normalizeFileType(opts.FileType)
	if fileType == "" {
		fileType = normalizeFileType(filepath.Ext(absolutePath))
	}
	if fileType == "" {
		return nil, errors.New("cannot determine file type; provide Options.FileType")
	}
	pipeline := strings.ToLower(strings.TrimSpace(opts.Pipeline))
	if pipeline == "" {
		pipeline = PipelineLocal
	}
	if pipeline != PipelineLocal && pipeline != PipelinePrecision && pipeline != PipelineAgent && pipeline != PipelineVLM {
		return nil, fmt.Errorf("unknown parser pipeline %q", pipeline)
	}
	if pipeline == PipelineVLM {
		return p.parseTaaSVLM(ctx, absolutePath, fileType, opts)
	}
	if pipeline != PipelineLocal {
		return p.parseMinerU(ctx, absolutePath, fileType, pipeline, opts)
	}
	profile := strings.ToLower(strings.TrimSpace(opts.Profile))
	if profile == "" {
		profile = ProfileWebDefault
	}
	if profile != ProfileWebDefault && profile != ProfileV3Native {
		return nil, fmt.Errorf("unknown parser profile %q", profile)
	}
	plan := configuredPlan(PlanFor(fileType, profile, opts.Additional), opts)
	if profile == ProfileWebDefault && plan.DirectV2 {
		var missing []string
		for _, dependency := range plan.Dependencies {
			if dependency.Required && dependency.Status == "not_configured" {
				missing = append(missing, dependency.Name)
			}
		}
		if len(missing) > 0 {
			return nil, fmt.Errorf(
				"file type %q requires a MatrixFlow parser backend that is not configured: %s; run the plan command for the exact web route",
				fileType, strings.Join(missing, ", "),
			)
		}
	}
	artifactDir := strings.TrimSpace(opts.ArtifactDir)
	if artifactDir == "" {
		artifactDir = filepath.Join(filepath.Dir(absolutePath), ".matrixflow-parser-artifacts")
	}
	store, err := newLocalFileStore(artifactDir)
	if err != nil {
		return nil, err
	}
	provider := &localClientProvider{files: store}
	if baseURL := strings.TrimSpace(opts.OpenXML.BaseURL); baseURL != "" {
		provider.openXML = clients.NewDirectOpenXMLServiceClient(baseURL)
		provider.openXMLLayout = clients.NewDirectOpenXMLLayoutClient(baseURL)
	}
	if strings.TrimSpace(opts.VLM.BaseURL) != "" && strings.TrimSpace(opts.VLM.APIKey) != "" && strings.TrimSpace(opts.VLM.Model) != "" {
		provider.vlm = clients.NewOpenAICompatibleVLMClient(opts.VLM.BaseURL, opts.VLM.APIKey, opts.VLM.Model)
	}
	if binary := strings.TrimSpace(opts.Soffice.Binary); binary != "" {
		provider.converter = clients.NewSofficeTaggedPDFConverterWithBinary(binary)
	}
	parserVersion := "v3"
	engine := EngineV3Native
	if profile == ProfileWebDefault && plan.DirectV2 {
		parserVersion = "v2"
		engine = EngineWebDefaultV2
	}
	if parserVersion == "v3" && !isLocalNativeType(fileType, opts) {
		return nil, unsupportedLocalTypeError(fileType)
	}
	versionRouter := productparser.NewVersionRouter(productparser.VersionRoutingConfig{
		DefaultVersion: parserVersion,
		EnableV2:       parserVersion == "v2",
		EnableV3:       parserVersion == "v3",
	}, productparser.FeatureFlagsConfig{})
	workspaceID := strings.TrimSpace(opts.WorkspaceID)
	if workspaceID == "" {
		workspaceID = "local-matrixflow-parser"
	}
	userID := strings.TrimSpace(opts.UserID)
	if userID == "" {
		userID = "local-parser-user"
	}
	execCtx := runtime.ExecutionContext{WorkspaceId: workspaceID, UserId: userID}
	product := productparser.NewUnifiedParseService(
		runtime.NewClientFactory("", "", time.Minute),
		versionRouter,
		execCtx,
		productparser.WithClientProvider(provider),
	)
	parseOptions := defaultWebOptions(opts.Debug, opts.VLM.Model)
	if parserVersion == "v3" {
		parseOptions = map[string]any{
			"parse_tier":          "native",
			"debug_enabled":       opts.Debug,
			"docx_openxml_strict": true,
			"image_caption":       false,
			"image_ocr":           false,
			"complex_table":       false,
			"formula":             false,
		}
	}
	if opts.PageSelector != "" {
		parseOptions["page_selector"] = opts.PageSelector
	}
	for key, value := range opts.Additional {
		if key == "parser_version" || key == "parse_tier" {
			continue
		}
		parseOptions[key] = value
	}
	started := time.Now()
	output, err := product.Parse(ctx, productparser.ParseInput{
		Sources:       []types.Source{{FileID: absolutePath}},
		FileType:      fileType,
		ParserVersion: parserVersion,
		Options:       parseOptions,
	})
	if err != nil {
		return nil, fmt.Errorf("MatrixFlow product parser: %w", err)
	}
	if output == nil {
		return nil, errors.New("MatrixFlow product parser returned nil output")
	}
	annotateDocuments(output.Documents, absolutePath)
	return &Result{
		SchemaVersion: SchemaVersion,
		Engine:        engine,
		SourcePath:    absolutePath,
		FileType:      fileType,
		DurationMS:    float64(time.Since(started).Microseconds()) / 1000,
		Documents:     output.Documents,
		PlainText:     output.PlainText,
		LayoutFileID:  output.LayoutFileID,
		MDFileID:      output.MDFileID,
		TextRepair:    output.TextRepair,
		Metadata:      output.Metadata,
		Conformance:   plan.Conformance,
		Dependencies:  plan.Dependencies,
	}, nil
}

func annotateDocuments(documents []types.Document, sourcePath string) {
	localFileID := stableLocalFileID(sourcePath)
	for index := range documents {
		if documents[index].Metadata == nil {
			documents[index].Metadata = map[string]any{}
		}
		documents[index].Metadata["file_id"] = localFileID
		documents[index].Metadata["raw_file_id"] = localFileID
		documents[index].Metadata["file_name"] = filepath.Base(sourcePath)
		documents[index].Metadata["source_path"] = sourcePath
		documents[index].Metadata["document_index"] = index
	}
}

func stableLocalFileID(path string) string {
	digest := sha256.Sum256([]byte(filepath.Clean(path)))
	return "local_" + hex.EncodeToString(digest[:12])
}

func defaultWebOptions(debug bool, vlmModel string) map[string]any {
	if strings.TrimSpace(vlmModel) == "" {
		vlmModel = "qwen3-vl-plus"
	}
	return map[string]any{
		// Keep these options identical to rag-ingest-default-v1.yaml's
		// moi:parser.convert.document.rich invocation. The local adapter adds
		// only vlm_ocr_model because the standalone UnifiedParseService does not
		// receive the worker's injected runtime-config default.
		"workflow_parser":    true,
		"vlm_ocr_model":      vlmModel,
		"image_process_type": []string{"ocr", "caption"},
		"debug_enabled":      debug,
	}
}

func normalizeFileType(value string) string {
	return strings.ToLower(strings.TrimPrefix(strings.TrimSpace(value), "."))
}

func isLocalNativeType(fileType string, opts Options) bool {
	switch fileType {
	case "txt", "text", "csv", "json", "jsonl", "md", "markdown", "html", "htm", "pdf":
		return true
	case "docx", "pptx", "xlsx":
		return strings.TrimSpace(opts.OpenXML.BaseURL) != ""
	case "doc", "ppt", "xls":
		return strings.TrimSpace(opts.OpenXML.BaseURL) != "" && strings.TrimSpace(opts.Soffice.Binary) != ""
	default:
		return false
	}
}

func configuredPlan(plan ParsePlan, opts Options) ParsePlan {
	for index := range plan.Dependencies {
		switch plan.Dependencies[index].Name {
		case "openxml":
			if strings.TrimSpace(opts.OpenXML.BaseURL) != "" {
				plan.Dependencies[index].Status = "online"
			}
		case "vlm":
			if strings.TrimSpace(opts.VLM.BaseURL) != "" && strings.TrimSpace(opts.VLM.APIKey) != "" && strings.TrimSpace(opts.VLM.Model) != "" {
				plan.Dependencies[index].Status = "online"
			}
		case "soffice":
			if strings.TrimSpace(opts.Soffice.Binary) != "" {
				plan.Dependencies[index].Status = "online"
			}
		}
	}
	return plan
}

func unsupportedLocalTypeError(fileType string) error {
	return fmt.Errorf(
		"file type %q requires a MatrixFlow parser backend not bundled in local-native mode; "+
			"DOC/DOCX/PPT/PPTX need OpenXML or conversion/MinerU, XLS/XLSX need OpenXML, "+
			"images need OCR/VLM, and media need ASR",
		fileType,
	)
}
