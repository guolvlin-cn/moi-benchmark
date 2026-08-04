package localparser

import (
	"context"
	"encoding/json"
	"image"
	"image/color"
	"image/png"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestParseTaaSVLMNormalizesMarkdownThroughMatrixFlow(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost || r.URL.Path != "/v1/chat/completions" {
			t.Fatalf("request = %s %s", r.Method, r.URL.Path)
		}
		if got := r.Header.Get("Authorization"); got != "Bearer taas-test-key" {
			t.Fatalf("Authorization = %q", got)
		}
		var body struct {
			Model    string `json:"model"`
			Messages []struct {
				Content []map[string]any `json:"content"`
			} `json:"messages"`
		}
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			t.Fatal(err)
		}
		if body.Model != "qwen3-vl-plus" {
			t.Fatalf("model = %q", body.Model)
		}
		if len(body.Messages) != 1 || len(body.Messages[0].Content) != 2 {
			t.Fatalf("messages = %#v", body.Messages)
		}
		imageURL, ok := body.Messages[0].Content[0]["image_url"].(map[string]any)
		if !ok || !strings.HasPrefix(imageURL["url"].(string), "data:image/png;base64,") {
			t.Fatalf("image content = %#v", body.Messages[0].Content[0])
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"choices":[{"message":{"content":"# Invoice\n\n| Item | Amount |\n| --- | ---: |\n| Test | 42 |"}}]}`))
	}))
	defer server.Close()

	tempDir := t.TempDir()
	imagePath := filepath.Join(tempDir, "invoice.png")
	file, err := os.Create(imagePath)
	if err != nil {
		t.Fatal(err)
	}
	picture := image.NewRGBA(image.Rect(0, 0, 2, 2))
	picture.Set(0, 0, color.White)
	if err := png.Encode(file, picture); err != nil {
		_ = file.Close()
		t.Fatal(err)
	}
	if err := file.Close(); err != nil {
		t.Fatal(err)
	}

	result, err := New().ParseFile(context.Background(), imagePath, Options{
		Pipeline:    PipelineVLM,
		ArtifactDir: filepath.Join(tempDir, "artifacts"),
		VLM: VLMOptions{
			APIKey:  "taas-test-key",
			BaseURL: server.URL + "/v1",
			Model:   "qwen3-vl-plus",
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	if result.Engine != EngineTaaSVLM || result.VLM == nil || result.VLM.Model != "qwen3-vl-plus" {
		t.Fatalf("result metadata = %+v", result)
	}
	if len(result.Documents) == 0 || !strings.Contains(result.PlainText, "Invoice") {
		t.Fatalf("documents = %#v, plain text = %q", result.Documents, result.PlainText)
	}
	markdown, err := os.ReadFile(result.MDFileID)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(markdown), "| Test | 42 |") {
		t.Fatalf("markdown = %q", markdown)
	}
}
