package memory

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strings"
)

var (
	// ErrInvalidUserID reports a user ID that is empty or unsafe as a
	// directory name.
	ErrInvalidUserID = errors.New("memory: invalid user id")
	// ErrInvalidPageID reports a page ID that is not kebab-case.
	ErrInvalidPageID = errors.New("memory: invalid page id")
	// ErrOutsideVault reports a resolved path that escapes the caller's
	// vault. This is the path-boundary half of the cross-user isolation
	// guarantee (the policy rule is the other half).
	ErrOutsideVault = errors.New("memory: path escapes user vault")
)

// userIDPattern intentionally excludes path separators, "..", and leading
// dots. It admits typical user IDs (login names, emails, UUIDs).
var userIDPattern = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9_@.-]*$`)

// pageIDPattern is the kebab-case contract from SCHEMA.md.
var pageIDPattern = regexp.MustCompile(`^[a-z0-9]+(-[a-z0-9]+)*$`)

const (
	wikiDirName = "wiki"
	rawDirName  = "raw"
	indexFile   = "index.md"
	logFile     = "log.md"
)

// Vault resolves per-user wiki directories under a single memory root.
// It performs no policy evaluation; it only guarantees that every path it
// returns is inside the vault of the user it was asked about.
type Vault struct {
	root string
}

// NewVault returns a Vault rooted at dir. The directory is created if it
// does not exist.
func NewVault(dir string) (*Vault, error) {
	if dir == "" {
		return nil, errors.New("memory: vault root must not be empty")
	}
	abs, err := filepath.Abs(dir)
	if err != nil {
		return nil, fmt.Errorf("memory: resolve vault root: %w", err)
	}
	if err := os.MkdirAll(abs, 0o755); err != nil {
		return nil, fmt.Errorf("memory: create vault root: %w", err)
	}
	return &Vault{root: abs}, nil
}

// Root returns the memory root directory.
func (v *Vault) Root() string { return v.root }

// UserRoot returns the vault directory for userID without creating it.
func (v *Vault) UserRoot(userID string) (string, error) {
	if !userIDPattern.MatchString(userID) || strings.Contains(userID, "..") {
		return "", fmt.Errorf("%w: %q", ErrInvalidUserID, userID)
	}
	return v.contain(filepath.Join(v.root, userID))
}

// WikiDir returns the wiki directory for userID.
func (v *Vault) WikiDir(userID string) (string, error) {
	userRoot, err := v.UserRoot(userID)
	if err != nil {
		return "", err
	}
	return filepath.Join(userRoot, wikiDirName), nil
}

// RawDir returns the raw-sources directory for userID.
func (v *Vault) RawDir(userID string) (string, error) {
	userRoot, err := v.UserRoot(userID)
	if err != nil {
		return "", err
	}
	return filepath.Join(userRoot, rawDirName), nil
}

// PagePath resolves the on-disk path of a wiki page. pageID must be
// kebab-case per the frontmatter contract; the resolved path must stay
// inside the user's wiki directory.
func (v *Vault) PagePath(userID, pageID string) (string, error) {
	wiki, err := v.WikiDir(userID)
	if err != nil {
		return "", err
	}
	if !pageIDPattern.MatchString(pageID) {
		return "", fmt.Errorf("%w: %q", ErrInvalidPageID, pageID)
	}
	path, err := v.containIn(wiki, filepath.Join(wiki, pageID+".md"))
	if err != nil {
		return "", err
	}
	return path, nil
}

// EnsureUser creates the user's vault layout (wiki/ with seeded index.md
// and log.md, and raw/) if it does not already exist. It is idempotent and
// never overwrites existing files.
func (v *Vault) EnsureUser(userID string) error {
	wiki, err := v.WikiDir(userID)
	if err != nil {
		return err
	}
	raw, err := v.RawDir(userID)
	if err != nil {
		return err
	}
	for _, dir := range []string{wiki, raw} {
		if err := os.MkdirAll(dir, 0o755); err != nil {
			return fmt.Errorf("memory: create %s: %w", dir, err)
		}
	}
	seeds := map[string]string{
		filepath.Join(wiki, indexFile): "# Wiki Index\n\nNo pages yet.\n",
		filepath.Join(wiki, logFile):   "# Maintenance Log\n",
	}
	for path, content := range seeds {
		if _, err := os.Stat(path); err == nil {
			continue
		} else if !errors.Is(err, os.ErrNotExist) {
			return fmt.Errorf("memory: stat %s: %w", path, err)
		}
		if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
			return fmt.Errorf("memory: seed %s: %w", path, err)
		}
	}
	return nil
}

// Contains reports whether path (after cleaning) lies inside the vault of
// userID. Executors use this as the defense-in-depth check before any
// filesystem operation.
func (v *Vault) Contains(userID, path string) bool {
	userRoot, err := v.UserRoot(userID)
	if err != nil {
		return false
	}
	if _, err := v.containIn(userRoot, path); err != nil {
		return false
	}
	return true
}

func (v *Vault) contain(path string) (string, error) {
	return v.containIn(v.root, path)
}

// containIn cleans path and verifies it is base itself or a descendant.
func (v *Vault) containIn(base, path string) (string, error) {
	abs, err := filepath.Abs(filepath.Clean(path))
	if err != nil {
		return "", fmt.Errorf("memory: resolve path: %w", err)
	}
	rel, err := filepath.Rel(base, abs)
	if err != nil || rel == ".." || strings.HasPrefix(rel, ".."+string(filepath.Separator)) {
		return "", fmt.Errorf("%w: %q outside %q", ErrOutsideVault, path, base)
	}
	return abs, nil
}
