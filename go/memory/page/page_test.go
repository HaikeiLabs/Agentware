package page

import (
	"errors"
	"strings"
	"testing"
)

const samplePage = `---
id: go-worker-pools
type: sw:Skill
labels: ["Worker Pools", "worker pool pattern"]
topics: [twitch:Go, twitch:Concurrency]
links:
  - {pred: sw:requiresPrerequisite, target: goroutines}
  - {pred: skos:related, target: channels}
claims:
  - {id: c1, text: "Bounded worker pools prevent goroutine leaks under load",
     sources: [src-pprof-talk], confidence: null}
sources: [src-pprof-talk, src-go-blog-pipelines]
updated: 2026-07-30
---

Worker pools bound concurrency. They build on [[goroutines]] and
[[select-statement|pred=sw:requiresPrerequisite]]; mastering them
[[go-concurrency-expert|pred=sw:buildsToward]].
`

func TestParseSamplePage(t *testing.T) {
	p, err := Parse([]byte(samplePage))
	if err != nil {
		t.Fatalf("Parse: %v", err)
	}
	if p.ID != "go-worker-pools" || p.Type != "sw:Skill" {
		t.Errorf("frontmatter mismatch: id=%q type=%q", p.ID, p.Type)
	}
	if len(p.Labels) != 2 || p.Labels[0] != "Worker Pools" {
		t.Errorf("labels mismatch: %v", p.Labels)
	}
	if len(p.Claims) != 1 || p.Claims[0].ID != "c1" || p.Claims[0].Confidence != nil {
		t.Errorf("claims mismatch: %+v", p.Claims)
	}
	wantProse := []Link{
		{Pred: "skos:related", Target: "goroutines"},
		{Pred: "sw:requiresPrerequisite", Target: "select-statement"},
		{Pred: "sw:buildsToward", Target: "go-concurrency-expert"},
	}
	if len(p.ProseLinks) != len(wantProse) {
		t.Fatalf("prose links: got %v want %v", p.ProseLinks, wantProse)
	}
	for i, want := range wantProse {
		if p.ProseLinks[i] != want {
			t.Errorf("prose link %d: got %v want %v", i, p.ProseLinks[i], want)
		}
	}
	// AllLinks dedupes: frontmatter has 2, prose has 3, one overlap
	// (goroutines via skos:related is distinct from sw:requiresPrerequisite).
	all := p.AllLinks()
	if len(all) != 5 {
		t.Errorf("AllLinks: got %d links %v, want 5", len(all), all)
	}
}

func TestParseContractViolations(t *testing.T) {
	cases := map[string]string{
		"no frontmatter":     "just prose\n",
		"unterminated":       "---\nid: x\n",
		"missing id":         "---\ntype: sw:Skill\n---\n",
		"bad id case":        "---\nid: BadID\ntype: sw:Skill\n---\n",
		"missing type":       "---\nid: ok-page\n---\n",
		"type not curie":     "---\nid: ok-page\ntype: Skill\n---\n",
		"topic not curie":    "---\nid: ok-page\ntype: sw:Skill\ntopics: [NotCurie]\n---\n",
		"bad link target":    "---\nid: ok-page\ntype: sw:Skill\nlinks:\n  - {pred: skos:related, target: \"../evil\"}\n---\n",
		"bad link pred":      "---\nid: ok-page\ntype: sw:Skill\nlinks:\n  - {pred: related, target: other-page}\n---\n",
		"duplicate claim id": "---\nid: ok-page\ntype: sw:Skill\nclaims:\n  - {id: c1, text: a}\n  - {id: c1, text: b}\n---\n",
		"empty claim text":   "---\nid: ok-page\ntype: sw:Skill\nclaims:\n  - {id: c1, text: \"  \"}\n---\n",
		"unknown field":      "---\nid: ok-page\ntype: sw:Skill\nbogus: field\n---\n",
	}
	for name, src := range cases {
		if _, err := Parse([]byte(src)); err == nil {
			t.Errorf("%s: expected error, got nil", name)
		}
	}
}

func TestParseErrorKinds(t *testing.T) {
	if _, err := Parse([]byte("plain\n")); !errors.Is(err, ErrNoFrontmatter) {
		t.Errorf("expected ErrNoFrontmatter, got %v", err)
	}
	if _, err := Parse([]byte("---\nid: Bad_ID\ntype: sw:Skill\n---\n")); !errors.Is(err, ErrContract) {
		t.Errorf("expected ErrContract, got %v", err)
	}
}

func TestTriplesEmitsABox(t *testing.T) {
	p, err := Parse([]byte(samplePage))
	if err != nil {
		t.Fatal(err)
	}
	var sb strings.Builder
	if err := p.WriteNTriples(&sb, DefaultBase+"alice/", nil); err != nil {
		t.Fatalf("WriteNTriples: %v", err)
	}
	nt := sb.String()
	want := []string{
		`<http://soypete.tech/memory/alice/go-worker-pools> <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <http://soypete.tech/l2ws/Skill> .`,
		`<http://soypete.tech/memory/alice/go-worker-pools> <http://www.w3.org/2004/02/skos/core#prefLabel> "Worker Pools" .`,
		`<http://soypete.tech/memory/alice/go-worker-pools> <http://www.w3.org/2004/02/skos/core#altLabel> "worker pool pattern" .`,
		`<http://soypete.tech/memory/alice/go-worker-pools> <http://purl.org/dc/terms/subject> <http://soypete.tech/twitch/topics/Go> .`,
		`<http://soypete.tech/memory/alice/go-worker-pools> <http://soypete.tech/l2ws/requiresPrerequisite> <http://soypete.tech/memory/alice/goroutines> .`,
		`<http://soypete.tech/memory/alice/go-worker-pools> <http://soypete.tech/l2ws/buildsToward> <http://soypete.tech/memory/alice/go-concurrency-expert> .`,
	}
	for _, line := range want {
		if !strings.Contains(nt, line) {
			t.Errorf("missing triple:\n%s\nin output:\n%s", line, nt)
		}
	}
	if got := strings.Count(nt, "\n"); got != 10 {
		t.Errorf("expected 10 triples (1 type + 2 labels + 2 topics + 5 links), got %d:\n%s", got, nt)
	}
}

func TestTriplesUnknownPrefix(t *testing.T) {
	src := "---\nid: ok-page\ntype: bogus:Thing\n---\n"
	p, err := Parse([]byte(src))
	if err != nil {
		t.Fatal(err)
	}
	if _, err := p.Triples("", nil); !errors.Is(err, ErrUnknownPrefix) {
		t.Errorf("expected ErrUnknownPrefix, got %v", err)
	}
}
