package main

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/matrixflow/moi-core/model/mowl"
	"github.com/matrixflow/moi-core/workers/go-worker/pkg/workitems"
)

type parsedDocument struct {
	ID       string         `json:"id,omitempty"`
	Content  string         `json:"content"`
	Type     string         `json:"type"`
	Metadata map[string]any `json:"metadata"`
}

func ingestParsedDocuments(ctx context.Context, cfg Config, documentsPath, runDir string, force bool) (*IngestState, error) {
	documents, err := readParsedDocuments(documentsPath)
	if err != nil {
		return nil, err
	}
	return ingestProductDocuments(ctx, cfg, documents, runDir, force, nil)
}

func ingestProductDocuments(ctx context.Context, cfg Config, documents []parsedDocument, runDir string, force bool, seedSources []SourceDocument) (*IngestState, error) {
	if len(documents) == 0 {
		return nil, errors.New("parsed documents JSONL is empty")
	}
	chunked, err := productSplitDocuments(ctx, documents, cfg.ChunkSize, cfg.Overlap)
	if err != nil {
		return nil, fmt.Errorf("MatrixFlow split documents: %w", err)
	}
	expanded, err := productMultiLevelDocuments(ctx, chunked, cfg.SectionSize)
	if err != nil {
		return nil, fmt.Errorf("MatrixFlow multi-level index: %w", err)
	}
	productionDocs := make([]workitems.Document, 0, len(expanded))
	sourceByID := make(map[string]SourceDocument, len(seedSources))
	for _, source := range seedSources {
		sourceByID[source.FileID] = source
	}
	for position, document := range expanded {
		meta := document.Metadata
		if meta == nil {
			meta = map[string]any{}
			document.Metadata = meta
		}
		// Keep a corpus-global locator available for the production stable-ID
		// contract.  It is only a fallback for blocks whose parser metadata does
		// not already contain a chunk/block locator, and is important when the
		// ingest is committed in batches (the preparation helper otherwise sees a
		// batch-local position).
		if _, exists := meta["document_index"]; !exists {
			meta["document_index"] = position
		}
		fileID := firstString(meta, "file_id", "raw_file_id", "source_file_id")
		if fileID == "" {
			return nil, fmt.Errorf("expanded document %d is missing file_id", position)
		}
		fileName := firstString(meta, "file_name", "source_file_name")
		if fileName == "" {
			fileName = filepath.Base(fileID)
			meta["file_name"] = fileName
		}
		productionDocs = append(productionDocs, workitems.Document{
			ID: document.ID, Content: document.Content, Type: document.Type, Metadata: meta,
		})
		if _, exists := sourceByID[fileID]; !exists {
			sourceByID[fileID] = SourceDocument{FileID: fileID, Path: fileName}
		}
	}
	_ = writeJSON(filepath.Join(runDir, "ingest-progress.json"), map[string]any{
		"stage":            "prepared",
		"parsed_documents": len(documents),
		"expanded_entries": len(expanded),
		"embedded_entries": 0,
		"total_entries":    len(productionDocs),
	})

	indexes, inputs := workitems.CollectEmbeddingInputsForLocalRAG(productionDocs)
	if len(inputs) == 0 {
		return nil, errors.New("product index contains no non-empty text entries")
	}
	batches := splitEmbeddingInputsForLocalRAG(inputs, cfg.EmbeddingBatchSize)

	// Open the database before paying for the embedding pass.  The vector
	// index is removed by openIngestDB and rebuilt once at the end; keeping the
	// connection open also lets us commit each embedding batch immediately,
	// so a late MatrixOne restart cannot discard an otherwise completed run.
	dimension := cfg.Embedding.Dimension
	db, err := openIngestDB(ctx, cfg, dimension, force)
	if err != nil {
		return nil, err
	}
	defer db.Close()
	writePolicy := "OVERWRITE"
	if force {
		// --force has just recreated an empty table, so avoid the production
		// delete-then-insert transaction for every batch during a full rebuild.
		writePolicy = "FAIL"
	}

	embedder, err := newEmbedder(cfg.Embedding)
	if err != nil {
		return nil, err
	}
	embedded := 0
	committed := 0
	indexed := make([]IndexedChunk, 0, len(inputs))
	for batchIndex, batch := range batches {
		vectors, err := embedder.CreateEmbedding(ctx, cfg.Workspace, cfg.Embedding.Model, batch.Inputs)
		if err != nil {
			return nil, fmt.Errorf("embed product index entries %d:%d: %w", batch.Start, batch.End, err)
		}
		if len(vectors) != len(batch.Inputs) {
			return nil, fmt.Errorf("embedding count mismatch in batch %d: got %d want %d", batchIndex, len(vectors), len(batch.Inputs))
		}
		batchDocs := make([]workitems.Document, 0, len(vectors))
		for i := range vectors {
			documentIndex := indexes[batch.Start+i]
			document := productionDocs[documentIndex]
			document.Embedding = vectors[i]
			document.Metadata = workitems.MarkEmbeddedProvenanceForLocalRAG(document.Metadata)
			batchDocs = append(batchDocs, document)
		}
		vectorDocs, err := workitems.PrepareVectorDocumentsForLocalRAG(batchDocs, "", "")
		if err != nil {
			return nil, fmt.Errorf("prepare MatrixFlow vector documents for batch %d: %w", batchIndex, err)
		}
		if len(vectorDocs) == 0 {
			return nil, fmt.Errorf("product index produced no embedded entries in batch %d", batchIndex)
		}
		for _, document := range vectorDocs {
			if len(document.Embedding) != dimension {
				return nil, fmt.Errorf("embedding dimension changed within batch %d: got %d want %d", batchIndex, len(document.Embedding), dimension)
			}
		}
		written, err := workitems.UpsertVectorRowsForLocalRAG(ctx, db, cfg.MatrixOne.VectorTable, vectorDocs, writePolicy)
		if err != nil {
			return nil, fmt.Errorf("write MatrixFlow vector documents for batch %d: %w", batchIndex, err)
		}
		embedded += len(vectors)
		committed += written
		indexed = append(indexed, indexedChunksFromVectorDocsAt(vectorDocs, len(indexed))...)
		_ = writeJSON(filepath.Join(runDir, "ingest-progress.json"), map[string]any{
			"stage":             "writing",
			"parsed_documents":  len(documents),
			"expanded_entries":  len(expanded),
			"embedded_entries":  embedded,
			"total_entries":     len(inputs),
			"committed_entries": committed,
			"batch_start":       batch.Start,
			"batch_end":         batch.End,
			"batch_bytes":       batch.Bytes,
		})
		fmt.Printf("ingest_batch=%d/%d embedded=%d/%d committed=%d\n", batchIndex+1, len(batches), embedded, len(inputs), committed)
	}

	if len(indexed) == 0 || committed == 0 {
		return nil, errors.New("product index produced no embedded entries")
	}
	if err := workitems.EnsureVectorTableForLocalRAG(db, cfg.MatrixOne.VectorTable, dimension); err != nil {
		return nil, fmt.Errorf("rebuild MatrixFlow vector index after ingest: %w", err)
	}
	sources := make([]SourceDocument, 0, len(sourceByID))
	for _, source := range sourceByID {
		sources = append(sources, source)
	}
	state := &IngestState{
		SchemaVersion: schemaVersion, CreatedAt: time.Now().UTC().Format(time.RFC3339),
		Database: cfg.MatrixOne.Database, VectorTable: cfg.MatrixOne.VectorTable,
		EmbeddingModel: cfg.Embedding.Model, Dimension: dimension,
		Documents: sources, Chunks: indexed,
	}
	if err := writeJSON(filepath.Join(runDir, "ingest-state.json"), state); err != nil {
		return nil, err
	}
	_ = writeJSON(filepath.Join(runDir, "ingest-progress.json"), map[string]any{
		"stage":             "committed",
		"parsed_documents":  len(documents),
		"expanded_entries":  len(expanded),
		"embedded_entries":  embedded,
		"committed_entries": committed,
		"total_entries":     len(inputs),
	})
	fmt.Printf("ingested parsed_documents=%d index_entries=%d dimension=%d\n", len(documents), len(indexed), dimension)
	return state, nil
}

