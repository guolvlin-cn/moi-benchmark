package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/matrixflow/moi-core/agent-tools/knowledge"
	knowledgeservice "github.com/matrixflow/moi-core/agent-tools/knowledge/service"
)

type ExploreResult struct {
	Question        string                 `json:"question"`
	Answer          string                 `json:"answer"`
	SelectedSources []map[string]any       `json:"selected_sources"`
	ToolTrace       []ExploreToolTraceItem `json:"tool_trace"`
	DurationMS      float64                `json:"duration_ms"`
}

type ExploreToolTraceItem struct {
	Name       string          `json:"name"`
	Arguments  json.RawMessage `json:"arguments"`
	Result     any             `json:"result"`
	DurationMS float64         `json:"duration_ms"`
}

type exploreMessage struct {
	Role       string            `json:"role"`
	Content    string            `json:"content,omitempty"`
	ToolCallID string            `json:"tool_call_id,omitempty"`
	Name       string            `json:"name,omitempty"`
	ToolCalls  []exploreToolCall `json:"tool_calls,omitempty"`
}

type exploreToolCall struct {
	ID       string `json:"id"`
	Type     string `json:"type"`
	Function struct {
		Name      string `json:"name"`
		Arguments string `json:"arguments"`
	} `json:"function"`
}

func runExploreQuestion(ctx context.Context, cfg Config, question string) (*ExploreResult, error) {
	if !cfg.Generation.Enabled || cfg.Generation.BaseURL == "" || cfg.Generation.Model == "" {
		return nil, errors.New("Explore QA requires generation.enabled=true with base_url and model")
	}
	promptPath := filepath.Join(cfg.MatrixFlowRoot, "moi-core/catalog/pkg/agentresource/systemagents/knowledge-explore/system_prompt.zh-CN.md")
	prompt, err := os.ReadFile(promptPath)
	if err != nil {
		return nil, fmt.Errorf("read MatrixFlow Explore system prompt: %w", err)
	}
	embedder, err := newEmbedder(cfg.Embedding)
	if err != nil {
		return nil, err
	}
	db, err := openBenchmarkDB(ctx, cfg, cfg.Embedding.Dimension, false)
	if err != nil {
		return nil, err
	}
	defer db.Close()
	executor := matrixOneExecutor{db: db}
	finder := knowledgeservice.NewFindRAGFiles(knowledgeservice.Deps{SQLExecutor: executor})
	searcher := knowledgeservice.NewSearchRAGChunks(knowledgeservice.Deps{
		SQLExecutor: executor, Embedder: embedder,
		DefaultRetrieverConfig: knowledge.RetrieverConfig{EmbeddingModel: cfg.Embedding.Model},
	})
	scope := knowledge.WorkspaceScope{
		WorkspaceID: cfg.Workspace, DBName: cfg.MatrixOne.Database,
		VectorTable: cfg.MatrixOne.VectorTable, EmbeddingModel: cfg.Embedding.Model,
	}
	messages := []exploreMessage{
		{Role: "system", Content: string(prompt)},
		{Role: "user", Content: question},
	}
	started := time.Now()
	result := &ExploreResult{Question: question}
	retrievalCompleted := false
	sourcesSelected := false
	allowedChunkIDs := map[string]struct{}{}
	for turn := 0; turn < 10; turn++ {
		assistant, err := callExploreModel(ctx, cfg.Generation, messages)
		if err != nil {
			return nil, err
		}
		messages = append(messages, assistant)
		if len(assistant.ToolCalls) == 0 {
			if strings.TrimSpace(assistant.Content) == "" {
				return nil, errors.New("Explore model returned neither content nor tool calls")
			}
			if !sourcesSelected {
				repair := knowledge.SelectFinalSourcesRepairPrompt
				if !retrievalCompleted {
					repair = knowledge.SubmitFinalAnswerEvidenceRepairPrompt
				}
				messages = append(messages, exploreMessage{Role: "system", Content: repair})
				continue
			}
			result.Answer = assistant.Content
			result.DurationMS = float64(time.Since(started).Microseconds()) / 1000
			return result, nil
		}
		for _, call := range assistant.ToolCalls {
			toolStarted := time.Now()
			var value any
			switch call.Function.Name {
			case "find_rag_files":
				var args struct {
					Query string `json:"query"`
					TopK  int    `json:"top_k"`
				}
				if err := json.Unmarshal([]byte(call.Function.Arguments), &args); err != nil {
					return nil, fmt.Errorf("decode find_rag_files arguments: %w", err)
				}
				value, err = finder.Execute(ctx, knowledge.FindRAGFilesRequest{
					Scope: scope, Query: args.Query, MaxFiles: args.TopK,
				})
			case "search_rag_chunks":
				var args struct {
					Keywords []string `json:"keywords"`
					FileIDs  []string `json:"file_ids"`
					MaxHits  int      `json:"max_hits"`
					MaxRows  int      `json:"max_rows"`
					Before   int      `json:"before"`
					After    int      `json:"after"`
				}
				if err := json.Unmarshal([]byte(call.Function.Arguments), &args); err != nil {
					return nil, fmt.Errorf("decode search_rag_chunks arguments: %w", err)
				}
				searchResponse, searchErr := searcher.Execute(ctx, knowledge.SearchRAGChunksRequest{
					Scope: scope, Keywards: args.Keywords, FileIDs: args.FileIDs,
					MaxHits: args.MaxHits, MaxRows: args.MaxRows, Before: args.Before, After: args.After,
				})
				err = searchErr
				value = searchResponse
				if searchErr == nil && searchResponse != nil {
					retrievalCompleted = true
					for _, chunk := range searchResponse.Chunks {
						if strings.TrimSpace(chunk.ChunkID) != "" {
							allowedChunkIDs[chunk.ChunkID] = struct{}{}
						}
					}
				}
			case "select_final_sources":
				var args struct {
					Sources []map[string]any `json:"sources"`
				}
				if err := json.Unmarshal([]byte(call.Function.Arguments), &args); err != nil {
					return nil, fmt.Errorf("decode select_final_sources arguments: %w", err)
				}
				if !retrievalCompleted {
					value = map[string]any{"ok": false, "error": "select_final_sources requires a completed search_rag_chunks call"}
					break
				}
				if invalid := invalidSelectedChunkID(args.Sources, allowedChunkIDs); invalid != "" {
					value = map[string]any{"ok": false, "error": "unknown RAG chunk id: " + invalid}
					break
				}
				result.SelectedSources = args.Sources
				sourcesSelected = true
				value = map[string]any{"ok": true, "selected": len(args.Sources)}
			default:
				err = fmt.Errorf("unsupported Explore tool %q", call.Function.Name)
			}
			if err != nil {
				return nil, err
			}
			rawArgs := json.RawMessage(call.Function.Arguments)
			result.ToolTrace = append(result.ToolTrace, ExploreToolTraceItem{
				Name: call.Function.Name, Arguments: rawArgs, Result: value,
				DurationMS: float64(time.Since(toolStarted).Microseconds()) / 1000,
			})
			toolJSON, _ := json.Marshal(value)
			messages = append(messages, exploreMessage{
				Role: "tool", ToolCallID: call.ID, Name: call.Function.Name, Content: string(toolJSON),
			})
		}
	}
	return nil, errors.New("Explore Agent exceeded 10 tool turns")
}

