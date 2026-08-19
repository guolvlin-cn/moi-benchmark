package localparser

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestParseFileExecutesMatrixFlowNativeMarkdownParser(t *testing.T) {
	root := t.TempDir()
	source := filepath.Join(root, "sample.md")
	content := "# Product parser\n\nBody text.\n\n| A | B |\n| - | - |\n| 1 | 2 |\n"
	if err := os.WriteFile(source, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}
	result, err := New().ParseFile(context.Background(), source, Options{
		ArtifactDir: filepath.Join(root, "artifacts"),
	})
	if err != nil {
		t.Fatal(err)
	}
	if result.Metadata.ParserVersion != "v3" {
		t.Fatalf("parser version = %q, want v3", result.Metadata.ParserVersion)
	}
	if result.Metadata.BackendUsed != "native-text" {
		t.Fatalf("backend = %q, want native-text", result.Metadata.BackendUsed)
	}
	var title, table bool
	for _, document := range result.Documents {
		switch document.Type {
		case "title":
			title = strings.Contains(document.Content, "Product parser")
		case "table":
			table = strings.Contains(document.Content, "<table>")
		}
	}
	if !title || !table {
		t.Fatalf("MatrixFlow Markdown blocks missing: title=%v table=%v documents=%+v", title, table, result.Documents)
	}
}

func TestParseFileRejectsBackendDependentFormat(t *testing.T) {
	source := filepath.Join(t.TempDir(), "sample.docx")
	if err := os.WriteFile(source, []byte("not a real docx"), 0o644); err != nil {
		t.Fatal(err)
	}
	_, err := New().ParseFile(context.Background(), source, Options{})
	if err == nil || !strings.Contains(err.Error(), "requires a MatrixFlow parser backend") {
		t.Fatalf("error = %v, want explicit backend dependency error", err)
	}
}

func TestLocalFileStoreEnforcesBoundedDownload(t *testing.T) {
	root := t.TempDir()
	source := filepath.Join(root, "source.txt")
	if err := os.WriteFile(source, []byte("12345"), 0o644); err != nil {
		t.Fatal(err)
	}
	store, err := newLocalFileStore(filepath.Join(root, "artifacts"))
	if err != nil {
		t.Fatal(err)
	}
	if _, err := store.DownloadLimited(context.Background(), source, 4); err == nil {
		t.Fatal("bounded download accepted an oversized file")
	}
	prefix, err := store.DownloadPrefix(context.Background(), source, 3)
	if err != nil {
		t.Fatal(err)
	}
	if string(prefix) != "123" {
		t.Fatalf("prefix = %q, want 123", prefix)
	}
}
