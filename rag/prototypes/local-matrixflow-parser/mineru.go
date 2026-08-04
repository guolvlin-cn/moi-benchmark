package localparser

import (
	"archive/zip"
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"
)

const (
	defaultMinerUBaseURL       = "https://mineru.net"
	defaultMinerUPollInterval  = 3 * time.Second
	defaultMinerUTimeout       = 15 * time.Minute
	defaultMinerUResponseLimit = 4 << 20
	defaultMinerUArchiveLimit  = 256 << 20
	defaultMinerUMarkdownLimit = 64 << 20
	precisionSourceLimit       = 200 << 20
	agentSourceLimit           = 10 << 20
)

var errUnsafeRedirect = errors.New("unsafe HTTP redirect")

type MinerUOptions struct {
	Token            string
	BaseURL          string
	HTTPClient       *http.Client
	PollInterval     time.Duration
	Timeout          time.Duration
	MaxArchiveBytes  int64
	MaxMarkdownBytes int64
}

type MinerURunMetadata struct {
	Provider     string  `json:"provider"`
	Pipeline     string  `json:"pipeline"`
	Model        string  `json:"model,omitempty"`
	TaskID       string  `json:"task_id,omitempty"`
	BatchID      string  `json:"batch_id,omitempty"`
	TraceID      string  `json:"trace_id,omitempty"`
	UploadMS     float64 `json:"upload_ms"`
	ProcessingMS float64 `json:"processing_ms"`
	DownloadMS   float64 `json:"download_ms"`
	DownloadVia  string  `json:"download_via,omitempty"`
}

type minerUClient struct {
	baseURL          string
	token            string
	httpClient       *http.Client
	pollInterval     time.Duration
	maxArchiveBytes  int64
	maxMarkdownBytes int64
	wgetPath         string
}

type minerUEnvelope[T any] struct {
	Code    int    `json:"code"`
	Msg     string `json:"msg"`
	TraceID string `json:"trace_id"`
	Data    T      `json:"data"`
}

type precisionCreateData struct {
	BatchID  string   `json:"batch_id"`
	FileURLs []string `json:"file_urls"`
}

type precisionResultData struct {
	BatchID       string                   `json:"batch_id"`
	ExtractResult []precisionExtractResult `json:"extract_result"`
}

type precisionExtractResult struct {
	FileName   string `json:"file_name"`
	State      string `json:"state"`
	FullZIPURL string `json:"full_zip_url"`
	Error      string `json:"err_msg"`
}

type agentCreateData struct {
	TaskID  string `json:"task_id"`
	FileURL string `json:"file_url"`
}

type agentResultData struct {
	TaskID      string `json:"task_id"`
	State       string `json:"state"`
	MarkdownURL string `json:"markdown_url"`
	ErrorCode   int    `json:"err_code"`
	Error       string `json:"err_msg"`
}

