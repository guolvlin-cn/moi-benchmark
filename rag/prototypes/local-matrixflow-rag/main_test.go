package main

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/matrixflow/moi-core/agent-tools/knowledge"
	knowledgeservice "github.com/matrixflow/moi-core/agent-tools/knowledge/service"
)

func TestLoadConfigAppliesTaaSDefaults(t *testing.T) {
	path := filepath.Join(t.TempDir(), "config.json")
	raw := `{
		"matrixone": {
			"dsn": "root:111@tcp(127.0.0.1:6001)/",
			"database": "benchmark",
			"vector_table": "embedding_results"
		},
		"embedding": {
			"mode": "taas",
			"model": "qwen3-embedding-0.6b",
			"dimension": 1024
		},
		"generation": {
			"enabled": true,
			"provider": "taas",
			"model": "qwen3.6-flash"
		}
	}`
	if err := os.WriteFile(path, []byte(raw), 0o600); err != nil {
		t.Fatal(err)
	}

	cfg, err := loadConfig(path)
	if err != nil {
		t.Fatal(err)
	}
	if cfg.Embedding.BaseURL != taasAPIBaseURL || cfg.Generation.BaseURL != taasAPIBaseURL {
		t.Fatalf("TaaS base URLs = embedding %q, generation %q", cfg.Embedding.BaseURL, cfg.Generation.BaseURL)
	}
	if cfg.Embedding.APIKeyEnv != taasAPIKeyEnvName || cfg.Generation.APIKeyEnv != taasAPIKeyEnvName {
		t.Fatalf("TaaS key envs = embedding %q, generation %q", cfg.Embedding.APIKeyEnv, cfg.Generation.APIKeyEnv)
	}
	if _, err := newEmbedder(cfg.Embedding); err != nil {
		t.Fatalf("newEmbedder() rejected TaaS mode: %v", err)
	}
}

func TestPostOpenAIJSONUsesBearerToken(t *testing.T) {
	t.Setenv(taasAPIKeyEnvName, "test-taas-key")
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		if got := request.URL.Path; got != "/embeddings" {
			t.Errorf("request path = %q, want /embeddings", got)
		}
		if got := request.Header.Get("Authorization"); got != "Bearer test-taas-key" {
			t.Errorf("Authorization = %q", got)
		}
		writer.Header().Set("Content-Type", "application/json")
		_, _ = writer.Write([]byte(`{"data":[]}`))
	}))
	defer server.Close()

	var response map[string]any
	err := postOpenAIJSON(
		context.Background(),
		server.Client(),
		server.URL,
		"/embeddings",
		taasAPIKeyEnvName,
		map[string]any{"model": "qwen3-embedding-0.6b", "input": []string{"hello"}},
		&response,
	)
	if err != nil {
		t.Fatal(err)
	}
	if _, ok := response["data"].([]any); !ok {
		encoded, _ := json.Marshal(response)
		t.Fatalf("response did not contain data array: %s", encoded)
	}
}

func TestPostOpenAIJSONRejectsMissingConfiguredAPIKey(t *testing.T) {
	t.Setenv(taasAPIKeyEnvName, "")
	err := postOpenAIJSON(
		context.Background(),
		http.DefaultClient,
		"https://example.invalid",
		"/embeddings",
		taasAPIKeyEnvName,
		map[string]any{},
		&map[string]any{},
	)
	if err == nil || !strings.Contains(err.Error(), taasAPIKeyEnvName) {
		t.Fatalf("missing-key error = %v", err)
	}
}

func TestChunkTextUsesDeterministicOverlap(t *testing.T) {
	chunks := chunkText("abcdefghij", 6, 2)
	if len(chunks) != 2 {
		t.Fatalf("chunk count = %d, want 2", len(chunks))
	}
	if got, want := chunks[0], (textChunk{Start: 0, End: 6, Content: "abcdef"}); got != want {
		t.Fatalf("first chunk = %+v, want %+v", got, want)
	}
	if got, want := chunks[1], (textChunk{Start: 4, End: 10, Content: "efghij"}); got != want {
		t.Fatalf("second chunk = %+v, want %+v", got, want)
	}
}

func TestAllocateRunDirNeverReusesAnExistingDirectory(t *testing.T) {
	root := filepath.Join(t.TempDir(), "runs", "mock")
	now := time.Date(2026, 7, 31, 12, 34, 56, 789000000, time.Local)
	first, err := allocateRunDir(root, now)
	if err != nil {
		t.Fatal(err)
	}
	second, err := allocateRunDir(root, now)
	if err != nil {
		t.Fatal(err)
	}
	if first == second {
		t.Fatalf("run directories were reused: %s", first)
	}
	if filepath.Base(first) != "20260731-123456.789" {
		t.Fatalf("first run directory = %s", first)
	}
	if filepath.Base(second) != "20260731-123456.789-01" {
		t.Fatalf("second run directory = %s", second)
	}
	for _, path := range []string{first, second} {
		info, statErr := os.Stat(path)
		if statErr != nil || !info.IsDir() {
			t.Fatalf("run directory %s was not created", path)
		}
	}
}

