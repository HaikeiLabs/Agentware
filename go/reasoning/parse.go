package reasoning

import (
	"regexp"
	"strings"
	"time"
)

// parseNodes turns reasoning text into a chain of context-tree nodes. The
// parser is intentionally deterministic: paragraphs (blank-line separated) map
// to nodes, the first node is the root, and every subsequent node's parent is
// its predecessor. Nodes carry bounded summaries; raw reasoning never reaches
// the tree.
//
// Limits fail closed: too many nodes, too deep a chain, or reasoning larger
// than the configured cap abort the parse instead of emitting a partial tree.
func (a *Adapter) parseNodes(reasoning string, now time.Time) ([]Node, error) {
	if len(reasoning) > a.opts.MaxReasoningBytes {
		return nil, ErrReasoningTooLarge
	}

	paragraphs := splitParagraphs(reasoning)
	if len(paragraphs) > a.opts.MaxNodes {
		return nil, ErrTooManyNodes
	}

	nodes := make([]Node, 0, len(paragraphs))
	var parentID string
	depth := 0

	for _, para := range paragraphs {
		depth++
		if depth > a.opts.MaxDepth {
			return nil, ErrTooDeep
		}

		kind, summary := classifyParagraph(para)
		status, summary := statusFromSummary(summary, kind)
		summary = truncateRunes(summary, a.opts.MaxSummaryChars)
		if summary == "" {
			// An empty node carries no reasoning; skip it rather than emit a
			// meaningless tree entry.
			depth--
			continue
		}

		id := nodeID(kind, parentID, summary)
		nodes = append(nodes, Node{
			ID:           id,
			ParentID:     parentID,
			Kind:         kind,
			Status:       status,
			Summary:      summary,
			EvidenceRefs: extractEvidence(summary),
			ToolCallRefs: extractToolRefs(kind, summary),
			CreatedAt:    now,
			UpdatedAt:    now,
		})
		parentID = id
	}
	return nodes, nil
}

var paragraphSep = regexp.MustCompile("\n[ \t]*\n")

// splitParagraphs splits reasoning text on blank lines and drops empty
// paragraphs.
func splitParagraphs(s string) []string {
	raw := paragraphSep.Split(s, -1)
	paragraphs := make([]string, 0, len(raw))
	for _, p := range raw {
		p = strings.TrimSpace(p)
		if p != "" {
			paragraphs = append(paragraphs, p)
		}
	}
	return paragraphs
}

var listOrnament = regexp.MustCompile(`^\s*(?:[-*+•]|\d+[.)])\s+`)

// kindPrefix matches an explicit kind label at the start of a paragraph.
var kindPrefix = regexp.MustCompile(`(?i)^\s*(goal|observation|decision|tool-call|tool_call|tool-result|tool_result|tool|conclusion|blocker)\s*[:=]\s*`)

// kindFromLabel maps a matched prefix label to its NodeKind.
func kindFromLabel(label string) NodeKind {
	switch strings.ToLower(label) {
	case "goal":
		return KindGoal
	case "observation":
		return KindObservation
	case "decision":
		return KindDecision
	case "tool-call", "tool_call", "tool":
		return KindToolCall
	case "tool-result", "tool_result":
		return KindToolResult
	case "conclusion":
		return KindConclusion
	case "blocker":
		return KindBlocker
	default:
		return KindObservation
	}
}

// classifyParagraph strips list ornaments and an optional kind label, and
// returns the node kind and the remaining summary text.
func classifyParagraph(para string) (NodeKind, string) {
	summary := listOrnament.ReplaceAllString(para, "")
	if m := kindPrefix.FindStringSubmatch(summary); m != nil {
		kind := kindFromLabel(m[1])
		rest := summary[len(m[0]):]
		return kind, strings.TrimSpace(rest)
	}
	return KindObservation, summary
}

// statusMarker matches a trailing status marker like [BLOCKED].
var statusMarker = regexp.MustCompile(`(?i)\s*\[(blocked|pending|active|superseded|complete)\]\s*$`)

func statusFromMarker(label string) NodeStatus {
	switch strings.ToLower(label) {
	case "blocked":
		return StatusBlocked
	case "pending", "active":
		return StatusActive
	case "superseded":
		return StatusSuperseded
	case "complete":
		return StatusComplete
	default:
		return StatusComplete
	}
}

// statusFromSummary applies a trailing status marker and infers blocker
// status. The marker is removed from the summary.
func statusFromSummary(summary string, kind NodeKind) (NodeStatus, string) {
	if m := statusMarker.FindStringSubmatch(summary); m != nil {
		return statusFromMarker(m[1]), strings.TrimSpace(summary[:len(summary)-len(m[0])])
	}
	if kind == KindBlocker {
		return StatusBlocked, summary
	}
	return StatusComplete, summary
}

var evidencePatterns = []*regexp.Regexp{
	regexp.MustCompile(`\[E\d+\]`),
	regexp.MustCompile(`\bref\s*[=:]\s*(\S+)`),
	regexp.MustCompile(`\bevidence\s*[=:]\s*(\S+)`),
}

// extractEvidence collects evidence references from a summary, in order, with
// duplicates removed. Bracketed [E1]-style refs are stored without the
// brackets.
func extractEvidence(summary string) []string {
	var out []string
	seen := make(map[string]bool)
	for _, re := range evidencePatterns {
		for _, m := range re.FindAllStringSubmatch(summary, -1) {
			var ref string
			if len(m) > 1 {
				ref = m[1]
			} else {
				ref = m[0]
			}
			ref = strings.Trim(ref, "[]")
			if ref != "" && !seen[ref] {
				seen[ref] = true
				out = append(out, ref)
			}
		}
	}
	return out
}

var toolRefPattern = regexp.MustCompile(`\b(?:tool|call)\s*[=:]\s*([a-zA-Z_][a-zA-Z0-9_.-]*)`)

// leadingIdentifier matches a leading `name:` / `name=` label in a tool node
// summary (e.g. "refund_tool: {...}").
var leadingIdentifier = regexp.MustCompile(`^([a-zA-Z_][a-zA-Z0-9_.-]*)\s*[:=]`)

// extractToolRefs collects tool identifiers referenced by a tool-call or
// tool-result node: first a leading `name:` label, then an explicit
// tool=/call= reference, then a bare identifier summary.
func extractToolRefs(kind NodeKind, summary string) []string {
	if kind != KindToolCall && kind != KindToolResult {
		return nil
	}
	if m := leadingIdentifier.FindStringSubmatch(summary); m != nil {
		return []string{m[1]}
	}
	if m := toolRefPattern.FindStringSubmatch(summary); m != nil {
		return []string{m[1]}
	}
	if regexp.MustCompile(`^[a-zA-Z_][a-zA-Z0-9_.-]*$`).MatchString(summary) {
		return []string{summary}
	}
	return nil
}

// truncateRunes truncates s to at most n Unicode code points. It never splits
// a code point.
func truncateRunes(s string, n int) string {
	if n <= 0 {
		return ""
	}
	runes := []rune(s)
	if len(runes) <= n {
		return s
	}
	return string(runes[:n])
}
