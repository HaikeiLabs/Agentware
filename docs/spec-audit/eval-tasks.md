# eval-tasks

Eval candidates and subagent proposals, drawn from workflows that already exist
rather than invented for the demo (SPEC.md §13, day-0 output 5).

---

## Proposed subagent: Moderator (stretch)

Owner's proposal, this session. Watches a user-specified Slack channel; on a
schedule produces summaries and action items, and escalates immediate action
items. Explicitly **no banning — escalate to a human**. Needs per-channel
configuration and moderation instructions. Kitaru for durability.

### Fit against the spec

Strong. It lands on requirements the current three subagents cover thinly:

- **§3 Agent Runtime** ("long-running async execution") — a scheduled watcher is
  a better proof than a request/response agent.
- **§6 core item 1** — subject propagation has a natural story: the human who
  configured the watch is the `invoking_subject` for every action the agent
  takes hours later, which is exactly the attribution-survives-delegation claim.
- **Human-in-the-loop escalation** is a governance beat the current demo lacks.
  §8's only governance moment is a denial (2:15–2:45); an escalation is the
  *other* half of policy — "not denied, but not autonomous either."

Overlaps the "Social media" subagent's role in §6 (async, scheduled, memory
across sessions). Worth deciding whether Moderator **replaces** it rather than
adds to it — §6's discipline is "ship 3, catalog the rest," and four implemented
agents is scope creep by the spec's own reasoning.

### Kitaru dependency — what exists

`python/adapters/kitaru/` is present and real:

- `KitaruAdapter.execute` maps tool names → Kitaru flow names via a
  `flow_mapping` dict (`adapters/kitaru/adapter.py:42-49`) and calls
  `flow.run_with_wait(args, poll_interval=...)` (`adapter.py:53-56`).
- `Client` exposes `invoke`, `wait_for_completion`, `get_execution`,
  `list_executions` (`adapters/kitaru/client.py:62-119`) — an execution-id model
  with polling, which is the durability primitive the Moderator needs.
- Packaged separately as `pedro-agentware-kitaru`
  (`adapters/kitaru/pyproject.toml`), deps `httpx` + `pydantic` only.

So durability is available and does not need building.

### Kitaru's role

Kitaru makes certain agent shapes easier to run — long-running, scheduled,
resumable work. It is an execution convenience, not part of the governance
story: governance is demonstrated at the policy decision point regardless of
what drives execution underneath.

So the Moderator can use it or not. `run_with_wait`'s synchronous polling
(`adapters/kitaru/adapter.py:53`) only decides where the schedule lives, not
whether the agent can be governed.

### Blockers

1. **No Python adapter has a policy seam.** Neither Kitaru
   (`adapters/kitaru/*.py`) nor Pydantic (`adapters/pydantic/adapter.py:38`)
   references `middleware`, `caller`, `policy`, or `auditor`; both `execute()`
   signatures take no caller. Whichever backend the Moderator runs on, the seam
   has to exist first or the agent produces no audit rows.
   This is G-046 and it is **not Moderator-specific** — it is a prerequisite for
   demonstrating governance in any agent on any Python backend.

2. **Escalation has no policy vocabulary.** agentware's `Action` is
   `allow`/`deny`/`filter` (`go/middleware/types.go:7-11`, mirrored in Python).
   "Escalate to a human" is a fourth outcome. kei has `enrollment_required`
   (G-044) — a third, different one. If escalation is the governance beat, the
   frozen `decision` enum has to represent it. **Settle before day 3**, since
   §4's field is being frozen either way.

### Recommendation

Keep it a stretch, as the owner scoped it — but note it competes with the §6
cut line rather than sitting outside it. If it ships, the honest framing is
Moderator *instead of* Social media, not in addition.

The escalation vocabulary question (blocker 3) is worth an answer even if the
agent never ships, because §4's `decision` field is being frozen either way and
a two-value enum forecloses it.

---

## Eval task candidates

_Not yet populated. §2.3 model parity needs a fixed task set run across
framework × model combinations; §13 day-0 output 5 requires it be drawn from
existing workflows. Blocked on the tool inventory (G-025) — no concrete tools
have been catalogued yet, so there is nothing to build tasks from._