func (p *Parser) parseMinerU(ctx context.Context, sourcePath, fileType, pipeline string, opts Options) (*Result, error) {
	info, err := os.Stat(sourcePath)
	if err != nil {
		return nil, fmt.Errorf("stat MinerU source: %w", err)
	}
	if pipeline == PipelinePrecision && info.Size() > precisionSourceLimit {
		return nil, fmt.Errorf("MinerU precision source exceeds %d-byte limit", precisionSourceLimit)
	}
	if pipeline == PipelineAgent && info.Size() > agentSourceLimit {
		return nil, fmt.Errorf("MinerU Agent source exceeds %d-byte limit", agentSourceLimit)
	}
	config := opts.MinerU
	if config.BaseURL == "" {
		config.BaseURL = defaultMinerUBaseURL
	}
	if config.PollInterval <= 0 {
		config.PollInterval = defaultMinerUPollInterval
	}
	if config.Timeout <= 0 {
		config.Timeout = defaultMinerUTimeout
	}
	if config.MaxArchiveBytes <= 0 {
		config.MaxArchiveBytes = defaultMinerUArchiveLimit
	}
	if config.MaxMarkdownBytes <= 0 {
		config.MaxMarkdownBytes = defaultMinerUMarkdownLimit
	}
	if config.HTTPClient == nil {
		config.HTTPClient = &http.Client{Timeout: config.Timeout}
	}
	if pipeline == PipelinePrecision && strings.TrimSpace(config.Token) == "" {
		config.Token = os.Getenv("MINERU_API_TOKEN")
	}
	if pipeline == PipelinePrecision && strings.TrimSpace(config.Token) == "" {
		return nil, errors.New("precision pipeline requires MINERU_API_TOKEN")
	}
	if pipeline == PipelineAgent && fileType == "html" {
		return nil, errors.New("MinerU Agent lightweight pipeline does not support HTML")
	}

	baseURL, err := validateBaseURL(config.BaseURL)
	if err != nil {
		return nil, err
	}
	client := &minerUClient{
		baseURL:          baseURL,
		token:            strings.TrimSpace(config.Token),
		httpClient:       safeHTTPClient(config.HTTPClient),
		pollInterval:     config.PollInterval,
		maxArchiveBytes:  config.MaxArchiveBytes,
		maxMarkdownBytes: config.MaxMarkdownBytes,
	}
	if path, lookupErr := exec.LookPath("wget"); lookupErr == nil {
		client.wgetPath = path
	}
	runCtx, cancel := context.WithTimeout(ctx, config.Timeout)
	defer cancel()
	started := time.Now()

	var markdown []byte
	var remote MinerURunMetadata
	if pipeline == PipelinePrecision {
		markdown, remote, err = client.parsePrecision(runCtx, sourcePath, fileType, opts)
	} else {
		markdown, remote, err = client.parseAgent(runCtx, sourcePath, opts)
	}
	if err != nil {
		return nil, err
	}

	artifactDir := strings.TrimSpace(opts.ArtifactDir)
	if artifactDir == "" {
		artifactDir = filepath.Join(filepath.Dir(sourcePath), ".matrixflow-parser-artifacts")
	}
	if err := os.MkdirAll(artifactDir, 0o755); err != nil {
		return nil, fmt.Errorf("create artifact directory: %w", err)
	}
	markdownPath := filepath.Join(artifactDir, "mineru-full.md")
	if err := os.WriteFile(markdownPath, markdown, 0o644); err != nil {
		return nil, fmt.Errorf("write MinerU markdown: %w", err)
	}

	result, err := p.ParseFile(runCtx, markdownPath, Options{
		Profile:     ProfileV3Native,
		Pipeline:    PipelineLocal,
		ArtifactDir: artifactDir,
		WorkspaceID: opts.WorkspaceID,
		UserID:      opts.UserID,
		Debug:       opts.Debug,
	})
	if err != nil {
		return nil, fmt.Errorf("parse MinerU markdown through MatrixFlow: %w", err)
	}
	annotateDocuments(result.Documents, sourcePath)
	result.SourcePath = sourcePath
	result.FileType = fileType
	result.DurationMS = milliseconds(time.Since(started))
	result.MDFileID = markdownPath
	result.Remote = &remote
	result.Dependencies = []ExternalDependency{{
		Name: "mineru-official", Required: true, Status: "online", UsedFor: "cloud document parsing",
	}}
	if pipeline == PipelinePrecision {
		result.Engine = EngineMinerUPrecision
		result.Metadata.BackendUsed = EngineMinerUPrecision
		result.Metadata.ParserVersion = "mineru-v4"
		result.Metadata.TierRequested = PipelinePrecision
		result.Metadata.TierEffective = PipelinePrecision
		result.Conformance = Conformance{
			Profile: "mineru-precision", Route: "mineru:/api/v4/file-urls/batch",
			Reason: "official MinerU VLM output is normalized through MatrixFlow Markdown blocks; it is not MatrixFlow's pinned MinerU deployment",
		}
	} else {
		result.Engine = EngineMinerUAgent
		result.Metadata.BackendUsed = EngineMinerUAgent
		result.Metadata.ParserVersion = "mineru-agent-v1"
		result.Metadata.TierRequested = PipelineAgent
		result.Metadata.TierEffective = PipelineAgent
		result.Conformance = Conformance{
			Profile: "mineru-agent", Route: "mineru:/api/v1/agent/parse/file",
			Reason: "lightweight public Agent API returns Markdown only and is not web-equivalent",
		}
	}
	return result, nil
}

