package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	localparser "github.com/matrixorigin/moi-benchmark/local-matrixflow-parser"
)

type summary struct {
	SchemaVersion string                           `json:"schema_version"`
	Engine        string                           `json:"engine"`
	SourcePath    string                           `json:"source_path"`
	FileType      string                           `json:"file_type"`
	Documents     int                              `json:"documents"`
	BlockTypes    map[string]int                   `json:"block_types"`
	ContentChars  int                              `json:"content_chars"`
	DurationMS    float64                          `json:"duration_ms"`
	BackendUsed   string                           `json:"backend_used"`
	ParserVersion string                           `json:"parser_version"`
	TierRequested string                           `json:"tier_requested,omitempty"`
	TierEffective string                           `json:"tier_effective,omitempty"`
	WebEquivalent bool                             `json:"web_equivalent"`
	Route         string                           `json:"route"`
	Dependencies  []localparser.ExternalDependency `json:"external_dependencies,omitempty"`
}

func main() {
	if len(os.Args) < 2 || (os.Args[1] != "parse" && os.Args[1] != "plan") {
		fmt.Fprintln(os.Stderr, "usage: local-matrixflow-parser <parse|plan> --input FILE [--pipeline local|precision|agent|vlm] [--run DIR] [--type TYPE] [--profile web-default|v3-native]")
		os.Exit(2)
	}
	var err error
	if os.Args[1] == "plan" {
		err = runPlan(os.Args[2:])
	} else {
		err = runParse(os.Args[2:])
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, "error:", err)
		os.Exit(1)
	}
}

