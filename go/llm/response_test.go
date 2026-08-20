package llm

import (
	"testing"
)

func TestResponse(t *testing.T) {
	resp := Response{
		Content:      "Hello!",
		ToolCalls:    []ToolCall{{ID: "call_1", Name: "tool1", Args: map[string]any{}}},
		FinishReason: "stop",
		UsageTokens: TokenUsage{
			PromptTokens:     10,
			CompletionTokens: 5,
			TotalTokens:      15,
		},
	}

	if resp.Content != "Hello!" {
		t.Errorf("expected 'Hello!', got '%s'", resp.Content)
	}
	if resp.FinishReason != "stop" {
		t.Errorf("expected 'stop', got '%s'", resp.FinishReason)
	}
	if resp.UsageTokens.TotalTokens != 15 {
		t.Errorf("expected 15, got %d", resp.UsageTokens.TotalTokens)
	}
}

func TestToolCall(t *testing.T) {
	tc := ToolCall{
		ID:   "call_abc",
		Name: "my_tool",
		Args: map[string]any{"param": "value"},
	}

	if tc.ID != "call_abc" {
		t.Errorf("expected 'call_abc', got '%s'", tc.ID)
	}
	if tc.Name != "my_tool" {
		t.Errorf("expected 'my_tool', got '%s'", tc.Name)
	}
	if tc.Args["param"] != "value" {
		t.Errorf("expected 'value', got '%v'", tc.Args["param"])
	}
}

func TestTokenUsage(t *testing.T) {
	usage := TokenUsage{
		PromptTokens:     100,
		CompletionTokens: 50,
		TotalTokens:      150,
		CachedTokens:     80,
	}

	if usage.PromptTokens != 100 {
		t.Errorf("expected 100, got %d", usage.PromptTokens)
	}
	if usage.CompletionTokens != 50 {
		t.Errorf("expected 50, got %d", usage.CompletionTokens)
	}
	if usage.TotalTokens != 150 {
		t.Errorf("expected 150, got %d", usage.TotalTokens)
	}
	if usage.CachedTokens != 80 {
		t.Errorf("expected 80, got %d", usage.CachedTokens)
	}
}

// TestTokenUsage_CachedTokensDefaultsToZero documents that backends which do
// not report cache usage leave CachedTokens at zero rather than guessing.
func TestTokenUsage_CachedTokensDefaultsToZero(t *testing.T) {
	usage := TokenUsage{PromptTokens: 100, CompletionTokens: 50, TotalTokens: 150}

	if usage.CachedTokens != 0 {
		t.Errorf("expected 0, got %d", usage.CachedTokens)
	}
}
