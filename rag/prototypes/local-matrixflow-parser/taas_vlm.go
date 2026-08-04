package localparser

import (
	"context"
	"errors"
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

func (p *Parser) parseTaaSVLM(ctx context.Context, sourcePath, fileType string, opts Options) (*Result, error) {
	if !isImageType(fileType) {
		return nil, fmt.Errorf("TaaS VLM pipeline supports document images only, got %q", fileType)
	}
	if strings.TrimSpace(opts.VLM.APIKey) == "" {
		return nil, errors.New("TaaS VLM pipeline requires TAAS_API_KEY")
	}
	if strings.TrimSpace(opts.VLM.BaseURL) == "" {
		return nil, errors.New("TaaS VLM pipeline requires TAAS_BASE_URL")
	}
	if strings.TrimSpace(opts.VLM.Model) == "" {
		return nil, errors.New("TaaS VLM pipeline requires TAAS_VL_MODEL")
	}
	info, err := os.Stat(sourcePath)
	if err != nil {
		return nil, err
	}
	if info.Size() > taasVLMSourceLimit {
		return nil, fmt.Errorf("TaaS VLM source exceeds %d-byte limit", taasVLMSourceLimit)
	}
	raw, err := os.ReadFile(sourcePath)
	if err != nil {
		return nil, fmt.Errorf("read TaaS VLM source: %w", err)
	}
	client := clients.NewOpenAICompatibleVLMClient(opts.VLM.BaseURL, opts.VLM.APIKey, opts.VLM.Model)
	started := time.Now()
	markdown, err := client.GenerateVisionText(ctx, [][]byte{raw}, documentImageToMarkdownPrompt)
	if err != nil {
		return nil, fmt.Errorf("TaaS VLM document OCR: %w", err)
	}
	markdown = strings.TrimSpace(markdown)
	if markdown == "" {
		return nil, errors.New("TaaS VLM returned empty Markdown")
	}
	processingMS := milliseconds(time.Since(started))
	artifactDir := strings.TrimSpace(opts.ArtifactDir)
	if artifactDir == "" {
		artifactDir = filepath.Join(filepath.Dir(sourcePath), ".matrixflow-parser-artifacts")
	}
	if err := os.MkdirAll(artifactDir, 0o755); err != nil {
		return nil, fmt.Errorf("create TaaS VLM artifact directory: %w", err)
	}
	markdownPath := filepath.Join(artifactDir, "taas-vlm.md")
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
	result.Engine = EngineTaaSVLM
	result.SourcePath = sourcePath
	result.FileType = fileType
	result.DurationMS = processingMS + result.DurationMS
	result.MDFileID = markdownPath
	result.Metadata.BackendUsed = EngineTaaSVLM
	result.Metadata.ParserVersion = opts.VLM.Model
	result.Metadata.TierRequested = PipelineVLM
	result.Metadata.TierEffective = PipelineVLM
	result.VLM = &VLMRunMetadata{Provider: "matrixorigin-taas", Model: opts.VLM.Model, ProcessingMS: processingMS}
	result.Conformance = Conformance{
		Profile: "taas-vlm", WebEquivalent: false, Route: "taas:/v1/chat/completions",
		Reason: "OpenAI-compatible TaaS multimodal OCR normalized through MatrixFlow Markdown blocks",
	}
	result.Dependencies = []ExternalDependency{{
		Name: "matrixorigin-taas-vlm", Required: true, Status: "online", UsedFor: "document image OCR and Markdown reconstruction",
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
