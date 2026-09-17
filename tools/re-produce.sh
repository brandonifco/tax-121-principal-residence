#!/usr/bin/env bash
# re-produce.sh -- re-run `factory produce` on this engine, from the factory commit the record names.
#
#   tools/re-produce.sh                 re-produce this engine, gate and all
#   tools/re-produce.sh --dry-run       print the produce it would run, and change nothing
#   tools/re-produce.sh --no-verify     (and any other argument) passed through to produce
#
# Emitted by rules-factory as a managed file (decision 0029).
#
# **An overlay edit is finished by a re-produce.** `provenance.json` and `backlog/` are generated
# files (decision 0018): `factory produce` is their only author, and nothing in a produced engine
# can refresh them. The gate's own regeneration step refreshes the generated C# and nothing else,
# so after an overlay change the record still hashes the old bytes and the backlog still lists the
# entry as one to build. `scripts/engine-gate.py provenance` fails while that is true, and names
# this script.
#
# **Why a script and not a paragraph.** The procedure is: clone rules-factory at the commit the
# record names, and run produce with the package, corpus, name and output this engine's record
# gives. Written as prose it is four lookups and a clone that an operator has to get right, and it
# has a trap in it: cloning the factory's `main` instead of the recorded commit re-emits the gate,
# the rails and the vendored generator from a factory nobody asked for, and folds that into an
# implementation pull request where no reviewer is looking for it. So the clone below is pinned to
# `factory.commit`, and moving this engine to a newer factory stays a deliberate act with its own
# issue.
#
# **It makes no commit.** `produce` makes none by design, and neither does this. What it changes is
# yours to read and stage.
#
# Standard library tools only: bash, git and python3.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

GIT="${RULES_ENGINE_GIT:-git}"
PYTHON="${RULES_ENGINE_PYTHON:-python3}"
RECORD="provenance.json"
# provenance.json names the factory's commit, not where the factory lives, so the URL is a constant
# here. If the record ever gains a `factory.repository`, the read below prefers it and this becomes
# the fallback. $RULES_ENGINE_FACTORY_REPO overrides both, for a mirror or an offline clone.
FACTORY_REPO_DEFAULT="https://github.com/brandonifco/rules-factory.git"

DRY_RUN=0
EXTRA=()

die() { printf 'error: %s\n' "$1" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) sed -n '2,7p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) EXTRA+=("$1"); shift ;;
  esac
done

[[ -f "$RECORD" ]] || die "$RECORD is not here; run this from a produced engine"

# Everything produce needs, read from the record in one pass so a malformed field is named once.
# The corpus is the one generated file under corpus/ -- the same rule provenance.recompute uses to
# find it, and it refuses anything but exactly one.
FIELDS="$("$PYTHON" - "$RECORD" "$FACTORY_REPO_DEFAULT" <<'PY'
import json, sys
try:
    with open(sys.argv[1], encoding="utf-8") as handle:
        record = json.load(handle)
except (OSError, ValueError) as error:
    sys.exit(f"{sys.argv[1]} cannot be read ({error})")
factory = record.get("factory") or {}
commit = factory.get("commit")
if not (isinstance(commit, str) and len(commit) == 40 and all(c in "0123456789abcdef" for c in commit)):
    sys.exit(f"{sys.argv[1]} names no factory.commit to re-produce from (got {commit!r})")
source = record.get("map") or {}
name = (record.get("engine") or {}).get("name")
corpora = [item.get("path") for item in record.get("generated") or []
           if isinstance(item, dict) and str(item.get("path", "")).startswith("corpus/")]
if len(corpora) != 1:
    sys.exit(f"{sys.argv[1]} names {len(corpora)} corpus/ files; exactly one is the corpus")
for label, value in (("map.packageId", source.get("packageId")), ("map.version", source.get("version")),
                     ("engine.name", name)):
    if not value:
        sys.exit(f"{sys.argv[1]} names no {label}")
print(commit)
print(f"{source['packageId']}@{source['version']}")
print(corpora[0])
print(name)
print(factory.get("repository") or sys.argv[2])
print("dirty" if factory.get("dirty") else "clean")
PY
)" || die "the record does not say what to re-produce (above)"

mapfile -t FIELD <<<"$FIELDS"
COMMIT="${FIELD[0]}"; PACKAGE="${FIELD[1]}"; CORPUS="${FIELD[2]}"; NAME="${FIELD[3]}"
FACTORY_REPO="${RULES_ENGINE_FACTORY_REPO:-${FIELD[4]}}"; FACTORY_DIRTY="${FIELD[5]}"

[[ -f "$CORPUS" ]] || die "$RECORD names the corpus $CORPUS, which is not in this engine"