// splitEmbeddingInputsForLocalRAG keeps MatrixFlow's 256 KiB request-byte
// guard while allowing the local TaaS benchmark to use a larger input count
// per request. The production worker currently uses 64 inputs, but the
// OpenAI-compatible TaaS endpoint accepts larger batches and is less likely
// to trigger its long-run security-gateway rate heuristic when we use them.
func splitEmbeddingInputsForLocalRAG(inputs []string, maxCount int) []workitems.LocalRAGEmbeddingBatch {
	if len(inputs) == 0 {
		return nil
	}
	if maxCount <= 0 {
		maxCount = 64
	}
	const maxBytes = 256 * 1024
	batches := make([]workitems.LocalRAGEmbeddingBatch, 0, (len(inputs)+maxCount-1)/maxCount)
	start := 0
	currentBytes := 0
	for index, input := range inputs {
		inputBytes := len(input)
		currentCount := index - start
		if currentCount > 0 && (currentCount >= maxCount || currentBytes+inputBytes > maxBytes) {
			batches = append(batches, workitems.LocalRAGEmbeddingBatch{
				Start: start, End: index, Bytes: currentBytes, Inputs: inputs[start:index],
			})
			start = index
			currentBytes = 0
		}
		currentBytes += inputBytes
	}
	batches = append(batches, workitems.LocalRAGEmbeddingBatch{
		Start: start, End: len(inputs), Bytes: currentBytes, Inputs: inputs[start:],
	})
	return batches
}

