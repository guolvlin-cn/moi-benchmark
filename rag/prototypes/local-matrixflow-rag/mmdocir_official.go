package main

import (
	"bufio"
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/matrixflow/moi-core/workers/go-worker/pkg/workitems"
)

type mmdocirCandidate struct {
	ID         string         `json:"id"`
	FileID     string         `json:"file_id"`
	Content    string         `json:"content"`
	PageNumber int            `json:"page_number"`
	ChunkIndex int            `json:"chunk_index"`
	Metadata   map[string]any `json:"metadata"`
}

type mmdocirQuestion struct {
	ID            string              `json:"id"`
	QueryIndex    int                 `json:"query_index"`
	Question      string              `json:"question"`
	Answer        any                 `json:"answer"`
	Domain        string              `json:"domain"`
	DocName       string              `json:"doc_name"`
	FileID        string              `json:"file_id"`
	PageIDs       []int               `json:"page_ids"`
	LayoutMapping []mmdocirLayoutGold `json:"layout_mapping"`
	EvidenceType  string              `json:"evidence_type"`
}

type mmdocirLayoutGold struct {
	Page     int       `json:"page"`
	PageSize []float64 `json:"page_size"`
	BBox     []float64 `json:"bbox"`
}

type mmdocirHit struct {
	ID       string    `json:"id"`
	PageID   int       `json:"page_id"`
	LayoutID int       `json:"layout_id,omitempty"`
	BBox     []float64 `json:"bbox,omitempty"`
	Distance float64   `json:"distance"`
	FileName string    `json:"file_name,omitempty"`
	Content  string    `json:"content,omitempty"`
}

type mmdocirAttempt struct {
	QuestionID string                 `json:"question_id"`
	QueryIndex int                    `json:"query_index"`
	Domain     string                 `json:"domain"`
	DocName    string                 `json:"doc_name"`
	Question   string                 `json:"question"`
	Status     string                 `json:"status"`
	Error      string                 `json:"error,omitempty"`
	LatencyMS  float64                `json:"latency_ms"`
	Hits       []mmdocirHit           `json:"hits,omitempty"`
	RecallAtK  map[string]float64     `json:"recall_at_k"`
	Metadata   map[string]interface{} `json:"metadata"`
}

type mmdocirSummary struct {
	Granularity        string                        `json:"granularity"`
	Protocol           string                        `json:"protocol"`
	Model              string                        `json:"embedding_model"`
	Attempts           int                           `json:"attempts"`
	SuccessfulAttempts int                           `json:"successful_attempts"`
	FailedAttempts     int                           `json:"failed_attempts"`
	RecallAtK          map[string]float64            `json:"recall_at_k"`
	MacroDomainRecall  map[string]float64            `json:"macro_domain_recall_at_k"`
	ByDomain           map[string]map[string]float64 `json:"by_domain_recall_at_k"`
	LatencyP50MS       float64                       `json:"latency_p50_ms"`
	LatencyP95MS       float64                       `json:"latency_p95_ms"`
}

func cloneStringAnyMap(input map[string]any) map[string]any {
	output := make(map[string]any, len(input)+1)
	for key, value := range input {
		output[key] = value
	}
	return output
}

