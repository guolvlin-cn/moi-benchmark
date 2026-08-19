package localparser

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"io"
	"os"
	"path/filepath"

	"github.com/matrixflow/moi-core/workers/go-worker/pkg/workitems/parser/clients"
)

type localFileStore struct {
	artifactDir string
}

func newLocalFileStore(artifactDir string) (*localFileStore, error) {
	absolute, err := filepath.Abs(artifactDir)
	if err != nil {
		return nil, fmt.Errorf("resolve artifact directory: %w", err)
	}
	if err := os.MkdirAll(absolute, 0o755); err != nil {
		return nil, fmt.Errorf("create artifact directory: %w", err)
	}
	return &localFileStore{artifactDir: absolute}, nil
}

func (s *localFileStore) Download(ctx context.Context, fileID string) ([]byte, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	return os.ReadFile(fileID)
}

func (s *localFileStore) DownloadLimited(ctx context.Context, fileID string, maxBytes int64) ([]byte, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	if maxBytes <= 0 {
		return s.Download(ctx, fileID)
	}
	file, err := os.Open(fileID)
	if err != nil {
		return nil, err
	}
	defer file.Close()
	data, err := io.ReadAll(io.LimitReader(file, maxBytes+1))
	if err != nil {
		return nil, err
	}
	if int64(len(data)) > maxBytes {
		return nil, fmt.Errorf("file %s exceeds %d-byte limit", fileID, maxBytes)
	}
	return data, nil
}

func (s *localFileStore) DownloadPrefix(ctx context.Context, fileID string, maxBytes int64) ([]byte, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	file, err := os.Open(fileID)
	if err != nil {
		return nil, err
	}
	defer file.Close()
	if maxBytes <= 0 {
		return []byte{}, nil
	}
	return io.ReadAll(io.LimitReader(file, maxBytes))
}

func (s *localFileStore) Upload(ctx context.Context, data []byte, filename string) (string, error) {
	if err := ctx.Err(); err != nil {
		return "", err
	}
	digest := sha256.Sum256(data)
	name := hex.EncodeToString(digest[:8]) + "-" + filepath.Base(filename)
	path := filepath.Join(s.artifactDir, name)
	if err := os.WriteFile(path, data, 0o644); err != nil {
		return "", err
	}
	return path, nil
}

type localClientProvider struct {
	files         *localFileStore
	openXML       clients.OpenXMLClient
	openXMLLayout clients.OpenXMLLayoutClient
	vlm           clients.VLMClient
	converter     clients.ConverterClient
}

func (p *localClientProvider) FileService(context.Context) (clients.FileServiceClient, error) {
	return p.files, nil
}

func (p *localClientProvider) MinerU(context.Context) (clients.MinerUClient, error) {
	return nil, backendUnavailable("MinerU")
}

func (p *localClientProvider) Paddle(context.Context) (clients.PaddleClient, error) {
	return nil, backendUnavailable("Paddle")
}

func (p *localClientProvider) VLM(context.Context) (clients.VLMClient, error) {
	if p.vlm == nil {
		return nil, backendUnavailable("VLM")
	}
	return p.vlm, nil
}

func (p *localClientProvider) OpenXML(context.Context) (clients.OpenXMLClient, error) {
	if p.openXML == nil {
		return nil, backendUnavailable("OpenXML")
	}
	return p.openXML, nil
}

func (p *localClientProvider) OpenXMLLayout(context.Context) (clients.OpenXMLLayoutClient, error) {
	if p.openXMLLayout == nil {
		return nil, backendUnavailable("OpenXML layout")
	}
	return p.openXMLLayout, nil
}

func (p *localClientProvider) UnoServer(context.Context) (clients.UnoServerClient, error) {
	return nil, backendUnavailable("UNO")
}

func (p *localClientProvider) Converter(context.Context) (clients.ConverterClient, error) {
	if p.converter == nil {
		return nil, backendUnavailable("converter")
	}
	return p.converter, nil
}

func (p *localClientProvider) WPSConverter(context.Context) (clients.ConverterClient, error) {
	return nil, backendUnavailable("WPS converter")
}

func (p *localClientProvider) SofficeConverter(context.Context) (clients.ConverterClient, error) {
	if p.converter == nil {
		return nil, backendUnavailable("LibreOffice converter")
	}
	return p.converter, nil
}

func (p *localClientProvider) AudioService(context.Context) (clients.AudioServiceClient, error) {
	return nil, backendUnavailable("audio service")
}

func (p *localClientProvider) SpreadsheetRenderer(context.Context) (clients.SpreadsheetRendererClient, error) {
	return nil, backendUnavailable("spreadsheet renderer")
}

func backendUnavailable(name string) error {
	return fmt.Errorf("%s backend is unavailable in local-native mode", name)
}
