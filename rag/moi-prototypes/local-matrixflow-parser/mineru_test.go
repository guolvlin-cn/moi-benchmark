package localparser

import (
	"archive/zip"
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestParseFileMinerUPrecisionPipeline(t *testing.T) {
	archive := testMarkdownZIPWithImages(t, "# Precision title\n\nPrecision body.\n\n![](images/figure.jpg)\n", map[string][]byte{
		"images/figure.jpg": []byte("fake-image-bytes"),
	})
	var server *httptest.Server
	server = httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodPost && r.URL.Path == "/api/v4/file-urls/batch":
			if r.Header.Get("Authorization") != "Bearer precision-token" {
				t.Fatalf("authorization = %q", r.Header.Get("Authorization"))
			}
			var payload map[string]any
			if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
				t.Fatal(err)
			}
			if payload["model_version"] != "vlm" {
				t.Fatalf("model_version = %v", payload["model_version"])
			}
			writeTestJSON(t, w, map[string]any{
				"code": 0, "trace_id": "create-trace",
				"data": map[string]any{"batch_id": "batch-1", "file_urls": []string{server.URL + "/upload"}},
			})
		case r.Method == http.MethodPut && r.URL.Path == "/upload":
			body, err := io.ReadAll(r.Body)
			if err != nil {
				t.Fatal(err)
			}
			if string(body) != "fake pdf" {
				t.Fatalf("upload = %q", body)
			}
			w.WriteHeader(http.StatusOK)
		case r.Method == http.MethodGet && r.URL.Path == "/api/v4/extract-results/batch/batch-1":
			writeTestJSON(t, w, map[string]any{
				"code": 0, "trace_id": "result-trace",
				"data": map[string]any{"batch_id": "batch-1", "extract_result": []map[string]any{{
					"file_name": "sample.pdf", "state": "done", "full_zip_url": server.URL + "/result.zip",
				}}},
			})
		case r.Method == http.MethodGet && r.URL.Path == "/result.zip":
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write(archive)
		default:
			http.NotFound(w, r)
		}
	}))
	defer server.Close()

	source := filepath.Join(t.TempDir(), "sample.pdf")
	if err := os.WriteFile(source, []byte("fake pdf"), 0o644); err != nil {
		t.Fatal(err)
	}
	artifactDir := t.TempDir()
	result, err := New().ParseFile(context.Background(), source, Options{
		Pipeline:    PipelinePrecision,
		ArtifactDir: artifactDir,
		MinerU: MinerUOptions{
			Token: "precision-token", BaseURL: server.URL, HTTPClient: server.Client(),
			PollInterval: time.Millisecond, Timeout: time.Second,
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	if result.Engine != EngineMinerUPrecision || result.Remote == nil {
		t.Fatalf("engine=%q remote=%+v", result.Engine, result.Remote)
	}
	if result.Remote.BatchID != "batch-1" || result.Remote.TraceID != "result-trace" {
		t.Fatalf("remote = %+v", result.Remote)
	}
	if len(result.Documents) == 0 || !strings.Contains(result.Documents[0].Content, "Precision") {
		t.Fatalf("documents = %+v", result.Documents)
	}
	if result.Documents[0].Metadata["source_path"] != source {
		t.Fatalf("source metadata = %v", result.Documents[0].Metadata["source_path"])
	}
	imagePath := filepath.Join(artifactDir, "images", "figure.jpg")
	image, err := os.ReadFile(imagePath)
	if err != nil {
		t.Fatalf("read extracted MinerU image %s: %v", imagePath, err)
	}
	if string(image) != "fake-image-bytes" {
		t.Fatalf("extracted image = %q", image)
	}
	foundImageBlock := false
	for _, document := range result.Documents {
		if document.Type == "image" && document.Metadata["image_url"] == "images/figure.jpg" {
			foundImageBlock = true
			break
		}
	}
	if !foundImageBlock {
		t.Fatalf("image block was not returned: %+v", result.Documents)
	}
}

func TestParseFileMinerUAgentPipeline(t *testing.T) {
	var server *httptest.Server
	server = httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "" {
			t.Fatalf("Agent request unexpectedly authenticated")
		}
		switch {
		case r.Method == http.MethodPost && r.URL.Path == "/api/v1/agent/parse/file":
			writeTestJSON(t, w, map[string]any{
				"code": 0, "trace_id": "agent-create",
				"data": map[string]any{"task_id": "task-1", "file_url": server.URL + "/agent-upload"},
			})
		case r.Method == http.MethodPut && r.URL.Path == "/agent-upload":
			w.WriteHeader(http.StatusOK)
		case r.Method == http.MethodGet && r.URL.Path == "/api/v1/agent/parse/task-1":
			writeTestJSON(t, w, map[string]any{
				"code": 0, "trace_id": "agent-result",
				"data": map[string]any{"task_id": "task-1", "state": "done", "markdown_url": server.URL + "/full.md"},
			})
		case r.Method == http.MethodGet && r.URL.Path == "/full.md":
			_, _ = w.Write([]byte("# Agent title\n\nAgent body.\n"))
		default:
			http.NotFound(w, r)
		}
	}))
	defer server.Close()

	source := filepath.Join(t.TempDir(), "sample.docx")
	if err := os.WriteFile(source, []byte("fake office"), 0o644); err != nil {
		t.Fatal(err)
	}
	result, err := New().ParseFile(context.Background(), source, Options{
		Pipeline:    PipelineAgent,
		ArtifactDir: t.TempDir(),
		MinerU: MinerUOptions{
			BaseURL: server.URL, HTTPClient: server.Client(), PollInterval: time.Millisecond, Timeout: time.Second,
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	if result.Engine != EngineMinerUAgent || result.Remote == nil || result.Remote.TaskID != "task-1" {
		t.Fatalf("result = %+v", result)
	}
	if len(result.Documents) == 0 || !strings.Contains(result.Documents[0].Content, "Agent") {
		t.Fatalf("documents = %+v", result.Documents)
	}
}

func TestPrecisionPipelineRequiresToken(t *testing.T) {
	t.Setenv("MINERU_API_TOKEN", "")
	source := filepath.Join(t.TempDir(), "sample.pdf")
	if err := os.WriteFile(source, []byte("fake pdf"), 0o644); err != nil {
		t.Fatal(err)
	}
	_, err := New().ParseFile(context.Background(), source, Options{Pipeline: PipelinePrecision})
	if err == nil || !strings.Contains(err.Error(), "MINERU_API_TOKEN") {
		t.Fatalf("error = %v", err)
	}
}

func TestMarkdownFromZIPRejectsTraversal(t *testing.T) {
	var buffer bytes.Buffer
	writer := zip.NewWriter(&buffer)
	entry, err := writer.Create("../full.md")
	if err != nil {
		t.Fatal(err)
	}
	_, _ = entry.Write([]byte("unsafe"))
	if err := writer.Close(); err != nil {
		t.Fatal(err)
	}
	if _, err := markdownFromZIP(buffer.Bytes(), 1024); err == nil {
		t.Fatal("unsafe ZIP path was accepted")
	}
}

func TestDownloadFallsBackToWgetOnTransportFailure(t *testing.T) {
	wget := filepath.Join(t.TempDir(), "wget")
	if err := os.WriteFile(wget, []byte("#!/bin/sh\nprintf 'downloaded by fallback'\n"), 0o700); err != nil {
		t.Fatal(err)
	}
	client := &minerUClient{
		httpClient: &http.Client{Transport: roundTripperFunc(func(*http.Request) (*http.Response, error) {
			return nil, errors.New("TLS EOF")
		})},
		wgetPath: wget,
	}
	raw, via, err := client.download(context.Background(), "https://cdn.example.com/result.md", 1024)
	if err != nil {
		t.Fatal(err)
	}
	if via != "wget" || string(raw) != "downloaded by fallback" {
		t.Fatalf("via=%q raw=%q", via, raw)
	}
}

func TestDownloadRejectsCrossHostRedirect(t *testing.T) {
	redirectTarget := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		t.Fatal("redirect target was contacted")
	}))
	defer redirectTarget.Close()
	redirectSource := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Redirect(w, r, redirectTarget.URL, http.StatusFound)
	}))
	defer redirectSource.Close()

	client := &minerUClient{httpClient: redirectSource.Client()}
	if _, _, err := client.download(context.Background(), redirectSource.URL, 1024); err == nil || !strings.Contains(err.Error(), "unsafe HTTP redirect") {
		t.Fatalf("error = %v", err)
	}
}

