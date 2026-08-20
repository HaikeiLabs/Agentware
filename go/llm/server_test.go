package llm

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

// newTestBackend returns a serverBackend pointed at a stub server that always
// replies with the given JSON body.
func newTestBackend(t *testing.T, body string) Backend {
	t.Helper()

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		// #nosec G104
		_, _ = w.Write([]byte(body))
	}))
	t.Cleanup(srv.Close)

	return NewServerBackend(ServerConfig{
		BaseURL: srv.URL,
		Model:   "test-model",
		Timeout: 5 * time.Second,
	})
}

func TestServerBackend_Complete_CapturesCachedTokens(t *testing.T) {
	backend := newTestBackend(t, `{
		"choices": [{"message": {"role": "assistant", "content": "hi"}, "finish_reason": "stop"}],
		"usage": {
			"prompt_tokens": 100,
			"completion_tokens": 20,
			"total_tokens": 120,
			"prompt_tokens_details": {"cached_tokens": 64}
		}
	}`)

	resp, err := backend.Complete(context.Background(), &Request{
		Messages: []Message{{Role: RoleUser, Content: "hello"}},
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if resp.UsageTokens.CachedTokens != 64 {
		t.Errorf("expected CachedTokens 64, got %d", resp.UsageTokens.CachedTokens)
	}
	if resp.UsageTokens.PromptTokens != 100 {
		t.Errorf("expected PromptTokens 100, got %d", resp.UsageTokens.PromptTokens)
	}
	if resp.UsageTokens.CompletionTokens != 20 {
		t.Errorf("expected CompletionTokens 20, got %d", resp.UsageTokens.CompletionTokens)
	}
	if resp.UsageTokens.TotalTokens != 120 {
		t.Errorf("expected TotalTokens 120, got %d", resp.UsageTokens.TotalTokens)
	}
}

// Backends that omit prompt_tokens_details must not fail; CachedTokens stays 0.
func TestServerBackend_Complete_MissingCachedTokens(t *testing.T) {
	backend := newTestBackend(t, `{
		"choices": [{"message": {"role": "assistant", "content": "hi"}, "finish_reason": "stop"}],
		"usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}
	}`)

	resp, err := backend.Complete(context.Background(), &Request{
		Messages: []Message{{Role: RoleUser, Content: "hello"}},
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if resp.UsageTokens.CachedTokens != 0 {
		t.Errorf("expected CachedTokens 0, got %d", resp.UsageTokens.CachedTokens)
	}
	if resp.UsageTokens.PromptTokens != 100 {
		t.Errorf("expected PromptTokens 100, got %d", resp.UsageTokens.PromptTokens)
	}
}
