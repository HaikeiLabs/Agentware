package memory

import (
	"encoding/json"
	"slices"
	"testing"
)

func lintIssues(t *testing.T, w *WikiMemory, args map[string]any) []map[string]any {
	t.Helper()
	res, err := w.Execute(callerCtx("alice"), ToolLint, args)
	if err != nil || !res.Success {
		t.Fatalf("lint failed: %+v %v", res, err)
	}
	var raw []map[string]any
	if err := json.Unmarshal([]byte(res.Output), &raw); err != nil {
		t.Fatalf("bad lint output %q: %v", res.Output, err)
	}
	return raw
}

func constraintsByPage(rows []map[string]any) map[string][]string {
	out := map[string][]string{}
	for _, row := range rows {
		page, _ := row["page"].(string)
		violation := row["Violation"].(map[string]any)
		out[page] = append(out[page], violation["constraint"].(string))
	}
	return out
}

func TestLintFindsHygieneIssues(t *testing.T) {
	w := enableTestMemory(t)
	ctx := callerCtx("alice")
	pages := []string{
		// Orphan: no links in or out.
		"---\nid: island-page\ntype: sw:Skill\n---\nNothing links here.\n",
		// Stale + only bare skos:related links (missing typed links) +
		// dangling target.
		"---\nid: old-notes\ntype: sw:Skill\nupdated: 2020-01-01\n---\nSee [[missing-page]].\n",
		// Healthy: typed link both ways keeps these two non-orphans.
		"---\nid: goroutines\ntype: sw:Skill\n---\nPart of [[channels|pred=sw:buildsToward]].\n",
		"---\nid: channels\ntype: sw:Skill\nlinks:\n  - {pred: sw:requiresPrerequisite, target: goroutines}\n---\n",
	}
	for _, content := range pages {
		if res, err := w.Execute(ctx, ToolWritePage, map[string]any{"content": content}); err != nil || !res.Success {
			t.Fatalf("write failed: %+v %v", res, err)
		}
	}
	got := constraintsByPage(lintIssues(t, w, map[string]any{}))

	assertHas := func(page, constraint string) {
		t.Helper()
		if !slices.Contains(got[page], constraint) {
			t.Errorf("expected %s on %s, got %v", constraint, page, got)
		}
	}
	assertHas("island-page", LintOrphanPage)
	assertHas("old-notes", LintStalePage)
	assertHas("old-notes", LintMissingTypedLink)
	assertHas("old-notes", LintDanglingLink)
	for _, healthy := range []string{"goroutines", "channels"} {
		if len(got[healthy]) != 0 {
			t.Errorf("healthy page %s should be clean, got %v", healthy, got[healthy])
		}
	}
	// stale_days is tunable: with a huge threshold the stale finding goes away.
	relaxed := constraintsByPage(lintIssues(t, w, map[string]any{"stale_days": float64(36500)}))
	for _, c := range relaxed["old-notes"] {
		if c == LintStalePage {
			t.Errorf("stale finding must respect stale_days, got %v", relaxed["old-notes"])
		}
	}
}