func TestForceRebuildsVectorTableWhenEmbeddingDimensionChanges(t *testing.T) {
	dsn := os.Getenv("MATRIXONE_INTEGRATION_DSN")
	if dsn == "" {
		t.Skip("set MATRIXONE_INTEGRATION_DSN to run MatrixOne integration tests")
	}
	table := fmt.Sprintf("embedding_dimension_test_%d", time.Now().UnixNano())
	cfg := Config{MatrixOne: MatrixOneConfig{
		DSN: dsn, Database: "matrixflow_rag_benchmark", VectorTable: table,
	}}
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	db, err := openBenchmarkDB(ctx, cfg, 256, true)
	if err != nil {
		t.Fatal(err)
	}
	if err := db.Close(); err != nil {
		t.Fatal(err)
	}
	db, err = openBenchmarkDB(ctx, cfg, 1024, true)
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	defer db.ExecContext(context.Background(), "DROP TABLE IF EXISTS `"+table+"`")

	var tableName, createSQL string
	if err := db.QueryRowContext(ctx, "SHOW CREATE TABLE `"+table+"`").Scan(&tableName, &createSQL); err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(strings.ToLower(createSQL), "vecf64(1024)") {
		t.Fatalf("force kept the old vector dimension; SHOW CREATE TABLE = %s", createSQL)
	}
}

func TestScoreCaseSeparatesSourceAndEvidenceRecall(t *testing.T) {
	answerable := true
	item := QuestionCase{
		RelevantDocuments:  []string{"guide.md", "policy.md"},
		RelevantEvidence:   []string{"MatrixFlow native retrieval", "missing evidence"},
		ExpectedAnswerable: &answerable,
	}
	chunks := []ChunkResult{
		{Rank: 1, FileName: "guide.md", Content: "MatrixFlow native retrieval uses hybrid search."},
		{Rank: 2, FileName: "other.md", Content: "Unrelated."},
	}
	metrics := scoreCase(item, chunks)
	if metrics.SourceRecall != 0.5 {
		t.Fatalf("source recall = %v, want 0.5", metrics.SourceRecall)
	}
	if metrics.EvidenceRecall != 0.5 {
		t.Fatalf("evidence recall = %v, want 0.5", metrics.EvidenceRecall)
	}
	if metrics.ReciprocalRank != 1 {
		t.Fatalf("MRR = %v, want 1", metrics.ReciprocalRank)
	}
	if metrics.RecallAtK["1"] != 0.5 {
		t.Fatalf("source recall@1 = %v, want 0.5", metrics.RecallAtK["1"])
	}
	if metrics.AnswerabilityAccuracy == nil || *metrics.AnswerabilityAccuracy != 1 {
		t.Fatalf("answerability accuracy = %v, want 1", metrics.AnswerabilityAccuracy)
	}
}

func TestScoreCasePenalizesUnexpectedEvidenceForUnanswerableCase(t *testing.T) {
	answerable := false
	metrics := scoreCase(QuestionCase{ExpectedAnswerable: &answerable}, []ChunkResult{{Content: "irrelevant evidence"}})
	if metrics.AnswerabilityAccuracy == nil || *metrics.AnswerabilityAccuracy != 0 {
		t.Fatalf("answerability accuracy = %v, want 0", metrics.AnswerabilityAccuracy)
	}
}

func TestClassifySQLStage(t *testing.T) {
	cases := map[string]string{
		"SHOW COLUMNS FROM t":                                "schema_inspection",
		"SELECT * FROM t WHERE MATCH(content) AGAINST ('x')": "fulltext_search",
		"SELECT l2_distance(embedding, '[1]') FROM t":        "vector_search",
		"SELECT * FROM t WHERE chunk_index BETWEEN 1 AND 3":  "evidence_expansion",
	}
	for query, want := range cases {
		if got := classifySQLStage(query); got != want {
			t.Errorf("classifySQLStage(%q) = %q, want %q", query, got, want)
		}
	}
}