func TestUploadRejectsCrossHostRedirect(t *testing.T) {
	redirectTarget := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		t.Fatal("redirect target was contacted")
	}))
	defer redirectTarget.Close()
	redirectSource := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Redirect(w, r, redirectTarget.URL, http.StatusFound)
	}))
	defer redirectSource.Close()

	source := filepath.Join(t.TempDir(), "sample.pdf")
	if err := os.WriteFile(source, []byte("fake pdf"), 0o644); err != nil {
		t.Fatal(err)
	}
	client := &minerUClient{httpClient: redirectSource.Client()}
	if err := client.uploadFile(context.Background(), redirectSource.URL, source); err == nil || !strings.Contains(err.Error(), "unsafe HTTP redirect") {
		t.Fatalf("error = %v", err)
	}
}

func TestDownloadDoesNotFallbackOnHTTPStatus(t *testing.T) {
	wget := filepath.Join(t.TempDir(), "wget")
	marker := filepath.Join(t.TempDir(), "called")
	script := "#!/bin/sh\ntouch '" + marker + "'\n"
	if err := os.WriteFile(wget, []byte(script), 0o700); err != nil {
		t.Fatal(err)
	}
	client := &minerUClient{
		httpClient: &http.Client{Transport: roundTripperFunc(func(*http.Request) (*http.Response, error) {
			return &http.Response{StatusCode: http.StatusForbidden, Body: io.NopCloser(strings.NewReader("forbidden"))}, nil
		})},
		wgetPath: wget,
	}
	if _, _, err := client.download(context.Background(), "https://cdn.example.com/result.md", 1024); err == nil {
		t.Fatal("HTTP error was accepted")
	}
	if _, err := os.Stat(marker); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("wget fallback unexpectedly executed: %v", err)
	}
}

