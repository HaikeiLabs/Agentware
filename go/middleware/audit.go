package middleware

import "time"

type AuditRecord struct {
	ID               string
	InvokedAt        time.Time
	InvokingSubject  string
	ParentSpan       string
	DelegationDepth  int
	AgentID          string
	AgentVersion     string
	Framework        string
	ToolName         string
	ToolArgsDigest   string
	ResourcesTouched []string
	Decision         string
	PolicyID         string
	Model            string
	TokensIn         int
	TokensOut        int
	CachedTokens     int
	LatencyMs        int
	Error            string
	Success          bool
	RetryCount       int
}

type Auditor interface {
	Record(record AuditRecord)
	Query(filter AuditFilter) []AuditRecord
}

type AuditFilter struct {
	SessionID string
	ToolName  string
	Action    Action
	Since     time.Time
	Limit     int
}

type InMemoryAuditor struct {
	records []AuditRecord
}

func NewInMemoryAuditor() *InMemoryAuditor {
	return &InMemoryAuditor{
		records: make([]AuditRecord, 0),
	}
}

func (a *InMemoryAuditor) Record(record AuditRecord) {
	a.records = append(a.records, record)
}

func (a *InMemoryAuditor) Query(filter AuditFilter) []AuditRecord {
	result := make([]AuditRecord, 0)
	for _, r := range a.records {
		if filter.SessionID != "" && r.ParentSpan != filter.SessionID {
			continue
		}
		if filter.ToolName != "" && r.ToolName != filter.ToolName {
			continue
		}
		if filter.Action != "" && r.Decision != string(filter.Action) {
			continue
		}
		if !filter.Since.IsZero() && r.InvokedAt.Before(filter.Since) {
			continue
		}
		result = append(result, r)
		if filter.Limit > 0 && len(result) >= filter.Limit {
			break
		}
	}
	return result
}
