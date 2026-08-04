package main

import (
	"bytes"
	"context"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"math"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"
	"unicode"

	_ "github.com/go-sql-driver/mysql"
	mysqlDriver "github.com/go-sql-driver/mysql"
	"github.com/matrixflow/moi-core/agent-tools/knowledge"
	knowledgeservice "github.com/matrixflow/moi-core/agent-tools/knowledge/service"
)

const (
	schemaVersion     = "matrixflow-product-rag-local-v2"
	taasAPIBaseURL    = "https://api-taas.moi.matrixorigin.cn/v1"
	taasAPIKeyEnvName = "TAAS_API_KEY"
)

var identifierPattern = regexp.MustCompile(`^[A-Za-z_][A-Za-z0-9_]*$`)

type Config struct {
	MatrixOne      MatrixOneConfig  `json:"matrixone"`
	Workspace      string           `json:"workspace_id"`
	MatrixFlowRoot string           `json:"matrixflow_root,omitempty"`
	ChunkSize      int              `json:"chunk_size"`
	Overlap        int              `json:"chunk_overlap"`
	SectionSize    int              `json:"section_size"`
	Embedding      EndpointConfig   `json:"embedding"`
	Generation     GenerationConfig `json:"generation"`
}

type MatrixOneConfig struct {
	DSN         string `json:"dsn"`
	Database    string `json:"database"`
	VectorTable string `json:"vector_table"`
}

type EndpointConfig struct {
	Mode           string `json:"mode"`
	BaseURL        string `json:"base_url"`
	Model          string `json:"model"`
	APIKeyEnv      string `json:"api_key_env"`
	Dimension      int    `json:"dimension"`
	TimeoutSeconds int    `json:"timeout_seconds"`
}

type GenerationConfig struct {
	Enabled        bool   `json:"enabled"`
	Provider       string `json:"provider"`
	BaseURL        string `json:"base_url"`
	Model          string `json:"model"`
	APIKeyEnv      string `json:"api_key_env"`
	TimeoutSeconds int    `json:"timeout_seconds"`
}

type SourceDocument struct {
	FileID string `json:"file_id"`
	Path   string `json:"path"`
	SHA256 string `json:"sha256"`
	Text   string `json:"-"`
}

type IndexedChunk struct {
	ID         string         `json:"id"`
	FileID     string         `json:"file_id"`
	FileName   string         `json:"file_name"`
	Index      int            `json:"chunk_index"`
	Start      int            `json:"start_offset"`
	End        int            `json:"end_offset"`
	Content    string         `json:"content"`
	Embedding  []float64      `json:"-"`
	Metadata   map[string]any `json:"-"`
	IndexVer   int64          `json:"index_version"`
	ContentSHA string         `json:"sha256"`
	Level      string         `json:"level"`
	DocID      string         `json:"doc_id,omitempty"`
	SectionID  string         `json:"section_id,omitempty"`
}

type IngestState struct {
	SchemaVersion  string           `json:"schema_version"`
	CreatedAt      string           `json:"created_at"`
	Database       string           `json:"database"`
	VectorTable    string           `json:"vector_table"`
	EmbeddingModel string           `json:"embedding_model"`
	Dimension      int              `json:"embedding_dimension"`
	Documents      []SourceDocument `json:"documents"`
	Chunks         []IndexedChunk   `json:"chunks"`
}

type QuestionCase struct {
	ID                     string   `json:"id"`
	Question               string   `json:"question"`
	RetrievalKeywords      []string `json:"retrieval_keywords"`
	RelevantDocuments      []string `json:"relevant_documents"`
	RelevantEvidence       []string `json:"relevant_evidence"`
	ExpectedAnswerKeywords []string `json:"expected_answer_keywords"`
	ExpectedAnswerable     *bool    `json:"expected_answerable,omitempty"`
}

type ChunkResult struct {
	Rank            int      `json:"rank"`
	ChunkID         string   `json:"chunk_id"`
	FileID          string   `json:"file_id"`
	FileName        string   `json:"file_name"`
	PageNumber      int      `json:"page_number,omitempty"`
	Score           float64  `json:"score"`
	Routes          []string `json:"routes"`
	Content         string   `json:"content"`
	SemanticModelID int64    `json:"semantic_model_id,omitempty"`
}

type CaseMetrics struct {
	SourceRecall          float64            `json:"source_recall"`
	EvidenceRecall        float64            `json:"evidence_recall"`
	ReciprocalRank        float64            `json:"reciprocal_rank"`
	RecallAtK             map[string]float64 `json:"source_recall_at_k"`
	AnswerabilityAccuracy *float64           `json:"answerability_accuracy,omitempty"`
	AnswerKeywordScore    *float64           `json:"answer_keyword_recall,omitempty"`
}

type RunResult struct {
	Case               QuestionCase       `json:"case"`
	Repeat             int                `json:"repeat"`
	StartedAt          string             `json:"started_at"`
	EndedAt            string             `json:"ended_at"`
	Status             string             `json:"status"`
	RetrievalLatencyMS float64            `json:"retrieval_latency_ms"`
	StageLatencyMS     map[string]float64 `json:"stage_latency_ms"`
	GenerationLatency  *float64           `json:"generation_latency_ms,omitempty"`
	Routes             []string           `json:"routes"`
	EmbeddingModel     string             `json:"embedding_model"`
	Chunks             []ChunkResult      `json:"chunks"`
	Answer             string             `json:"answer,omitempty"`
	Metrics            CaseMetrics        `json:"metrics"`
	Error              string             `json:"error,omitempty"`
}

type Summary struct {
	SchemaVersion             string             `json:"schema_version"`
	CreatedAt                 string             `json:"created_at"`
	Attempts                  int                `json:"attempts"`
	SuccessfulAttempts        int                `json:"successful_attempts"`
	MeanSourceRecall          float64            `json:"mean_source_recall"`
	MeanEvidenceRecall        float64            `json:"mean_evidence_recall"`
	MeanReciprocalRank        float64            `json:"mean_reciprocal_rank"`
	MeanAnswerabilityAccuracy *float64           `json:"mean_answerability_accuracy,omitempty"`
	MeanAnswerKeywordRecall   *float64           `json:"mean_answer_keyword_recall,omitempty"`
	RetrievalLatencyMeanMS    float64            `json:"retrieval_latency_mean_ms"`
	RetrievalLatencyP50MS     float64            `json:"retrieval_latency_p50_ms"`
	RetrievalLatencyP95MS     float64            `json:"retrieval_latency_p95_ms"`
	StageLatencyMeanMS        map[string]float64 `json:"stage_latency_mean_ms"`
	StageLatencyP95MS         map[string]float64 `json:"stage_latency_p95_ms"`
	GenerationLatencyMeanMS   *float64           `json:"generation_latency_mean_ms,omitempty"`
	GenerationLatencyP95MS    *float64           `json:"generation_latency_p95_ms,omitempty"`
}