func (c *minerUClient) parsePrecision(ctx context.Context, sourcePath, fileType string, opts Options) ([]byte, MinerURunMetadata, error) {
	remote := MinerURunMetadata{Provider: "mineru-official", Pipeline: PipelinePrecision, Model: "vlm"}
	if fileType == "html" || fileType == "htm" {
		remote.Model = "MinerU-HTML"
	}
	file := map[string]any{
		"name":    filepath.Base(sourcePath),
		"data_id": strings.TrimPrefix(stableLocalFileID(sourcePath), "local_"),
	}
	if opts.PageSelector != "" {
		file["page_ranges"] = opts.PageSelector
	}
	if value, ok := optionBool(opts.Additional, "is_ocr"); ok {
		file["is_ocr"] = value
	}
	payload := map[string]any{
		"files":          []any{file},
		"model_version":  remote.Model,
		"enable_formula": optionBoolDefault(opts.Additional, "enable_formula", true),
		"enable_table":   optionBoolDefault(opts.Additional, "enable_table", true),
		"language":       optionStringDefault(opts.Additional, "language", "ch"),
	}
	uploadStarted := time.Now()
	var created minerUEnvelope[precisionCreateData]
	if err := c.doJSON(ctx, http.MethodPost, "/api/v4/file-urls/batch", payload, true, &created); err != nil {
		return nil, remote, fmt.Errorf("create MinerU precision upload: %w", err)
	}
	if err := validateEnvelope(created.Code, created.Msg); err != nil {
		return nil, remote, err
	}
	if created.Data.BatchID == "" || len(created.Data.FileURLs) != 1 {
		return nil, remote, errors.New("MinerU precision response missing batch_id or upload URL")
	}
	remote.BatchID, remote.TraceID = created.Data.BatchID, created.TraceID
	if err := c.uploadFile(ctx, created.Data.FileURLs[0], sourcePath); err != nil {
		return nil, remote, fmt.Errorf("upload file to MinerU precision storage: %w", err)
	}
	remote.UploadMS = milliseconds(time.Since(uploadStarted))

	processingStarted := time.Now()
	zipURL, traceID, err := c.pollPrecision(ctx, created.Data.BatchID)
	if err != nil {
		return nil, remote, err
	}
	remote.ProcessingMS = milliseconds(time.Since(processingStarted))
	if traceID != "" {
		remote.TraceID = traceID
	}
	downloadStarted := time.Now()
	archive, downloadVia, err := c.download(ctx, zipURL, c.maxArchiveBytes)
	if err != nil {
		return nil, remote, fmt.Errorf("download MinerU precision result: %w", err)
	}
	markdown, err := markdownFromZIP(archive, c.maxMarkdownBytes)
	if err != nil {
		return nil, remote, err
	}
	remote.DownloadMS = milliseconds(time.Since(downloadStarted))
	remote.DownloadVia = downloadVia
	return markdown, remote, nil
}

func (c *minerUClient) pollPrecision(ctx context.Context, batchID string) (string, string, error) {
	for {
		var result minerUEnvelope[precisionResultData]
		path := "/api/v4/extract-results/batch/" + url.PathEscape(batchID)
		if err := c.doJSON(ctx, http.MethodGet, path, nil, true, &result); err != nil {
			return "", "", fmt.Errorf("query MinerU precision result: %w", err)
		}
		if err := validateEnvelope(result.Code, result.Msg); err != nil {
			return "", result.TraceID, err
		}
		if len(result.Data.ExtractResult) > 0 {
			item := result.Data.ExtractResult[0]
			switch item.State {
			case "done":
				if item.FullZIPURL == "" {
					return "", result.TraceID, errors.New("MinerU precision completed without full_zip_url")
				}
				return item.FullZIPURL, result.TraceID, nil
			case "failed":
				return "", result.TraceID, fmt.Errorf("MinerU precision failed: %s", item.Error)
			}
		}
		if err := waitForPoll(ctx, c.pollInterval); err != nil {
			return "", result.TraceID, err
		}
	}
}

