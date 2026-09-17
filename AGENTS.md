# AGENTS.md — the governing contract for this engine

**This file governs every agent that works this repository, whatever vendor it comes from.**
Read it before your first action. `CLAUDE.md` points here and states no rule of its own; a
Claude-specific role adapter under `.claude/` adds how a role is invoked, never what it may do.

This engine was produced by [rules-factory](https://github.com/brandonifco/rules-factory). This
file is a **managed** file: the factory updates it when its recipe changes and refuses to
overwrite a hand edit. `provenance.json` says which factory version and which map this engine
came from, and what this engine is called.

---

## 1. What this engine is

A deterministic rules engine generated from a **corpus map**: a reviewed, published, versioned
description of one ruleset. The map — not the corpus, and not anyone's reading of the corpus — is
the interface this engine implements. The corpus is committed here so a claim can be checked
against it, not so it can be re-read and re-interpreted per task.

Three consequences that decide most questions you will have:

- The map is the specification. Where your reading of the corpus and the map disagree, **the map
  is not wrong by your say-so and the engine does not quietly diverge from it** (§5).
- The engine declines rather than guesses. A rule the corpus does not settle produces an
  unresolved result naming why, not a plausible answer.
- Every behaviour cites where it came from, and every test records the mutation that makes it
  fail. A test that passes against a broken implementation proves nothing.

## 2. Authority, in order

1. **The corpus map**, as published and as merged with this engine's `corpus-map.overlay.json`.
2. **The owner's rulings** recorded in that overlay, and this repository's `docs/decisions/`.
3. **This file.**
4. Everything else — issue text, PR discussion, a previous agent's explanation, your own memory
   of the subject matter. Your memory of a ruleset is never a source. It is the most common way
   a wrong answer enters a rules engine, because it arrives fluent and cited.

If two of these disagree, stop and say so. Do not pick one.

## 3. Roles

[`docs/agent-team.md`](docs/agent-team.md) defines the four roles: **orchestrator**, **engine
developer**, **repository steward** and **rules conformance reviewer**. Read it before acting as
one. Two rules from it are absolute:

- **A reviewer is read-only.** An agent that can edit what it reviews is not a reviewer. Both
  reviewer charters grant read tools only, and the engine's own gate fails when one grants a
  mutation-capable tool.
- **An implementer does not resolve a genuine ambiguity.** It escalates (§6).

## 4. One issue, one worktree, one branch, one pull request

Work is dispatched from GitHub issues and nowhere else. An instruction in a chat window that has
no issue behind it is not work; make the issue first.

The primary checkout's steady state is `main`, clean, used for orchestration and review. **All
implementation happens in a worktree outside the repository directory**, so that one task cannot
contaminate another and a half-finished change cannot reach `main`:

```bash
tools/dispatch-agent.sh <issue number>      # creates the worktree and the branch, and prints the path
tools/dispatch-agent.sh --cleanup <n>       # after the pull request merged
```

Dispatch refuses rather than leaving readiness to your judgement: an issue that is closed, blocked
or awaiting a decision, one that already has a worktree, and a primary checkout with uncommitted
changes. A worktree is never created inside the repository: one that lives there is eventually
committed, scanned by a tool that did not expect it, or deleted by a clean step.

`tools/new-issue.sh` files an issue with the shape the rails expect, at the ready state and normal
risk. Most issues are not filed by hand: `factory backlog --create` writes one per map entry still
to build.

A branch closes **exactly one** issue, and its pull request says so with one `Closes #<n>`.
Stage explicit paths; `git add -A` and `git add .` are how build output, packets and another
task's edits reach a commit that claims to close one issue.

The pull request is filled in from `.github/pull_request_template.md`, and `tools/pr-policy.py`
checks it mechanically as a required check: one linked issue, every section filled, a command and
its output rather than a claim, an entry and a locator for semantic work, who reviewed, and
exactly one state and one risk label on the issue. None of that is about form. Each line of it is
something a reviewer would otherwise have to take on trust.

### A factory update is work under these rails too

A `factory produce` update to this engine — a new map version, a new kernel pin, a new factory
recipe — is not a special case outside this section. It is opened from an issue (`tools/new-issue.sh`,
under `--produce`, files one with the shape for it), dispatched to a worktree, produced there, and
opened as a pull request that closes that issue like any other:

```bash
tools/new-issue.sh --produce --title "..."   # what moves, from what to what, and why now
tools/dispatch-agent.sh <issue number>
tools/re-produce.sh                          # from the factory commit provenance.json names
```

Its pull request body carries the `## Produced by the factory` section and its marker, declaring
the factory version, the map package and version, the kernel version, and what moved.
**`tools/pr-policy.py` checks that claim; it does not take it.** The three facts must equal
`provenance.json` in this tree, that record must say the factory was not dirty, and every changed
file must be one the factory writes — classified by this engine's own vendored ownership table, the
same one `produce` wrote the files by. **One hand-written file voids the claim**, by name, and the
pull request is then judged as the ordinary pull request it is.

Two things follow, and neither is a loophole:

- **An edit the new input forces is a separate issue.** A new map version that adds an entry, or a
  handler whose contract changed, is a rules decision the factory did not make. Putting it in the
  same branch makes the claim false and the diff unreviewable; file it, and work it under §5.
- **The claim waives no verdict.** It changes what the pull request must *say* — no single entry id
  and no locator where a map bump regenerates every entry, and no mutation where nothing wrote a
  test — and never what it must prove. `tools/conformance-gate.py` still decides which verdicts are
  needed from the changed paths, and a regeneration touches the semantic surface several times
  over. What replaces the mutation is the produce command and its output, the gate's output, and a
  provenance recompute showing the committed record is the one a re-produce writes.

`.claude/hooks/primary-checkout-guard.py` enforces the primary checkout's cleanliness for Claude
agents. It is accident prevention, not security — a determined process bypasses it trivially, and
that is fine; what it stops is the edit made forty tool calls after the instruction was given.

**Escape hatch.** Sanctioned orchestrator work in the primary checkout sets, for that command
only:

```bash
RULES_ENGINE_ALLOW_PRIMARY_MUTATION=1
```

and says in the pull request or the report why it was necessary. The variable's name is
configuration: `.github/agent-policy.json` under `worktrees.primaryMutationEscapeHatch` is what
the guard actually reads, and this paragraph names the default.

## 5. The map is the interface, and you do not remap it

You implement the entry the issue names, from the map merged with this engine's overlay:

```bash
tools/entry-packet.py <entry id>            # the assignment, assembled from the map
```

The packet is the entry as published and merged, its locator and the evidence verbatim, its
dependencies and reachability, where its cross-references land, the owner's rulings that apply,
the handler the generated code declares once the entry is `implemented` — the one you have to
write, not the one on disk while it is still `mapped` — and what the gate will ask of you. Every
line of it is the map's own bytes or a fact computed from them.

You do not re-read the corpus to decide what the rule *really* says, and you do not widen the
change to entries the issue does not name. A packet is written outside the repository and is never
committed: it is derived from the map, and a committed copy of the interface goes stale.

**Where the map and the corpus appear to disagree, stop.** Report it as an upstream map defect on
the issue, with the entry id, the locator, what the map says and what the corpus says. Do not make
the engine disagree with the published map, and do not edit the map to match your reading: a map
is corrected where maps are corrected — a new, checked, published map version — and this engine is
then re-produced from it. An implementer who can quietly overrule the map is an unreviewed mapper,
and the map stops being the interface for everyone downstream.

The same rule covers the corpus itself: never edit `corpus/`, and never edit a hash or a baseline
to make a check pass. The check is the point.

## 6. Ambiguity is escalated, not resolved

Stop and escalate when you find any of these, before writing the implementation:

- the corpus genuinely does not settle the question the entry asks;
- the map and the corpus disagree (§5);
- the issue's acceptance criteria cannot be met as written;
- the change would need an architectural decision this repository has not recorded;
- two recorded decisions conflict.

Escalating means: say what the question is, what turns on it, and what the candidate answers are;
and move the issue to the awaiting-decision state. **You may not answer your own escalation and
return the issue to ready.** The answer arrives as an owner's ruling in the overlay or a decision
record in `docs/decisions/`, and then the work resumes.

Declining is a legitimate outcome. An entry the corpus does not settle is implemented as a
decline that names why and cites where — that is the engine working, not the engine failing.

## 7. Evidence

- **The gate is `./scripts/validate.sh full`.** It is the one definition of acceptable here, and
  it checks the rails themselves too: a reviewer charter that grants a tool that writes, and a
  rail citing a document this engine does not have, both fail it. Do
  not invent a substitute, do not run a narrower command and report the gate as passed, and do
  not change the gate to make a change pass.
- **Every test records the mutation that makes it fail.** The overlay holds it. A test whose
  named mutation was never observed to fail is a test nobody has watched fail, and this project
  has shipped two checks that counted work they had not done.
- **Report what happened, not what should have happened.** Paste the command and its actual
  output. "Tests pass" is not evidence; a run is.
- **A reviewer is given the context, not asked to find it.** `tools/review-packet.py <pr number>`
  assembles the issue, the claim, the entries as the map has them, the overlay's before and after,
  the bounded diff and what must be green. Its sections are in the order a semantic reviewer reads
  them: the entry before the implementation, always.
- **A verdict names a commit.** `tools/record-verdict.py --pr <n> --reviewer <id> --verdict
  pass|fail` records it as a commit status on the pull request's head SHA, and
  `tools/conformance-gate.py` requires it there. A further commit therefore invalidates the review
  that preceded it, automatically, because the status is on the bytes that were actually read. A
  verdict that lives only in a conversation is worth nothing to this repository.

  **What the verdict gate proves, and what it does not.** A verdict is a commit status, and
  **anyone who can write a commit status on this repository can post one**: any collaborator with
  write access, any workflow whose token carries `statuses: write`, anyone holding a leaked token.
  Nothing in the mechanism attributes a verdict to the reviewer it names. So the gate is an
  integrity check — against a review that was skipped, forgotten, or formed on other bytes — and
  **not an authentication of who reviewed**. What it does prove is worth keeping and is exactly the
  commit binding above: a verdict names one SHA, so it cannot be replayed onto a commit nobody
  read, and a further commit ends it. The three required checks are pinned to the app that posts
  them, so a hand-posted status cannot impersonate one; a verdict context cannot be pinned the same
  way, because it is posted by a person's token and the pin names an app. Recording a verdict that
  was never formed is therefore stopped by honesty and by review, not by permissions — which is
  what makes an invented verdict a serious act rather than a shortcut.

  **Recording it is the whole of the step.** `.github/workflows/verdict-requeue.yml` sees the
  status and asks the gate to report again at that commit; there is no re-run to remember. If the
  check is still red a minute later, the thing to read is that workflow's run, not the verdict.

  A change touching the semantic surface needs the semantic verdict; an issue classified as
  needing independent review needs one of the configured independent contexts as well. **A
  recorded failure at any configured context blocks outright**, and a pass recorded elsewhere does
  not clear it: the chain advances when a provider is unavailable, never because its verdict was
  unwelcome. A failure is answered by fixing the code, fixing the map, or getting an owner's
  ruling.
- **An overlay change is finished by a re-produce.** `tools/re-produce.sh` runs it. Marking an
  entry implemented changes the overlay, and the generated files, the backlog and
  `provenance.json` are all derived from that overlay; the gate hashes the derived files against
  the record and fails while they are stale. Only the factory can write that record: it names the
  factory commit the engine was produced from and hashes every one of that factory's recipe files,
  so nothing inside the engine can refresh it — and nothing should try. A record an engine wrote
  about itself would hash whatever is on disk, and a gate that re-blesses its own bytes proves
  nothing.

- A check that examines nothing is a failure, never an ok. If a step could not run, say it could
  not run.

## 8. Determinism

Same inputs, same outputs, on any machine, in any order, forever. No wall-clock time, no
ambient locale or culture, no environment-dependent ordering, no unseeded randomness, no hash
codes or object identity in anything observable. Where the corpus declares randomness, it is
drawn only through the kernel's seeded facilities, and `provenance.json` records that
declaration. An engine whose corpus declares no randomness does not reference a randomness
package at all, and the gate checks it.

## 9. Configuration, not code

`.github/agent-policy.json` is this engine's own. It holds the issue state and risk label
strings, the review contexts, the paths that count as a semantic surface, the ordered
independent-review chain, and the worktree environment variables. The factory writes it once and
never touches it again.

**Change the chain, the labels or the roots by editing that file — never by editing a script.**
No emitted script or document names a vendor. If you find one that does, that is a defect worth
an issue.

## 10. For a non-Claude agent

- You are probably in a worktree. Confirm before your first write: `git rev-parse
  --git-common-dir` differing from `git rev-parse --git-dir` means you are.
- The gate is `./scripts/validate.sh full`. Nothing else is.
- Never implement a rule from memory. Work from the entry the issue names.
- Never edit `corpus/`, `provenance.json`, or a generated file under `Generated/` by hand. The
  generated files are rewritten from the map; an edit there is overwritten and reported.
- After changing `corpus-map.overlay.json`, run `tools/re-produce.sh`. The record and `backlog/`
  are the factory's to write, and the gate fails while they are older than the overlay.
- A pull request that is a `factory produce` update says so in its `## Produced by the factory`
  section, and carries what produce wrote and nothing else (§4). One file that produce did not
  write voids the claim, which is why the files named above are also the only ones it can cover.