type openAIEmbeddingClient struct {
	config EndpointConfig
	client *http.Client
}

type hashEmbeddingClient struct {
	dimension int
}

type matrixOneExecutor struct {
	db *sql.DB
}

type timingRecorder struct {
	mu     sync.Mutex
	values map[string]time.Duration
}

type timedSQLExecutor struct {
	next     knowledge.SQLExecutor
	recorder *timingRecorder
}

type timedEmbeddingService struct {
	next     knowledge.EmbeddingService
	recorder *timingRecorder
}

func main() {
	if len(os.Args) < 2 {
		usage()
		os.Exit(2)
	}
	var err error
	switch os.Args[1] {
	case "ingest":
		err = ingestCommand(os.Args[2:])
	case "run":
		err = runCommand(os.Args[2:])
	case "pipeline":
		err = pipelineCommand(os.Args[2:])
	case "ask":
		err = askCommand(os.Args[2:])
	case "check":
		err = checkCommand(os.Args[2:])
	default:
		usage()
		os.Exit(2)
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, "error:", err)
		os.Exit(1)
	}
}

func usage() {
	fmt.Fprintln(os.Stderr, "usage: local-matrixflow-rag <check|ingest|run|ask|pipeline> [flags]")
}

type commonFlags struct {
	configPath string
	runDir     string
}

func addCommonFlags(fs *flag.FlagSet, common *commonFlags) {
	fs.StringVar(&common.configPath, "config", "config.local.json", "benchmark configuration JSON")
	fs.StringVar(&common.runDir, "run", "runs/local-product-rag", "artifact root; each invocation creates a timestamped child directory")
}

func ingestCommand(args []string) error {
	fs := flag.NewFlagSet("ingest", flag.ContinueOnError)
	var common commonFlags
	var source, documents string
	var force bool
	addCommonFlags(fs, &common)
	fs.StringVar(&source, "source", "data/documents", "document directory")
	fs.StringVar(&documents, "documents", "", "MatrixFlow parser documents.jsonl; when set, --source is ignored")
	fs.BoolVar(&force, "force", false, "replace all rows in the benchmark vector table")
	if err := fs.Parse(args); err != nil {
		return err
	}
	cfg, err := loadConfig(common.configPath)
	if err != nil {
		return err
	}
	runDir, err := allocateRunDir(common.runDir, time.Now())
	if err != nil {
		return err
	}
	fmt.Printf("run_dir=%s\n", runDir)
	if strings.TrimSpace(documents) != "" {
		_, err = ingestParsedDocuments(context.Background(), cfg, documents, runDir, force)
	} else {
		_, err = ingestCorpus(context.Background(), cfg, source, runDir, force)
	}
	return err
}

func runCommand(args []string) error {
	fs := flag.NewFlagSet("run", flag.ContinueOnError)
	var common commonFlags
	var dataset string
	var repeats, maxHits int
	addCommonFlags(fs, &common)
	fs.StringVar(&dataset, "dataset", "data/questions.jsonl", "question dataset JSONL")
	fs.IntVar(&repeats, "repeats", 1, "repeats per question")
	fs.IntVar(&maxHits, "max-hits", 10, "candidate hits per keyword and route")
	if err := fs.Parse(args); err != nil {
		return err
	}
	cfg, err := loadConfig(common.configPath)
	if err != nil {
		return err
	}
	runDir, err := allocateRunDir(common.runDir, time.Now())
	if err != nil {
		return err
	}
	fmt.Printf("run_dir=%s\n", runDir)
	return runDataset(context.Background(), cfg, dataset, runDir, repeats, maxHits)
}

func askCommand(args []string) error {
	fs := flag.NewFlagSet("ask", flag.ContinueOnError)
	var common commonFlags
	var question string
	addCommonFlags(fs, &common)
	fs.StringVar(&question, "question", "", "knowledge-base question")
	if err := fs.Parse(args); err != nil {
		return err
	}
	if strings.TrimSpace(question) == "" {
		return errors.New("--question is required")
	}
	cfg, err := loadConfig(common.configPath)
	if err != nil {
		return err
	}
	runDir, err := allocateRunDir(common.runDir, time.Now())
	if err != nil {
		return err
	}
	fmt.Printf("run_dir=%s\n", runDir)
	result, err := runExploreQuestion(context.Background(), cfg, question)
	if err != nil {
		return err
	}
	if err := writeJSON(filepath.Join(runDir, "answer.json"), result); err != nil {
		return err
	}
	fmt.Println(result.Answer)
	return nil
}

func pipelineCommand(args []string) error {
	fs := flag.NewFlagSet("pipeline", flag.ContinueOnError)
	var common commonFlags
	var source, documents, dataset string
	var repeats, maxHits int
	var force bool
	addCommonFlags(fs, &common)
	fs.StringVar(&source, "source", "data/documents", "document directory")
	fs.StringVar(&documents, "documents", "", "MatrixFlow parser documents.jsonl; when set, --source is ignored")
	fs.StringVar(&dataset, "dataset", "data/questions.jsonl", "question dataset JSONL")
	fs.IntVar(&repeats, "repeats", 1, "repeats per question")
	fs.IntVar(&maxHits, "max-hits", 10, "candidate hits per keyword and route")
	fs.BoolVar(&force, "force", false, "replace all rows in the benchmark vector table")
	if err := fs.Parse(args); err != nil {
		return err
	}
	cfg, err := loadConfig(common.configPath)
	if err != nil {
		return err
	}
	runDir, err := allocateRunDir(common.runDir, time.Now())
	if err != nil {
		return err
	}
	fmt.Printf("run_dir=%s\n", runDir)
	if strings.TrimSpace(documents) != "" {
		if _, err := ingestParsedDocuments(context.Background(), cfg, documents, runDir, force); err != nil {
			return err
		}
	} else {
		if _, err := ingestCorpus(context.Background(), cfg, source, runDir, force); err != nil {
			return err
		}
	}
	return runDataset(context.Background(), cfg, dataset, runDir, repeats, maxHits)
}