func invalidSelectedChunkID(sources []map[string]any, allowed map[string]struct{}) string {
	for _, source := range sources {
		if chunkID := strings.TrimSpace(fmt.Sprint(source["chunk_id"])); chunkID != "" && chunkID != "<nil>" {
			if _, ok := allowed[chunkID]; !ok {
				return chunkID
			}
		}
		if values, ok := source["chunk_ids"].([]any); ok {
			for _, value := range values {
				chunkID := strings.TrimSpace(fmt.Sprint(value))
				if _, exists := allowed[chunkID]; !exists {
					return chunkID
				}
			}
		}
	}
	return ""
}

func callExploreModel(ctx context.Context, cfg GenerationConfig, messages []exploreMessage) (exploreMessage, error) {
	payload := map[string]any{
		"model": cfg.Model, "messages": messages, "temperature": 0, "stream": false,
		"tools": exploreToolDefinitions(), "tool_choice": "auto",
	}
	var response struct {
		Choices []struct {
			Message exploreMessage `json:"message"`
		} `json:"choices"`
	}
	client := &http.Client{
		Timeout:   time.Duration(cfg.TimeoutSeconds) * time.Second,
		Transport: newHTTPTransport(strings.EqualFold(strings.TrimSpace(cfg.Provider), "taas")),
	}
	if err := postOpenAIJSON(ctx, client, cfg.BaseURL, "/chat/completions", cfg.APIKeyEnv, payload, &response); err != nil {
		return exploreMessage{}, err
	}
	if len(response.Choices) == 0 {
		return exploreMessage{}, errors.New("Explore chat completion returned no choices")
	}
	return response.Choices[0].Message, nil
}

func exploreToolDefinitions() []map[string]any {
	function := func(name, description string, parameters map[string]any) map[string]any {
		return map[string]any{"type": "function", "function": map[string]any{
			"name": name, "description": description, "parameters": parameters,
		}}
	}
	return []map[string]any{
		function("find_rag_files", "Locate candidate source files in the selected knowledge base.", map[string]any{
			"type": "object", "properties": map[string]any{
				"query": map[string]any{"type": "string"},
				"top_k": map[string]any{"type": "integer", "minimum": 1},
			}, "required": []string{"query"},
		}),
		function("search_rag_chunks", "Search primary document evidence using MatrixFlow full-text and vector routes.", map[string]any{
			"type": "object", "properties": map[string]any{
				"keywords": map[string]any{"type": "array", "items": map[string]any{"type": "string"}},
				"file_ids": map[string]any{"type": "array", "items": map[string]any{"type": "string"}},
				"max_hits": map[string]any{"type": "integer", "minimum": 1},
				"max_rows": map[string]any{"type": "integer", "minimum": 1},
				"before":   map[string]any{"type": "integer", "minimum": 0},
				"after":    map[string]any{"type": "integer", "minimum": 0},
			}, "required": []string{"keywords", "max_hits"},
		}),
		function("select_final_sources", "Select only evidence that supports the final answer.", map[string]any{
			"type": "object", "properties": map[string]any{
				"sources": map[string]any{"type": "array", "items": map[string]any{
					"type": "object", "properties": map[string]any{
						"type":      map[string]any{"type": "string", "enum": []string{"rag_chunk"}},
						"chunk_id":  map[string]any{"type": "string"},
						"chunk_ids": map[string]any{"type": "array", "items": map[string]any{"type": "string"}},
					}, "required": []string{"type"},
				}},
			}, "required": []string{"sources"},
		}),
	}
}
