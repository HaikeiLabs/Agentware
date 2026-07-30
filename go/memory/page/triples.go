package page

import (
	"errors"
	"fmt"
	"io"
	"sort"
	"strings"

	"github.com/soypete/ontology-go/types"
)

// Namespaces used when emitting the A-box. All standard or T-box
// vocabularies — never invented terms (see SCHEMA.md).
const (
	skosNS      = "http://www.w3.org/2004/02/skos/core#"
	skosPref    = skosNS + "prefLabel"
	skosAlt     = skosNS + "altLabel"
	dctermsNS   = "http://purl.org/dc/terms/"
	dctermsSubj = dctermsNS + "subject"
	l2wsNS      = "http://soypete.tech/l2ws/"
	twitchNS    = "http://soypete.tech/twitch/topics/"

	// DefaultBase is the default namespace for page IRIs. Callers embed the
	// vault owner to keep A-boxes user-scoped, e.g. DefaultBase + "alice/".
	DefaultBase = "http://soypete.tech/memory/"
)

// ErrUnknownPrefix reports a CURIE whose prefix is not in the prefix map.
// The evaluator turns this into a DENY diagnostic listing valid prefixes.
var ErrUnknownPrefix = errors.New("page: unknown CURIE prefix")

// DefaultPrefixes returns the prefix map from SCHEMA.md plus the standard
// RDF vocabularies.
func DefaultPrefixes() map[string]string {
	return map[string]string{
		"sw":      l2wsNS,
		"twitch":  twitchNS,
		"skos":    skosNS,
		"rdf":     types.RDFNS,
		"rdfs":    types.RDFSNamespace,
		"dcterms": dctermsNS,
	}
}

// ExpandCURIE resolves prefix:local against prefixes.
func ExpandCURIE(curie string, prefixes map[string]string) (string, error) {
	prefix, local, ok := strings.Cut(curie, ":")
	if !ok {
		return "", fmt.Errorf("page: %q is not a CURIE", curie)
	}
	ns, ok := prefixes[prefix]
	if !ok {
		known := make([]string, 0, len(prefixes))
		for p := range prefixes {
			known = append(known, p)
		}
		sort.Strings(known)
		return "", fmt.Errorf("%w: %q (known: %s)", ErrUnknownPrefix, prefix, strings.Join(known, ", "))
	}
	return ns + local, nil
}

// Triples emits the page's A-box: rdf:type, labels, topics, and all typed
// links (frontmatter and prose). base is the IRI namespace for page ids in
// this vault. Claims are not emitted as RDF — they stay in frontmatter and
// feed the inference layer, not T-box validation.
func (p *Page) Triples(base string, prefixes map[string]string) ([]types.Triple, error) {
	if base == "" {
		base = DefaultBase
	}
	if prefixes == nil {
		prefixes = DefaultPrefixes()
	}
	subj := base + p.ID

	var triples []types.Triple

	typeIRI, err := ExpandCURIE(p.Type, prefixes)
	if err != nil {
		return nil, err
	}
	triples = append(triples, types.Triple{Subject: subj, Predicate: types.RDFType, Object: typeIRI})

	for i, label := range p.Labels {
		pred := skosAlt
		if i == 0 {
			pred = skosPref
		}
		triples = append(triples, types.Triple{Subject: subj, Predicate: pred, Object: label, IsLiteral: true})
	}

	for _, topic := range p.Topics {
		iri, err := ExpandCURIE(topic, prefixes)
		if err != nil {
			return nil, err
		}
		triples = append(triples, types.Triple{Subject: subj, Predicate: dctermsSubj, Object: iri})
	}

	for _, link := range p.AllLinks() {
		predIRI, err := ExpandCURIE(link.Pred, prefixes)
		if err != nil {
			return nil, err
		}
		triples = append(triples, types.Triple{Subject: subj, Predicate: predIRI, Object: base + link.Target})
	}
	return triples, nil
}

// WriteNTriples serializes the page's A-box to w in N-Triples format.
func (p *Page) WriteNTriples(w io.Writer, base string, prefixes map[string]string) error {
	triples, err := p.Triples(base, prefixes)
	if err != nil {
		return err
	}
	for _, t := range triples {
		if _, err := io.WriteString(w, FormatNTriple(t)+"\n"); err != nil {
			return fmt.Errorf("page: write triple: %w", err)
		}
	}
	return nil
}

// FormatNTriple renders one triple as an N-Triples line (without newline).
func FormatNTriple(t types.Triple) string {
	obj := "<" + t.Object + ">"
	if t.IsLiteral {
		obj = `"` + escapeLiteral(t.Object) + `"`
		switch {
		case t.Language != "":
			obj += "@" + t.Language
		case t.Datatype != "" && t.Datatype != types.XSDString:
			obj += "^^<" + t.Datatype + ">"
		}
	}
	return fmt.Sprintf("<%s> <%s> %s .", t.Subject, t.Predicate, obj)
}

var literalEscaper = strings.NewReplacer(
	`\`, `\\`, `"`, `\"`, "\n", `\n`, "\r", `\r`, "\t", `\t`,
)

func escapeLiteral(s string) string { return literalEscaper.Replace(s) }