func allocateRunDir(root string, now time.Time) (string, error) {
	root = filepath.Clean(strings.TrimSpace(root))
	if root == "." {
		return "", errors.New("run artifact root must not be empty")
	}
	if err := os.MkdirAll(root, 0o755); err != nil {
		return "", fmt.Errorf("create run artifact root: %w", err)
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
			return "", fmt.Errorf("create run artifact directory: %w", err)
		}
	}
}

func checkCommand(args []string) error {
	fs := flag.NewFlagSet("check", flag.ContinueOnError)
	var configPath string
	fs.StringVar(&configPath, "config", "config.local.json", "benchmark configuration JSON")
	if err := fs.Parse(args); err != nil {
		return err
	}
	cfg, err := loadConfig(configPath)
	if err != nil {
		return err
	}
	embedder, err := newEmbedder(cfg.Embedding)
	if err != nil {
		return err
	}
	vectors, err := embedder.CreateEmbedding(context.Background(), cfg.Workspace, cfg.Embedding.Model, []string{"MatrixFlow RAG health check"})
	if err != nil {
		return fmt.Errorf("embedding check: %w", err)
	}
	if len(vectors) != 1 || len(vectors[0]) == 0 {
		return errors.New("embedding check returned an empty vector")
	}
	db, err := openBenchmarkDB(context.Background(), cfg, len(vectors[0]), false)
	if err != nil {
		return err
	}
	defer db.Close()
	fmt.Printf("ok database=%s table=%s embedding_dimension=%d\n", cfg.MatrixOne.Database, cfg.MatrixOne.VectorTable, len(vectors[0]))
	return nil
}

func loadConfig(path string) (Config, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return Config{}, fmt.Errorf("read config: %w", err)
	}
	var cfg Config
	if err := json.Unmarshal(raw, &cfg); err != nil {
		return Config{}, fmt.Errorf("decode config: %w", err)
	}
	if cfg.Workspace == "" {
		cfg.Workspace = "local-rag-benchmark"
	}
	if cfg.MatrixFlowRoot == "" {
		cfg.MatrixFlowRoot = filepath.Clean("../../../../matrixflow")
	}
	if cfg.ChunkSize <= 0 {
		cfg.ChunkSize = 512
	}
	if cfg.Overlap == 0 {
		cfg.Overlap = 50
	}
	if cfg.Overlap < 0 || cfg.Overlap >= cfg.ChunkSize {
		return Config{}, errors.New("chunk_overlap must be >= 0 and smaller than chunk_size")
	}
	if cfg.SectionSize <= 0 {
		cfg.SectionSize = 5
	}
	if cfg.MatrixOne.DSN == "" || cfg.MatrixOne.Database == "" || cfg.MatrixOne.VectorTable == "" {
		return Config{}, errors.New("matrixone.dsn, database, and vector_table are required")
	}
	if !identifierPattern.MatchString(cfg.MatrixOne.Database) || !identifierPattern.MatchString(cfg.MatrixOne.VectorTable) {
		return Config{}, errors.New("database and vector_table must be simple SQL identifiers")
	}
	if cfg.Embedding.Mode == "" {
		cfg.Embedding.Mode = "openai"
	}
	if cfg.Embedding.Model == "" {
		cfg.Embedding.Model = "bge-m3"
	}
	if strings.EqualFold(cfg.Embedding.Mode, "taas") {
		if cfg.Embedding.BaseURL == "" {
			cfg.Embedding.BaseURL = taasAPIBaseURL
		}
		if cfg.Embedding.APIKeyEnv == "" {
			cfg.Embedding.APIKeyEnv = taasAPIKeyEnvName
		}
	}
	if cfg.Embedding.Dimension <= 0 {
		if strings.EqualFold(cfg.Embedding.Mode, "hash") {
			cfg.Embedding.Dimension = 256
		} else {
			return Config{}, errors.New("embedding.dimension must be positive")
		}
	}
	if cfg.Embedding.TimeoutSeconds <= 0 {
		cfg.Embedding.TimeoutSeconds = 60
	}
	if cfg.Generation.TimeoutSeconds <= 0 {
		cfg.Generation.TimeoutSeconds = 120
	}
	if strings.EqualFold(cfg.Generation.Provider, "taas") {
		if cfg.Generation.BaseURL == "" {
			cfg.Generation.BaseURL = taasAPIBaseURL
		}
		if cfg.Generation.APIKeyEnv == "" {
			cfg.Generation.APIKeyEnv = taasAPIKeyEnvName
		}
	}
	return cfg, nil
}

func ingestCorpus(ctx context.Context, cfg Config, sourceDir, runDir string, force bool) (*IngestState, error) {
	documents, err := loadDocuments(sourceDir)
	if err != nil {
		return nil, err
	}
	chunks := make([]IndexedChunk, 0)
	for _, document := range documents {
		for index, part := range chunkText(document.Text, cfg.ChunkSize, cfg.Overlap) {
			id := stableID("chunk", document.FileID+"\x00"+strconv.Itoa(index)+"\x00"+part.Content)
			chunks = append(chunks, IndexedChunk{
				ID:         id,
				FileID:     document.FileID,
				FileName:   document.Path,
				Index:      index,
				Start:      part.Start,
				End:        part.End,
				Content:    part.Content,
				IndexVer:   1,
				ContentSHA: sha256Text(part.Content),
				Level:      "chunk",
				DocID:      document.FileID,
				SectionID:  document.FileID,
				Metadata: map[string]any{
					"chunk_id":          id,
					"source_file_name":  document.Path,
					"source_uri":        "benchmark://" + document.Path,
					"parent_index":      index,
					"chunk_start":       part.Start,
					"chunk_end":         part.End,
					"chunk_index_scope": "document",
				},
			})
		}
	}
	embedder, err := newEmbedder(cfg.Embedding)
	if err != nil {
		return nil, err
	}
	const batchSize = 32
	for start := 0; start < len(chunks); start += batchSize {
		end := min(start+batchSize, len(chunks))
		inputs := make([]string, 0, end-start)
		for _, chunk := range chunks[start:end] {
			inputs = append(inputs, chunk.Content)
		}
		vectors, err := embedder.CreateEmbedding(ctx, cfg.Workspace, cfg.Embedding.Model, inputs)
		if err != nil {
			return nil, fmt.Errorf("embed chunks %d:%d: %w", start, end, err)
		}
		if len(vectors) != len(inputs) {
			return nil, fmt.Errorf("embedding count mismatch: got %d want %d", len(vectors), len(inputs))
		}
		for i := range vectors {
			chunks[start+i].Embedding = vectors[i]
		}
	}
	if len(chunks) == 0 || len(chunks[0].Embedding) == 0 {
		return nil, errors.New("corpus produced no embedded chunks")
	}
	dimension := len(chunks[0].Embedding)
	for _, chunk := range chunks {
		if len(chunk.Embedding) != dimension {
			return nil, errors.New("embedding dimension changed within one ingest")
		}
	}
	db, err := openBenchmarkDB(ctx, cfg, dimension, force)
	if err != nil {
		return nil, err
	}
	defer db.Close()
	if err := writeChunks(ctx, db, cfg.MatrixOne.VectorTable, chunks); err != nil {
		return nil, err
	}
	state := &IngestState{
		SchemaVersion:  schemaVersion,
		CreatedAt:      time.Now().UTC().Format(time.RFC3339),
		Database:       cfg.MatrixOne.Database,
		VectorTable:    cfg.MatrixOne.VectorTable,
		EmbeddingModel: cfg.Embedding.Model,
		Dimension:      dimension,
		Documents:      documents,
		Chunks:         chunks,
	}
	if err := writeJSON(filepath.Join(runDir, "ingest-state.json"), state); err != nil {
		return nil, err
	}
	fmt.Printf("ingested documents=%d chunks=%d dimension=%d\n", len(documents), len(chunks), dimension)
	return state, nil
}

