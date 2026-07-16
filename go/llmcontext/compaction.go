package llmcontext

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

type CompactionConfig struct {
	Threshold       float64 `json:"threshold"`         // Trigger at this % of context limit (default 0.75)
	KeepRecent      int     `json:"keep_recent"`       // Number of recent rounds to keep (default 3)
	ContextLimit    int     `json:"context_limit"`     // Total context window size (default 100000)
	SummarizeViaLLM bool    `json:"summarize_via_llm"` // Use LLM for summarization (not implemented)
}

func DefaultCompactionConfig() CompactionConfig {
	return CompactionConfig{
		Threshold:    0.75,
		KeepRecent:   3,
		ContextLimit: 100000,
	}
}

type CompactionStats struct {
	TotalRounds      int `json:"total_rounds"`
	RecentRounds     int `json:"recent_rounds"`
	CompactedRounds  int `json:"compacted_rounds"`
	ThresholdTokens  int `json:"threshold_tokens"`
	EstimatedTokens  int `json:"estimated_tokens"`
	CompactionTimeMs int `json:"compaction_time_ms"`
}

type Compactor struct {
	config    CompactionConfig
	jobDir    string
	debugMode bool
}

func NewCompactor(jobDir string, config CompactionConfig) *Compactor {
	if config.Threshold == 0 {
		config = DefaultCompactionConfig()
	}
	return &Compactor{
		config:    config,
		jobDir:    jobDir,
		debugMode: false,
	}
}

func (c *Compactor) ShouldCompact() bool {
	files, err := c.getPromptFiles()
	if err != nil || len(files) <= c.config.KeepRecent {
		return false
	}

	threshold := int(float64(c.config.ContextLimit) * c.config.Threshold)
	estimated := c.estimateTokenCount()

	return estimated >= threshold
}

func (c *Compactor) Compact() (string, error) {
	files, err := c.getPromptFiles()
	if err != nil {
		return "", fmt.Errorf("get prompt files: %w", err)
	}

	if len(files) <= c.config.KeepRecent {
		return "", nil
	}

	recentFiles := files[len(files)-c.config.KeepRecent:]
	oldFiles := files[:len(files)-c.config.KeepRecent]

	return c.summarizeHistory(oldFiles, recentFiles)
}

func (c *Compactor) getPromptFiles() ([]string, error) {
	entries, err := os.ReadDir(c.jobDir)
	if err != nil {
		return nil, err
	}

	var prompts []string
	for _, e := range entries {
		if e.IsDir() {
			continue
		}
		if strings.HasSuffix(e.Name(), "-prompt.txt") {
			prompts = append(prompts, e.Name())
		}
	}

	sort.Strings(prompts)
	return prompts, nil
}

func (c *Compactor) summarizeHistory(oldFiles, recentFiles []string) (string, error) {
	var summary strings.Builder

	if len(oldFiles) > 0 {
		fmt.Fprintf(&summary, "Previous Work Summary (%d earlier rounds):\n\n", len(oldFiles))
	}

	for _, file := range oldFiles {
		roundNum := strings.TrimSuffix(file, "-prompt.txt")

		var calls []ToolCall
		var foundToolCalls bool

		for offset := 1; offset <= 5; offset++ {
			toolCallsFile := filepath.Join(c.jobDir, fmt.Sprintf("%03d-tool-calls.json", offset))

			if data, err := os.ReadFile(toolCallsFile); err == nil {
				if json.Unmarshal(data, &calls) == nil && len(calls) > 0 {
					foundToolCalls = true
					fmt.Fprintf(&summary, "- Round %s: %d tool call(s)\n", roundNum, len(calls))

					for _, call := range calls {
						fmt.Fprintf(&summary, "  - %s", call.Name)

						if args, ok := call.Args.(map[string]interface{}); ok {
							if file, ok := args["file"].(string); ok {
								fmt.Fprintf(&summary, " (file: %s)", file)
							}
							if pattern, ok := args["pattern"].(string); ok {
								fmt.Fprintf(&summary, " (pattern: %s)", pattern)
							}
							if path, ok := args["path"].(string); ok {
								fmt.Fprintf(&summary, " (path: %s)", path)
							}
							if command, ok := args["command"].(string); ok {
								// Truncate long commands
								if len(command) > 50 {
									command = command[:50] + "..."
								}
								fmt.Fprintf(&summary, " (cmd: %s)", command)
							}
						}
						summary.WriteString("\n")
					}

					// Check for modified files in results
					for resultOffset := offset; resultOffset <= offset+2; resultOffset++ {
						toolResultsFile := filepath.Join(c.jobDir, fmt.Sprintf("%03d-tool-results.json", resultOffset))
						if resultData, err := os.ReadFile(toolResultsFile); err == nil {
							var results []ToolResultEntry
							if json.Unmarshal(resultData, &results) == nil {
								for _, result := range results {
									if len(result.Output) > 0 && strings.Contains(result.Output, "Modified:") {
										lines := strings.Split(result.Output, "\n")
										for _, line := range lines {
											if strings.HasPrefix(line, "Modified:") {
												fmt.Fprintf(&summary, "  %s\n", strings.TrimSpace(line))
											}
										}
									}
								}
							}
							break
						}
					}
					break
				}
			}
		}

		if !foundToolCalls {
			responseFile := filepath.Join(c.jobDir, fmt.Sprintf("%s-response.txt", roundNum))
			if data, err := os.ReadFile(responseFile); err == nil {
				response := string(data)
				if len(response) > 100 {
					response = response[:100] + "..."
				}
				fmt.Fprintf(&summary, "- Round %s: %s\n", roundNum, response)
			}
		}
	}

	summary.WriteString("\nRecent Context:\n")
	for _, file := range recentFiles {
		roundNum := strings.TrimSuffix(file, "-prompt.txt")
		fmt.Fprintf(&summary, "- %s: (kept for context)\n", roundNum)
	}

	return summary.String(), nil
}

func (c *Compactor) GetStats() CompactionStats {
	files, _ := c.getPromptFiles()
	totalRounds := len(files)

	recentRounds := c.config.KeepRecent
	if recentRounds > totalRounds {
		recentRounds = totalRounds
	}

	compactedRounds := totalRounds - recentRounds
	if compactedRounds < 0 {
		compactedRounds = 0
	}

	thresholdTokens := int(float64(c.config.ContextLimit) * c.config.Threshold)
	estimatedTokens := c.estimateTokenCount()

	return CompactionStats{
		TotalRounds:      totalRounds,
		RecentRounds:     recentRounds,
		CompactedRounds:  compactedRounds,
		ThresholdTokens:  thresholdTokens,
		EstimatedTokens:  estimatedTokens,
		CompactionTimeMs: 0,
	}
}

func (c *Compactor) estimateTokenCount() int {
	files, err := c.getPromptFiles()
	if err != nil {
		return 0
	}

	total := 0
	for _, file := range files {
		path := filepath.Join(c.jobDir, file)
		if data, err := os.ReadFile(path); err == nil {
			// Rough token estimate: ~4 chars per token
			total += len(data) / 4
		}

		// Also check response files
		roundNum := strings.TrimSuffix(file, "-prompt.txt")
		responsePath := filepath.Join(c.jobDir, fmt.Sprintf("%s-response.txt", roundNum))
		if data, err := os.ReadFile(responsePath); err == nil {
			total += len(data) / 4
		}
	}

	return total
}

type ToolCall struct {
	Name string      `json:"name"`
	Args interface{} `json:"args"`
}
