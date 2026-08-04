package main

import (
	"os"
	"path/filepath"
	"testing"
)

func TestResolveEnvValueReadsRequestedKeyOnly(t *testing.T) {
	t.Setenv("MINERU_API_TOKEN", "")
	path := filepath.Join(t.TempDir(), ".env")
	if err := os.WriteFile(path, []byte("TAAS_API_KEY=not-this-one\nexport MINERU_API_TOKEN='mineru-secret'\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	value, err := resolveEnvValue("MINERU_API_TOKEN", path)
	if err != nil {
		t.Fatal(err)
	}
	if value != "mineru-secret" {
		t.Fatalf("value = %q", value)
	}
}

func TestResolveEnvValuePrefersProcessEnvironment(t *testing.T) {
	t.Setenv("MINERU_API_TOKEN", "process-secret")
	value, err := resolveEnvValue("MINERU_API_TOKEN", filepath.Join(t.TempDir(), "missing.env"))
	if err != nil {
		t.Fatal(err)
	}
	if value != "process-secret" {
		t.Fatalf("value = %q", value)
	}
}

func TestResolveOptionalEnvValueAllowsMissingKey(t *testing.T) {
	value, err := resolveOptionalEnvValue("OPENXML_BASE_URL", filepath.Join(t.TempDir(), "missing.env"))
	if err != nil {
		t.Fatal(err)
	}
	if value != "" {
		t.Fatalf("value = %q", value)
	}
}