type textChunk struct {
	Start, End int
	Content    string
}

func chunkText(text string, size, overlap int) []textChunk {
	runes := []rune(text)
	if len(runes) == 0 {
		return nil
	}
	step := size - overlap
	var out []textChunk
	for start := 0; start < len(runes); start += step {
		end := min(start+size, len(runes))
		content := strings.TrimSpace(string(runes[start:end]))
		if content != "" {
			out = append(out, textChunk{Start: start, End: end, Content: content})
		}
		if end == len(runes) {
			break
		}
	}
	return out
}

func loadDocuments(root string) ([]SourceDocument, error) {
	var documents []SourceDocument
	err := filepath.WalkDir(root, func(path string, entry os.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if entry.IsDir() {
			return nil
		}
		ext := strings.ToLower(filepath.Ext(entry.Name()))
		if ext != ".md" && ext != ".txt" {
			return nil
		}
		raw, err := os.ReadFile(path)
		if err != nil {
			return err
		}
		text := strings.TrimSpace(string(raw))
		if text == "" {
			return nil
		}
		relative, err := filepath.Rel(root, path)
		if err != nil {
			return err
		}
		relative = filepath.ToSlash(relative)
		documents = append(documents, SourceDocument{
			FileID: stableID("file", relative),
			Path:   relative,
			SHA256: sha256Text(text),
			Text:   text,
		})
		return nil
	})
	if err != nil {
		return nil, fmt.Errorf("load documents: %w", err)
	}
	sort.Slice(documents, func(i, j int) bool { return documents[i].Path < documents[j].Path })
	if len(documents) == 0 {
		return nil, fmt.Errorf("no non-empty .md or .txt documents under %s", root)
	}
	return documents, nil
}

func newEmbedder(cfg EndpointConfig) (knowledge.EmbeddingService, error) {
	switch strings.ToLower(strings.TrimSpace(cfg.Mode)) {
	case "hash":
		if cfg.Dimension <= 0 {
			cfg.Dimension = 256
		}
		return hashEmbeddingClient{dimension: cfg.Dimension}, nil
	case "openai", "taas":
		if cfg.BaseURL == "" || cfg.Model == "" {
			return nil, fmt.Errorf("%s embedding mode requires base_url and model", cfg.Mode)
		}
		return &openAIEmbeddingClient{
			config: cfg,
			client: &http.Client{Timeout: time.Duration(cfg.TimeoutSeconds) * time.Second},
		}, nil
	default:
		return nil, fmt.Errorf("unsupported embedding mode %q", cfg.Mode)
	}
}

func (c *openAIEmbeddingClient) CreateEmbedding(ctx context.Context, _ string, model string, texts []string) ([][]float64, error) {
	if model == "" {
		model = c.config.Model
	}
	payload := map[string]any{"model": model, "input": texts, "encoding_format": "float"}
	var response struct {
		Data []struct {
			Index     int       `json:"index"`
			Embedding []float64 `json:"embedding"`
		} `json:"data"`
	}
	if err := postOpenAIJSON(ctx, c.client, c.config.BaseURL, "/embeddings", c.config.APIKeyEnv, payload, &response); err != nil {
		return nil, err
	}
	out := make([][]float64, len(texts))
	for _, item := range response.Data {
		if item.Index < 0 || item.Index >= len(out) {
			return nil, fmt.Errorf("embedding response index %d out of range", item.Index)
		}
		out[item.Index] = item.Embedding
	}
	for i, embedding := range out {
		if len(embedding) == 0 {
			return nil, fmt.Errorf("embedding response missing index %d", i)
		}
	}
	return out, nil
}

func (c hashEmbeddingClient) CreateEmbedding(_ context.Context, _, _ string, texts []string) ([][]float64, error) {
	out := make([][]float64, 0, len(texts))
	for _, text := range texts {
		vector := make([]float64, c.dimension)
		for _, token := range tokenize(text) {
			digest := sha256.Sum256([]byte(token))
			index := int(digest[0])<<8 | int(digest[1])
			sign := 1.0
			if digest[2]&1 == 1 {
				sign = -1
			}
			vector[index%c.dimension] += sign
		}
		var norm float64
		for _, value := range vector {
			norm += value * value
		}
		if norm > 0 {
			norm = math.Sqrt(norm)
			for i := range vector {
				vector[i] /= norm
			}
		}
		out = append(out, vector)
	}
	return out, nil
}

func tokenize(text string) []string {
	text = strings.ToLower(text)
	var tokens []string
	var current []rune
	flush := func() {
		if len(current) > 0 {
			tokens = append(tokens, string(current))
			current = nil
		}
	}
	var han []rune
	flushHan := func() {
		if len(han) == 1 {
			tokens = append(tokens, string(han))
		} else if len(han) > 1 {
			for i := 0; i < len(han)-1; i++ {
				tokens = append(tokens, string(han[i:i+2]))
			}
		}
		han = nil
	}
	for _, r := range text {
		switch {
		case unicode.In(r, unicode.Han):
			flush()
			han = append(han, r)
		case unicode.IsLetter(r) || unicode.IsDigit(r):
			flushHan()
			current = append(current, r)
		default:
			flush()
			flushHan()
		}
	}
	flush()
	flushHan()
	return tokens
}

