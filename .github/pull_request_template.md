<!--
Emitted by rules-factory as a managed file (decision 0029). Every section below is required, and
tools/pr-policy.py checks that mechanically on every push to this pull request. A section left as
its placeholder, or filled with a claim where the template asks for output, is a failed check —
not because the form matters, but because a reviewer who cannot see what you ran has to take your
word for it, and this repository does not run on anybody's word.
-->

## Linked issue

<!-- Exactly one. A branch closes exactly one issue (AGENTS.md section 4). -->

Closes #

## Produced by the factory

<!-- rules-factory-produce -->

<!-- Delete this whole section unless this pull request is a `factory produce` update to this
     engine — a new map version, a new kernel pin, a new factory recipe — and carries what produce
     wrote and nothing else. `factory produce --produce-report <file>` writes all four values.

     tools/pr-policy.py checks this claim; it does not take it. The three facts must equal this
     tree's provenance.json, that record must say the factory was not dirty, and every changed file
     must be one the factory writes. One hand-written file voids the claim and the pull request is
     judged as an ordinary one — including the mutation and the entry it cannot name. An overlay
     edit the new map forces is a separate issue: it is a rules decision the factory did not make.

     This changes what the pull request says, not what it proves. Every verdict this change needs
     is still required, and `conformance-gate.py` decides which from the changed paths. -->

- factory version:
- map package and version:
- kernel version:
- what moved:

## Exact behavioural claim

<!-- What this engine does after this change that it did not do before, in terms a caller would
     recognise. Not "adds support for X" — what input now produces what output, and what is
     declined and why. -->

## Scope, and what this deliberately does not do

<!-- The non-goals are what make the diff reviewable. Anything you noticed and did not fix
     belongs here by name, as a new issue, not as a second commit. -->

## Map and rules conformance

<!-- For anything touching the rules surface. "N/A" only where nothing here does.

     A factory update (above) names the map package and version and nothing else here: a map
     version bump regenerates every entry, so there is no single entry id and no single locator,
     and "all of them" names nothing a reviewer can check. -->

- entry id(s):
- map package and version:
- source locator(s):
- owner's rulings used, if any:

## Tests and evidence

<!-- The exact commands, and what they actually printed. "Tests pass" is not evidence; a run is.
     Every test names the mutation that makes it fail, and you must have watched it fail — a test
     nobody has watched fail is not yet a test.

     A factory update writes no test of its own, so it names no mutation. It shows instead the
     `factory produce` command and its output, the gate's output, and a `factory provenance
     --engine <dir>` recompute saying the committed record is the one a re-produce writes. That is
     a replacement, not a discount: a reviewer can re-run all three. -->

```
$ ./scripts/validate.sh full
```

Mutations observed:

<!-- one line per test: the test name, the mutation, and that it failed with it in place -->

## Determinism

<!-- What this change does about wall-clock time, ambient locale or culture, environment-dependent
     ordering, randomness, and hash codes or object identity in anything observable. "Nothing here
     reads the machine" is a fine answer where it is true. -->

## Decisions and trade-offs

<!-- What you chose, what you rejected, and why. If you resolved something that felt like a
     judgement call about what a rule means, it was probably an escalation you should have raised
     instead (AGENTS.md section 6) — say so here rather than leaving it buried in the diff. -->

## Known limitations and unresolved behaviour

<!-- What this does not answer, and what the engine declines. A decline that names why and cites
     where is the engine working; say which cases they are. -->

## Agent provenance

<!-- Who did what. "Independently reviewed by" is required only for an issue classified as
     needing independent review; say "not required" otherwise. -->

- implemented by:
- structurally reviewed by:
- semantically reviewed by:
- independently reviewed by:

## Unrelated changes

None
