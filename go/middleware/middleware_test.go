package middleware

import (
	"context"
	"testing"

	"github.com/soypete/pedro-agentware/go/tools"
)

type mockExecutor struct {
	execFn func(ctx context.Context, toolName string, args map[string]any) (*tools.Result, error)
}

func (m *mockExecutor) Execute(ctx context.Context, toolName string, args map[string]any) (*tools.Result, error) {
	if m.execFn != nil {
		return m.execFn(ctx, toolName, args)
	}
	return &tools.Result{Success: true}, nil
}

type mockEvaluator struct {
	decision Decision
}

func (m *mockEvaluator) Evaluate(toolName string, args map[string]any, caller CallerContext) Decision {
	return m.decision
}

type mockAuditor struct {
	records  []AuditRecord
	onRecord func()
}

func (m *mockAuditor) Record(record AuditRecord) {
	m.records = append(m.records, record)
	if m.onRecord != nil {
		m.onRecord()
	}
}

type mockAuditHook struct {
	records          []AuditRecord
	onAfterExecution func()
}

func (m *mockAuditHook) AfterExecution(record AuditRecord) {
	m.records = append(m.records, record)
	if m.onAfterExecution != nil {
		m.onAfterExecution()
	}
}

func (m *mockAuditor) Query(filter AuditFilter) []AuditRecord {
	return m.records
}

func TestNewMiddleware(t *testing.T) {
	exec := &mockExecutor{}
	mw := NewMiddleware(exec)

	if mw == nil {
		t.Fatal("expected non-nil middleware")
	}
}

func TestMiddlewareExecute_Allow(t *testing.T) {
	exec := &mockExecutor{}
	eval := &mockEvaluator{decision: Decision{Action: ActionAllow, Rule: "test"}}
	aud := &mockAuditor{}

	mw := NewMiddleware(exec).WithPolicy(eval).WithAuditor(aud)

	result, err := mw.Execute(context.Background(), "test_tool", map[string]any{"arg": "value"})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !result.Success {
		t.Error("expected success")
	}
}

func TestMiddlewareExecute_Deny(t *testing.T) {
	exec := &mockExecutor{}
	eval := &mockEvaluator{decision: Decision{Action: ActionDeny, Rule: "deny_rule", Reason: "not allowed"}}
	aud := &mockAuditor{}

	mw := NewMiddleware(exec).WithPolicy(eval).WithAuditor(aud)

	result, err := mw.Execute(context.Background(), "test_tool", map[string]any{})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Success {
		t.Error("expected failure")
	}
	if result.Error == "" {
		t.Error("expected error message")
	}
}

func TestMiddlewareExecute_Filter(t *testing.T) {
	var capturedArgs map[string]any
	exec := &mockExecutor{
		execFn: func(ctx context.Context, toolName string, args map[string]any) (*tools.Result, error) {
			capturedArgs = args
			return &tools.Result{Success: true}, nil
		},
	}
	eval := &mockEvaluator{
		decision: Decision{
			Action:       ActionFilter,
			Rule:         "filter_rule",
			RedactedArgs: map[string]any{"secret": "redacted"},
		},
	}

	mw := NewMiddleware(exec).WithPolicy(eval)

	_, err := mw.Execute(context.Background(), "test_tool", map[string]any{"secret": "original"})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if capturedArgs["secret"] != "redacted" {
		t.Errorf("expected secret to be redacted, got '%v'", capturedArgs["secret"])
	}
}

func TestMiddlewareAuditorRecords(t *testing.T) {
	exec := &mockExecutor{}
	eval := &mockEvaluator{decision: Decision{Action: ActionAllow, Rule: "test"}}
	aud := &mockAuditor{}

	mw := NewMiddleware(exec).WithPolicy(eval).WithAuditor(aud)

	_, err := mw.Execute(context.Background(), "my_tool", map[string]any{})
	if err != nil {
		t.Fatalf("Execute failed: %v", err)
	}

	if len(aud.records) != 1 {
		t.Fatalf("expected 1 audit record, got %d", len(aud.records))
	}
	if aud.records[0].ToolName != "my_tool" {
		t.Errorf("expected tool name 'my_tool', got '%s'", aud.records[0].ToolName)
	}
}

func TestMiddlewareAuditHooksRunAfterAuditRecording(t *testing.T) {
	exec := &mockExecutor{}
	eval := &mockEvaluator{decision: Decision{Action: ActionAllow, Rule: "test"}}
	order := make([]string, 0, 3)
	aud := &mockAuditor{onRecord: func() { order = append(order, "audit") }}
	firstHook := &mockAuditHook{onAfterExecution: func() { order = append(order, "first") }}
	secondHook := &mockAuditHook{onAfterExecution: func() { order = append(order, "second") }}

	mw := NewMiddleware(exec).
		WithPolicy(eval).
		WithAuditor(aud).
		AddHook(firstHook).
		AddHook(secondHook)

	_, err := mw.Execute(context.Background(), "my_tool", map[string]any{})
	if err != nil {
		t.Fatalf("Execute failed: %v", err)
	}

	expectedOrder := []string{"audit", "first", "second"}
	if len(order) != len(expectedOrder) {
		t.Fatalf("expected %d calls, got %d: %v", len(expectedOrder), len(order), order)
	}
	for i, expected := range expectedOrder {
		if order[i] != expected {
			t.Fatalf("expected call %d to be %q, got %q", i, expected, order[i])
		}
	}
	if len(firstHook.records) != 1 || firstHook.records[0].ToolName != "my_tool" {
		t.Fatalf("expected first hook to receive the audit record, got %#v", firstHook.records)
	}
	if len(secondHook.records) != 1 || secondHook.records[0].ToolName != "my_tool" {
		t.Fatalf("expected second hook to receive the audit record, got %#v", secondHook.records)
	}
}

func TestMiddlewareAuditHooksRunForDeniedExecution(t *testing.T) {
	exec := &mockExecutor{}
	eval := &mockEvaluator{decision: Decision{Action: ActionDeny, Reason: "not allowed"}}
	hook := &mockAuditHook{}

	mw := NewMiddleware(exec).WithPolicy(eval).AddHook(hook)

	_, err := mw.Execute(context.Background(), "denied_tool", map[string]any{})
	if err != nil {
		t.Fatalf("Execute failed: %v", err)
	}

	if len(hook.records) != 1 {
		t.Fatalf("expected hook to receive 1 audit record, got %d", len(hook.records))
	}
	if hook.records[0].Success {
		t.Error("expected denied audit record to be unsuccessful")
	}
}

func TestWithCallerContext(t *testing.T) {
	caller := CallerContext{
		UserID:    "user123",
		SessionID: "session456",
		Role:      "admin",
	}

	ctx := WithCallerContext(context.Background(), caller)

	if c, ok := ctx.Value(callerContextKey).(CallerContext); !ok {
		t.Error("expected CallerContext in context")
	} else if c.UserID != "user123" {
		t.Errorf("expected UserID 'user123', got '%s'", c.UserID)
	}
}