func openBenchmarkDB(ctx context.Context, cfg Config, dimension int, rebuild bool) (*sql.DB, error) {
	if dimension <= 0 {
		return nil, fmt.Errorf("embedding dimension must be positive, got %d", dimension)
	}
	parsed, err := mysqlDriver.ParseDSN(cfg.MatrixOne.DSN)
	if err != nil {
		return nil, fmt.Errorf("parse MatrixOne DSN: %w", err)
	}
	parsed.DBName = ""
	admin, err := sql.Open("mysql", parsed.FormatDSN())
	if err != nil {
		return nil, err
	}
	if err := admin.PingContext(ctx); err != nil {
		admin.Close()
		return nil, fmt.Errorf("connect MatrixOne: %w", err)
	}
	if _, err := admin.ExecContext(ctx, "CREATE DATABASE IF NOT EXISTS `"+cfg.MatrixOne.Database+"`"); err != nil {
		admin.Close()
		return nil, fmt.Errorf("create benchmark database: %w", err)
	}
	admin.Close()
	parsed.DBName = cfg.MatrixOne.Database
	db, err := sql.Open("mysql", parsed.FormatDSN())
	if err != nil {
		return nil, err
	}
	if err := db.PingContext(ctx); err != nil {
		db.Close()
		return nil, fmt.Errorf("connect benchmark database: %w", err)
	}
	table := "`" + cfg.MatrixOne.VectorTable + "`"
	if rebuild {
		if _, err := db.ExecContext(ctx, "DROP TABLE IF EXISTS "+table); err != nil {
			db.Close()
			return nil, fmt.Errorf("rebuild vector table: %w", err)
		}
	}
	createSQL := fmt.Sprintf(`CREATE TABLE IF NOT EXISTS %s (
  id VARCHAR(128) PRIMARY KEY,
  embedding VECF64(%d),
  content TEXT,
  meta JSON,
  file_id VARCHAR(128),
  volume_id VARCHAR(128),
  page_number INT,
  level VARCHAR(16) DEFAULT 'chunk',
  doc_id VARCHAR(64),
  section_id VARCHAR(64),
  chunk_index INT,
  index_version BIGINT DEFAULT 0,
  disabled TINYINT(1) DEFAULT 0,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_file_id (file_id),
  INDEX idx_level (level),
  INDEX idx_chunk_index (chunk_index),
  FULLTEXT KEY idx_content_ft (content)
)`, table, dimension)
	if _, err := db.ExecContext(ctx, createSQL); err != nil {
		db.Close()
		return nil, fmt.Errorf("create product-compatible vector table: %w", err)
	}
	if err := ensureVectorIndex(ctx, db, cfg.MatrixOne.VectorTable); err != nil {
		db.Close()
		return nil, err
	}
	return db, nil
}

func ensureVectorIndex(ctx context.Context, db *sql.DB, table string) error {
	const indexName = "idx_embedding_cos"
	var count int
	err := db.QueryRowContext(ctx, `SELECT COUNT(*) FROM information_schema.statistics
WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = ?
  AND COLUMN_NAME = 'embedding' AND LOWER(INDEX_TYPE) = 'ivfflat'`, table).Scan(&count)
	if err != nil {
		return fmt.Errorf("inspect vector index: %w", err)
	}
	if count > 0 {
		return nil
	}
	query := fmt.Sprintf(`CREATE INDEX %s
USING ivfflat ON %s (embedding)
LISTS = 256 OP_TYPE 'vector_cosine_ops'`, indexName, "`"+table+"`")
	if _, err := db.ExecContext(ctx, query); err != nil {
		message := strings.ToLower(err.Error())
		if strings.Contains(message, "already exists") || strings.Contains(message, "duplicate") ||
			(strings.Contains(message, "multiple ivfflat") && strings.Contains(message, "same column")) {
			return nil
		}
		return fmt.Errorf("create MatrixFlow-compatible vector index: %w", err)
	}
	return nil
}

func writeChunks(ctx context.Context, db *sql.DB, table string, chunks []IndexedChunk) error {
	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer tx.Rollback()
	query := fmt.Sprintf(`INSERT INTO %s
  (id, embedding, content, meta, file_id, level, doc_id, section_id, chunk_index, index_version, disabled)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)`, "`"+table+"`")
	stmt, err := tx.PrepareContext(ctx, query)
	if err != nil {
		return fmt.Errorf("prepare chunk insert: %w", err)
	}
	defer stmt.Close()
	fileIDs := compactStrings(chunkFileIDs(chunks))
	for _, fileID := range fileIDs {
		if _, err := tx.ExecContext(ctx, "DELETE FROM `"+table+"` WHERE file_id = ?", fileID); err != nil {
			return fmt.Errorf("remove prior chunks for file %s: %w", fileID, err)
		}
	}
	for _, chunk := range chunks {
		meta, err := json.Marshal(chunk.Metadata)
		if err != nil {
			return err
		}
		vector, err := json.Marshal(chunk.Embedding)
		if err != nil {
			return err
		}
		level := chunk.Level
		if level == "" {
			level = "chunk"
		}
		if _, err := stmt.ExecContext(ctx, chunk.ID, string(vector), chunk.Content, string(meta), chunk.FileID, level, chunk.DocID, chunk.SectionID, chunk.Index, chunk.IndexVer); err != nil {
			return fmt.Errorf("insert chunk %s: %w", chunk.ID, err)
		}
	}
	return tx.Commit()
}

func chunkFileIDs(chunks []IndexedChunk) []string {
	out := make([]string, 0, len(chunks))
	for _, chunk := range chunks {
		out = append(out, chunk.FileID)
	}
	return out
}

func (e matrixOneExecutor) ExecuteSQL(ctx context.Context, _ string, query string) (*knowledge.SQLExecutionResult, error) {
	rows, err := e.db.QueryContext(ctx, query)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	columns, err := rows.Columns()
	if err != nil {
		return nil, err
	}
	result := &knowledge.SQLExecutionResult{Columns: columns}
	for rows.Next() {
		values := make([]any, len(columns))
		pointers := make([]any, len(columns))
		for i := range values {
			pointers[i] = &values[i]
		}
		if err := rows.Scan(pointers...); err != nil {
			return nil, err
		}
		for i, value := range values {
			if raw, ok := value.([]byte); ok {
				values[i] = string(raw)
			}
		}
		result.Rows = append(result.Rows, values)
	}
	return result, rows.Err()
}

