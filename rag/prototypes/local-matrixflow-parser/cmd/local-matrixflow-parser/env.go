package main

import (
	"bufio"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

func findDefaultEnvFile() string {
	directory, err := os.Getwd()
	if err != nil {
		return ""
	}
	for {
		candidate := filepath.Join(directory, ".env")
		if info, statErr := os.Stat(candidate); statErr == nil && !info.IsDir() {
			return candidate
		}
		parent := filepath.Dir(directory)
		if parent == directory {
			return ""
		}
		directory = parent
	}
}

func resolveEnvValue(key, envFile string) (string, error) {
	value, found, err := lookupEnvValue(key, envFile)
	if err != nil {
		return "", err
	}
	if !found {
		if strings.TrimSpace(envFile) == "" {
			return "", fmt.Errorf("%s is not set and no .env file was found", strings.TrimSpace(key))
		}
		return "", fmt.Errorf("%s is not set in the environment or %s", strings.TrimSpace(key), envFile)
	}
	return value, nil
}

func resolveOptionalEnvValue(key, envFile string) (string, error) {
	value, _, err := lookupEnvValue(key, envFile)
	return value, err
}

func lookupEnvValue(key, envFile string) (string, bool, error) {
	key = strings.TrimSpace(key)
	if key == "" {
		return "", false, errors.New("environment variable name must not be empty")
	}
	if value := strings.TrimSpace(os.Getenv(key)); value != "" {
		return value, true, nil
	}
	if strings.TrimSpace(envFile) == "" {
		return "", false, nil
	}
	file, err := os.Open(envFile)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return "", false, nil
		}
		return "", false, fmt.Errorf("open env file %s: %w", envFile, err)
	}
	defer file.Close()
	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		line = strings.TrimSpace(strings.TrimPrefix(line, "export "))
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		name, value, ok := strings.Cut(line, "=")
		if !ok || strings.TrimSpace(name) != key {
			continue
		}
		value = strings.TrimSpace(value)
		if len(value) >= 2 && ((value[0] == '\'' && value[len(value)-1] == '\'') || (value[0] == '"' && value[len(value)-1] == '"')) {
			value = value[1 : len(value)-1]
		}
		if strings.TrimSpace(value) == "" {
			return "", false, fmt.Errorf("%s is empty in %s", key, envFile)
		}
		return value, true, nil
	}
	if err := scanner.Err(); err != nil {
		return "", false, fmt.Errorf("read env file %s: %w", envFile, err)
	}
	return "", false, nil
}