func TestDownloadWgetFallbackEnforcesSizeLimit(t *testing.T) {
	wget := filepath.Join(t.TempDir(), "wget")
	if err := os.WriteFile(wget, []byte("#!/bin/sh\nprintf 'content-too-large'\n"), 0o700); err != nil {
		t.Fatal(err)
	}
	client := &minerUClient{
		httpClient: &http.Client{Transport: roundTripperFunc(func(*http.Request) (*http.Response, error) {
			return nil, errors.New("TLS EOF")
		})},
		wgetPath: wget,
	}
	if _, _, err := client.download(context.Background(), "https://cdn.example.com/result.md", 4); err == nil || !strings.Contains(err.Error(), "exceeds 4-byte limit") {
		t.Fatalf("error = %v", err)
	}
}

func TestWgetFallbackReadsURLFromStdin(t *testing.T) {
	temporary := t.TempDir()
	argsPath := filepath.Join(temporary, "args")
	stdinPath := filepath.Join(temporary, "stdin")
	wget := filepath.Join(temporary, "wget")
	script := "#!/bin/sh\nprintf '%s\\n' \"$@\" > '" + argsPath + "'\ncat > '" + stdinPath + "'\nprintf 'downloaded'\n"
	if err := os.WriteFile(wget, []byte(script), 0o700); err != nil {
		t.Fatal(err)
	}
	client := &minerUClient{
		httpClient: &http.Client{Transport: roundTripperFunc(func(*http.Request) (*http.Response, error) {
			return nil, errors.New("TLS EOF")
		})},
		wgetPath: wget,
	}
	rawURL := "https://cdn.example.com/result.md?X-Amz-Signature=secret"
	if _, _, err := client.download(context.Background(), rawURL, 1024); err != nil {
		t.Fatal(err)
	}
	args, err := os.ReadFile(argsPath)
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(args), rawURL) {
		t.Fatalf("signed URL appeared in wget arguments: %q", args)
	}
	stdin, err := os.ReadFile(stdinPath)
	if err != nil {
		t.Fatal(err)
	}
	if string(stdin) != rawURL+"\n" {
		t.Fatalf("wget stdin = %q", stdin)
	}
}

func TestSafeDownloaderEnvironmentExcludesAPITokens(t *testing.T) {
	t.Setenv("MINERU_API_TOKEN", "mineru-secret")
	t.Setenv("TAAS_API_KEY", "taas-secret")
	joined := strings.Join(safeDownloaderEnvironment(), "\n")
	if strings.Contains(joined, "mineru-secret") || strings.Contains(joined, "taas-secret") {
		t.Fatal("download subprocess inherited an API token")
	}
}

type roundTripperFunc func(*http.Request) (*http.Response, error)

func (function roundTripperFunc) RoundTrip(request *http.Request) (*http.Response, error) {
	return function(request)
}

func testMarkdownZIP(t *testing.T, markdown string) []byte {
	return testMarkdownZIPWithImages(t, markdown, nil)
}

func testMarkdownZIPWithImages(t *testing.T, markdown string, images map[string][]byte) []byte {
	t.Helper()
	var buffer bytes.Buffer
	writer := zip.NewWriter(&buffer)
	entry, err := writer.Create("result/full.md")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := entry.Write([]byte(markdown)); err != nil {
		t.Fatal(err)
	}
	for name, content := range images {
		entry, err := writer.Create(name)
		if err != nil {
			t.Fatal(err)
		}
		if _, err := entry.Write(content); err != nil {
			t.Fatal(err)
		}
	}
	if err := writer.Close(); err != nil {
		t.Fatal(err)
	}
	return buffer.Bytes()
}

func writeTestJSON(t *testing.T, writer http.ResponseWriter, value any) {
	t.Helper()
	writer.Header().Set("Content-Type", "application/json")
	if err := json.NewEncoder(writer).Encode(value); err != nil {
		t.Fatal(err)
	}
}
