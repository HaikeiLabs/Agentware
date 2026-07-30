package memory

import (
	"context"
	"encoding/json"
	"fmt"
	"testing"
)

// buildLearningVault writes a small skill graph through the enforced path:
//
//	goroutines <-requiresPrerequisite- channels <-req- go-worker-pools
//	go-worker-pools -buildsToward-> go-concurrency ; both appropriate for
//	backend-engineer (a sw:Role page). Claims carry confidence/contested.
func buildLearningVault(t *testing.T, w *WikiMemory) context.Context {
	t.Helper()
	ctx := callerCtx("alice")
	pages := []string{
		"---\nid: backend-engineer\ntype: sw:Role\nlabels: [\"Backend Engineer\"]\n---\n",
		"---\nid: goroutines\ntype: sw:Skill\nlabels: [\"Goroutines\"]\n---\n",
		"---\nid: channels\ntype: sw:Skill\nlabels: [\"Channels\"]\nlinks:\n" +
			"  - {pred: sw:requiresPrerequisite, target: goroutines}\n---\n",
		"---\nid: go-concurrency\ntype: sw:Skill\nlabels: [\"Advanced Concurrency\"]\n" +
			"links:\n  - {pred: sw:isAppropriateFor, target: backend-engineer}\n---\n",
		"---\nid: go-worker-pools\ntype: sw:Skill\nlabels: [\"Worker Pools\"]\nlinks:\n" +
			"  - {pred: sw:requiresPrerequisite, target: channels}\n" +
			"  - {pred: sw:buildsToward, target: go-concurrency}\n" +
			"  - {pred: sw:isAppropriateFor, target: backend-engineer}\n" +
			"claims:\n" +
			"  - {id: c1, text: \"Pools prevent leaks\", confidence: 0.94}\n" +
			"  - {id: c2, text: \"Leaks are harmless\", confidence: 0.21, contested: true}\n" +
			"  - {id: c3, text: \"Pools are slower than unbounded spawning\", confidence: 0.4}\n---\n",
	}
	for _, content := range pages {
		res, err := w.Execute(ctx, ToolWritePage, map[string]any{"content": content})
		if err != nil || !res.Success {
			t.Fatalf("write failed: %+v %v", res, err)
		}
	}
	return ctx
}

func structQuery(t *testing.T, w *WikiMemory, ctx context.Context, args map[string]any) []map[string]any {
	t.Helper()
	res, err := w.Execute(ctx, ToolQuery, args)
	if err != nil || !res.Success {
		t.Fatalf("query %v failed: %+v %v", args, res, err)
	}
	var out []map[string]any
	if err := json.Unmarshal([]byte(res.Output), &out); err != nil {
		t.Fatalf("bad query output %q: %v", res.Output, err)
	}
	return out
}

func ids(rows []map[string]any) []string {
	out := make([]string, len(rows))
	for i, r := range rows {
		out[i] = fmt.Sprint(r["id"])
	}
	return out
}

func TestQueryPrerequisitesTransitive(t *testing.T) {
	w := enableTestMemory(t)
	ctx := buildLearningVault(t, w)
	rows := structQuery(t, w, ctx, map[string]any{
		"kind": QueryPrerequisites, "page_id": "go-worker-pools",
	})
	if got := ids(rows); len(got) != 2 || got[0] != "channels" || got[1] != "goroutines" {
		t.Errorf("prerequisites = %v, want [channels goroutines] (BFS order)", got)
	}
	if rows[1]["depth"].(float64) != 2 {
		t.Errorf("goroutines should be depth 2, got %v", rows[1]["depth"])
	}
}

func TestQueryBuildsToward(t *testing.T) {
	w := enableTestMemory(t)
	ctx := buildLearningVault(t, w)
	rows := structQuery(t, w, ctx, map[string]any{
		"kind": QueryBuildsToward, "page_id": "go-worker-pools",
	})
	if got := ids(rows); len(got) != 1 || got[0] != "go-concurrency" {
		t.Errorf("builds_toward = %v, want [go-concurrency]", got)
	}
}

func TestQueryLearningPathTopologicalOrder(t *testing.T) {
	w := enableTestMemory(t)
	ctx := buildLearningVault(t, w)
	rows := structQuery(t, w, ctx, map[string]any{
		"kind": QueryLearningPath, "role": "backend-engineer",
	})
	got := ids(rows)
	// Prerequisites first: goroutines before channels before worker pools;
	// go-concurrency has no prerequisites so it sorts among the roots.
	index := map[string]int{}
	for i, id := range got {
		index[id] = i
	}
	for _, pair := range [][2]string{
		{"goroutines", "channels"}, {"channels", "go-worker-pools"},
	} {
		if index[pair[0]] >= index[pair[1]] {
			t.Errorf("learning path %v must place %s before %s", got, pair[0], pair[1])
		}
	}
	if len(got) != 4 {
		t.Errorf("learning path should cover appropriate skills plus transitive prerequisites, got %v", got)
	}
}

func TestQueryContestedAndLowConfidenceClaims(t *testing.T) {
	w := enableTestMemory(t)
	ctx := buildLearningVault(t, w)
	contested := structQuery(t, w, ctx, map[string]any{"kind": QueryContestedClaims})
	if len(contested) != 1 || contested[0]["id"] != "c2" {
		t.Errorf("contested claims = %v, want [c2]", contested)
	}
	low := structQuery(t, w, ctx, map[string]any{"kind": QueryLowConfidence})
	if got := ids(low); len(got) != 2 || got[0] != "c2" || got[1] != "c3" {
		t.Errorf("low confidence = %v, want [c2 c3]", got)
	}
	strict := structQuery(t, w, ctx, map[string]any{
		"kind": QueryLowConfidence, "threshold": 0.3,
	})
	if got := ids(strict); len(got) != 1 || got[0] != "c2" {
		t.Errorf("low confidence @0.3 = %v, want [c2]", got)
	}
}

func TestQueryUnknownKindAndMissingPage(t *testing.T) {
	w := enableTestMemory(t)
	ctx := buildLearningVault(t, w)
	res, err := w.Execute(ctx, ToolQuery, map[string]any{"kind": "bogus"})
	if err != nil || res.Success {
		t.Errorf("unknown kind must fail cleanly: %+v %v", res, err)
	}
	res, err = w.Execute(ctx, ToolQuery, map[string]any{
		"kind": QueryPrerequisites, "page_id": "no-such-page",
	})
	if err != nil || res.Success {
		t.Errorf("missing page must fail cleanly: %+v %v", res, err)
	}
}
