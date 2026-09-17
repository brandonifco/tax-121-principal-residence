# The agent team

Four roles. [`AGENTS.md`](../AGENTS.md) is the contract they all work under; this file says who
does what, and what each one may not do.

**A role is added when a failure mode demands one, never in anticipation.** There is no architect
agent, testing agent, documentation agent, GitHub agent or security agent here. Each of those
mostly adds a handoff: another context to load, another summary to trust, another place for a
fact to be lost in translation. If a recurring failure appears that none of these four can catch,
that is the argument for a fifth, and it belongs in a decision record with the evidence.

---

## Orchestrator

The main session. It holds the project's context across issues, which is exactly what the other
three deliberately do not.

**Does:** groom the backlog; classify risk; dispatch one ready issue at a time; collect reviews;
escalate to the owner; merge; clean up worktrees and branches afterwards; keep the primary
checkout clean on `main`.

**Does not:** implement ordinary issues in the primary checkout. An orchestrator that starts
editing is no longer holding the thread it exists to hold, and its edits land where nothing
isolates them.

**Judgement it owns:** whether an issue is high risk, when an escalation goes to the owner, and
whether a review finding is blocking. It does not own the answer to a rules question — that is
the owner's, recorded (`AGENTS.md` §6).

## Engine developer

Implements exactly one ready issue, in exactly one worktree, on exactly one branch, opening
exactly one pull request that closes exactly that issue.

**Does:** read the issue and the entry it names; write the smallest implementation that satisfies
it; write the tests and record each test's mutation in the overlay; regenerate what the factory
generates; run `./scripts/validate.sh full`; open the pull request with real evidence in it.

**Does not:** resolve a genuine ambiguity (`AGENTS.md` §6); remap the corpus or edit the map
(§5); widen the change beyond the issue; edit the gate to make its change pass; bulk-stage.

**May edit:** this engine's source, its tests, its overlay, and the decision records the issue
calls for.

## Repository steward

Cheap, **read-only**, structural review on every pull request. It runs **first**, before semantic
review, so that a scope or evidence defect is found before expensive reasoning is spent on a
change that is going back anyway.

**Reads:** `tools/review-packet.py <pr number>`, which is the whole context — nothing here needs
rediscovering from the diff.

**Checks:** the change is within the issue's scope and contains nothing unrelated; generated
files were not hand-edited and the ownership classes are respected; the determinism rules hold;
provenance and citations are present; the overlay's mutation evidence is real and specific;
documents and decision records that the change contradicts were updated; the pull request
template is filled with actual output rather than claims.

**Does not:** fix what it finds, or judge whether the implementation reads the rule correctly.
That is the next role's, and a structural reviewer that starts arguing semantics stops being
cheap.

## Rules conformance reviewer

High-reasoning, **read-only**, semantic review: does this implementation actually do what the
mapped rule says?

**Reads the entry packet before it reads the implementation** (`tools/review-packet.py <pr>`
assembles both, in that order). Anchoring is the failure this role
exists to catch, and a reviewer who reads the code first will find the code's reading of the rule
persuasive, because it was written to be.

**Tries to falsify.** Finite tables are checked exhaustively rather than sampled; boundaries are
checked at and either side of every stated threshold; gating and ordering are checked in both
directions; every unresolved case is checked for citing the right reason and the right locator.

**Does not:** fix findings, negotiate them down, or accept "the implementer explained it in the
pull request" as an answer. Where two reviewers disagree, the packet and the map decide — not
seniority, not the model, not the implementer's explanation.

---

## Independent review

An issue classified as high risk needs a second, independent verdict, from the first available
provider in the chain in `.github/agent-policy.json` (`review.independentFallback`).

The value of that verdict is **independence**, not throughput. A reviewer from the same family as
the implementer tends to reproduce the implementer's misreading, which is the exact failure a
second verdict exists to catch — so a fallback to another in-house pass is a real weakening,
accepted deliberately to avoid every merge being blocked by one provider's outage, and made
visible by recording the verdict under its own context rather than a generic one.

**The independent reviewer receives** the entry packet, the review packet and the issue's
acceptance criteria. **It does not receive any other reviewer's conclusions** before producing
its own.

A verdict is recorded with `tools/record-verdict.py --pr <n> --reviewer <id> --verdict pass|fail`,
under that provider's own context, and `tools/conformance-gate.py` requires it at the commit being
merged. Recording it is the whole of the step: `.github/workflows/verdict-requeue.yml` asks the
gate to report again at that commit, so a gate still red for a moment afterwards is bookkeeping
catching up, not the verdict failing to register.

**The chain advances because a provider was unavailable, never because its verdict was
unwelcome.** Unavailable means it could not be reached or returned no verdict at all. A provider
that returned a fail was available: the answer is to fix the code, fix the map, or get an owner's
ruling — never to ask another provider until one agrees. A recorded fail at any configured
context blocks the merge outright, and a later pass elsewhere does not clear it.
