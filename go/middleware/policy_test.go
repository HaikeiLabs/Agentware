package middleware

import (
	"testing"
	"time"
)

func TestPolicyEvaluate(t *testing.T) {
	policy := &Policy{
		Rules: []Rule{
			{
				Name:   "allow_read",
				Tools:  []string{"read", "list"},
				Action: ActionAllow,
			},
			{
				Name:   "deny_delete",
				Tools:  []string{"delete"},
				Action: ActionDeny,
			},
		},
		DefaultDeny: false,
	}

	t.Run("allow matching rule", func(t *testing.T) {
		decision := policy.Evaluate("read", map[string]any{}, CallerContext{})
		if decision.Action != ActionAllow {
			t.Errorf("expected ActionAllow, got '%s'", decision.Action)
		}
		if decision.Rule != "allow_read" {
			t.Errorf("expected rule 'allow_read', got '%s'", decision.Rule)
		}
	})

	t.Run("deny matching rule", func(t *testing.T) {
		decision := policy.Evaluate("delete", map[string]any{}, CallerContext{})
		if decision.Action != ActionDeny {
			t.Errorf("expected ActionDeny, got '%s'", decision.Action)
		}
	})

	t.Run("no matching rule with default allow", func(t *testing.T) {
		decision := policy.Evaluate("unknown", map[string]any{}, CallerContext{})
		if decision.Action != ActionAllow {
			t.Errorf("expected ActionAllow, got '%s'", decision.Action)
		}
	})

	t.Run("no matching rule with default deny", func(t *testing.T) {
		policy.DefaultDeny = true
		decision := policy.Evaluate("unknown", map[string]any{}, CallerContext{})
		if decision.Action != ActionDeny {
			t.Errorf("expected ActionDeny, got '%s'", decision.Action)
		}
	})
}

func TestRuleMatchesTool(t *testing.T) {
	rule := Rule{
		Tools: []string{"read", "write", "*"},
	}

	tests := []struct {
		toolName string
		expected bool
	}{
		{"read", true},
		{"write", true},
		{"delete", true},
		{"execute", true},
	}

	for _, tt := range tests {
		result := rule.matchesTool(tt.toolName)
		if result != tt.expected {
			t.Errorf("expected matchesTool('%s') = %v, got %v", tt.toolName, tt.expected, result)
		}
	}
}

func TestRuleMatchesToolWildcard(t *testing.T) {
	rule := Rule{Tools: []string{"*"}}

	if !rule.matchesTool("any_tool") {
		t.Error("expected wildcard to match any tool")
	}
}

func TestRuleEvaluateConditions(t *testing.T) {
	rule := Rule{
		Conditions: []Condition{
			{Field: "caller.role", Operator: OperatorEq, Value: "admin"},
		},
	}

	args := map[string]any{}
	caller := CallerContext{Role: "admin"}
	if !rule.evaluateConditions(args, caller) {
		t.Error("expected conditions to evaluate to true")
	}

	caller.Role = "user"
	if rule.evaluateConditions(args, caller) {
		t.Error("expected conditions to evaluate to false")
	}
}

func TestConditionEvaluate(t *testing.T) {
	t.Run("caller.role eq", func(t *testing.T) {
		cond := Condition{Field: "caller.role", Operator: OperatorEq, Value: "admin"}
		args := map[string]any{}
		caller := CallerContext{Role: "admin"}

		if !cond.evaluate(args, caller) {
			t.Error("expected condition to evaluate to true")
		}
	})

	t.Run("caller.role not_eq", func(t *testing.T) {
		cond := Condition{Field: "caller.role", Operator: OperatorNotEq, Value: "admin"}
		args := map[string]any{}
		caller := CallerContext{Role: "user"}

		if !cond.evaluate(args, caller) {
			t.Error("expected condition to evaluate to true")
		}
	})

	t.Run("caller.trusted", func(t *testing.T) {
		cond := Condition{Field: "caller.trusted", Operator: OperatorEq, Value: "true"}
		args := map[string]any{}
		caller := CallerContext{Trusted: true}

		if !cond.evaluate(args, caller) {
			t.Error("expected condition to evaluate to true")
		}
	})

	t.Run("args.field", func(t *testing.T) {
		cond := Condition{Field: "args.filename", Operator: OperatorEq, Value: "secret.txt"}
		args := map[string]any{"filename": "secret.txt"}
		caller := CallerContext{}

		if !cond.evaluate(args, caller) {
			t.Error("expected condition to evaluate to true")
		}
	})

	t.Run("unknown field", func(t *testing.T) {
		cond := Condition{Field: "unknown", Operator: OperatorEq, Value: "value"}
		args := map[string]any{}
		caller := CallerContext{}

		if cond.evaluate(args, caller) {
			t.Error("expected condition to evaluate to false for unknown field")
		}
	})
}

