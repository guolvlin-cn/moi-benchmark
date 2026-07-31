package main

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
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
	indexed := make([]IndexedChunk, 0, len(expanded))
	sourceByID := map[string]SourceDocument{}
	indexVersion := time.Now().UnixMilli()
	for position, document := range expanded {
		meta := document.Metadata
		fileID := firstString(meta, "file_id", "raw_file_id", "source_file_id")
		if fileID == "" {
			return nil, fmt.Errorf("expanded document %d is missing file_id", position)
		}
		fileName := firstString(meta, "file_name", "source_file_name")
		if fileName == "" {
			fileName = filepath.Base(fileID)
			meta["file_name"] = fileName
		}
		level := firstString(meta, "level")
		if level == "" {
			level = "chunk"
			meta["level"] = level
		}
		docID := firstString(meta, "doc_id")
		sectionID := firstString(meta, "section_id")
		chunkIndex := intValue(meta["chunk_index"], position)
		if value := int64Value(meta["index_version"], 0); value > 0 {
			indexVersion = value
		} else {
			meta["index_version"] = indexVersion
		}
		id := firstString(meta, "chunk_id")
		if id == "" {
			id = stableID(level, strings.Join([]string{fileID, docID, sectionID, strconv.Itoa(chunkIndex), document.Content}, "\x00"))
			meta["chunk_id"] = id
		}
		indexed = append(indexed, IndexedChunk{
			ID: id, FileID: fileID, FileName: fileName, Index: chunkIndex,
			Content: document.Content, Metadata: meta, IndexVer: indexVersion,
			ContentSHA: sha256Text(document.Content), Level: level,
			DocID: docID, SectionID: sectionID,
		})
		sourceByID[fileID] = SourceDocument{FileID: fileID, Path: fileName}
	}

	embedder, err := newEmbedder(cfg.Embedding)
	if err != nil {
		return nil, err
	}
	for start := 0; start < len(indexed); start += 32 {
		end := min(start+32, len(indexed))
		inputs := make([]string, 0, end-start)
		for _, item := range indexed[start:end] {
			inputs = append(inputs, item.Content)
		}
		vectors, err := embedder.CreateEmbedding(ctx, cfg.Workspace, cfg.Embedding.Model, inputs)
		if err != nil {
			return nil, fmt.Errorf("embed product index entries %d:%d: %w", start, end, err)
		}
		if len(vectors) != len(inputs) {
			return nil, fmt.Errorf("embedding count mismatch: got %d want %d", len(vectors), len(inputs))
		}
		for i := range vectors {
			indexed[start+i].Embedding = vectors[i]
		}
	}
	if len(indexed) == 0 || len(indexed[0].Embedding) == 0 {
		return nil, errors.New("product index produced no embedded entries")
	}
	dimension := len(indexed[0].Embedding)
	db, err := openBenchmarkDB(ctx, cfg, dimension, force)
	if err != nil {
		return nil, err
	}
	defer db.Close()
	if err := writeChunks(ctx, db, cfg.MatrixOne.VectorTable, indexed); err != nil {
		return nil, err
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
	fmt.Printf("ingested parsed_documents=%d index_entries=%d dimension=%d\n", len(documents), len(indexed), dimension)
	return state, nil
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
