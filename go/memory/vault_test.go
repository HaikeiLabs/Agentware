package memory

import (
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func newTestVault(t *testing.T) *Vault {
	t.Helper()
	v, err := NewVault(t.TempDir())
	if err != nil {
		t.Fatalf("NewVault: %v", err)
	}
	return v
}

func TestEnsureUserSeedsLayout(t *testing.T) {
	v := newTestVault(t)
	if err := v.EnsureUser("alice"); err != nil {
		t.Fatalf("EnsureUser: %v", err)
	}
	wiki, _ := v.WikiDir("alice")
	raw, _ := v.RawDir("alice")
	for _, path := range []string{
		filepath.Join(wiki, "index.md"),
		filepath.Join(wiki, "log.md"),
	} {
		if _, err := os.Stat(path); err != nil {
			t.Errorf("expected seeded file %s: %v", path, err)
		}
	}
	if info, err := os.Stat(raw); err != nil || !info.IsDir() {
		t.Errorf("expected raw dir %s: %v", raw, err)
	}
}

func TestEnsureUserIdempotentAndNonDestructive(t *testing.T) {
	v := newTestVault(t)
	if err := v.EnsureUser("alice"); err != nil {
		t.Fatalf("EnsureUser: %v", err)
	}
	wiki, _ := v.WikiDir("alice")
	index := filepath.Join(wiki, "index.md")
	if err := os.WriteFile(index, []byte("edited"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := v.EnsureUser("alice"); err != nil {
		t.Fatalf("EnsureUser second call: %v", err)
	}
	data, err := os.ReadFile(index)
	if err != nil {
		t.Fatal(err)
	}
	if string(data) != "edited" {
		t.Errorf("EnsureUser overwrote existing index.md: %q", data)
	}
}

func TestUserRootRejectsUnsafeIDs(t *testing.T) {
	v := newTestVault(t)
	for _, id := range []string{
		"", "..", "../alice", "alice/bob", "a/../../etc", ".hidden",
		"alice\x00", "/abs",
	} {
		if _, err := v.UserRoot(id); err == nil {
			t.Errorf("UserRoot(%q): expected error, got nil", id)
		}
	}
	for _, id := range []string{"alice", "user@example.com", "a-b_c.d", "42"} {
		if _, err := v.UserRoot(id); err != nil {
			t.Errorf("UserRoot(%q): unexpected error %v", id, err)
		}
	}
}

func TestPagePathEnforcesKebabCaseAndContainment(t *testing.T) {
	v := newTestVault(t)
	path, err := v.PagePath("alice", "go-worker-pools")
	if err != nil {
		t.Fatalf("PagePath: %v", err)
	}
	if !strings.HasSuffix(path, filepath.Join("alice", "wiki", "go-worker-pools.md")) {
		t.Errorf("unexpected page path %s", path)
	}
	for _, id := range []string{
		"", "UPPER", "has space", "trailing-", "-leading", "a..b",
		"../escape", "nested/page", "double--dash",
	} {
		if _, err := v.PagePath("alice", id); !errors.Is(err, ErrInvalidPageID) {
			t.Errorf("PagePath(%q): expected ErrInvalidPageID, got %v", id, err)
		}
	}
}

func TestContainsRejectsCrossUserPaths(t *testing.T) {
	v := newTestVault(t)
	alicePage, err := v.PagePath("alice", "notes")
	if err != nil {
		t.Fatal(err)
	}
	if !v.Contains("alice", alicePage) {
		t.Errorf("Contains should accept alice's own page")
	}
	if v.Contains("bob", alicePage) {
		t.Errorf("Contains must reject alice's page for bob")
	}
	sneaky := filepath.Join(v.Root(), "bob", "..", "alice", "wiki", "notes.md")
	if v.Contains("bob", sneaky) {
		t.Errorf("Contains must reject traversal into another user's vault")
	}
	if v.Contains("alice", filepath.Join(v.Root(), "..", "outside.md")) {
		t.Errorf("Contains must reject paths outside the memory root")
	}
}