func runParse(args []string) error {
	fs := flag.NewFlagSet("parse", flag.ContinueOnError)
	var input, runRoot, fileType, pageSelector, profile, pipeline string
	var envFile, tokenEnv, minerUBaseURL string
	var openXMLBaseURL, sofficeBinary, docxGeometryAligner, vlmProvider, vlmAPIKeyEnv, vlmBaseURL, vlmModel string
	var minerUPollInterval, minerUTimeout time.Duration
	var debug, imageOCR, imageCaption bool
	fs.StringVar(&input, "input", "", "local document path")
	fs.StringVar(&runRoot, "run", "runs/local-native", "artifact root; each invocation creates a timestamped child directory")
	fs.StringVar(&fileType, "type", "", "file type override")
	fs.StringVar(&profile, "profile", localparser.ProfileWebDefault, "web-default or v3-native")
	fs.StringVar(&pipeline, "pipeline", localparser.PipelineLocal, "local, precision, agent, or vlm")
	fs.StringVar(&pageSelector, "page-selector", "", "optional page selector such as 1-3,5")
	fs.BoolVar(&debug, "debug", false, "request MatrixFlow parser debug artifacts")
	fs.StringVar(&envFile, "env-file", findDefaultEnvFile(), "optional .env file containing parser backend configuration")
	fs.StringVar(&tokenEnv, "mineru-token-env", "MINERU_API_TOKEN", "environment variable containing the official MinerU token")
	fs.StringVar(&minerUBaseURL, "mineru-base-url", "https://mineru.net", "official MinerU API base URL")
	fs.DurationVar(&minerUPollInterval, "mineru-poll-interval", 3*time.Second, "MinerU result polling interval")
	fs.DurationVar(&minerUTimeout, "mineru-timeout", 15*time.Minute, "overall MinerU parsing timeout")
	fs.StringVar(&openXMLBaseURL, "openxml-base-url", "", "OpenXML service base URL; defaults to OPENXML_BASE_URL")
	fs.StringVar(&sofficeBinary, "soffice-bin", "", "soffice executable; defaults to SOFFICE_BIN or PATH")
	fs.StringVar(&docxGeometryAligner, "docx-geometry-aligner", "", "DOCX geometry aligner executable; defaults to MOI_DOCX_GEOMETRY_ALIGNER")
	fs.StringVar(&vlmProvider, "vlm-provider", "taas", "OpenAI-compatible VLM provider: taas or maas")
	fs.StringVar(&vlmAPIKeyEnv, "vlm-api-key-env", "", "environment variable containing the VLM API key; provider default when empty")
	fs.StringVar(&vlmBaseURL, "vlm-base-url", "", "OpenAI-compatible VLM base URL; provider default when empty")
	fs.StringVar(&vlmModel, "vlm-model", "", "VLM model; provider default when empty")
	fs.BoolVar(&imageOCR, "image-ocr", false, "enable VLM OCR enrichment for supported local parse routes")
	fs.BoolVar(&imageCaption, "image-caption", false, "enable VLM image caption enrichment for supported local parse routes")
	if err := fs.Parse(args); err != nil {
		return err
	}
	if strings.TrimSpace(input) == "" {
		return errors.New("--input is required")
	}
	var err error
	var minerUToken string
	if strings.EqualFold(strings.TrimSpace(pipeline), localparser.PipelinePrecision) {
		resolvedToken, resolveErr := resolveEnvValue(tokenEnv, envFile)
		if resolveErr != nil {
			return resolveErr
		}
		minerUToken = resolvedToken
	}
	if strings.TrimSpace(openXMLBaseURL) == "" {
		openXMLBaseURL, err = resolveOptionalEnvValue("OPENXML_BASE_URL", envFile)
		if err != nil {
			return err
		}
	}
	if strings.TrimSpace(sofficeBinary) == "" {
		sofficeBinary, err = resolveOptionalEnvValue("SOFFICE_BIN", envFile)
		if err != nil {
			return err
		}
	}
	if strings.TrimSpace(docxGeometryAligner) == "" {
		docxGeometryAligner, err = resolveOptionalEnvValue("MOI_DOCX_GEOMETRY_ALIGNER", envFile)
		if err != nil {
			return err
		}
	}
	if strings.TrimSpace(docxGeometryAligner) != "" {
		if err := os.Setenv("MOI_DOCX_GEOMETRY_ALIGNER", docxGeometryAligner); err != nil {
			return fmt.Errorf("configure DOCX geometry aligner: %w", err)
		}
	}
	if strings.TrimSpace(sofficeBinary) == "" {
		if detected, lookupErr := exec.LookPath("soffice"); lookupErr == nil {
			sofficeBinary = detected
		}
	}
	needsVLM := strings.EqualFold(strings.TrimSpace(pipeline), localparser.PipelineVLM) || imageOCR || imageCaption
	var vlmAPIKey string
	if needsVLM {
		providerName := strings.ToLower(strings.TrimSpace(vlmProvider))
		baseURLEnv := "TAAS_BASE_URL"
		modelEnv := "TAAS_VL_MODEL"
		if providerName == "maas" || providerName == "huawei-maas" {
			vlmProvider = "maas"
			baseURLEnv = "MAAS_BASE_URL"
			modelEnv = "MAAS_VL_MODEL"
			if strings.TrimSpace(vlmAPIKeyEnv) == "" {
				vlmAPIKeyEnv = "MAAS_API_KEY"
			}
		} else if providerName == "taas" || providerName == "matrixorigin-taas" {
			vlmProvider = "taas"
			if strings.TrimSpace(vlmAPIKeyEnv) == "" {
				vlmAPIKeyEnv = "TAAS_API_KEY"
			}
		} else {
			return fmt.Errorf("unsupported VLM provider %q", vlmProvider)
		}
		vlmAPIKey, err = resolveEnvValue(vlmAPIKeyEnv, envFile)
		if err != nil {
			return err
		}
		if strings.TrimSpace(vlmBaseURL) == "" {
			vlmBaseURL, err = resolveOptionalEnvValue(baseURLEnv, envFile)
			if err != nil {
				return err
			}
			if strings.TrimSpace(vlmBaseURL) == "" && vlmProvider == "maas" {
				vlmBaseURL = "https://api.modelarts-maas.com/v1"
			}
		}
		if strings.TrimSpace(vlmModel) == "" {
			vlmModel, err = resolveOptionalEnvValue(modelEnv, envFile)
			if err != nil {
				return err
			}
			if strings.TrimSpace(vlmModel) == "" && vlmProvider == "maas" {
				vlmModel = "qwen2.5-vl-72b"
			}
		}
	}
	runDir, err := allocateRunDir(runRoot, time.Now())
	if err != nil {
		return err
	}
	fmt.Printf("run_dir=%s\n", runDir)
	additional := map[string]any{}
	if imageOCR {
		additional["image_ocr"] = true
	}
	if imageCaption {
		additional["image_caption"] = true
	}
	result, err := localparser.New().ParseFile(context.Background(), input, localparser.Options{
		FileType:     fileType,
		Profile:      profile,
		PageSelector: pageSelector,
		Debug:        debug,
		ArtifactDir:  filepath.Join(runDir, "product-artifacts"),
		Pipeline:     pipeline,
		Additional:   additional,
		MinerU: localparser.MinerUOptions{
			Token:        minerUToken,
			BaseURL:      minerUBaseURL,
			PollInterval: minerUPollInterval,
			Timeout:      minerUTimeout,
		},
		OpenXML: localparser.OpenXMLOptions{BaseURL: openXMLBaseURL},
		VLM: localparser.VLMOptions{
			Provider: vlmProvider, APIKey: vlmAPIKey, BaseURL: vlmBaseURL, Model: vlmModel,
		},
		Soffice: localparser.SofficeOptions{Binary: sofficeBinary},
	})
	if err != nil {
		return err
	}
	if err := writeJSON(filepath.Join(runDir, "result.json"), result); err != nil {
		return err
	}
	if err := writeDocumentsJSONL(filepath.Join(runDir, "documents.jsonl"), result); err != nil {
		return err
	}
	if result.PlainText != "" {
		if err := os.WriteFile(filepath.Join(runDir, "plain-text.txt"), []byte(result.PlainText), 0o644); err != nil {
			return err
		}
	}
	blockTypes := make(map[string]int)
	contentChars := 0
	for _, document := range result.Documents {
		blockTypes[document.Type]++
		contentChars += len([]rune(document.Content))
	}
	runSummary := summary{
		SchemaVersion: result.SchemaVersion,
		Engine:        result.Engine,
		SourcePath:    result.SourcePath,
		FileType:      result.FileType,
		Documents:     len(result.Documents),
		BlockTypes:    blockTypes,
		ContentChars:  contentChars,
		DurationMS:    result.DurationMS,
		BackendUsed:   result.Metadata.BackendUsed,
		ParserVersion: result.Metadata.ParserVersion,
		TierRequested: result.Metadata.TierRequested,
		TierEffective: result.Metadata.TierEffective,
		WebEquivalent: result.Conformance.WebEquivalent,
		Route:         result.Conformance.Route,
		Dependencies:  result.Dependencies,
	}
	if err := writeJSON(filepath.Join(runDir, "summary.json"), runSummary); err != nil {
		return err
	}
	fmt.Printf("documents=%d content_chars=%d backend=%s parser=%s duration_ms=%.2f\n",
		runSummary.Documents, runSummary.ContentChars, runSummary.BackendUsed, runSummary.ParserVersion, runSummary.DurationMS)
	return nil
}

