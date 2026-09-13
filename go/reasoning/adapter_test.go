package reasoning

import (
	"errors"
	"strings"
	"testing"
	"time"
)

func fixedClock() func() time.Time {
	t := time.Date(2026, 9, 10, 12, 0, 0, 0, time.UTC)
	return func() time.Time { return t }
}

func TestAdapter_Strip_NativeReasoningContent(t *testing.T) {
	a := New()
	raw := map[string]any{
		"message": map[string]any{
			"role":              "assistant",
			"content":           `{"tool": "search", "args": {"q": "x"}}`,
			"reasoning_content": "I need to search first.",
		},
	}
	clean, err := a.Strip(raw)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if want := `{"tool": "search", "args": {"q": "x"}}`; clean != want {
		t.Errorf("expected clean %q, got %q", want, clean)
	}
}

func TestAdapter_Strip_ThinkingTags(t *testing.T) {
	a := New()
	raw := "<thinking>First, check the index.</thinking>\n[TOOL_CALLS] tool1: {\"a\":1} [/TOOL_CALLS]"
	clean, err := a.Strip(raw)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if want := "\n[TOOL_CALLS] tool1: {\"a\":1} [/TOOL_CALLS]"; clean != want {
		t.Errorf("expected clean %q, got %q", want, clean)
	}
}

func TestAdapter_Strip_NoReasoningPassthrough(t *testing.T) {
	a := New()
	cases := []string{
		`{"tool": "search", "args": {}}`,
		`[{"id":"1","name":"search","arguments":{}}]`,
		"plain text response",
		"",
	}
	for _, in := range cases {
		clean, err := a.Strip(in)
		if err != nil {
			t.Fatalf("input %q: unexpected error: %v", in, err)
		}
		if clean != in {
			t.Errorf("input %q: expected unchanged, got %q", in, clean)
		}
	}
}

func TestAdapter_Strip_ModelSpecificField(t *testing.T) {
	a := New()
	a.RegisterModelField("spark", "thinking_payload")
	raw := map[string]any{
		"content":          "hello",
		"thinking_payload": "spark reasoning",
	}
	clean, err := a.Strip(raw)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if clean != "hello" {
		t.Errorf("expected clean %q, got %q", "hello", clean)
	}
}

func TestAdapter_FailClosed(t *testing.T) {
	t.Run("non-string reasoning field", func(t *testing.T) {
		a := New()
		raw := map[string]any{"reasoning_content": []any{"not", "a", "string"}}
		if _, err := a.Strip(raw); !errors.Is(err, ErrMalformedReasoningField) {
			t.Fatalf("expected ErrMalformedReasoningField, got %v", err)
		}
	})

	t.Run("non-string content", func(t *testing.T) {
		a := New()
		raw := map[string]any{"content": []any{"parts"}}
		if _, err := a.Strip(raw); !errors.Is(err, ErrMalformedContent) {
			t.Fatalf("expected ErrMalformedContent, got %v", err)
		}
	})

	t.Run("unbalanced thinking tag", func(t *testing.T) {
		a := New()
		raw := "<thinking>never closed"
		if _, err := a.Strip(raw); !errors.Is(err, ErrUnbalancedThinking) {
			t.Fatalf("expected ErrUnbalancedThinking, got %v", err)
		}
	})

	t.Run("dangling close tag", func(t *testing.T) {
		a := New()
		raw := "no open tag [/THINK]"
		if _, err := a.Strip(raw); !errors.Is(err, ErrUnbalancedThinking) {
			t.Fatalf("expected ErrUnbalancedThinking, got %v", err)
		}
	})

	t.Run("malformed json that looks structured", func(t *testing.T) {
		a := New()
		raw := `{"message": {"content": "x"}`
		if _, err := a.Strip(raw); !errors.Is(err, ErrMalformedJSON) {
			t.Fatalf("expected ErrMalformedJSON, got %v", err)
		}
	})

	t.Run("unsupported type", func(t *testing.T) {
		a := New()
		if _, err := a.Strip(42); !errors.Is(err, ErrMalformedInput) {
			t.Fatalf("expected ErrMalformedInput, got %v", err)
		}
	})
}