# A dirty working tree is the normal case here: this is what you run *after* editing the overlay
# and regenerating, so the overlay and the generated C# are modified by definition, and refusing
# that would refuse the only workflow this script exists for. Hand-written source, tests and build
# inputs are the engine's to change, and produce hashes whatever is on disk, which is what the
# commit that follows will carry.
#
# What genuinely must not be in doubt is the one field this script *obeys*: `factory.commit`
# decides which factory code is about to rewrite the gate, the rails and the vendored generator.
# So the working tree's record is compared with the committed one, on that field alone. A
# re-produce writes back the commit it read, so running this twice before committing is fine; a
# hand edit that points it at another factory is refused by name. Everything else the record holds
# is produce's own output and is expected to differ here.
#
# Two related cases need no rule of their own, because produce already refuses them and says why:
# a modified corpus/ file (intake hashes it against the map's baseline) and a hand-edited managed
# file (ownership.py names it and offers --adopt or --reset).
if "$GIT" rev-parse --verify -q HEAD >/dev/null 2>&1 && "$GIT" ls-files --error-unmatch "$RECORD" >/dev/null 2>&1; then
  COMMITTED_COMMIT="$("$GIT" show "HEAD:./$RECORD" 2>/dev/null | "$PYTHON" -c \
    'import json,sys; print((json.load(sys.stdin).get("factory") or {}).get("commit") or "")' 2>/dev/null || true)"
  if [[ -n "$COMMITTED_COMMIT" && "$COMMITTED_COMMIT" != "$COMMIT" ]]; then
    die "$RECORD in the working tree names factory.commit $COMMIT, and the committed one names
       $COMMITTED_COMMIT. This script checks out the commit the record names, so an uncommitted
       change to that field decides which factory rewrites this engine. Restore it with
       \`git checkout -- $RECORD\`, or commit the move to a new factory deliberately, on its own
       issue, before re-producing."
  fi
else
  printf 'note: this engine is not a git checkout with a committed %s, so the recorded factory\n' "$RECORD" >&2
  printf '      commit could not be compared with a reviewed one.\n' >&2
fi

[[ "$FACTORY_DIRTY" == "clean" ]] || printf 'note: %s records factory.dirty: true, so commit %s is not the whole of the\n      code that produced this engine; this re-produce runs that commit as committed.\n' "$RECORD" "$COMMIT" >&2

PRODUCE=("$PYTHON" "<factory>/tools/factory" produce --package "$PACKAGE" --corpus "$REPO_ROOT/$CORPUS"
         --name "$NAME" --out "$REPO_ROOT" ${EXTRA[@]+"${EXTRA[@]}"})

printf 'factory   %s at %s\n' "$FACTORY_REPO" "$COMMIT"
printf 'package   %s\n' "$PACKAGE"
printf 'corpus    %s\n' "$CORPUS"
printf 'engine    %s (%s)\n' "$NAME" "$REPO_ROOT"
printf 'produce   %s\n' "${PRODUCE[*]}"

if [[ "$DRY_RUN" -eq 1 ]]; then
  printf '\n--dry-run: nothing was cloned, produced or committed.\n'
  exit 0
fi

CLONE="$(mktemp -d)"
trap 'rm -rf "$CLONE"' EXIT

# Fetched by SHA at a depth of one, so no factory history is downloaded and `main` is never
# checked out. A server that refuses a by-SHA fetch (uploadpack.allowReachableSHA1InWant off)
# falls back to a full clone, which still checks out the recorded commit and never `main`.
printf '\ncloning the factory at %s\n' "$COMMIT"
"$GIT" init -q "$CLONE"
"$GIT" -C "$CLONE" remote add origin "$FACTORY_REPO"
if "$GIT" -C "$CLONE" fetch -q --depth 1 origin "$COMMIT" 2>/dev/null; then
  "$GIT" -C "$CLONE" checkout -q FETCH_HEAD
  # Best effort, and never fatal: provenance names the factory's version from a `factory/vX.Y.Z`
  # tag on that commit, so a clone without tags would record 0.0.0-dev+<sha> for a tagged release.
  "$GIT" -C "$CLONE" fetch -q --depth 1 origin "+refs/tags/*:refs/tags/*" 2>/dev/null || true
else
  rm -rf "$CLONE"
  "$GIT" clone -q "$FACTORY_REPO" "$CLONE" || die "could not clone $FACTORY_REPO"
  "$GIT" -C "$CLONE" checkout -q "$COMMIT" || die "$FACTORY_REPO has no commit $COMMIT"
fi

PRODUCE[1]="$CLONE/tools/factory"
printf 'running   %s\n\n' "${PRODUCE[*]}"
"${PRODUCE[@]}"

printf '\nre-produced. No commit was made: read what changed (provenance.json, backlog/ and the\n'
printf 'generated files) and stage it with the rest of your change.\n'