func TestHashEmbeddingIsStableAndNormalized(t *testing.T) {
	client := hashEmbeddingClient{dimension: 64}
	first, err := client.CreateEmbedding(context.Background(), "", "", []string{"MatrixFlow 检索"})
	if err != nil {
		t.Fatal(err)
	}
	second, err := client.CreateEmbedding(context.Background(), "", "", []string{"MatrixFlow 检索"})
	if err != nil {
		t.Fatal(err)
	}
	if len(first) != 1 || len(first[0]) != 64 {
		t.Fatalf("embedding shape = %dx%d, want 1x64", len(first), len(first[0]))
	}
	var norm float64
	for index, value := range first[0] {
		if value != second[0][index] {
			t.Fatal("hash embedding is not deterministic")
		}
		norm += value * value
	}
	if norm < 0.999 || norm > 1.001 {
		t.Fatalf("squared norm = %v, want approximately 1", norm)
	}
}

func TestHarnessExecutesMatrixFlowNativeSearchRAGChunks(t *testing.T) {
	executor := &productRAGExecutor{}
	recorder := &timingRecorder{}
	recorder.reset()
	searcher := knowledgeservice.NewSearchRAGChunks(knowledgeservice.Deps{
		SQLExecutor: timedSQLExecutor{next: executor, recorder: recorder},
		Embedder: timedEmbeddingService{
			next:     hashEmbeddingClient{dimension: 3},
			recorder: recorder,
		},
		DefaultRetrieverConfig: knowledge.RetrieverConfig{
			EmbeddingModel: "test-embedding",
		},
	})
	response, err := searcher.Execute(context.Background(), knowledge.SearchRAGChunksRequest{
		Scope: knowledge.WorkspaceScope{
			WorkspaceID:    "local",
			DBName:         "benchmark",
			VectorTable:    "embedding_results",
			EmbeddingModel: "test-embedding",
		},
		Keywards: []string{"native retrieval"},
		MaxHits:  5,
	})
	if err != nil {
		t.Fatalf("SearchRAGChunks.Execute() error = %v", err)
	}
	if len(response.Chunks) != 1 {
		t.Fatalf("chunk count = %d, want 1", len(response.Chunks))
	}
	if response.Chunks[0].ChunkID != "chunk_native_1" {
		t.Fatalf("chunk id = %q, want chunk_native_1", response.Chunks[0].ChunkID)
	}
	if len(executor.queries) < 3 {
		t.Fatalf("query count = %d, want product column/fulltext/vector routes", len(executor.queries))
	}
	if !strings.Contains(executor.queries[1], "rag_fulltext_candidates") {
		t.Fatalf("second query is not MatrixFlow fulltext route: %s", executor.queries[1])
	}
	if !strings.Contains(executor.queries[2], "l2_distance") {
		t.Fatalf("third query is not MatrixFlow vector route: %s", executor.queries[2])
	}
	stageLatency := recorder.milliseconds()
	for _, stage := range []string{"schema_inspection", "fulltext_search", "vector_search", "embedding"} {
		if _, ok := stageLatency[stage]; !ok {
			t.Errorf("missing %s latency from native retrieval trace: %#v", stage, stageLatency)
		}
	}
}

type productRAGExecutor struct {
	queries []string
}

func (e *productRAGExecutor) ExecuteSQL(_ context.Context, _ string, query string) (*knowledge.SQLExecutionResult, error) {
	e.queries = append(e.queries, query)
	switch {
	case strings.HasPrefix(query, "SHOW COLUMNS"):
		return &knowledge.SQLExecutionResult{
			Columns: []string{"Field"},
			Rows: [][]any{
				{"file_id"}, {"index_version"}, {"level"}, {"content"}, {"meta"},
				{"embedding"}, {"chunk_index"}, {"disabled"},
			},
		}, nil
	case strings.Contains(query, "rag_fulltext_candidates"):
		return &knowledge.SQLExecutionResult{
			Columns: []string{
				"route", "level", "content", "meta", "file_id", "markdown_file_id",
				"index_version", "chunk_index", "chunk_index_scope", "parent_index",
				"chunk_start", "chunk_end", "score",
			},
			Rows: [][]any{{
				"fulltext", "chunk", "MatrixFlow native retrieval evidence",
				`{"chunk_id":"chunk_native_1","source_file_name":"guide.md"}`,
				"file_guide", "", "1", 0, "", "", "", "", 1.0,
			}},
		}, nil
	case strings.Contains(query, "rag_vector_candidates"):
		return &knowledge.SQLExecutionResult{
			Columns: []string{
				"route", "level", "content", "meta", "file_id", "markdown_file_id",
				"index_version", "chunk_index", "chunk_index_scope", "parent_index",
				"chunk_start", "chunk_end", "score",
			},
		}, nil
	default:
		return &knowledge.SQLExecutionResult{}, nil
	}
}