func (c *minerUClient) parseAgent(ctx context.Context, sourcePath string, opts Options) ([]byte, MinerURunMetadata, error) {
	remote := MinerURunMetadata{Provider: "mineru-official", Pipeline: PipelineAgent, Model: "pipeline-lightweight"}
	if strings.Contains(opts.PageSelector, ",") {
		return nil, remote, errors.New("MinerU Agent page range supports only one page or one from-to range")
	}
	payload := map[string]any{
		"file_name":      filepath.Base(sourcePath),
		"language":       optionStringDefault(opts.Additional, "language", "ch"),
		"enable_table":   optionBoolDefault(opts.Additional, "enable_table", true),
		"enable_formula": optionBoolDefault(opts.Additional, "enable_formula", true),
		"is_ocr":         optionBoolDefault(opts.Additional, "is_ocr", false),
	}
	if opts.PageSelector != "" {
		payload["page_range"] = opts.PageSelector
	}
	uploadStarted := time.Now()
	var created minerUEnvelope[agentCreateData]
	if err := c.doJSON(ctx, http.MethodPost, "/api/v1/agent/parse/file", payload, false, &created); err != nil {
		return nil, remote, fmt.Errorf("create MinerU Agent upload: %w", err)
	}
	if err := validateEnvelope(created.Code, created.Msg); err != nil {
		return nil, remote, err
	}
	if created.Data.TaskID == "" || created.Data.FileURL == "" {
		return nil, remote, errors.New("MinerU Agent response missing task_id or upload URL")
	}
	remote.TaskID, remote.TraceID = created.Data.TaskID, created.TraceID
	if err := c.uploadFile(ctx, created.Data.FileURL, sourcePath); err != nil {
		return nil, remote, fmt.Errorf("upload file to MinerU Agent storage: %w", err)
	}
	remote.UploadMS = milliseconds(time.Since(uploadStarted))

	processingStarted := time.Now()
	markdownURL, traceID, err := c.pollAgent(ctx, created.Data.TaskID)
	if err != nil {
		return nil, remote, err
	}
	remote.ProcessingMS = milliseconds(time.Since(processingStarted))
	if traceID != "" {
		remote.TraceID = traceID
	}
	downloadStarted := time.Now()
	markdown, downloadVia, err := c.download(ctx, markdownURL, c.maxMarkdownBytes)
	if err != nil {
		return nil, remote, fmt.Errorf("download MinerU Agent markdown: %w", err)
	}
	remote.DownloadMS = milliseconds(time.Since(downloadStarted))
	remote.DownloadVia = downloadVia
	return markdown, remote, nil
}

func (c *minerUClient) pollAgent(ctx context.Context, taskID string) (string, string, error) {
	for {
		var result minerUEnvelope[agentResultData]
		path := "/api/v1/agent/parse/" + url.PathEscape(taskID)
		if err := c.doJSON(ctx, http.MethodGet, path, nil, false, &result); err != nil {
			return "", "", fmt.Errorf("query MinerU Agent result: %w", err)
		}
		if err := validateEnvelope(result.Code, result.Msg); err != nil {
			return "", result.TraceID, err
		}
		switch result.Data.State {
		case "done":
			if result.Data.MarkdownURL == "" {
				return "", result.TraceID, errors.New("MinerU Agent completed without markdown_url")
			}
			return result.Data.MarkdownURL, result.TraceID, nil
		case "failed":
			return "", result.TraceID, fmt.Errorf("MinerU Agent failed (%d): %s", result.Data.ErrorCode, result.Data.Error)
		}
		if err := waitForPoll(ctx, c.pollInterval); err != nil {
			return "", result.TraceID, err
		}
	}
}

func (c *minerUClient) doJSON(ctx context.Context, method, path string, payload any, authenticated bool, destination any) error {
	var body io.Reader
	if payload != nil {
		raw, err := json.Marshal(payload)
		if err != nil {
			return err
		}
		body = bytes.NewReader(raw)
	}
	request, err := http.NewRequestWithContext(ctx, method, c.baseURL+path, body)
	if err != nil {
		return err
	}
	request.Header.Set("Accept", "application/json")
	if payload != nil {
		request.Header.Set("Content-Type", "application/json")
	}
	if authenticated {
		request.Header.Set("Authorization", "Bearer "+c.token)
	}
	response, err := safeHTTPClient(c.httpClient).Do(request)
	if err != nil {
		return err
	}
	defer response.Body.Close()
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		return fmt.Errorf("HTTP %d", response.StatusCode)
	}
	limited := io.LimitReader(response.Body, defaultMinerUResponseLimit+1)
	raw, err := io.ReadAll(limited)
	if err != nil {
		return err
	}
	if int64(len(raw)) > defaultMinerUResponseLimit {
		return errors.New("MinerU JSON response exceeds size limit")
	}
	if err := json.Unmarshal(raw, destination); err != nil {
		return fmt.Errorf("decode MinerU response: %w", err)
	}
	return nil
}