func (r *timingRecorder) reset() {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.values = make(map[string]time.Duration)
}

func (r *timingRecorder) add(stage string, elapsed time.Duration) {
	r.mu.Lock()
	defer r.mu.Unlock()
	if r.values == nil {
		r.values = make(map[string]time.Duration)
	}
	r.values[stage] += elapsed
}

func (r *timingRecorder) milliseconds() map[string]float64 {
	r.mu.Lock()
	defer r.mu.Unlock()
	values := make(map[string]float64, len(r.values))
	for stage, elapsed := range r.values {
		values[stage] = float64(elapsed.Microseconds()) / 1000
	}
	return values
}

func (e timedSQLExecutor) ExecuteSQL(ctx context.Context, workspaceID, query string) (*knowledge.SQLExecutionResult, error) {
	started := time.Now()
	result, err := e.next.ExecuteSQL(ctx, workspaceID, query)
	e.recorder.add(classifySQLStage(query), time.Since(started))
	return result, err
}

func classifySQLStage(query string) string {
	normalized := strings.ToLower(query)
	switch {
	case strings.Contains(normalized, "show columns"):
		return "schema_inspection"
	case strings.Contains(normalized, "match("):
		return "fulltext_search"
	case strings.Contains(normalized, "l2_distance"):
		return "vector_search"
	default:
		return "evidence_expansion"
	}
}

func (e timedEmbeddingService) CreateEmbedding(ctx context.Context, workspaceID, model string, texts []string) ([][]float64, error) {
	started := time.Now()
	result, err := e.next.CreateEmbedding(ctx, workspaceID, model, texts)
	e.recorder.add("embedding", time.Since(started))
	return result, err
}

func runDataset(ctx context.Context, cfg Config, datasetPath, runDir string, repeats, maxHits int) error {
	if repeats < 1 || maxHits < 1 {
		return errors.New("repeats and max-hits must be positive")
	}
	cases, err := loadQuestions(datasetPath)
	if err != nil {
		return err
	}
	embedder, err := newEmbedder(cfg.Embedding)
	if err != nil {
		return err
	}
	db, err := openBenchmarkDB(ctx, cfg, cfg.Embedding.Dimension, false)
	if err != nil {
		return err
	}
	defer db.Close()
	recorder := &timingRecorder{}
	searcher := knowledgeservice.NewSearchRAGChunks(knowledgeservice.Deps{
		SQLExecutor:            timedSQLExecutor{next: matrixOneExecutor{db: db}, recorder: recorder},
		Embedder:               timedEmbeddingService{next: embedder, recorder: recorder},
		DefaultRetrieverConfig: knowledge.RetrieverConfig{EmbeddingModel: cfg.Embedding.Model},
	})
	var results []RunResult
	for _, item := range cases {
		keywords := compactStrings(item.RetrievalKeywords)
		if len(keywords) == 0 {
			keywords = []string{item.Question}
		}
		for repeat := 1; repeat <= repeats; repeat++ {
			recorder.reset()
			started := time.Now()
			response, searchErr := searcher.Execute(ctx, knowledge.SearchRAGChunksRequest{
				Scope: knowledge.WorkspaceScope{
					WorkspaceID:    cfg.Workspace,
					DBName:         cfg.MatrixOne.Database,
					VectorTable:    cfg.MatrixOne.VectorTable,
					EmbeddingModel: cfg.Embedding.Model,
				},
				Keywards: keywords,
				MaxHits:  maxHits,
			})
			result := RunResult{
				Case:               item,
				Repeat:             repeat,
				StartedAt:          started.UTC().Format(time.RFC3339Nano),
				EndedAt:            time.Now().UTC().Format(time.RFC3339Nano),
				RetrievalLatencyMS: float64(time.Since(started).Microseconds()) / 1000,
				StageLatencyMS:     recorder.milliseconds(),
				Status:             "ok",
			}
			if searchErr != nil {
				result.Status = "failed"
				result.Error = searchErr.Error()
				result.EndedAt = time.Now().UTC().Format(time.RFC3339Nano)
				results = append(results, result)
				continue
			}
			result.Routes = response.Routes
			result.EmbeddingModel = response.EmbeddingModel
			result.Chunks = normalizeChunkResults(response.Chunks)
			result.Metrics = scoreCase(item, result.Chunks)
			if cfg.Generation.Enabled {
				generationStarted := time.Now()
				answer, generationErr := generateAnswer(ctx, cfg.Generation, item.Question, result.Chunks)
				latency := float64(time.Since(generationStarted).Microseconds()) / 1000
				result.GenerationLatency = &latency
				if generationErr != nil {
					result.Status = "failed"
					result.Error = generationErr.Error()
				} else {
					result.Answer = answer
					score := keywordRecall(answer, item.ExpectedAnswerKeywords)
					result.Metrics.AnswerKeywordScore = score
				}
			}
			result.EndedAt = time.Now().UTC().Format(time.RFC3339Nano)
			results = append(results, result)
		}
	}
	if err := writeJSONL(filepath.Join(runDir, "results.jsonl"), results); err != nil {
		return err
	}
	summary := summarize(results)
	if err := writeJSON(filepath.Join(runDir, "summary.json"), summary); err != nil {
		return err
	}
	if err := writeReport(filepath.Join(runDir, "report.md"), summary); err != nil {
		return err
	}
	fmt.Printf("attempts=%d successful=%d source_recall=%.3f evidence_recall=%.3f p95_ms=%.2f\n",
		summary.Attempts, summary.SuccessfulAttempts, summary.MeanSourceRecall, summary.MeanEvidenceRecall, summary.RetrievalLatencyP95MS)
	return nil
}

func loadQuestions(path string) ([]QuestionCase, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var cases []QuestionCase
	for index, line := range strings.Split(string(raw), "\n") {
		if strings.TrimSpace(line) == "" {
			continue
		}
		var item QuestionCase
		if err := json.Unmarshal([]byte(line), &item); err != nil {
			return nil, fmt.Errorf("decode dataset line %d: %w", index+1, err)
		}
		if strings.TrimSpace(item.ID) == "" || strings.TrimSpace(item.Question) == "" {
			return nil, fmt.Errorf("dataset line %d requires id and question", index+1)
		}
		cases = append(cases, item)
	}
	if len(cases) == 0 {
		return nil, errors.New("dataset is empty")
	}
	return cases, nil
}