func TestOperatorConstants(t *testing.T) {
	if OperatorEq != "eq" {
		t.Errorf("expected 'eq', got '%s'", OperatorEq)
	}
	if OperatorNotEq != "not_eq" {
		t.Errorf("expected 'not_eq', got '%s'", OperatorNotEq)
	}
	if OperatorContains != "contains" {
		t.Errorf("expected 'contains', got '%s'", OperatorContains)
	}
	if OperatorExists != "exists" {
		t.Errorf("expected 'exists', got '%s'", OperatorExists)
	}
}

func TestRateLimit(t *testing.T) {
	rl := RateLimit{
		Count:  10,
		Window: time.Minute,
	}

	if rl.Count != 10 {
		t.Errorf("expected Count 10, got %d", rl.Count)
	}
	if rl.Window != time.Minute {
		t.Errorf("expected Window 1m, got %v", rl.Window)
	}
}

func TestPolicyEvaluateFilterPopulatesRedactedArgs(t *testing.T) {
	p := &Policy{
		Rules: []Rule{
			{
				Name:         "redact_secrets",
				Tools:        []string{"send_email"},
				Action:       ActionFilter,
				RedactFields: []string{"password", "api_key"},
			},
		},
	}

	args := map[string]any{
		"password": "hunter2",
		"api_key":  "sk-live-123",
		"to":       "user@example.com",
	}
	decision := p.Evaluate("send_email", args, CallerContext{})

	if decision.Action != ActionFilter {
		t.Fatalf("expected filter action, got %q", decision.Action)
	}
	if len(decision.RedactedArgs) != 2 {
		t.Fatalf("expected 2 redacted args, got %d: %v", len(decision.RedactedArgs), decision.RedactedArgs)
	}
	for _, field := range []string{"password", "api_key"} {
		if decision.RedactedArgs[field] != RedactedPlaceholder {
			t.Errorf("expected %s to be %q, got %v", field, RedactedPlaceholder, decision.RedactedArgs[field])
		}
	}
	if _, ok := decision.RedactedArgs["to"]; ok {
		t.Error("non-sensitive field 'to' should not be redacted")
	}
	if args["password"] != "hunter2" {
		t.Error("Evaluate must not mutate the caller's args map")
	}
}

func TestPolicyEvaluateRedactsOnlyPresentFields(t *testing.T) {
	p := &Policy{
		Rules: []Rule{{
			Name:         "redact",
			Tools:        []string{"*"},
			Action:       ActionFilter,
			RedactFields: []string{"password", "missing_field"},
		}},
	}

	decision := p.Evaluate("any_tool", map[string]any{"password": "x"}, CallerContext{})
	if len(decision.RedactedArgs) != 1 {
		t.Fatalf("expected only present fields redacted, got %v", decision.RedactedArgs)
	}
	if _, ok := decision.RedactedArgs["missing_field"]; ok {
		t.Error("absent field should not appear in RedactedArgs")
	}
}

func TestPolicyEvaluateNonFilterRuleHasNoRedactedArgs(t *testing.T) {
	p := &Policy{
		Rules: []Rule{{
			Name:         "allow_rule",
			Tools:        []string{"*"},
			Action:       ActionAllow,
			RedactFields: []string{"password"},
		}},
	}

	decision := p.Evaluate("any_tool", map[string]any{"password": "x"}, CallerContext{})
	if len(decision.RedactedArgs) != 0 {
		t.Errorf("allow rule should not populate RedactedArgs, got %v", decision.RedactedArgs)
	}
}