func runPlan(args []string) error {
	fs := flag.NewFlagSet("plan", flag.ContinueOnError)
	var input, fileType, profile, pipeline string
	fs.StringVar(&input, "input", "", "local document path")
	fs.StringVar(&fileType, "type", "", "file type override")
	fs.StringVar(&profile, "profile", localparser.ProfileWebDefault, "web-default or v3-native")
	fs.StringVar(&pipeline, "pipeline", localparser.PipelineLocal, "local, precision, agent, or vlm")
	if err := fs.Parse(args); err != nil {
		return err
	}
	if fileType == "" && input != "" {
		fileType = strings.TrimPrefix(strings.ToLower(filepath.Ext(input)), ".")
	}
	if fileType == "" {
		return errors.New("--input or --type is required")
	}
	plan := localparser.PlanFor(fileType, profile, nil)
	if pipeline == localparser.PipelinePrecision {
		plan = localparser.ParsePlan{Conformance: localparser.Conformance{
			Profile: "mineru-precision", Route: "mineru:/api/v4/file-urls/batch",
			Reason: "official MinerU precision API; requires MINERU_API_TOKEN",
		}, Dependencies: []localparser.ExternalDependency{{
			Name: "mineru-official", Required: true, Status: "requires_token", UsedFor: "precision cloud parsing",
		}}}
	} else if pipeline == localparser.PipelineAgent {
		plan = localparser.ParsePlan{Conformance: localparser.Conformance{
			Profile: "mineru-agent", Route: "mineru:/api/v1/agent/parse/file",
			Reason: "official token-free lightweight Agent API",
		}, Dependencies: []localparser.ExternalDependency{{
			Name: "mineru-official-agent", Required: true, Status: "public", UsedFor: "lightweight cloud parsing",
		}}}
	} else if pipeline == localparser.PipelineVLM {
		plan = localparser.ParsePlan{Conformance: localparser.Conformance{
			Profile: "taas-vlm", Route: "taas:/v1/chat/completions",
			Reason: "TaaS multimodal OCR normalized through MatrixFlow Markdown blocks",
		}, Dependencies: []localparser.ExternalDependency{{
			Name: "matrixorigin-taas-vlm", Required: true, Status: "requires_token", UsedFor: "document image OCR",
		}}}
	} else if pipeline != localparser.PipelineLocal {
		return fmt.Errorf("unknown parser pipeline %q", pipeline)
	}
	raw, err := json.MarshalIndent(plan, "", "  ")
	if err != nil {
		return err
	}
	fmt.Println(string(raw))
	return nil
}

func allocateRunDir(root string, now time.Time) (string, error) {
	root = filepath.Clean(strings.TrimSpace(root))
	if root == "." {
		return "", errors.New("run artifact root must not be empty")
	}
	if err := os.MkdirAll(root, 0o755); err != nil {
		return "", err
	}
	stamp := now.Format("20060102-150405.000")
	for sequence := 0; ; sequence++ {
		name := stamp
		if sequence > 0 {
			name += fmt.Sprintf("-%02d", sequence)
		}
		candidate := filepath.Join(root, name)
		err := os.Mkdir(candidate, 0o755)
		if err == nil {
			return candidate, nil
		}
		if !errors.Is(err, os.ErrExist) {
			return "", err
		}
	}
}

func writeJSON(path string, value any) error {
	raw, err := json.MarshalIndent(value, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, append(raw, '\n'), 0o644)
}

func writeDocumentsJSONL(path string, result *localparser.Result) error {
	var builder strings.Builder
	for _, document := range result.Documents {
		raw, err := json.Marshal(document)
		if err != nil {
			return err
		}
		builder.Write(raw)
		builder.WriteByte('\n')
	}
	return os.WriteFile(path, []byte(builder.String()), 0o644)
}