func normalizeChunkResults(hits []knowledge.RAGChunkHit) []ChunkResult {
	out := make([]ChunkResult, 0, len(hits))
	for index, hit := range hits {
		out = append(out, ChunkResult{
			Rank:            index + 1,
			ChunkID:         hit.ChunkID,
			FileID:          hit.FileID,
			FileName:        hit.FileName,
			PageNumber:      hit.PageNumber,
			Score:           hit.Score,
			Routes:          hit.Routes,
			Content:         hit.Content,
			SemanticModelID: hit.SemanticModelID,
		})
	}
	return out
}

func scoreCase(item QuestionCase, chunks []ChunkResult) CaseMetrics {
	metrics := CaseMetrics{RecallAtK: map[string]float64{}}
	metrics.SourceRecall = sourceRecall(item.RelevantDocuments, chunks)
	metrics.EvidenceRecall = evidenceRecall(item.RelevantEvidence, chunks)
	metrics.ReciprocalRank = reciprocalRank(item.RelevantDocuments, chunks)
	if item.ExpectedAnswerable != nil {
		value := 0.0
		if !*item.ExpectedAnswerable && len(chunks) == 0 {
			value = 1
		}
		if *item.ExpectedAnswerable && (metrics.SourceRecall > 0 || metrics.EvidenceRecall > 0) {
			value = 1
		}
		metrics.AnswerabilityAccuracy = &value
	}
	for _, k := range []int{1, 3, 5, 10} {
		end := min(k, len(chunks))
		metrics.RecallAtK[strconv.Itoa(k)] = sourceRecall(item.RelevantDocuments, chunks[:end])
	}
	return metrics
}

func sourceRecall(expected []string, chunks []ChunkResult) float64 {
	expected = compactStrings(expected)
	if len(expected) == 0 {
		return 1
	}
	hits := map[string]struct{}{}
	for _, chunk := range chunks {
		for _, source := range expected {
			if strings.EqualFold(filepath.ToSlash(chunk.FileName), filepath.ToSlash(source)) {
				hits[strings.ToLower(source)] = struct{}{}
			}
		}
	}
	return float64(len(hits)) / float64(len(expected))
}

func evidenceRecall(expected []string, chunks []ChunkResult) float64 {
	expected = compactStrings(expected)
	if len(expected) == 0 {
		return 1
	}
	haystack := normalizeText(joinChunkContent(chunks))
	hits := 0
	for _, evidence := range expected {
		if strings.Contains(haystack, normalizeText(evidence)) {
			hits++
		}
	}
	return float64(hits) / float64(len(expected))
}

func reciprocalRank(expected []string, chunks []ChunkResult) float64 {
	if len(expected) == 0 {
		return 1
	}
	for index, chunk := range chunks {
		for _, source := range expected {
			if strings.EqualFold(filepath.ToSlash(chunk.FileName), filepath.ToSlash(source)) {
				return 1 / float64(index+1)
			}
		}
	}
	return 0
}

func generateAnswer(ctx context.Context, cfg GenerationConfig, question string, chunks []ChunkResult) (string, error) {
	if cfg.BaseURL == "" || cfg.Model == "" {
		return "", errors.New("generation enabled but base_url or model is empty")
	}
	var contextParts []string
	for _, chunk := range chunks {
		contextParts = append(contextParts, fmt.Sprintf("[source=%s chunk=%s]\n%s", chunk.FileName, chunk.ChunkID, chunk.Content))
	}
	payload := map[string]any{
		"model": cfg.Model,
		"messages": []map[string]string{
			{"role": "system", "content": "Answer only from the supplied evidence. If the evidence is insufficient, say so. Cite source filenames in square brackets."},
			{"role": "user", "content": "Question:\n" + question + "\n\nEvidence:\n" + strings.Join(contextParts, "\n\n")},
		},
		"temperature": 0,
		"stream":      false,
	}
	var response struct {
		Choices []struct {
			Message struct {
				Content string `json:"content"`
			} `json:"message"`
		} `json:"choices"`
	}
	client := &http.Client{Timeout: time.Duration(cfg.TimeoutSeconds) * time.Second}
	if err := postOpenAIJSON(ctx, client, cfg.BaseURL, "/chat/completions", cfg.APIKeyEnv, payload, &response); err != nil {
		return "", err
	}
	if len(response.Choices) == 0 {
		return "", errors.New("chat completion returned no choices")
	}
	return response.Choices[0].Message.Content, nil
}

func postOpenAIJSON(ctx context.Context, client *http.Client, baseURL, path, apiKeyEnv string, payload, output any) error {
	body, err := json.Marshal(payload)
	if err != nil {
		return err
	}
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, strings.TrimRight(baseURL, "/")+path, bytes.NewReader(body))
	if err != nil {
		return err
	}
	request.Header.Set("Content-Type", "application/json")
	if apiKeyEnv != "" {
		apiKey := strings.TrimSpace(os.Getenv(apiKeyEnv))
		if apiKey == "" {
			return fmt.Errorf("API key environment variable %s is not set", apiKeyEnv)
		}
		request.Header.Set("Authorization", "Bearer "+apiKey)
	}
	response, err := client.Do(request)
	if err != nil {
		return err
	}
	defer response.Body.Close()
	raw, err := io.ReadAll(io.LimitReader(response.Body, 8<<20))
	if err != nil {
		return err
	}
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		return fmt.Errorf("HTTP %d: %s", response.StatusCode, strings.TrimSpace(string(raw)))
	}
	if err := json.Unmarshal(raw, output); err != nil {
		return fmt.Errorf("decode HTTP response: %w", err)
	}
	return nil
}

