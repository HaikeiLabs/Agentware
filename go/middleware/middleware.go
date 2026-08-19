package middleware

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"time"

	"github.com/soypete/pedro-agentware/go/tools"
)

type ToolExecutor interface {
	Execute(ctx context.Context, toolName string, args map[string]any) (*tools.Result, error)
}

type Middleware interface {
	ToolExecutor
	WithPolicy(evaluator PolicyEvaluator) Middleware
	WithAuditor(auditor Auditor) Middleware
}

type middlewareImpl struct {
	exec      ToolExecutor
	evaluator PolicyEvaluator
	auditor   Auditor
}

func NewMiddleware(exec ToolExecutor) Middleware {
	return &middlewareImpl{
		exec: exec,
	}
}

func (m *middlewareImpl) Execute(ctx context.Context, toolName string, args map[string]any) (*tools.Result, error) {
	caller := getCallerContext(ctx)

	var decision Decision
	if m.evaluator != nil {
		decision = m.evaluator.Evaluate(toolName, args, caller)
	} else {
		decision = Decision{Action: ActionAllow, Reason: "no policy configured"}
	}

	argsBytes, _ := json.Marshal(args)
	argsHash := sha256.Sum256(argsBytes)
	argsDigest := hex.EncodeToString(argsHash[:])

	auditRecord := AuditRecord{
		InvokedAt:       time.Now(),
		InvokingSubject: caller.UserID,
		ParentSpan:      caller.SessionID,
		ToolName:        toolName,
		ToolArgsDigest:  argsDigest,
		Decision:        string(decision.Action),
		PolicyID:        decision.Rule,
	}

	if decision.Action == ActionDeny {
		auditRecord.LatencyMs = 0
		auditRecord.Error = "denied by policy: " + decision.Reason
		auditRecord.Success = false
		if m.auditor != nil {
			m.auditor.Record(auditRecord)
		}
		return &tools.Result{
			Success: false,
			Error:   "denied by policy: " + decision.Reason,
		}, nil
	}

	if decision.Action == ActionFilter && len(decision.RedactedArgs) > 0 {
		for k, v := range decision.RedactedArgs {
			args[k] = v
		}
	}

	start := time.Now()
	result, err := m.exec.Execute(ctx, toolName, args)
	auditRecord.LatencyMs = int(time.Since(start).Milliseconds())
	if err != nil {
		auditRecord.Error = err.Error()
		auditRecord.Success = false
	} else if result != nil {
		auditRecord.Success = result.Success
		if !result.Success && result.Error != "" {
			auditRecord.Error = result.Error
		}
	} else {
		auditRecord.Success = false
		auditRecord.Error = "nil result with no error"
	}

	if m.auditor != nil {
		m.auditor.Record(auditRecord)
	}

	return result, err
}

func (m *middlewareImpl) WithPolicy(evaluator PolicyEvaluator) Middleware {
	m.evaluator = evaluator
	return m
}

func (m *middlewareImpl) WithAuditor(auditor Auditor) Middleware {
	m.auditor = auditor
	return m
}

func getCallerContext(ctx context.Context) CallerContext {
	if c, ok := ctx.Value(callerContextKey).(CallerContext); ok {
		return c
	}
	return CallerContext{
		Trusted: false,
	}
}

type contextKey string

const callerContextKey contextKey = "caller_context"

func WithCallerContext(ctx context.Context, caller CallerContext) context.Context {
	return context.WithValue(ctx, callerContextKey, caller)
}

// CallerFromContext returns the CallerContext attached to ctx, if any.
// Downstream executors use this to scope work to the calling user.
func CallerFromContext(ctx context.Context) (CallerContext, bool) {
	c, ok := ctx.Value(callerContextKey).(CallerContext)
	return c, ok
}
