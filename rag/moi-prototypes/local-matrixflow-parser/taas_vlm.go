package localparser

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/matrixflow/moi-core/workers/go-worker/pkg/workitems/parser/clients"
)

const taasVLMSourceLimit = 32 << 20

const documentImageToMarkdownPrompt = `Convert this document image to Markdown.
Preserve all visible text, heading hierarchy, reading order, lists, tables, and mathematical formulas.
Represent tables as HTML and formulas as LaTeX. Do not infer content that is not visible.
Return Markdown only, without a code fence or explanation.`

type VLMRunMetadata struct {
	Provider     string  `json:"provider"`
	Model        string  `json:"model"`
	ProcessingMS float64 `json:"processing_ms"`
}

func (p *Parser) parseOpenAIVLM(ctx context.Context, sourcePath, fileType string, opts Options) (*Result, error) {
	provider := strings.ToLower(strings.TrimSpace(opts.VLM.Provider))
	if provider == "" || provider == "taas" {
		provider = "matrixorigin-taas"
	}
	engine := EngineTaaSVLM
	profile := "taas-vlm"
	artifactName := "taas-vlm.md"
	if provider == "maas" || provider == "huawei-maas" {
		provider = "huawei-maas"
		engine = EngineHuaweiMaaSVLM
		profile = "huawei-maas-vlm"
		artifactName = "huawei-maas-vlm.md"
	}
	if !isImageType(fileType) {
		return nil, fmt.Errorf("%s VLM pipeline supports document images only, got %q", provider, fileType)
	}
	if strings.TrimSpace(opts.VLM.APIKey) == "" {
		return nil, fmt.Errorf("%s VLM pipeline requires an API key", provider)
	}
	if strings.TrimSpace(opts.VLM.BaseURL) == "" {
		return nil, fmt.Errorf("%s VLM pipeline requires a base URL", provider)
	}
	if strings.TrimSpace(opts.VLM.Model) == "" {
		return nil, fmt.Errorf("%s VLM pipeline requires a model", provider)
	}
	info, err := os.Stat(sourcePath)
	if err != nil {
		return nil, err
	}
	if info.Size() > taasVLMSourceLimit {
		return nil, fmt.Errorf("%s VLM source exceeds %d-byte limit", provider, taasVLMSourceLimit)
	}
	raw, err := os.ReadFile(sourcePath)
	if err != nil {
		return nil, fmt.Errorf("read %s VLM source: %w", provider, err)
	}
	client := clients.NewOpenAICompatibleVLMClient(opts.VLM.BaseURL, opts.VLM.APIKey, opts.VLM.Model)
	started := time.Now()
	markdown, err := client.GenerateVisionText(ctx, [][]byte{raw}, documentImageToMarkdownPrompt)
	if err != nil {
		return nil, fmt.Errorf("%s VLM document OCR: %w", provider, err)
	}
	markdown = strings.TrimSpace(markdown)
	if markdown == "" {
		return nil, fmt.Errorf("%s VLM returned empty Markdown", provider)
	}
	processingMS := milliseconds(time.Since(started))
	artifactDir := strings.TrimSpace(opts.ArtifactDir)
	if artifactDir == "" {
		artifactDir = filepath.Join(filepath.Dir(sourcePath), ".matrixflow-parser-artifacts")
	}
	if err := os.MkdirAll(artifactDir, 0o755); err != nil {
		return nil, fmt.Errorf("create TaaS VLM artifact directory: %w", err)
	}
	markdownPath := filepath.Join(artifactDir, artifactName)
	if err := os.WriteFile(markdownPath, []byte(markdown+"\n"), 0o644); err != nil {
		return nil, fmt.Errorf("write TaaS VLM Markdown: %w", err)
	}
	result, err := p.ParseFile(ctx, markdownPath, Options{
		Profile:     ProfileV3Native,
		Pipeline:    PipelineLocal,
		ArtifactDir: artifactDir,
		WorkspaceID: opts.WorkspaceID,
		UserID:      opts.UserID,
		Debug:       opts.Debug,
	})
	if err != nil {
		return nil, fmt.Errorf("parse TaaS VLM Markdown through MatrixFlow: %w", err)
	}
	annotateDocuments(result.Documents, sourcePath)
	result.Engine = engine
	result.SourcePath = sourcePath
	result.FileType = fileType
	result.DurationMS = processingMS + result.DurationMS
	result.MDFileID = markdownPath
	result.Metadata.BackendUsed = engine
	result.Metadata.ParserVersion = opts.VLM.Model
	result.Metadata.TierRequested = PipelineVLM
	result.Metadata.TierEffective = PipelineVLM
	result.VLM = &VLMRunMetadata{Provider: provider, Model: opts.VLM.Model, ProcessingMS: processingMS}
	result.Conformance = Conformance{
		Profile: profile, WebEquivalent: false, Route: provider + ":/v1/chat/completions",
		Reason: "OpenAI-compatible multimodal OCR normalized through MatrixFlow Markdown blocks",
	}
	result.Dependencies = []ExternalDependency{{
		Name: provider + "-vlm", Required: true, Status: "online", UsedFor: "document image OCR and Markdown reconstruction",
	}}
	return result, nil
}

func isImageType(fileType string) bool {
	switch normalizeFileType(fileType) {
	case "png", "jpg", "jpeg", "gif", "bmp", "webp", "tif", "tiff":
		return true
	default:
		return false
	}
}