func summarize(results []RunResult) Summary {
	summary := Summary{
		SchemaVersion: schemaVersion,
		CreatedAt:     time.Now().UTC().Format(time.RFC3339),
		Attempts:      len(results),
	}
	var sourceScores, evidenceScores, reciprocalRanks, retrievalLatencies, answerabilityScores, answerScores, generationLatencies []float64
	stageLatencies := make(map[string][]float64)
	for _, result := range results {
		retrievalLatencies = append(retrievalLatencies, result.RetrievalLatencyMS)
		for stage, latency := range result.StageLatencyMS {
			stageLatencies[stage] = append(stageLatencies[stage], latency)
		}
		if result.Status != "ok" {
			continue
		}
		summary.SuccessfulAttempts++
		sourceScores = append(sourceScores, result.Metrics.SourceRecall)
		evidenceScores = append(evidenceScores, result.Metrics.EvidenceRecall)
		reciprocalRanks = append(reciprocalRanks, result.Metrics.ReciprocalRank)
		if result.Metrics.AnswerabilityAccuracy != nil {
			answerabilityScores = append(answerabilityScores, *result.Metrics.AnswerabilityAccuracy)
		}
		if result.Metrics.AnswerKeywordScore != nil {
			answerScores = append(answerScores, *result.Metrics.AnswerKeywordScore)
		}
		if result.GenerationLatency != nil {
			generationLatencies = append(generationLatencies, *result.GenerationLatency)
		}
	}
	summary.MeanSourceRecall = mean(sourceScores)
	summary.MeanEvidenceRecall = mean(evidenceScores)
	summary.MeanReciprocalRank = mean(reciprocalRanks)
	summary.RetrievalLatencyMeanMS = mean(retrievalLatencies)
	summary.RetrievalLatencyP50MS = percentile(retrievalLatencies, 0.50)
	summary.RetrievalLatencyP95MS = percentile(retrievalLatencies, 0.95)
	summary.StageLatencyMeanMS = make(map[string]float64, len(stageLatencies))
	summary.StageLatencyP95MS = make(map[string]float64, len(stageLatencies))
	for stage, latencies := range stageLatencies {
		summary.StageLatencyMeanMS[stage] = mean(latencies)
		summary.StageLatencyP95MS[stage] = percentile(latencies, 0.95)
	}
	if len(answerabilityScores) > 0 {
		value := mean(answerabilityScores)
		summary.MeanAnswerabilityAccuracy = &value
	}
	if len(answerScores) > 0 {
		value := mean(answerScores)
		summary.MeanAnswerKeywordRecall = &value
	}
	if len(generationLatencies) > 0 {
		meanValue := mean(generationLatencies)
		p95 := percentile(generationLatencies, 0.95)
		summary.GenerationLatencyMeanMS = &meanValue
		summary.GenerationLatencyP95MS = &p95
	}
	return summary
}

func writeReport(path string, summary Summary) error {
	lines := []string{
		"# Local MatrixFlow product RAG benchmark",
		"",
		"This run executes MatrixFlow's native `SearchRAGChunks` implementation against a local MatrixOne vector table.",
		"",
		fmt.Sprintf("- Attempts: %d", summary.Attempts),
		fmt.Sprintf("- Successful attempts: %d", summary.SuccessfulAttempts),
		fmt.Sprintf("- Mean source recall: %.4f", summary.MeanSourceRecall),
		fmt.Sprintf("- Mean evidence recall: %.4f", summary.MeanEvidenceRecall),
		fmt.Sprintf("- Mean reciprocal rank: %.4f", summary.MeanReciprocalRank),
		fmt.Sprintf("- Retrieval latency mean: %.2f ms", summary.RetrievalLatencyMeanMS),
		fmt.Sprintf("- Retrieval latency P50: %.2f ms", summary.RetrievalLatencyP50MS),
		fmt.Sprintf("- Retrieval latency P95: %.2f ms", summary.RetrievalLatencyP95MS),
	}
	stages := make([]string, 0, len(summary.StageLatencyMeanMS))
	for stage := range summary.StageLatencyMeanMS {
		stages = append(stages, stage)
	}
	sort.Strings(stages)
	for _, stage := range stages {
		lines = append(lines, fmt.Sprintf("- %s latency mean / P95: %.2f / %.2f ms",
			stage, summary.StageLatencyMeanMS[stage], summary.StageLatencyP95MS[stage]))
	}
	if summary.MeanAnswerabilityAccuracy != nil {
		lines = append(lines, fmt.Sprintf("- Mean answerability accuracy: %.4f", *summary.MeanAnswerabilityAccuracy))
	}
	if summary.MeanAnswerKeywordRecall != nil {
		lines = append(lines, fmt.Sprintf("- Mean answer keyword recall: %.4f", *summary.MeanAnswerKeywordRecall))
	}
	return writeFile(path, strings.Join(lines, "\n")+"\n")
}

func keywordRecall(text string, expected []string) *float64 {
	expected = compactStrings(expected)
	if len(expected) == 0 {
		return nil
	}
	normalized := normalizeText(text)
	hits := 0
	for _, item := range expected {
		if strings.Contains(normalized, normalizeText(item)) {
			hits++
		}
	}
	value := float64(hits) / float64(len(expected))
	return &value
}

func normalizeText(value string) string {
	return strings.ToLower(strings.Join(strings.Fields(value), ""))
}

func joinChunkContent(chunks []ChunkResult) string {
	parts := make([]string, 0, len(chunks))
	for _, chunk := range chunks {
		parts = append(parts, chunk.Content)
	}
	return strings.Join(parts, "\n")
}

func compactStrings(values []string) []string {
	var out []string
	seen := map[string]struct{}{}
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value == "" {
			continue
		}
		key := strings.ToLower(value)
		if _, ok := seen[key]; ok {
			continue
		}
		seen[key] = struct{}{}
		out = append(out, value)
	}
	return out
}

func mean(values []float64) float64 {
	if len(values) == 0 {
		return 0
	}
	var total float64
	for _, value := range values {
		total += value
	}
	return total / float64(len(values))
}

func percentile(values []float64, fraction float64) float64 {
	if len(values) == 0 {
		return 0
	}
	sorted := append([]float64(nil), values...)
	sort.Float64s(sorted)
	index := int(math.Ceil(float64(len(sorted))*fraction)) - 1
	if index < 0 {
		index = 0
	}
	return sorted[index]
}

func stableID(prefix, value string) string {
	digest := sha256.Sum256([]byte(value))
	return prefix + "_" + hex.EncodeToString(digest[:8])
}

func sha256Text(value string) string {
	digest := sha256.Sum256([]byte(value))
	return hex.EncodeToString(digest[:])
}

func writeJSON(path string, value any) error {
	raw, err := json.MarshalIndent(value, "", "  ")
	if err != nil {
		return err
	}
	return writeFile(path, string(raw)+"\n")
}

func writeJSONL(path string, values []RunResult) error {
	var builder strings.Builder
	for _, value := range values {
		raw, err := json.Marshal(value)
		if err != nil {
			return err
		}
		builder.Write(raw)
		builder.WriteByte('\n')
	}
	return writeFile(path, builder.String())
}

func writeFile(path, content string) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	return os.WriteFile(path, []byte(content), 0o644)
}
