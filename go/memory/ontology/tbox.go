// Package ontology loads a read-only T-box and validates wiki-memory
// content against it. It is the single source of validation rules with two
// consumers: the middleware OntologyEvaluator (write-time enforcement) and
// the memlint CI check. Gaps in the T-box are recorded in SCHEMA_GAPS.md,
// never patched here.
package ontology

import (
	"fmt"
	"os"
	"sort"
	"strings"

	"github.com/soypete/ontology-go/ttl"
	"github.com/soypete/ontology-go/types"
)

const (
	owlClass       = "http://www.w3.org/2002/07/owl#Class"
	rdfsClass      = types.RDFSNamespace + "Class"
	skosNS         = "http://www.w3.org/2004/02/skos/core#"
	skosConcept    = skosNS + "Concept"
	skosPrefLabel  = skosNS + "prefLabel"
	skosAltLabel   = skosNS + "altLabel"
	skosRelated    = skosNS + "related"
	skosBroader    = skosNS + "broader"
	skosNarrower   = skosNS + "narrower"
	dctermsSubject = "http://purl.org/dc/terms/subject"
	rdfsLabel      = types.RDFSLabel
)

// Property is a T-box property with its declared domains and ranges.
type Property struct {
	IRI    string
	Domain []string
	Range  []string
}

// TBox is an indexed, read-only terminology: classes, properties with
// domain/range, SKOS concepts, and labels for suggestions and ingest-time
// label matching.
type TBox struct {
	classes    map[string]bool
	properties map[string]*Property
	concepts   map[string]bool
	superOf    map[string][]string
	labelIndex map[string]string // lowercased pref/alt label -> concept IRI
	triples    []types.Triple
}

// Load parses the given Turtle files and builds a merged T-box index.
func Load(paths ...string) (*TBox, error) {
	var all []types.Triple
	for _, path := range paths {
		f, err := os.Open(path)
		if err != nil {
			return nil, fmt.Errorf("ontology: open %s: %w", path, err)
		}
		triples, err := ttl.NewTurtleParser().Parse(f)
		f.Close()
		if err != nil {
			return nil, fmt.Errorf("ontology: parse %s: %w", path, err)
		}
		all = append(all, triples...)
	}
	return New(all), nil
}

// New builds a T-box index from already-parsed triples.
func New(triples []types.Triple) *TBox {
	t := &TBox{
		classes:    make(map[string]bool),
		properties: make(map[string]*Property),
		concepts:   make(map[string]bool),
		superOf:    make(map[string][]string),
		labelIndex: make(map[string]string),
		triples:    triples,
	}
	// SKOS core properties and the topic predicate are usable without being
	// re-declared in the T-box (standard vocabulary, not invented terms).
	for _, iri := range []string{skosRelated, skosBroader, skosNarrower, dctermsSubject} {
		t.properties[iri] = &Property{IRI: iri}
	}
	prop := func(subj string) *Property {
		if t.properties[subj] == nil {
			t.properties[subj] = &Property{IRI: subj}
		}
		return t.properties[subj]
	}
	for _, tr := range triples {
		switch tr.Predicate {
		case types.RDFType:
			switch tr.Object {
			case owlClass, rdfsClass:
				t.classes[tr.Subject] = true
			case skosConcept:
				t.concepts[tr.Subject] = true
			case types.OWLObjectProperty, types.OWLDatatypeProperty,
				types.OWLAnnotationProperty, types.RDFNS + "Property":
				prop(tr.Subject)
			}
		case types.RDFSSubClassOf:
			t.superOf[tr.Subject] = append(t.superOf[tr.Subject], tr.Object)
		case types.RDFSdomain:
			p := prop(tr.Subject)
			p.Domain = append(p.Domain, tr.Object)
		case types.RDFSRange:
			p := prop(tr.Subject)
			p.Range = append(p.Range, tr.Object)
		case skosPrefLabel, skosAltLabel, rdfsLabel:
			if tr.IsLiteral {
				t.labelIndex[strings.ToLower(tr.Object)] = tr.Subject
			}
		}
	}
	return t
}

// Triples returns the raw T-box triples (read-only; callers must not modify).
func (t *TBox) Triples() []types.Triple { return t.triples }

// HasClass reports whether iri is a declared class.
func (t *TBox) HasClass(iri string) bool { return t.classes[iri] }

// HasConcept reports whether iri is a declared SKOS concept.
func (t *TBox) HasConcept(iri string) bool { return t.concepts[iri] }

// PropertyFor returns the property declaration for iri, if any.
func (t *TBox) PropertyFor(iri string) (*Property, bool) {
	p, ok := t.properties[iri]
	return p, ok
}

// IsSubclassOf reports whether class equals ancestor or reaches it via
// rdfs:subClassOf (transitive).
func (t *TBox) IsSubclassOf(class, ancestor string) bool {
	if class == ancestor {
		return true
	}
	seen := map[string]bool{class: true}
	queue := append([]string{}, t.superOf[class]...)
	for len(queue) > 0 {
		c := queue[0]
		queue = queue[1:]
		if c == ancestor {
			return true
		}
		if seen[c] {
			continue
		}
		seen[c] = true
		queue = append(queue, t.superOf[c]...)
	}
	return false
}

// MatchConceptLabel resolves a human label ("Golang") to a concept IRI via
// case-insensitive prefLabel/altLabel matching. Used during ingest.
func (t *TBox) MatchConceptLabel(label string) (string, bool) {
	iri, ok := t.labelIndex[strings.ToLower(strings.TrimSpace(label))]
	return iri, ok
}

// TermKind selects which vocabulary Nearest searches.
type TermKind int

const (
	KindClass TermKind = iota
	KindProperty
	KindConcept
)

// Nearest returns up to n known terms of the given kind closest to iri by
// edit distance over local names. Used to build self-correction diagnostics.
func (t *TBox) Nearest(iri string, kind TermKind, n int) []string {
	var pool []string
	switch kind {
	case KindClass:
		for c := range t.classes {
			pool = append(pool, c)
		}
	case KindProperty:
		for p := range t.properties {
			pool = append(pool, p)
		}
	case KindConcept:
		for c := range t.concepts {
			pool = append(pool, c)
		}
	}
	target := strings.ToLower(localName(iri))
	sort.Slice(pool, func(i, j int) bool {
		di := levenshtein(target, strings.ToLower(localName(pool[i])))
		dj := levenshtein(target, strings.ToLower(localName(pool[j])))
		if di != dj {
			return di < dj
		}
		return pool[i] < pool[j]
	})
	if len(pool) > n {
		pool = pool[:n]
	}
	return pool
}

func localName(iri string) string {
	for _, sep := range []string{"#", "/"} {
		if i := strings.LastIndex(iri, sep); i >= 0 && i < len(iri)-1 {
			return iri[i+1:]
		}
	}
	return iri
}

func levenshtein(a, b string) int {
	ra, rb := []rune(a), []rune(b)
	prev := make([]int, len(rb)+1)
	cur := make([]int, len(rb)+1)
	for j := range prev {
		prev[j] = j
	}
	for i := 1; i <= len(ra); i++ {
		cur[0] = i
		for j := 1; j <= len(rb); j++ {
			cost := 1
			if ra[i-1] == rb[j-1] {
				cost = 0
			}
			cur[j] = min(prev[j]+1, min(cur[j-1]+1, prev[j-1]+cost))
		}
		prev, cur = cur, prev
	}
	return prev[len(rb)]
}