func TestAdapter_Strip_BoundedInput(t *testing.T) {
	t.Run("reasoning too large", func(t *testing.T) {
		a := New(Options{MaxReasoningBytes: 16})
		raw := map[string]any{
			"content":           "",
			"reasoning_content": strings.Repeat("x", 64),
		}
		if _, err := a.Extract(raw, "deepseek", "test"); !errors.Is(err, ErrReasoningTooLarge) {
			t.Fatalf("expected ErrReasoningTooLarge, got %v", err)
		}
	})

	t.Run("too many nodes", func(t *testing.T) {
		a := New(Options{MaxNodes: 2, Clock: fixedClock()})
		raw := "<thinking>p1\n\np2\n\np3\n\np4</thinking>"
		if _, err := a.Extract(raw, "m", "b"); !errors.Is(err, ErrTooManyNodes) {
			t.Fatalf("expected ErrTooManyNodes, got %v", err)
		}
	})

	t.Run("too deep", func(t *testing.T) {
		a := New(Options{MaxDepth: 2, Clock: fixedClock()})
		raw := "<thinking>a\n\nb\n\nc</thinking>"
		if _, err := a.Extract(raw, "m", "b"); !errors.Is(err, ErrTooDeep) {
			t.Fatalf("expected ErrTooDeep, got %v", err)
		}
	})
}

func TestAdapter_Extract_ContextTree(t *testing.T) {
	a := New(Options{Clock: fixedClock()})
	raw := "<thinking>" +
		"goal: verify the payment gateway\n\n" +
		"observation: gateway returned 200 [E1]\n\n" +
		"decision: call refund tool\n\n" +
		"tool-call: refund_tool: {\"id\": \"txn1\"}\n\n" +
		"tool-result: refund_tool: ok [SUPERSEDED]\n\n" +
		"conclusion: refund issued\n\n" +
		"blocker: regulatory approval pending" +
		"</thinking>"

	tree, err := a.Extract(raw, "deepseek-reasoner", "test-backend")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if tree.Version != ContractVersion {
		t.Errorf("expected version %s, got %s", ContractVersion, tree.Version)
	}
	if tree.Format != FormatThinking {
		t.Errorf("expected format thinking, got %s", tree.Format)
	}
	if tree.Model != "deepseek-reasoner" || tree.Backend != "test-backend" {
		t.Errorf("model/backend metadata not carried: %+v", tree)
	}
	if tree.RootID == "" {
		t.Fatal("expected a root node")
	}

	if len(tree.Nodes) != 7 {
		t.Fatalf("expected 7 nodes, got %d", len(tree.Nodes))
	}

	kinds := []NodeKind{KindGoal, KindObservation, KindDecision, KindToolCall, KindToolResult, KindConclusion, KindBlocker}
	for i, want := range kinds {
		if tree.Nodes[i].Kind != want {
			t.Errorf("node %d: expected kind %s, got %s", i, want, tree.Nodes[i].Kind)
		}
	}

	// Chain: root has empty parent, every other node's parent is its predecessor.
	if tree.Nodes[0].ParentID != "" {
		t.Errorf("root parent should be empty, got %q", tree.Nodes[0].ParentID)
	}
	for i := 1; i < len(tree.Nodes); i++ {
		if tree.Nodes[i].ParentID != tree.Nodes[i-1].ID {
			t.Errorf("node %d parent mismatch: %q != %q", i, tree.Nodes[i].ParentID, tree.Nodes[i-1].ID)
		}
	}

	// Statuses: blocker is blocked, superseded marker honored, default complete.
	if tree.Nodes[0].Status != StatusComplete {
		t.Errorf("goal status: expected complete, got %s", tree.Nodes[0].Status)
	}
	if tree.Nodes[4].Status != StatusSuperseded {
		t.Errorf("tool-result status: expected superseded, got %s", tree.Nodes[4].Status)
	}
	if tree.Nodes[6].Status != StatusBlocked {
		t.Errorf("blocker status: expected blocked, got %s", tree.Nodes[6].Status)
	}

	// Evidence and tool-call refs.
	if got := tree.Nodes[1].EvidenceRefs; len(got) != 1 || got[0] != "E1" {
		t.Errorf("observation evidence refs: expected [E1], got %v", got)
	}
	if got := tree.Nodes[3].ToolCallRefs; len(got) != 1 || got[0] != "refund_tool" {
		t.Errorf("tool-call refs: expected [refund_tool], got %v", got)
	}

	// Timestamps.
	want := fixedClock()().UTC()
	for _, n := range tree.Nodes {
		if !n.CreatedAt.Equal(want) || !n.UpdatedAt.Equal(want) {
			t.Errorf("node %s timestamps not from clock", n.ID)
		}
	}
}

