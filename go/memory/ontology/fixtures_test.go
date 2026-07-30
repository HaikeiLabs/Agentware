package ontology

// Fixture gate for the SKOS validation layer: the loop spec requires these
// exact behaviors on the thesaurus fixtures before the validator is trusted
// on real memory content.

import (
	"context"
	"os"
	"slices"
	"testing"

	"github.com/soypete/ontology-go/ttl"
	"github.com/soypete/ontology-go/types"
)

const thesaurusDir = "../../../ontologies/thesaurus/"

func loadFixture(t *testing.T, name string) []types.Triple {
	t.Helper()
	f, err := os.Open(thesaurusDir + name)
	if err != nil {
		t.Skipf("fixture unavailable (run: git submodule update --init): %v", err)
	}
	defer func() { _ = f.Close() }()
	triples, err := ttl.NewTurtleParser().Parse(f)
	if err != nil {
		t.Fatalf("parse %s: %v", name, err)
	}
	if len(triples) == 0 {
		t.Fatalf("fixture %s parsed to zero triples", name)
	}
	return triples
}

func checkGraph(t *testing.T, triples []types.Triple) []Violation {
	t.Helper()
	vs, err := CheckSKOSGraph(context.Background(), triples)
	if err != nil {
		t.Fatalf("CheckSKOSGraph: %v", err)
	}
	return vs
}

func TestFullSKOSFixturePasses(t *testing.T) {
	vs := checkGraph(t, loadFixture(t, "full_skos.ttl"))
	if len(vs) != 0 {
		t.Errorf("full_skos.ttl must pass, got violations: %v", vs)
	}
}

func TestTransitiveBroaderFixturePasses(t *testing.T) {
	triples := loadFixture(t, "transitive_broader.ttl")
	if vs := checkGraph(t, triples); len(vs) != 0 {
		t.Errorf("transitive_broader.ttl must pass, got violations: %v", vs)
	}
	// selfPaced → onlineCourse → course must close transitively.
	closure := TransitiveBroader(triples, "http://example.org/selfPaced")
	want := []string{"http://example.org/onlineCourse", "http://example.org/course"}
	for _, iri := range want {
		if !slices.Contains(closure, iri) {
			t.Errorf("transitive closure of selfPaced missing %s (got %v)", iri, closure)
		}
	}
}

func TestCycleDetectionFixtureRejected(t *testing.T) {
	vs := checkGraph(t, loadFixture(t, "cycle_detection.ttl"))
	var cycles []Violation
	for _, v := range vs {
		if v.Constraint == ConstraintSKOSCycle {
			cycles = append(cycles, v)
		}
	}
	if len(cycles) == 0 {
		t.Fatalf("cycle_detection.ttl must be rejected with a %s violation, got %v",
			ConstraintSKOSCycle, vs)
	}
	// Diagnostics must be clear: name an offending concept and say "circular".
	v := cycles[0]
	if v.Term == "" || v.Message == "" {
		t.Errorf("cycle violation lacks diagnostics: %+v", v)
	}
	// TransitiveBroader must terminate on the cycle (A→B→C→A).
	closure := TransitiveBroader(loadFixture(t, "cycle_detection.ttl"), "http://example.org/A")
	if len(closure) != 2 {
		t.Errorf("cycle closure of A should visit B and C once each, got %v", closure)
	}
}

func TestInconsistencyFixtureRejected(t *testing.T) {
	vs := checkGraph(t, loadFixture(t, "inconsistency_broader_narrower.ttl"))
	found := false
	for _, v := range vs {
		if v.Constraint == ConstraintSKOSHierarchy {
			found = true
			if v.Term == "" || v.Message == "" {
				t.Errorf("inconsistency violation lacks diagnostics: %+v", v)
			}
		}
	}
	if !found {
		t.Errorf("inconsistency_broader_narrower.ttl must be rejected with a %s violation, got %v",
			ConstraintSKOSHierarchy, vs)
	}
}

func TestSymmetricRelatedFixtureInference(t *testing.T) {
	triples := loadFixture(t, "symmetric_related.ttl")
	inferred := InferSymmetricRelated(triples)
	want := types.Triple{
		Subject:   "http://example.org/science",
		Predicate: "http://www.w3.org/2004/02/skos/core#related",
		Object:    "http://example.org/math",
	}
	if len(inferred) != 1 || inferred[0] != want {
		t.Fatalf("expected inferred triple %v, got %v", want, inferred)
	}
	// Idempotent: once the symmetric closure is present, nothing new.
	if again := InferSymmetricRelated(append(triples, inferred...)); len(again) != 0 {
		t.Errorf("inference must be idempotent, got %v", again)
	}
}
