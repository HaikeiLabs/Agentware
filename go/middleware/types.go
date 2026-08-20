package middleware

import "time"

type Action string

const (
	ActionAllow  Action = "allow"
	ActionDeny   Action = "deny"
	ActionFilter Action = "filter"
)

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