func TestAdapter_Extract_EmptyReasoning(t *testing.T) {
	a := New(Options{Clock: fixedClock()})
	tree, err := a.Extract(map[string]any{"content": "hello"}, "m", "b")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !tree.Empty() {
		t.Fatalf("expected empty tree, got %d nodes", len(tree.Nodes))
	}
	if tree.RootID != "" {
		t.Errorf("expected empty root id, got %q", tree.RootID)
	}
	if tree.Format != FormatNone {
		t.Errorf("expected format none, got %s", tree.Format)
	}
}

func TestAdapter_Extract_DeterministicNodeIDs(t *testing.T) {
	raw := "<thinking>observation: x\n\ndecision: y</thinking>"
	a := New(Options{Clock: fixedClock()})
	t1, err := a.Extract(raw, "m", "b")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	t2, err := a.Extract(raw, "m", "b")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	for i := range t1.Nodes {
		if t1.Nodes[i].ID != t2.Nodes[i].ID {
			t.Errorf("node %d id not stable: %q != %q", i, t1.Nodes[i].ID, t2.Nodes[i].ID)
		}
	}
	if t1.RootID != t2.RootID {
		t.Errorf("root id not stable: %q != %q", t1.RootID, t2.RootID)
	}
}

func TestAdapter_Extract_SummaryBounded(t *testing.T) {
	a := New(Options{MaxSummaryChars: 10, Clock: fixedClock()})
	long := "observation: " + strings.Repeat("abcdefg", 20)
	raw := "<thinking>" + long + "</thinking>"
	tree, err := a.Extract(raw, "m", "b")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(tree.Nodes) != 1 {
		t.Fatalf("expected 1 node, got %d", len(tree.Nodes))
	}
	runes := []rune(tree.Nodes[0].Summary)
	if len(runes) > 10 {
		t.Errorf("summary not bounded: %d runes", len(runes))
	}
	// Raw reasoning is never stored: the summary must not contain the full raw text.
	if strings.Contains(tree.Nodes[0].Summary, strings.Repeat("abcdefg", 20)) {
		t.Error("raw reasoning leaked into summary")
	}
}

func TestAdapter_Extract_UnicodeSummaryTruncation(t *testing.T) {
	a := New(Options{MaxSummaryChars: 3, Clock: fixedClock()})
	raw := "<thinking>observation: héllo wörld 🚀 end</thinking>"
	tree, err := a.Extract(raw, "m", "b")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if tree.Nodes[0].Summary != "hél" {
		t.Errorf("expected summary 'hél', got %q", tree.Nodes[0].Summary)
	}
}

func TestAdapter_Parse_ReturnsCleanAndTree(t *testing.T) {
	a := New(Options{Clock: fixedClock()})
	raw := "<thinking>observation: x</thinking>\n" + `{"tool": "search", "args": {"q": "1"}}`
	clean, tree, err := a.Parse(raw, "m", "b")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if clean != "\n"+`{"tool": "search", "args": {"q": "1"}}` {
		t.Errorf("unexpected clean content %q", clean)
	}
	if tree.Empty() {
		t.Error("expected a non-empty tree")
	}
}

func TestAdapter_Strip_JSONStringInput(t *testing.T) {
	a := New()
	// A JSON tool-call array is opaque text: no recognized keys, unchanged.
	in := `[{"id":"1","name":"search","arguments":{"q":"x"}}]`
	clean, err := a.Strip(in)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if clean != in {
		t.Errorf("expected unchanged tool-call JSON, got %q", clean)
	}
}

func TestContractVocabulary(t *testing.T) {
	wantKinds := []NodeKind{KindGoal, KindObservation, KindDecision, KindToolCall, KindToolResult, KindConclusion, KindBlocker}
	gotKinds := []NodeKind{
		"goal", "observation", "decision", "tool-call", "tool-result", "conclusion", "blocker",
	}
	for i := range wantKinds {
		if wantKinds[i] != gotKinds[i] {
			t.Errorf("kind mismatch: %q != %q", wantKinds[i], gotKinds[i])
		}
	}

	wantStatuses := []NodeStatus{StatusActive, StatusComplete, StatusBlocked, StatusSuperseded}
	gotStatuses := []NodeStatus{"active", "complete", "blocked", "superseded"}
	for i := range wantStatuses {
		if wantStatuses[i] != gotStatuses[i] {
			t.Errorf("status mismatch: %q != %q", wantStatuses[i], gotStatuses[i])
		}
	}
}

func TestContextTreeEmpty(t *testing.T) {
	var nilTree *ContextTree
	if !nilTree.Empty() {
		t.Error("nil tree should be empty")
	}
	empty := &ContextTree{Nodes: []Node{}}
	if !empty.Empty() {
		t.Error("empty node list should be empty")
	}
}