func (c *minerUClient) uploadFile(ctx context.Context, rawURL, sourcePath string) error {
	if err := validateDownloadURL(rawURL); err != nil {
		return fmt.Errorf("unsafe upload URL: %w", err)
	}
	file, err := os.Open(sourcePath)
	if err != nil {
		return err
	}
	defer file.Close()
	info, err := file.Stat()
	if err != nil {
		return err
	}
	request, err := http.NewRequestWithContext(ctx, http.MethodPut, rawURL, file)
	if err != nil {
		return err
	}
	request.ContentLength = info.Size()
	response, err := safeHTTPClient(c.httpClient).Do(request)
	if err != nil {
		return err
	}
	defer response.Body.Close()
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		return fmt.Errorf("HTTP %d", response.StatusCode)
	}
	return nil
}

func (c *minerUClient) download(ctx context.Context, rawURL string, limit int64) ([]byte, string, error) {
	if err := validateDownloadURL(rawURL); err != nil {
		return nil, "", fmt.Errorf("unsafe result URL: %w", err)
	}
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, rawURL, nil)
	if err != nil {
		return nil, "", err
	}
	response, err := safeHTTPClient(c.httpClient).Do(request)
	if err != nil {
		if ctx.Err() != nil {
			return nil, "", ctx.Err()
		}
		if errors.Is(err, errUnsafeRedirect) {
			return nil, "", err
		}
		if c.wgetPath == "" {
			return nil, "", errors.New("Go HTTP transport failed and wget fallback is unavailable")
		}
		fallback, fallbackErr := downloadWithWget(ctx, c.wgetPath, rawURL, limit)
		if fallbackErr != nil {
			return nil, "", fmt.Errorf("HTTP client failed and wget fallback failed: %w", fallbackErr)
		}
		return fallback, "wget", nil
	}
	defer response.Body.Close()
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		return nil, "", fmt.Errorf("HTTP %d", response.StatusCode)
	}
	raw, err := io.ReadAll(io.LimitReader(response.Body, limit+1))
	if err != nil {
		return nil, "", err
	}
	if int64(len(raw)) > limit {
		return nil, "", fmt.Errorf("download exceeds %d-byte limit", limit)
	}
	return raw, "go-http", nil
}

func downloadWithWget(ctx context.Context, wgetPath, rawURL string, limit int64) ([]byte, error) {
	command := exec.CommandContext(ctx, wgetPath,
		"--quiet",
		"--tries=2",
		"--max-redirect=0",
		"--output-document=-",
		"--input-file=-",
	)
	command.Env = safeDownloaderEnvironment()
	command.Stdin = strings.NewReader(rawURL + "\n")
	stdout, err := command.StdoutPipe()
	if err != nil {
		return nil, err
	}
	if err := command.Start(); err != nil {
		return nil, err
	}
	raw, readErr := io.ReadAll(io.LimitReader(stdout, limit+1))
	if int64(len(raw)) > limit {
		_ = command.Process.Kill()
		_ = command.Wait()
		return nil, fmt.Errorf("download exceeds %d-byte limit", limit)
	}
	waitErr := command.Wait()
	if readErr != nil {
		return nil, readErr
	}
	if waitErr != nil {
		return nil, errors.New("wget exited unsuccessfully")
	}
	return raw, nil
}

func safeDownloaderEnvironment() []string {
	allowed := []string{
		"PATH", "SSL_CERT_FILE", "SSL_CERT_DIR",
		"HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "NO_PROXY", "no_proxy",
	}
	environment := make([]string, 0, len(allowed))
	for _, key := range allowed {
		if value, ok := os.LookupEnv(key); ok {
			environment = append(environment, key+"="+value)
		}
	}
	return environment
}

func safeHTTPClient(base *http.Client) *http.Client {
	if base == nil {
		base = &http.Client{}
	}
	clone := *base
	previousRedirect := base.CheckRedirect
	clone.CheckRedirect = func(request *http.Request, via []*http.Request) error {
		if len(via) > 0 {
			from := via[len(via)-1].URL
			if err := validateRedirectURL(from, request.URL); err != nil {
				return err
			}
		} else if err := validateDownloadURL(request.URL.String()); err != nil {
			return fmt.Errorf("%w: %v", errUnsafeRedirect, err)
		}
		if previousRedirect != nil {
			return previousRedirect(request, via)
		}
		return nil
	}
	return &clone
}

