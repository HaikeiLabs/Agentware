package evals

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"time"
)

type EvalCase struct {
	Name         string
	Description  string
	SystemPrompt string
	UserMessage  string
	Tools        []ToolDefinition
	ExpectedTool string
	MaxTurns     int
}

type EvalResult struct {
	CaseName   string
	ModelName  string
	Success    bool
	Turns      int
	ToolCalls  []map[string]interface{}
	Error      string
	DurationMs int64
}

type EvalReport struct {
	Timestamp string
	Models    []string
	Results   []EvalResult
}

func (r *EvalReport) PassRate(model string) float64 {
	var passed, total int
	for _, res := range r.Results {
		if res.ModelName == model {
			total++
			if res.Success {
				passed++
			}
		}
	}
	if total == 0 {
		return 0.0
	}
	return float64(passed) / float64(total)
}

type EvalRunner struct {
	BaseURL  string
	MaxTurns int
	Results  []EvalResult
}

func NewEvalRunner(baseURL string, maxTurns int) *EvalRunner {
	return &EvalRunner{
		BaseURL:  baseURL,
		MaxTurns: maxTurns,
	}
}

type ToolExecutor func(toolName string, args map[string]interface{}) string

func (r *EvalRunner) RunCase(case_ EvalCase, model string, toolExecutor ToolExecutor) EvalResult {
	start := time.Now()
	client := NewModelClient(r.BaseURL, model, "")

	messages := []ChatMessage{
		{Role: "system", Content: case_.SystemPrompt},
		{Role: "user", Content: case_.UserMessage},
	}

	var toolCallsMade []map[string]interface{}
	turns := 0
	errMsg := ""

	for turns < case_.MaxTurns {
		tools := case_.Tools
		result, err := client.Complete(messages, tools, 0.0, 2048)
		turns++
		if err != nil {
			errMsg = err.Error()
			break
		}

		if len(result.ToolCalls) == 0 {
			break
		}

		for _, tc := range result.ToolCalls {
			toolCallsMade = append(toolCallsMade, map[string]interface{}{
				"turn":      turns,
				"name":      tc.Name,
				"arguments": tc.Arguments,
			})

			if tc.Name == case_.ExpectedTool {
				durationMs := time.Since(start).Milliseconds()
				return EvalResult{
					CaseName:   case_.Name,
					ModelName:  model,
					Success:    true,
					Turns:      turns,
					ToolCalls:  toolCallsMade,
					DurationMs: durationMs,
				}
			}

			var args map[string]interface{}
			_ = json.Unmarshal([]byte(tc.Arguments), &args)

			toolResult := toolExecutor(tc.Name, args)

			messages = append(messages, ChatMessage{
				Role:    "assistant",
				Content: "",
			})
			messages = append(messages, ChatMessage{
				Role:    "tool",
				Content: toolResult,
			})
		}
	}

	durationMs := time.Since(start).Milliseconds()
	if errMsg == "" {
		errMsg = fmt.Sprintf("Expected tool '%s' not called in %d turns", case_.ExpectedTool, turns)
	}
	return EvalResult{
		CaseName:   case_.Name,
		ModelName:  model,
		Success:    false,
		Turns:      turns,
		ToolCalls:  toolCallsMade,
		Error:      errMsg,
		DurationMs: durationMs,
	}
}

func (r *EvalRunner) RunEvals(cases_ []EvalCase, models []string, toolExecutor ToolExecutor) EvalReport {
	report := EvalReport{
		Timestamp: time.Now().Format(time.RFC3339),
		Models:    models,
	}

	for _, model := range models {
		fmt.Printf("\n=== Testing model: %s ===\n", model)
		for _, case_ := range cases_ {
			fmt.Printf("  Running: %s...", case_.Name)
			result := r.RunCase(case_, model, toolExecutor)
			r.Results = append(r.Results, result)
			report.Results = append(report.Results, result)

			status := "PASS"
			if !result.Success {
				status = "FAIL"
			}
			fmt.Printf("%s (%d turns, %dms)\n", status, result.Turns, result.DurationMs)

			if !result.Success {
				fmt.Printf("    Error: %s\n", result.Error)
			}
		}
	}

	return report
}

func (r *EvalRunner) SaveReport(report EvalReport, outputPath string) {
	dir := filepath.Dir(outputPath)
	_ = os.MkdirAll(dir, 0755)

	output := map[string]interface{}{
		"timestamp": report.Timestamp,
		"models":    report.Models,
		"results":   []map[string]interface{}{
			// Results will be serialized individually below
		},
	}

	results := make([]map[string]interface{}, len(report.Results))
	for i, res := range report.Results {
		results[i] = map[string]interface{}{
			"case":        res.CaseName,
			"model":       res.ModelName,
			"success":     res.Success,
			"turns":       res.Turns,
			"tool_calls":  res.ToolCalls,
			"error":       res.Error,
			"duration_ms": res.DurationMs,
		}
	}
	output["results"] = results

	data, _ := json.MarshalIndent(output, "", "  ")
	if err := os.WriteFile(outputPath, data, 0644); err != nil {
		fmt.Fprintf(os.Stderr, "Warning: failed to write report: %v\n", err)
	}
}
