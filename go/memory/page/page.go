// Package page parses wiki-memory pages: YAML frontmatter per the contract
// in SCHEMA.md plus typed wikilinks in prose, and emits the page's A-box as
// N-Triples for validation against the T-box.
package page

import (
	"bytes"
	"errors"
	"fmt"
	"regexp"
	"strings"

	"gopkg.in/yaml.v3"
)

// DefaultLinkPred is the predicate assumed for bare [[target]] wikilinks.
const DefaultLinkPred = "skos:related"

var (
	// ErrNoFrontmatter reports a page without a leading YAML frontmatter block.
	ErrNoFrontmatter = errors.New("page: missing frontmatter block")
	// ErrContract reports frontmatter that violates the structural contract
	// (missing/invalid id or type). Semantic (ontology) violations are the
	// validator's job, not the parser's.
	ErrContract = errors.New("page: frontmatter contract violation")
)

// Link is a typed edge to another page in the same vault.
type Link struct {
	Pred   string `yaml:"pred"`
	Target string `yaml:"target"`
}

// Claim is an atomic assertion tracked by the inference layer. Supports
// and Contradicts reference other claims: "c2" within the same page or
// "other-page#c1" across pages.
type Claim struct {
	ID          string   `yaml:"id"`
	Text        string   `yaml:"text"`
	Sources     []string `yaml:"sources"`
	Supports    []string `yaml:"supports"`
	Contradicts []string `yaml:"contradicts"`
	Confidence  *float64 `yaml:"confidence"`
	Contested   bool     `yaml:"contested"`
}

// Frontmatter is the typed header of a wiki page (see SCHEMA.md).
type Frontmatter struct {
	ID      string   `yaml:"id"`
	Type    string   `yaml:"type"`
	Labels  []string `yaml:"labels"`
	Topics  []string `yaml:"topics"`
	Links   []Link   `yaml:"links"`
	Claims  []Claim  `yaml:"claims"`
	Sources []string `yaml:"sources"`
	Updated string   `yaml:"updated"`
}

// Page is a parsed wiki page.
type Page struct {
	Frontmatter
	// Body is the markdown after the frontmatter block.
	Body string
	// ProseLinks are wikilinks extracted from Body: [[target|pred=p]] typed,
	// [[target]] defaulting to skos:related.
	ProseLinks []Link
}

// AllLinks returns frontmatter links followed by prose links, deduplicated
// by (pred, target).
func (p *Page) AllLinks() []Link {
	seen := make(map[Link]bool)
	var out []Link
	for _, l := range append(append([]Link{}, p.Links...), p.ProseLinks...) {
		if !seen[l] {
			seen[l] = true
			out = append(out, l)
		}
	}
	return out
}

var (
	frontmatterDelim = []byte("---")
	pageIDPattern    = regexp.MustCompile(`^[a-z0-9]+(-[a-z0-9]+)*$`)
	curiePattern     = regexp.MustCompile(`^[A-Za-z][A-Za-z0-9]*:[A-Za-z0-9_-]+$`)
	wikilinkPattern  = regexp.MustCompile(`\[\[([a-z0-9-]+)(?:\|pred=([A-Za-z][A-Za-z0-9]*:[A-Za-z0-9_-]+))?\]\]`)
	claimRefPattern  = regexp.MustCompile(`^([a-z0-9]+(-[a-z0-9]+)*#)?[A-Za-z0-9_-]+$`)
)

// Parse parses raw page bytes. It enforces the structural contract (required
// kebab-case id, required CURIE type, kebab-case link targets, CURIE link
// predicates, unique claim ids); ontology-level validity is checked later by
// the validator.
func Parse(data []byte) (*Page, error) {
	fm, body, err := splitFrontmatter(data)
	if err != nil {
		return nil, err
	}
	var p Page
	dec := yaml.NewDecoder(bytes.NewReader(fm))
	dec.KnownFields(true)
	if err := dec.Decode(&p.Frontmatter); err != nil {
		return nil, fmt.Errorf("page: parse frontmatter: %w", err)
	}
	p.Body = string(body)
	for _, m := range wikilinkPattern.FindAllStringSubmatch(p.Body, -1) {
		link := Link{Pred: m[2], Target: m[1]}
		if link.Pred == "" {
			link.Pred = DefaultLinkPred
		}
		p.ProseLinks = append(p.ProseLinks, link)
	}
	if err := p.checkContract(); err != nil {
		return nil, err
	}
	return &p, nil
}

func (p *Page) checkContract() error {
	if !pageIDPattern.MatchString(p.ID) {
		return fmt.Errorf("%w: id %q is not kebab-case", ErrContract, p.ID)
	}
	if !curiePattern.MatchString(p.Type) {
		return fmt.Errorf("%w: type %q is not a CURIE", ErrContract, p.Type)
	}
	for _, t := range p.Topics {
		if !curiePattern.MatchString(t) {
			return fmt.Errorf("%w: topic %q is not a CURIE", ErrContract, t)
		}
	}
	for _, l := range p.Links {
		if !curiePattern.MatchString(l.Pred) {
			return fmt.Errorf("%w: link pred %q is not a CURIE", ErrContract, l.Pred)
		}
		if !pageIDPattern.MatchString(l.Target) {
			return fmt.Errorf("%w: link target %q is not a kebab-case page id", ErrContract, l.Target)
		}
	}
	claimIDs := make(map[string]bool)
	for _, c := range p.Claims {
		if c.ID == "" || strings.TrimSpace(c.Text) == "" {
			return fmt.Errorf("%w: claim needs non-empty id and text", ErrContract)
		}
		if claimIDs[c.ID] {
			return fmt.Errorf("%w: duplicate claim id %q", ErrContract, c.ID)
		}
		claimIDs[c.ID] = true
		for _, ref := range append(append([]string{}, c.Supports...), c.Contradicts...) {
			if !claimRefPattern.MatchString(ref) {
				return fmt.Errorf("%w: claim ref %q (want \"c2\" or \"page-id#c2\")", ErrContract, ref)
			}
		}
	}
	return nil
}

// splitFrontmatter returns the YAML block between the first two `---` lines
// and the remaining body.
func splitFrontmatter(data []byte) (fm, body []byte, err error) {
	lines := bytes.SplitAfter(data, []byte("\n"))
	if len(lines) == 0 || !bytes.Equal(bytes.TrimSpace(lines[0]), frontmatterDelim) {
		return nil, nil, ErrNoFrontmatter
	}
	for i := 1; i < len(lines); i++ {
		if bytes.Equal(bytes.TrimSpace(lines[i]), frontmatterDelim) {
			return bytes.Join(lines[1:i], nil), bytes.Join(lines[i+1:], nil), nil
		}
	}
	return nil, nil, fmt.Errorf("%w: unterminated block", ErrNoFrontmatter)
}
