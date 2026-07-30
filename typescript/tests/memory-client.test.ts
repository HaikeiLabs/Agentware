/**
 * WikiMemory client tests against the real Go core, including the
 * cross-SDK check: a page written via the Python SDK is readable through
 * the TypeScript SDK for the same user and invisible to another user.
 */

import { execFileSync } from "node:child_process";
import { mkdtempSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { WikiMemory, memoryTools, parseDiagnostics } from "../src/memory/index.js";

const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const TBOX_PATHS = [
  join(REPO_ROOT, "ontologies/education/TBOX_LEARNING_SOFTWARE.ttl"),
  join(REPO_ROOT, "ontologies/social/twitch_topics.ttl"),
];

const VALID_PAGE = `---
id: go-worker-pools
type: sw:Skill
labels: ["Worker Pools"]
topics: [twitch:Go]
claims:
  - {id: c1, text: "Bounded pools prevent goroutine leaks", sources: [src-talk]}
---
Pools bound concurrency.
`;

let memctl = "";
let available = false;

function tryExec(file: string, args: string[], options: object = {}): boolean {
  try {
    execFileSync(file, args, { stdio: "pipe", ...options });
    return true;
  } catch {
    return false;
  }
}

beforeAll(() => {
  if (!existsSync(TBOX_PATHS[0])) return;
  memctl = join(mkdtempSync(join(tmpdir(), "memctl-")), "memctl");
  available = tryExec("go", ["build", "-o", memctl, "./cmd/memctl"], {
    cwd: join(REPO_ROOT, "go"),
  });
});

function newMemory(root: string, userId: string): WikiMemory {
  return new WikiMemory({ userId, root, tboxPaths: TBOX_PATHS, memctlPath: memctl });
}

function freshRoot(): string {
  return join(mkdtempSync(join(tmpdir(), "vault-")), "memory");
}

function skippable(name: string, fn: () => Promise<void>): void {
  test(name, async () => {
    if (!available) {
      console.warn(`skipping ${name}: go toolchain or ontologies submodule missing`);
      return;
    }
    await fn();
  }, 30000);
}

skippable("lists the five memory tools", async () => {
  const memory = newMemory(freshRoot(), "alice");
  try {
    const names = (await memory.tools()).map((t) => t.name).sort();
    expect(names).toEqual([
      "memory_get_claims",
      "memory_ingest",
      "memory_lint",
      "memory_query",
      "memory_write_page",
    ]);
  } finally {
    memory.close();
  }
});

skippable("write, query, and claims round-trip", async () => {
  const memory = newMemory(freshRoot(), "alice");
  try {
    const [, ok, err] = await memory.writePage(VALID_PAGE);
    expect(err).toBe("");
    expect(ok).toBe(true);
    const [hits, qok] = await memory.query("worker pools");
    expect(qok).toBe(true);
    expect((hits as Array<{ id: string }>).map((h) => h.id)).toContain("go-worker-pools");
    const [claims, cok] = await memory.getClaims("go-worker-pools");
    expect(cok).toBe(true);
    expect((claims as Array<{ text: string; confidence: unknown }>)[0].confidence).toBeNull();
  } finally {
    memory.close();
  }
});

skippable("denies carry parseable diagnostics", async () => {
  const memory = newMemory(freshRoot(), "alice");
  try {
    const [, ok, err] = await memory.writePage("---\nid: bad-page\ntype: sw:Skil\n---\n");
    expect(ok).toBe(false);
    const violations = parseDiagnostics(err);
    expect(violations[0].constraint).toBe("unknown-class");
    expect(violations[0].nearest[0]).toMatch(/Skill$/);
  } finally {
    memory.close();
  }
});

skippable("vercel-ai-shaped tools render denials for self-correction", async () => {
  const memory = newMemory(freshRoot(), "alice");
  try {
    const tools = memoryTools(memory);
    expect(Object.keys(tools).sort()).toEqual([
      "memory_get_claims",
      "memory_ingest",
      "memory_lint",
      "memory_query",
      "memory_write_page",
    ]);
    const denied = await tools.memory_write_page.execute({
      content: "---\nid: p\ntype: nope\n---\n",
    });
    expect(denied.startsWith("DENIED:")).toBe(true);
    const okOut = await tools.memory_ingest.execute({ source_id: "src-a", text: "notes" });
    expect(okOut).toBe("ingested src-a");
  } finally {
    memory.close();
  }
});

skippable("cross-SDK: python-written page is visible to TS for the same user only", async () => {
  const root = freshRoot();
  // Write through the Python SDK (its own memctl subprocess, same vault root).
  const script = [
    "import sys",
    `sys.path.insert(0, ${JSON.stringify(join(REPO_ROOT, "python/src"))})`,
    "from pedro_agentware.memory import WikiMemory",
    `memory = WikiMemory(user_id="alice", root=${JSON.stringify(root)},`,
    `    tbox_paths=${JSON.stringify(TBOX_PATHS)}, memctl_path=${JSON.stringify(memctl)})`,
    `_, ok, err = memory.write_page(${JSON.stringify(VALID_PAGE)})`,
    "memory.close()",
    "assert ok, err",
  ].join("\n");
  execFileSync("python3", ["-c", script], { stdio: "pipe" });

  const alice = newMemory(root, "alice");
  const bob = newMemory(root, "bob");
  try {
    const [hits, ok] = await alice.query("worker pools");
    expect(ok).toBe(true);
    expect((hits as Array<{ id: string }>).map((h) => h.id)).toContain("go-worker-pools");

    const [bobHits, bobOk] = await bob.query("worker pools");
    expect(bobOk).toBe(true);
    expect(bobHits).toEqual([]);

    const [bobClaims, claimsOk] = await bob.getClaims();
    expect(claimsOk).toBe(true);
    expect(bobClaims).toEqual([]);
  } finally {
    alice.close();
    bob.close();
  }
});
