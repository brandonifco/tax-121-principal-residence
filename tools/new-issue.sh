#!/usr/bin/env bash
# new-issue.sh -- file an issue with the shape the rails expect.
#
#   tools/new-issue.sh --title "Widen the altitude limit to the tolerance case"
#   tools/new-issue.sh --title "..." --entry altitude-limit --risk independent --dry-run
#   tools/new-issue.sh --title "Take the engine to the next map version" --produce --dry-run
#
# Emitted by rules-factory as a managed file (decision 0029).
#
# Most issues in an engine are not filed by hand: `factory backlog --create` writes one per map
# entry still to build, with the entry, its source, its dependencies and its acceptance criteria
# already in it. This is for the rest -- a defect, a piece of engine work, an upstream map defect
# -- so that an issue filed from a terminal by an agent and one filed by a person look the same
# six months later, and so that both carry exactly one state label and one risk label.
#
# `--produce` files the other kind that is not a map entry: a `factory produce` update to this
# engine -- a new map version, a new kernel pin, a new factory recipe. Such work is work under
# these rails like any other, and it starts from an issue like any other (AGENTS.md section 4).
# The body it swaps in asks what moves, from what to what, why now, and the evidence such a pull
# request carries instead of a mutation.
#
# Every issue starts at the ready state and normal risk, `--produce` included: a factory update is
# not more or less risky by being one, and what it moves decides that. Promoting risk, or moving an
# issue to the awaiting-decision state, is the orchestrator's judgement (AGENTS.md section 6,
# docs/agent-team.md) and is done deliberately afterwards -- not asserted by whoever filed it, and
# not by a flag.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

GH="${RULES_ENGINE_GH:-gh}"
POLICY=".github/agent-policy.json"

label() {
  python3 - "$POLICY" "$1" "$2" <<'PY' 2>/dev/null || printf '%s' "$3"
import json, sys
try:
    with open(sys.argv[1], encoding="utf-8") as handle:
        value = (json.load(handle).get("labels") or {}).get(sys.argv[2])
except Exception:
    value = None
print(value or sys.argv[3])
PY
}

TITLE=""
ENTRY=""
RISK="normal"
BODY_FILE=""
PRODUCE=0
DRY_RUN=0
EXTRA_LABELS=()

die() { printf 'error: %s\n' "$1" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --title) TITLE="${2:-}"; shift 2 ;;
    --entry) ENTRY="${2:-}"; shift 2 ;;
    --risk) RISK="${2:-}"; shift 2 ;;
    --body-file) BODY_FILE="${2:-}"; shift 2 ;;
    --produce) PRODUCE=1; shift ;;
    --label) EXTRA_LABELS+=("${2:-}"); shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) sed -n '2,7p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
done

[[ -n "$TITLE" ]] || die "--title is required"
# Both name the body, and which one won would decide what the issue asks for. Say so instead.
if [[ "$PRODUCE" -eq 1 && -n "$BODY_FILE" ]]; then
  die "--produce and --body-file both say what the body is; pass one. --produce is the factory-update template, and --body-file is your own"
fi
case "$RISK" in
  normal|independent) ;;
  *) die "--risk is normal or independent, got: $RISK" ;;
esac

READY="$(label ready "ready" "state:ready")"
if [[ "$RISK" == "independent" ]]; then
  RISK_LABEL="$(label independentRisk "independentRisk" "risk:independent-review")"
else
  RISK_LABEL="$(label normalRisk "normalRisk" "risk:normal")"
fi

MARKER=""
[[ -n "$ENTRY" ]] && MARKER="<!-- rules-factory-entry: $ENTRY -->

"

if [[ -n "$BODY_FILE" ]]; then
  [[ -f "$BODY_FILE" ]] || die "no such file: $BODY_FILE"
  BODY="$MARKER$(cat "$BODY_FILE")"
elif [[ "$PRODUCE" -eq 1 ]]; then
  BODY="$MARKER$(cat <<'TPL'
## What moves

<!-- One of: the map version, the kernel pin, the factory recipe. If it is more than one, say
     which and why they move together; a produce that moves two things is still one produce, but
     it is two things to review. -->

- from:
- to:

## Why now

<!-- What the new version makes true that the current one does not, or what it fixes. "It is
     newer" is not a reason; the current engine passes its gate. -->

## Scope, and what it deliberately does not do

<!-- The pull request carries what `factory produce` wrote and nothing else. Any hand edit the new
     input forces -- an overlay entry the new map adds, a handler whose contract changed -- is a
     separate issue, because it is a rules decision the factory did not make and it is reviewed as
     one. Name the ones you expect here. -->

## Acceptance criteria

<!-- Observable conditions. Someone other than whoever ran produce must be able to check each. -->

- [ ] the pull request carries only files `factory produce` wrote, and `tools/pr-policy.py` admits
      the `## Produced by the factory` claim
- [ ] `./scripts/validate.sh full` passes, so every generated file regenerates byte for byte
- [ ] `factory provenance --engine <dir>` reports no mismatch
- [ ] every verdict the changed paths call for is recorded at the head commit

## Required evidence

<!-- A produce update writes no test of its own and names no mutation. It shows the `factory
     produce` command and its output, the gate's output, and the provenance recompute. -->

## Dependencies

<!-- The map version must be published, or the kernel released, before this can be worked. -->

None
TPL
)"
else
  BODY="$MARKER$(cat <<'TPL'
## What this is

<!-- One concern. If the sentence needs an "and", it is two issues. -->

## Why it exists

<!-- What becomes possible, or what is currently wrong. -->

## The rule, if this is rules work

<!-- The map entry id, and nothing quoted from the corpus that the map does not already quote.
     `tools/entry-packet.py <entry-id>` is the assignment; this section only needs to name it.
     If this is an upstream map defect: what the map says, what the corpus says, and the locator. -->

N/A

## Scope, and what it deliberately does not do

<!-- The non-goals are what keep the pull request reviewable. -->

## Acceptance criteria

<!-- Observable conditions. Someone other than the implementer must be able to check each one. -->

- [ ]

## Required evidence

<!-- What must be demonstrated, and how. Every test names the mutation that makes it fail.
     Where the corpus prints a finite table, the whole table is checked, not a sample. -->

## Dependencies

<!-- Issues or decision records this waits on. "None" is a valid answer. -->

None
TPL
)"
fi

if [[ "$DRY_RUN" -eq 1 ]]; then
  printf 'title:  %s\nlabels: %s\n\n%s\n' "$TITLE" "$READY,$RISK_LABEL${EXTRA_LABELS[*]:+,$(IFS=,; printf '%s' "${EXTRA_LABELS[*]}")}" "$BODY"
  exit 0
fi

command -v "$GH" >/dev/null 2>&1 || die "$GH is required to file an issue"

ARGS=(issue create --title "$TITLE" --body "$BODY" --label "$READY" --label "$RISK_LABEL")
for extra in "${EXTRA_LABELS[@]+"${EXTRA_LABELS[@]}"}"; do
  ARGS+=(--label "$extra")
done
"$GH" "${ARGS[@]}"
