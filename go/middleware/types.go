package middleware

import "time"

type Action string

const (
	ActionAllow  Action = "allow"
	ActionDeny   Action = "deny"
	ActionFilter Action = "filter"
)

// RedactedPlaceholder replaces the value of any argument redacted by a filter rule.
const RedactedPlaceholder = "[REDACTED]"

type CallerContext struct {
	UserID          string
	SessionID       string
	Role            string
	Source          string
	Trusted         bool
	Metadata        map[string]string
	InvokingSubject string
	ParentSpan      string
	DelegationDepth int
}

type Decision struct {
	Action       Action
	Rule         string
	Reason       string
	RedactedArgs map[string]any
	Timestamp    time.Time
}