func markdownFromZIP(raw []byte, limit int64) ([]byte, error) {
	reader, err := zip.NewReader(bytes.NewReader(raw), int64(len(raw)))
	if err != nil {
		return nil, fmt.Errorf("open MinerU result ZIP: %w", err)
	}
	for _, file := range reader.File {
		archiveName := strings.ReplaceAll(file.Name, "\\", "/")
		clean := filepath.ToSlash(filepath.Clean(archiveName))
		if clean == ".." || strings.HasPrefix(clean, "../") || filepath.IsAbs(file.Name) {
			return nil, fmt.Errorf("unsafe path in MinerU ZIP: %q", file.Name)
		}
		if filepath.Base(clean) != "full.md" {
			continue
		}
		if int64(file.UncompressedSize64) > limit {
			return nil, fmt.Errorf("MinerU Markdown exceeds %d-byte limit", limit)
		}
		stream, err := file.Open()
		if err != nil {
			return nil, err
		}
		content, readErr := io.ReadAll(io.LimitReader(stream, limit+1))
		closeErr := stream.Close()
		if readErr != nil {
			return nil, readErr
		}
		if closeErr != nil {
			return nil, closeErr
		}
		if int64(len(content)) > limit {
			return nil, fmt.Errorf("MinerU Markdown exceeds %d-byte limit", limit)
		}
		return content, nil
	}
	return nil, errors.New("MinerU result ZIP does not contain full.md")
}

func validateBaseURL(raw string) (string, error) {
	parsed, err := url.Parse(strings.TrimRight(strings.TrimSpace(raw), "/"))
	if err != nil || parsed.Host == "" {
		return "", errors.New("invalid MinerU base URL")
	}
	if parsed.Scheme != "https" && !isLoopbackHost(parsed.Hostname()) {
		return "", errors.New("MinerU base URL must use HTTPS")
	}
	if parsed.User != nil || parsed.RawQuery != "" || parsed.Fragment != "" {
		return "", errors.New("MinerU base URL must not contain credentials, query, or fragment")
	}
	if parsed.Path != "" && parsed.Path != "/" {
		return "", errors.New("MinerU base URL must not contain a path")
	}
	parsed.Path = ""
	return strings.TrimRight(parsed.String(), "/"), nil
}

func validateDownloadURL(raw string) error {
	parsed, err := url.Parse(raw)
	if err != nil || parsed.Host == "" {
		return errors.New("invalid URL")
	}
	if parsed.Scheme != "https" && !isLoopbackHost(parsed.Hostname()) {
		return errors.New("URL must use HTTPS")
	}
	if parsed.User != nil {
		return errors.New("URL must not contain user information")
	}
	return nil
}

func validateRedirectURL(from, to *url.URL) error {
	if err := validateDownloadURL(to.String()); err != nil {
		return fmt.Errorf("%w: %v", errUnsafeRedirect, err)
	}
	if !strings.EqualFold(from.Host, to.Host) {
		return fmt.Errorf("%w: redirect host changed from %q to %q", errUnsafeRedirect, from.Host, to.Host)
	}
	return nil
}

func isLoopbackHost(host string) bool {
	return strings.EqualFold(host, "localhost") || net.ParseIP(host).IsLoopback()
}

func validateEnvelope(code int, message string) error {
	if code == 0 {
		return nil
	}
	return fmt.Errorf("MinerU API error %d: %s", code, message)
}

func waitForPoll(ctx context.Context, interval time.Duration) error {
	timer := time.NewTimer(interval)
	defer timer.Stop()
	select {
	case <-ctx.Done():
		return fmt.Errorf("wait for MinerU result: %w", ctx.Err())
	case <-timer.C:
		return nil
	}
}

func optionBool(values map[string]any, key string) (bool, bool) {
	value, ok := values[key]
	if !ok {
		return false, false
	}
	switch typed := value.(type) {
	case bool:
		return typed, true
	case string:
		if strings.EqualFold(strings.TrimSpace(typed), "true") {
			return true, true
		}
		if strings.EqualFold(strings.TrimSpace(typed), "false") {
			return false, true
		}
	}
	return false, false
}

func optionBoolDefault(values map[string]any, key string, fallback bool) bool {
	if value, ok := optionBool(values, key); ok {
		return value
	}
	return fallback
}

func optionStringDefault(values map[string]any, key, fallback string) string {
	if value, ok := values[key].(string); ok && strings.TrimSpace(value) != "" {
		return strings.TrimSpace(value)
	}
	return fallback
}

func milliseconds(duration time.Duration) float64 {
	return float64(duration.Microseconds()) / 1000
}
