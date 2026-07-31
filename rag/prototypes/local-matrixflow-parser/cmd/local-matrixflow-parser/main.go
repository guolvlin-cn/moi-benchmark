package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"os"
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
		fmt.Fprintln(os.Stderr, "usage: local-matrixflow-parser <parse|plan> --input FILE [--run DIR] [--type TYPE] [--profile web-default|v3-native]")
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
	var input, runRoot, fileType, pageSelector, profile string
	var debug bool
	fs.StringVar(&input, "input", "", "local document path")
	fs.StringVar(&runRoot, "run", "runs/local-native", "artifact root; each invocation creates a timestamped child directory")
	fs.StringVar(&fileType, "type", "", "file type override")
	fs.StringVar(&profile, "profile", localparser.ProfileWebDefault, "web-default or v3-native")
	fs.StringVar(&pageSelector, "page-selector", "", "optional page selector such as 1-3,5")
	fs.BoolVar(&debug, "debug", false, "request MatrixFlow parser debug artifacts")
	if err := fs.Parse(args); err != nil {
		return err
	}
	if strings.TrimSpace(input) == "" {
		return errors.New("--input is required")
	}
	runDir, err := allocateRunDir(runRoot, time.Now())
	if err != nil {
		return err
	}
	fmt.Printf("run_dir=%s\n", runDir)
	result, err := localparser.New().ParseFile(context.Background(), input, localparser.Options{
		FileType:     fileType,
		Profile:      profile,
		PageSelector: pageSelector,
		Debug:        debug,
		ArtifactDir:  filepath.Join(runDir, "product-artifacts"),
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
	var input, fileType, profile string
	fs.StringVar(&input, "input", "", "local document path")
	fs.StringVar(&fileType, "type", "", "file type override")
	fs.StringVar(&profile, "profile", localparser.ProfileWebDefault, "web-default or v3-native")
	if err := fs.Parse(args); err != nil {
		return err
	}
	if fileType == "" && input != "" {
		fileType = strings.TrimPrefix(strings.ToLower(filepath.Ext(input)), ".")
	}
	if fileType == "" {
		return errors.New("--input or --type is required")
	}
	raw, err := json.MarshalIndent(localparser.PlanFor(fileType, profile, nil), "", "  ")
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
