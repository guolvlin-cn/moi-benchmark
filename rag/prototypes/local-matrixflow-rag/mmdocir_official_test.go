package main

import (
	"math"
	"os"
	"path/filepath"
	"testing"
)

func TestMMDocIRPageRecall(t *testing.T) {
	question := mmdocirQuestion{PageIDs: []int{2, 5}}
	hits := []mmdocirHit{{PageID: 5}, {PageID: 7}, {PageID: 2}}
	if got := scoreMMDocIR(question, hits, "page", 1); got != 0.5 {
		t.Fatalf("Recall@1=%v, want 0.5", got)
	}
	if got := scoreMMDocIR(question, hits, "page", 3); got != 1 {
		t.Fatalf("Recall@3=%v, want 1", got)
	}
}

func TestMMDocIRLayoutRecallMatchesOfficialOverlapRule(t *testing.T) {
	question := mmdocirQuestion{LayoutMapping: []mmdocirLayoutGold{{Page: 3, BBox: []float64{0, 0, 10, 10}}}}
	hits := []mmdocirHit{{PageID: 3, BBox: []float64{0, 0, 5, 10}}}
	if got := scoreMMDocIR(question, hits, "layout", 1); math.Abs(got-0.5) > 1e-9 {
		t.Fatalf("layout Recall@1=%v, want 0.5", got)
	}
}

func TestMMDocIRCutoffs(t *testing.T) {
	if got := mmdocirCutoffs("page"); len(got) != 3 || got[0] != 1 || got[1] != 3 || got[2] != 5 {
		t.Fatalf("page cutoffs=%v", got)
	}
	if got := mmdocirCutoffs("layout"); len(got) != 3 || got[0] != 1 || got[1] != 5 || got[2] != 10 {
		t.Fatalf("layout cutoffs=%v", got)
	}
}

func TestMMDocIREmptyEmbeddingInputUsesInvisiblePlaceholder(t *testing.T) {
	if got := mmdocirEmbeddingInput(""); got != "\u2060" {
		t.Fatalf("empty embedding input=%q", got)
	}
	if got := mmdocirEmbeddingInput("evidence"); got != "evidence" {
		t.Fatalf("non-empty embedding input=%q", got)
	}
}

func TestLoadMMDocIRResumeProgress(t *testing.T) {
	path := filepath.Join(t.TempDir(), "progress.json")
	if err := os.WriteFile(path, []byte(`{"stage":"writing","embedded":3879,"committed":3879,"total":170338}`), 0o644); err != nil {
		t.Fatal(err)
	}
	got, err := loadMMDocIRResumeProgress(path, 170338)
	if err != nil {
		t.Fatal(err)
	}
	if got != 3879 {
		t.Fatalf("resume=%d, want 3879", got)
	}
}