func mmdocirOfficialIngestCommand(args []string) error {
	fs := flag.NewFlagSet("mmdocir-ingest", flag.ContinueOnError)
	var common commonFlags
	var candidatesPath, resumeProgress string
	var force bool
	addCommonFlags(fs, &common)
	fs.StringVar(&candidatesPath, "candidates", "", "prepared MMDocIR page/layout candidates JSONL")
	fs.BoolVar(&force, "force", false, "replace the dedicated benchmark table")
	fs.StringVar(&resumeProgress, "resume-progress", "", "prior progress.json to continue from its committed candidate boundary")
	if err := fs.Parse(args); err != nil {
		return err
	}
	if strings.TrimSpace(candidatesPath) == "" {
		return errors.New("--candidates is required")
	}
	if force && strings.TrimSpace(resumeProgress) != "" {
		return errors.New("--force and --resume-progress cannot be used together")
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
	return ingestMMDocIROfficial(context.Background(), cfg, candidatesPath, runDir, force, resumeProgress)
}

func mmdocirOfficialRunCommand(args []string) error {
	fs := flag.NewFlagSet("mmdocir-run", flag.ContinueOnError)
	var common commonFlags
	var questionsPath, granularity string
	var limit int
	addCommonFlags(fs, &common)
	fs.StringVar(&questionsPath, "questions", "", "prepared MMDocIR questions JSONL")
	fs.StringVar(&granularity, "granularity", "page", "page or layout")
	fs.IntVar(&limit, "limit", 0, "maximum questions; 0 means all")
	if err := fs.Parse(args); err != nil {
		return err
	}
	if strings.TrimSpace(questionsPath) == "" {
		return errors.New("--questions is required")
	}
	if granularity != "page" && granularity != "layout" {
		return fmt.Errorf("unsupported granularity %q", granularity)
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
	return runMMDocIROfficial(context.Background(), cfg, questionsPath, runDir, granularity, limit)
}

// mmdocirQACommand runs a first-pass answer-generation diagnostic on the
// official MMDocIR page corpus.  It deliberately uses the benchmark's native
// document-local dense retrieval route (the same MOI page table as
// mmdocir-run), then feeds the returned page text to the configured generator.
// This avoids conflating the official retrieval protocol with the slower
// product hybrid full-text route while retaining all evidence locations for a
// later answer metric implementation.
func mmdocirQACommand(args []string) error {
	fs := flag.NewFlagSet("mmdocir-qa", flag.ContinueOnError)
	var common commonFlags
	var questionsPath string
	var limit, maxHits int
	addCommonFlags(fs, &common)
	fs.StringVar(&questionsPath, "questions", "", "prepared official MMDocIR questions JSONL")
	fs.IntVar(&limit, "limit", 0, "maximum questions; 0 means all")
	fs.IntVar(&maxHits, "max-hits", 10, "page evidence hits per question")
	if err := fs.Parse(args); err != nil {
		return err
	}
	if strings.TrimSpace(questionsPath) == "" {
		return errors.New("--questions is required")
	}
	if maxHits < 1 {
		return errors.New("--max-hits must be positive")
	}
	cfg, err := loadConfig(common.configPath)
	if err != nil {
		return err
	}
	if !cfg.Generation.Enabled {
		return errors.New("mmdocir-qa requires generation.enabled=true")
	}
	runDir, err := allocateRunDir(common.runDir, time.Now())
	if err != nil {
		return err
	}
	fmt.Printf("run_dir=%s\n", runDir)
	return runMMDocIRQA(context.Background(), cfg, questionsPath, runDir, limit, maxHits)
}

func runMMDocIRQA(ctx context.Context, cfg Config, questionsPath, runDir string, limit, maxHits int) error {
	questions, err := readMMDocIRJSONL[mmdocirQuestion](questionsPath)
	if err != nil {
		return err
	}
	if limit > 0 && limit < len(questions) {
		questions = questions[:limit]
	}
	if len(questions) == 0 {
		return errors.New("MMDocIR QA question file is empty")
	}
	db, err := openBenchmarkDB(ctx, cfg, cfg.Embedding.Dimension, false)
	if err != nil {
		return err
	}
	defer db.Close()
	if err := verifyMMDocIRTable(ctx, db, cfg.MatrixOne.VectorTable, "page"); err != nil {
		return err
	}
	embedder, err := newEmbedder(cfg.Embedding)
	if err != nil {
		return err
	}
	resultsPath := filepath.Join(runDir, "results.jsonl")
	results := make([]RunResult, 0, len(questions))
	started := time.Now()
	for index, question := range questions {
		attemptStarted := time.Now()
		caseItem := mmdocirQuestionCase(question)
		retrievalStarted := time.Now()
		vectors, embedErr := embedder.CreateEmbedding(ctx, cfg.Workspace, cfg.Embedding.Model, []string{question.Question})
		result := RunResult{
			Case:           caseItem,
			Repeat:         1,
			StartedAt:      attemptStarted.UTC().Format(time.RFC3339Nano),
			Status:         "ok",
			Routes:         []string{"vector_l2"},
			EmbeddingModel: cfg.Embedding.Model,
			StageLatencyMS: map[string]float64{},
		}
		if embedErr != nil {
			result.Status = "failed"
			result.Error = fmt.Errorf("API_ERROR: query embedding for %s: %w", question.ID, embedErr).Error()
			result.EndedAt = time.Now().UTC().Format(time.RFC3339Nano)
			results = append(results, result)
			if err := appendJSONValue(resultsPath, result); err != nil {
				return err
			}
			return fmt.Errorf("%s", result.Error)
		}
		result.StageLatencyMS["embedding"] = float64(time.Since(retrievalStarted).Microseconds()) / 1000
		if len(vectors) != 1 || len(vectors[0]) != cfg.Embedding.Dimension {
			return fmt.Errorf("query embedding shape for %s is invalid", question.ID)
		}
		vectorSearchStarted := time.Now()
		hits, searchErr := searchMMDocIRDense(ctx, db, cfg.MatrixOne.VectorTable, question.FileID, vectors[0], maxHits)
		result.StageLatencyMS["vector_search"] = float64(time.Since(vectorSearchStarted).Microseconds()) / 1000
		result.RetrievalLatencyMS = float64(time.Since(retrievalStarted).Microseconds()) / 1000
		if searchErr != nil {
			result.Status = "failed"
			result.Error = fmt.Errorf("MOI retrieval for %s: %w", question.ID, searchErr).Error()
			result.EndedAt = time.Now().UTC().Format(time.RFC3339Nano)
			results = append(results, result)
			if err := appendJSONValue(resultsPath, result); err != nil {
				return err
			}
			return fmt.Errorf("%s", result.Error)
		}
		result.Chunks = mmdocirQAChunks(question, hits)
		result.Metrics = scoreCase(caseItem, result.Chunks)
		generationStarted := time.Now()
		answer, provider, model, generationErr := generateAnswer(ctx, cfg.Generation, question.Question, result.Chunks)
		generationLatency := float64(time.Since(generationStarted).Microseconds()) / 1000
		result.GenerationLatency = &generationLatency
		if generationErr != nil {
			result.Status = "failed"
			result.Error = fmt.Errorf("API_ERROR: generation for %s: %w", question.ID, generationErr).Error()
			result.EndedAt = time.Now().UTC().Format(time.RFC3339Nano)
			results = append(results, result)
			if err := appendJSONValue(resultsPath, result); err != nil {
				return err
			}
			return fmt.Errorf("%s", result.Error)
		}
		result.Answer = answer
		result.GenerationProvider = provider
		result.GenerationModel = model
		result.EndedAt = time.Now().UTC().Format(time.RFC3339Nano)
		results = append(results, result)
		if err := appendJSONValue(resultsPath, result); err != nil {
			return err
		}
		summary := summarize(results)
		_ = writeJSON(filepath.Join(runDir, "summary.json"), summary)
		_ = writeReport(filepath.Join(runDir, "report.md"), summary)
		fmt.Printf("mmdocir_qa_query=%d/%d id=%s status=%s hits=%d retrieval_ms=%.0f generation_ms=%.0f eta_seconds=%.0f\n",
			index+1, len(questions), question.ID, result.Status, len(result.Chunks), result.RetrievalLatencyMS,
			generationLatency, estimateRemaining(started, index+1, len(questions)))
	}
	return nil
}

func mmdocirQuestionCase(question mmdocirQuestion) QuestionCase {
	answerable := true
	return QuestionCase{
		ID:                 question.ID,
		Question:           question.Question,
		RetrievalKeywords:  []string{question.Question},
		FileIDs:            []string{question.FileID},
		ExpectedAnswerable: &answerable,
		Metadata: map[string]any{
			"benchmark":           "MMDocIR",
			"benchmark_variant":   "page_text_qa_diagnostic",
			"qa_scope":            "page_text",
			"reference_answer":    question.Answer,
			"domain":              question.Domain,
			"doc_name":            question.DocName,
			"gold_page_ids":       question.PageIDs,
			"gold_layout_mapping": question.LayoutMapping,
			"question_type":       question.EvidenceType,
			"query_index":         question.QueryIndex,
			"retrieval_protocol":  "MMDocIR document-local dense page retrieval; MOI l2_distance",
			"retrieval_table":     "moi_stage1_mmdocir_official.pages_bge_m3_vlm",
			"answer_evaluation":   "deferred; retain raw reference and generated answer",
		},
	}
}

func mmdocirQAChunks(question mmdocirQuestion, hits []mmdocirHit) []ChunkResult {
	chunks := make([]ChunkResult, 0, len(hits))
	for index, hit := range hits {
		fileName := hit.FileName
		if fileName == "" {
			fileName = question.DocName
		}
		chunks = append(chunks, ChunkResult{
			Rank:       index + 1,
			ChunkID:    hit.ID,
			FileID:     question.FileID,
			FileName:   fileName,
			PageNumber: hit.PageID,
			Score:      hit.Distance,
			Routes:     []string{"vector_l2"},
			Content:    hit.Content,
			Level:      "chunk",
			BBox:       hit.BBox,
		})
	}
	return chunks
}

func readMMDocIRJSONL[T any](path string) ([]T, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer file.Close()
	var rows []T
	scanner := bufio.NewScanner(file)
	scanner.Buffer(make([]byte, 64*1024), 32*1024*1024)
	for line := 1; scanner.Scan(); line++ {
		if strings.TrimSpace(scanner.Text()) == "" {
			continue
		}
		var row T
		if err := json.Unmarshal(scanner.Bytes(), &row); err != nil {
			return nil, fmt.Errorf("decode %s line %d: %w", path, line, err)
		}
		rows = append(rows, row)
	}
	return rows, scanner.Err()
}

func ingestMMDocIROfficial(ctx context.Context, cfg Config, candidatesPath, runDir string, force bool, resumeProgress string) error {
	candidates, err := readMMDocIRJSONL[mmdocirCandidate](candidatesPath)
	if err != nil {
		return err
	}
	if len(candidates) == 0 {
		return errors.New("MMDocIR candidate file is empty")
	}
	for i, candidate := range candidates {
		if candidate.ID == "" || candidate.FileID == "" {
			return fmt.Errorf("candidate %d requires id and file_id", i)
		}
	}
	resumeFrom, err := loadMMDocIRResumeProgress(resumeProgress, len(candidates))
	if err != nil {
		return err
	}
	if !force && resumeFrom == 0 {
		return errors.New("mmdocir-ingest requires --force for a new table or --resume-progress for an interrupted table")
	}
	var db *sql.DB
	if resumeFrom > 0 {
		db, err = openExistingIngestDB(ctx, cfg)
	} else {
		db, err = openIngestDB(ctx, cfg, cfg.Embedding.Dimension, true)
	}
	if err != nil {
		return err
	}
	defer db.Close()
	if resumeFrom > 0 {
		var existingRows int
		if err := db.QueryRowContext(ctx, "SELECT COUNT(*) FROM `"+cfg.MatrixOne.VectorTable+"`").Scan(&existingRows); err != nil {
			return fmt.Errorf("count MMDocIR resume rows: %w", err)
		}
		if existingRows != resumeFrom {
			return fmt.Errorf("MMDocIR resume row count mismatch: database=%d checkpoint=%d", existingRows, resumeFrom)
		}
		fmt.Printf("mmdocir_resume=%d/%d progress=%s\n", resumeFrom, len(candidates), resumeProgress)
	}
	embedder, err := newEmbedder(cfg.Embedding)
	if err != nil {
		return err
	}
	inputs := make([]string, len(candidates))
	for i := range candidates {
		inputs[i] = mmdocirEmbeddingInput(candidates[i].Content)
	}
	batches := splitEmbeddingInputsForLocalRAG(inputs[resumeFrom:], cfg.EmbeddingBatchSize)
	embedded, committed := resumeFrom, resumeFrom
	started := time.Now()
	writeProgress := func(stage string) {
		_ = writeJSON(filepath.Join(runDir, "progress.json"), map[string]any{
			"stage": stage, "embedded": embedded, "committed": committed,
			"total": len(candidates), "elapsed_seconds": time.Since(started).Seconds(),
		})
	}
	writeProgress("prepared")
	for batchIndex, batch := range batches {
		globalStart, globalEnd := resumeFrom+batch.Start, resumeFrom+batch.End
		vectors, err := embedder.CreateEmbedding(ctx, cfg.Workspace, cfg.Embedding.Model, batch.Inputs)
		if err != nil {
			writeProgress("failed")
			return fmt.Errorf("API_ERROR: embed candidates %d:%d: %w", globalStart, globalEnd, err)
		}
		if len(vectors) != len(batch.Inputs) {
			return fmt.Errorf("embedding count mismatch: got %d want %d", len(vectors), len(batch.Inputs))
		}
		docs := make([]workitems.VectorDoc, 0, len(vectors))
		for i, vector := range vectors {
			candidate := candidates[globalStart+i]
			if len(vector) != cfg.Embedding.Dimension {
				return fmt.Errorf("embedding dimension for %s: got %d want %d", candidate.ID, len(vector), cfg.Embedding.Dimension)
			}
			page, chunk := candidate.PageNumber, candidate.ChunkIndex
			metadata := cloneStringAnyMap(candidate.Metadata)
			// SearchRAGChunks reads location fields from meta.  Keep the
			// benchmark's page_number column and mirror it into metadata so
			// native MOI QA results retain a page locator as well.
			metadata["page_number"] = candidate.PageNumber
			docs = append(docs, workitems.VectorDoc{
				ID: candidate.ID, Content: candidate.Content, Embedding: vector,
				Metadata: metadata, FileID: candidate.FileID, PageNumber: &page,
				ChunkIndex: &chunk, Level: "chunk", IndexVersion: 1,
			})
		}
		written, err := workitems.UpsertVectorRowsForLocalRAG(ctx, db, cfg.MatrixOne.VectorTable, docs, "FAIL")
		if err != nil {
			return fmt.Errorf("write candidates batch %d: %w", batchIndex, err)
		}
		embedded += len(vectors)
		committed += written
		writeProgress("writing")
		fmt.Printf("mmdocir_ingest_batch=%d/%d embedded=%d/%d committed=%d eta_seconds=%.0f\n",
			batchIndex+1, len(batches), embedded, len(candidates), committed,
			estimateRemaining(started, embedded, len(candidates)))
	}
	if err := workitems.EnsureVectorTableForLocalRAG(db, cfg.MatrixOne.VectorTable, cfg.Embedding.Dimension); err != nil {
		return fmt.Errorf("build MMDocIR vector index: %w", err)
	}
	writeProgress("committed")
	return writeJSON(filepath.Join(runDir, "ingest-summary.json"), map[string]any{
		"status": "committed", "database": cfg.MatrixOne.Database, "table": cfg.MatrixOne.VectorTable,
		"embedding_model": cfg.Embedding.Model, "candidates": len(candidates),
		"duration_seconds": time.Since(started).Seconds(),
	})
}

func loadMMDocIRResumeProgress(path string, total int) (int, error) {
	path = strings.TrimSpace(path)
	if path == "" {
		return 0, nil
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		return 0, fmt.Errorf("read MMDocIR resume progress: %w", err)
	}
	var progress struct {
		Stage     string `json:"stage"`
		Embedded  int    `json:"embedded"`
		Committed int    `json:"committed"`
		Total     int    `json:"total"`
	}
	if err := json.Unmarshal(raw, &progress); err != nil {
		return 0, fmt.Errorf("decode MMDocIR resume progress: %w", err)
	}
	if progress.Stage == "committed" {
		return 0, errors.New("MMDocIR resume progress is already committed")
	}
	if progress.Total != total {
		return 0, fmt.Errorf("MMDocIR resume total changed: candidates=%d checkpoint=%d", total, progress.Total)
	}
	if progress.Committed <= 0 || progress.Committed >= total || progress.Embedded != progress.Committed {
		return 0, fmt.Errorf("MMDocIR resume progress is not a valid committed boundary: embedded=%d committed=%d total=%d", progress.Embedded, progress.Committed, total)
	}
	return progress.Committed, nil
}

// The official corpus contains candidates whose OCR and VLM text are both
// empty. The upstream local BGE wrapper tokenizes an empty string, but the TaaS
// OpenAI-compatible endpoint rejects it before model inference. U+2060 is an
// invisible, non-whitespace placeholder that keeps those candidates in the
// benchmark without adding lexical terms that could match a query. The raw
// candidate content stored in MatrixOne remains unchanged.
func mmdocirEmbeddingInput(content string) string {
	if strings.TrimSpace(content) == "" {
		return "\u2060"
	}
	return content
}

func estimateRemaining(started time.Time, done, total int) float64 {
	if done <= 0 || total <= done {
		return 0
	}
	return time.Since(started).Seconds() * float64(total-done) / float64(done)
}

func runMMDocIROfficial(ctx context.Context, cfg Config, questionsPath, runDir, granularity string, limit int) error {
	questions, err := readMMDocIRJSONL[mmdocirQuestion](questionsPath)
	if err != nil {
		return err
	}
	if limit > 0 && limit < len(questions) {
		questions = questions[:limit]
	}
	if len(questions) == 0 {
		return errors.New("MMDocIR question file is empty")
	}
	db, err := openBenchmarkDB(ctx, cfg, cfg.Embedding.Dimension, false)
	if err != nil {
		return err
	}
	defer db.Close()
	if err := verifyMMDocIRTable(ctx, db, cfg.MatrixOne.VectorTable, granularity); err != nil {
		return err
	}
	embedder, err := newEmbedder(cfg.Embedding)
	if err != nil {
		return err
	}
	resultsPath := filepath.Join(runDir, "attempts.jsonl")
	started := time.Now()
	attempts := make([]mmdocirAttempt, 0, len(questions))
	for index, question := range questions {
		attemptStarted := time.Now()
		vectors, embedErr := embedder.CreateEmbedding(ctx, cfg.Workspace, cfg.Embedding.Model, []string{question.Question})
		if embedErr != nil {
			return fmt.Errorf("API_ERROR: query embedding for %s: %w", question.ID, embedErr)
		}
		if len(vectors) != 1 || len(vectors[0]) != cfg.Embedding.Dimension {
			return fmt.Errorf("query embedding shape for %s is invalid", question.ID)
		}
		hits, searchErr := searchMMDocIRDense(ctx, db, cfg.MatrixOne.VectorTable, question.FileID, vectors[0], 10)
		attempt := mmdocirAttempt{
			QuestionID: question.ID, QueryIndex: question.QueryIndex, Domain: question.Domain,
			DocName: question.DocName, Question: question.Question, Status: "ok", Hits: hits,
			RecallAtK: map[string]float64{}, Metadata: map[string]interface{}{
				"granularity": granularity, "evidence_type": question.EvidenceType,
			},
		}
		if searchErr != nil {
			attempt.Status, attempt.Error = "failed", searchErr.Error()
		} else {
			for _, k := range mmdocirCutoffs(granularity) {
				attempt.RecallAtK[strconv.Itoa(k)] = scoreMMDocIR(question, hits, granularity, k)
			}
		}
		attempt.LatencyMS = float64(time.Since(attemptStarted).Microseconds()) / 1000
		attempts = append(attempts, attempt)
		if err := appendJSONValue(resultsPath, attempt); err != nil {
			return err
		}
		summary := summarizeMMDocIR(attempts, granularity, cfg.Embedding.Model)
		_ = writeJSON(filepath.Join(runDir, "metrics.json"), summary)
		_ = writeMMDocIRReport(filepath.Join(runDir, "report.md"), summary)
		fmt.Printf("mmdocir_query=%d/%d id=%s status=%s recall=%v p95_ms=%.2f eta_seconds=%.0f\n",
			index+1, len(questions), question.ID, attempt.Status, attempt.RecallAtK,
			summary.LatencyP95MS, estimateRemaining(started, index+1, len(questions)))
		if searchErr != nil {
			return fmt.Errorf("MMDocIR retrieval failed for %s: %w", question.ID, searchErr)
		}
	}
	return nil
}

func verifyMMDocIRTable(ctx context.Context, db *sql.DB, table, granularity string) error {
	var total, matching int
	if err := db.QueryRowContext(ctx, "SELECT COUNT(*) FROM `"+table+"`").Scan(&total); err != nil {
		return err
	}
	query := "SELECT COUNT(*) FROM `" + table + "` WHERE JSON_UNQUOTE(JSON_EXTRACT(meta, '$.granularity')) = ?"
	if err := db.QueryRowContext(ctx, query, granularity).Scan(&matching); err != nil {
		return err
	}
	if total == 0 || matching != total {
		return fmt.Errorf("table %s integrity mismatch: total=%d granularity_%s=%d", table, total, granularity, matching)
	}
	return nil
}

func vectorLiteral(vector []float64) string {
	var out strings.Builder
	out.WriteByte('[')
	for i, value := range vector {
		if i > 0 {
			out.WriteByte(',')
		}
		out.WriteString(strconv.FormatFloat(value, 'g', -1, 64))
	}
	out.WriteByte(']')
	return out.String()
}

func searchMMDocIRDense(ctx context.Context, db *sql.DB, table, fileID string, vector []float64, topK int) ([]mmdocirHit, error) {
	query := "SELECT id, page_number, content, meta, l2_distance(embedding, '" + vectorLiteral(vector) +
		"') AS distance FROM `" + table + "` WHERE file_id = ? AND level = 'chunk' AND embedding IS NOT NULL " +
		"ORDER BY distance ASC LIMIT ?"
	rows, err := db.QueryContext(ctx, query, fileID, topK)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var hits []mmdocirHit
	for rows.Next() {
		var id string
		var pageID int
		var content string
		var rawMeta []byte
		var distance float64
		if err := rows.Scan(&id, &pageID, &content, &rawMeta, &distance); err != nil {
			return nil, err
		}
		var meta map[string]any
		if err := json.Unmarshal(rawMeta, &meta); err != nil {
			return nil, fmt.Errorf("decode metadata for %s: %w", id, err)
		}
		hit := mmdocirHit{ID: id, PageID: pageID, Distance: distance, Content: content}
		hit.FileName = mmdocirStringValue(meta["file_name"])
		if hit.FileName == "" {
			hit.FileName = mmdocirStringValue(meta["doc_name"])
		}
		hit.LayoutID = intValue(meta["layout_id"], 0)
		hit.BBox = floatSlice(meta["bbox"])
		hits = append(hits, hit)
	}
	return hits, rows.Err()
}

func mmdocirStringValue(value any) string {
	if text, ok := value.(string); ok {
		return strings.TrimSpace(text)
	}
	return ""
}

func floatSlice(value any) []float64 {
	values, ok := value.([]any)
	if !ok {
		return nil
	}
	out := make([]float64, 0, len(values))
	for _, value := range values {
		switch typed := value.(type) {
		case float64:
			out = append(out, typed)
		case json.Number:
			parsed, _ := typed.Float64()
			out = append(out, parsed)
		}
	}
	return out
}

func mmdocirCutoffs(granularity string) []int {
	if granularity == "layout" {
		return []int{1, 5, 10}
	}
	return []int{1, 3, 5}
}

func scoreMMDocIR(question mmdocirQuestion, hits []mmdocirHit, granularity string, k int) float64 {
	if k > len(hits) {
		k = len(hits)
	}
	if granularity == "page" {
		gold := make(map[int]struct{}, len(question.PageIDs))
		for _, pageID := range question.PageIDs {
			gold[pageID] = struct{}{}
		}
		found := make(map[int]struct{})
		for _, hit := range hits[:k] {
			if _, ok := gold[hit.PageID]; ok {
				found[hit.PageID] = struct{}{}
			}
		}
		if len(gold) == 0 {
			return 0
		}
		return float64(len(found)) / float64(len(gold))
	}
	gtArea, overlap := 0.0, 0.0
	for _, gold := range question.LayoutMapping {
		gtArea += bboxArea(gold.BBox)
	}
	for _, hit := range hits[:k] {
		for _, gold := range question.LayoutMapping {
			if hit.PageID == gold.Page {
				overlap += bboxIntersection(hit.BBox, gold.BBox)
			}
		}
	}
	if gtArea == 0 {
		return 0
	}
	return overlap / gtArea
}

func bboxArea(bbox []float64) float64 {
	if len(bbox) != 4 {
		return 0
	}
	return math.Max(0, bbox[2]-bbox[0]) * math.Max(0, bbox[3]-bbox[1])
}

func bboxIntersection(left, right []float64) float64 {
	if len(left) != 4 || len(right) != 4 {
		return 0
	}
	x1, y1 := math.Max(left[0], right[0]), math.Max(left[1], right[1])
	x2, y2 := math.Min(left[2], right[2]), math.Min(left[3], right[3])
	return math.Max(0, x2-x1) * math.Max(0, y2-y1)
}

func summarizeMMDocIR(attempts []mmdocirAttempt, granularity, model string) mmdocirSummary {
	summary := mmdocirSummary{
		Granularity: granularity, Protocol: "MMDocIR document-local dense retrieval (adapted to MOI/BGE-M3)",
		Model: model, Attempts: len(attempts), RecallAtK: map[string]float64{},
		MacroDomainRecall: map[string]float64{}, ByDomain: map[string]map[string]float64{},
	}
	cutoffs := mmdocirCutoffs(granularity)
	domainCounts := map[string]int{}
	var latencies []float64
	for _, attempt := range attempts {
		if attempt.Status != "ok" {
			summary.FailedAttempts++
			continue
		}
		summary.SuccessfulAttempts++
		latencies = append(latencies, attempt.LatencyMS)
		domainCounts[attempt.Domain]++
		if summary.ByDomain[attempt.Domain] == nil {
			summary.ByDomain[attempt.Domain] = map[string]float64{}
		}
		for _, k := range cutoffs {
			key := strconv.Itoa(k)
			summary.RecallAtK[key] += attempt.RecallAtK[key]
			summary.ByDomain[attempt.Domain][key] += attempt.RecallAtK[key]
		}
	}
	if summary.SuccessfulAttempts > 0 {
		for _, k := range cutoffs {
			key := strconv.Itoa(k)
			summary.RecallAtK[key] /= float64(summary.SuccessfulAttempts)
		}
	}
	for domain, values := range summary.ByDomain {
		for _, k := range cutoffs {
			key := strconv.Itoa(k)
			values[key] /= float64(domainCounts[domain])
		}
	}
	for _, k := range cutoffs {
		key := strconv.Itoa(k)
		for _, values := range summary.ByDomain {
			summary.MacroDomainRecall[key] += values[key]
		}
		if len(summary.ByDomain) > 0 {
			summary.MacroDomainRecall[key] /= float64(len(summary.ByDomain))
		}
	}
	sort.Float64s(latencies)
	summary.LatencyP50MS = percentile(latencies, 0.50)
	summary.LatencyP95MS = percentile(latencies, 0.95)
	return summary
}

func appendJSONValue(path string, value any) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	file, err := os.OpenFile(path, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o644)
	if err != nil {
		return err
	}
	defer file.Close()
	return json.NewEncoder(file).Encode(value)
}

func writeMMDocIRReport(path string, summary mmdocirSummary) error {
	var report strings.Builder
	report.WriteString("# MMDocIR MOI Retrieval Evaluation\n\n")
	report.WriteString("- Protocol: " + summary.Protocol + "\n")
	report.WriteString("- Granularity: " + summary.Granularity + "\n")
	report.WriteString("- Embedding model: " + summary.Model + "\n")
	report.WriteString(fmt.Sprintf("- Attempts: %d (%d successful, %d failed)\n\n", summary.Attempts, summary.SuccessfulAttempts, summary.FailedAttempts))
	report.WriteString("| K | Micro Recall | Macro-domain Recall |\n|---:|---:|---:|\n")
	for _, k := range mmdocirCutoffs(summary.Granularity) {
		key := strconv.Itoa(k)
		report.WriteString(fmt.Sprintf("| %d | %.4f | %.4f |\n", k, summary.RecallAtK[key], summary.MacroDomainRecall[key]))
	}
	report.WriteString(fmt.Sprintf("\nLatency: P50 %.2f ms, P95 %.2f ms.\n", summary.LatencyP50MS, summary.LatencyP95MS))
	return writeFile(path, report.String())
}