func indexedChunksFromVectorDocs(documents []workitems.VectorDoc) []IndexedChunk {
	return indexedChunksFromVectorDocsAt(documents, 0)
}

func indexedChunksFromVectorDocsAt(documents []workitems.VectorDoc, positionOffset int) []IndexedChunk {
	indexed := make([]IndexedChunk, 0, len(documents))
	for position, document := range documents {
		meta := document.Metadata
		chunkIndex := positionOffset + position
		if document.ChunkIndex != nil {
			chunkIndex = *document.ChunkIndex
		}
		indexed = append(indexed, IndexedChunk{
			ID:         document.ID,
			FileID:     document.FileID,
			FileName:   firstString(meta, "file_name", "source_file_name"),
			PageNumber: intPointerValue(document.PageNumber, intValue(meta["page_num"], intValue(meta["page_number"], 0))),
			Index:      chunkIndex,
			Start:      intValue(meta["chunk_start"], 0),
			End:        intValue(meta["chunk_end"], 0),
			Content:    document.Content,
			Metadata:   meta,
			IndexVer:   document.IndexVersion,
			ContentSHA: sha256Text(document.Content),
			Level:      document.Level,
			DocID:      document.DocID,
			SectionID:  document.SectionID,
		})
	}
	return indexed
}

func intPointerValue(value *int, fallback int) int {
	if value == nil {
		return fallback
	}
	return *value
}

func readParsedDocuments(path string) ([]parsedDocument, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, fmt.Errorf("open parsed documents: %w", err)
	}
	defer file.Close()
	var documents []parsedDocument
	scanner := bufio.NewScanner(file)
	scanner.Buffer(make([]byte, 64*1024), 16*1024*1024)
	for line := 1; scanner.Scan(); line++ {
		if strings.TrimSpace(scanner.Text()) == "" {
			continue
		}
		var document parsedDocument
		if err := json.Unmarshal(scanner.Bytes(), &document); err != nil {
			return nil, fmt.Errorf("decode parsed document line %d: %w", line, err)
		}
		if document.Metadata == nil {
			document.Metadata = map[string]any{}
		}
		documents = append(documents, document)
	}
	return documents, scanner.Err()
}

func productSplitDocuments(ctx context.Context, documents []parsedDocument, chunkSize, overlap int) ([]parsedDocument, error) {
	payload, _ := json.Marshal(map[string]any{
		"documents": documents, "chunk_size": chunkSize, "overlap": overlap,
	})
	message := &mowl.MowlMessage{Data: string(payload)}
	if _, err := workitems.SplitDocumentsLength(ctx, nil, message); err != nil {
		return nil, err
	}
	var output struct {
		Documents []parsedDocument `json:"documents"`
	}
	if err := json.Unmarshal([]byte(message.Data), &output); err != nil {
		return nil, err
	}
	return output.Documents, nil
}

func productMultiLevelDocuments(ctx context.Context, documents []parsedDocument, sectionSize int) ([]parsedDocument, error) {
	payload, _ := json.Marshal(map[string]any{
		"documents": documents, "enable": true, "section_size": sectionSize,
	})
	message := &mowl.MowlMessage{Data: string(payload)}
	if _, err := (&workitems.MultiLevelIndex{}).Handle(ctx, nil, message); err != nil {
		return nil, err
	}
	var output struct {
		Documents []parsedDocument `json:"documents"`
	}
	if err := json.Unmarshal([]byte(message.Data), &output); err != nil {
		return nil, err
	}
	return output.Documents, nil
}

func firstString(values map[string]any, keys ...string) string {
	for _, key := range keys {
		if value := strings.TrimSpace(fmt.Sprint(values[key])); value != "" && value != "<nil>" {
			return value
		}
	}
	return ""
}

func intValue(value any, fallback int) int {
	switch typed := value.(type) {
	case float64:
		return int(typed)
	case int:
		return typed
	case json.Number:
		if parsed, err := typed.Int64(); err == nil {
			return int(parsed)
		}
	}
	return fallback
}

func int64Value(value any, fallback int64) int64 {
	switch typed := value.(type) {
	case float64:
		return int64(typed)
	case int64:
		return typed
	case int:
		return int64(typed)
	case json.Number:
		if parsed, err := typed.Int64(); err == nil {
			return parsed
		}
	}
	return fallback
}
