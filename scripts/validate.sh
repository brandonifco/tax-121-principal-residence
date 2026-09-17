#!/usr/bin/env bash
# validate.sh -- the single canonical gate for this engine.
#
# Emitted by rules-factory tools/factory (the gate recipe, #3), generalised from
# hoyle-backgammon's hand-built gate. Rewritten by every `factory produce`; do not edit it here.
#
# Every step either proves something or says it could not:
#
#   * the SDK is the one global.json pins, with roll-forward disabled;
#   * restore is locked: every project has a packages.lock.json, and restore agrees with it;
#   * RulesKernel.Randomness is reachable only as the corpus declares (rules-factory decision 0019):
#     never under `randomness: none`, and under `seeded` pinned only in RulesFactory.Packages.g.props;
#   * the map is the published package plus this engine's corpus-map.overlay.json, merged under
#     rules-factory decision 0015, and the package's own check-map.py --phase consumer passes on it;
#   * the committed corpus hashes to the baseline the engine cites, under the posture the manifest
#     declares -- NOT VERIFIED where that posture leaves the bytes out of reach, and never ok;
#   * every *.g.cs is exactly a fresh regeneration: no hand edits to generated files;
#   * provenance.json still hashes the generated and managed files and the overlay it was
#     generated from, so an overlay edit that was never followed by a re-produce -- leaving a stale
#     record and a backlog still listing the entry as one to build -- fails here;
#   * format, then build and test in Debug and Release, reading the TRX files to show the tests
#     ran, and that every test an implemented entry names exists and ran.
#
#   ./scripts/validate.sh full   merge-equivalent gate (default)
#   ./scripts/validate.sh fast   Debug only; for the inner loop
#   ./scripts/validate.sh lock   (re)write packages.lock.json from a normal restore, then full.
#                                The lock files it writes must be committed; CI never uses it.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# The gate imports the factory scripts it ships (scripts/factory/*.py). Writing their bytecode would
# leave scripts/factory/__pycache__ in the engine tree, which is neither generated nor engine-owned;
# `factory verify` already sets this for the same reason.
export PYTHONDONTWRITEBYTECODE=1

MODE="${1:-full}"
case "$MODE" in full|fast|lock) ;; *) echo "usage: $0 [full|fast|lock]" >&2; exit 2 ;; esac
NAME="Tax121PrincipalResidence"
SOLUTION="$NAME.slnx"
GATE=(python3 scripts/engine-gate.py)
FAILED=0
STEP=0
NOT_VERIFIED=()

export DOTNET_NOLOGO=1
export DOTNET_CLI_TELEMETRY_OPTOUT=1

if [[ -t 1 ]]; then
  BOLD=$'\033[1m'; RED=$'\033[31m'; GREEN=$'\033[32m'; YEL=$'\033[33m'; OFF=$'\033[0m'
else
  BOLD=""; RED=""; GREEN=""; YEL=""; OFF=""
fi

step() { STEP=$((STEP + 1)); printf '\n%s==> [%d] %s%s\n' "$BOLD" "$STEP" "$1" "$OFF"; }
fail() { printf '%sFAIL%s %s\n' "$RED" "$OFF" "$1"; FAILED=1; }
run() {
  local label="$1"; shift
  if "$@"; then printf '%sok%s   %s\n' "$GREEN" "$OFF" "$label"; return 0; fi
  fail "$label"; return 1
}
# A failed build followed by `dotnet test --no-build` against stale binaries prints "ok".
skipped() { printf '%sskip%s %s (depends on a step that failed)\n' "$YEL" "$OFF" "$1"; }

SCRATCH="$(mktemp -d)"
trap 'rm -rf "$SCRATCH"' EXIT

step "SDK pin"
pinned="$(python3 -c 'import json;print(json.load(open("global.json"))["sdk"]["version"])')"
roll="$(python3 -c 'import json;print(json.load(open("global.json"))["sdk"].get("rollForward",""))')"
status=0
actual="$(dotnet --version 2>/dev/null)" || status=$?
if [[ "$roll" != "disable" ]]; then
  fail "global.json rollForward is '$roll', expected 'disable'"
elif [[ "$status" -ne 0 ]]; then
  fail "no installed SDK satisfies global.json's pin of $pinned"
elif [[ "$pinned" != "$actual" ]]; then
  fail "global.json pins $pinned but 'dotnet --version' reports $actual"
else
  printf '%sok%s   SDK %s (rollForward=%s)\n' "$GREEN" "$OFF" "$actual" "$roll"
fi

# Restore first: the map is a package (0015), so nothing below can be judged before it is
# restored. Locked mode means packages.lock.json decides; a reference, a lock file or a package's
# bytes that disagree fail here instead of being re-resolved.
step "Restore (locked)"
RESTORED=0
if [[ "$MODE" == "lock" ]]; then
  run "dotnet restore, writing packages.lock.json (commit them)" \
      dotnet restore "$SOLUTION" --force-evaluate -p:RestoreLockedMode=false || true
fi
if run "every project has a packages.lock.json" "${GATE[@]}" lock-files; then
  run "dotnet restore --locked-mode" dotnet restore "$SOLUTION" --locked-mode && RESTORED=1 || true
else
  skipped "dotnet restore --locked-mode"
fi

# The restored package's build props say where NuGet put the map, its manifest and its checker,
# so nothing here guesses at the global packages folder.
step "Map = merge(package, overlay)"
MAP_OK=0
if [[ "$RESTORED" -eq 1 ]]; then
  MAP_TF="$(python3 -c 'import re;print(re.search(r"<TargetFrameworks?>([^;<]+)",open("Directory.Build.props").read()).group(1))')"
  MAP_ITEM="$(dotnet msbuild "src/$NAME/$NAME.csproj" -getItem:RulesFactoryMap -p:TargetFramework="$MAP_TF" 2>/dev/null || true)"
  if MAP_ARGS="$(python3 -c '
import json, sys
try:
    items = json.loads(sys.argv[1])["Items"]["RulesFactoryMap"]
except Exception:
    items = []
if len(items) != 1:
    print(f"error: expected exactly one RulesFactoryMap item from the restored package, found {len(items)}", file=sys.stderr)
    sys.exit(1)
i = items[0]
fields = [i.get("FullPath"), i.get("PackageId"), i.get("PackageVersion"), i.get("Manifest"), i.get("ConsumerChecker")]
if not all(fields):
    print("error: the RulesFactoryMap item lacks a map, id, version, manifest or ConsumerChecker (rules-factory#51)", file=sys.stderr)
    sys.exit(1)
print("\n".join(fields))
' "$MAP_ITEM")"; then
    mapfile -t MAP_FIELDS <<<"$MAP_ARGS"
    PACKAGE_MAP="${MAP_FIELDS[0]}"; PACKAGE_ID="${MAP_FIELDS[1]}"; PACKAGE_VERSION="${MAP_FIELDS[2]}"
    PACKAGE_MANIFEST="${MAP_FIELDS[3]}"; CONSUMER_CHECKER="${MAP_FIELDS[4]}"
    MERGED="$SCRATCH/corpus-map.json"
    if run "merge($PACKAGE_ID@$PACKAGE_VERSION, corpus-map.overlay.json) obeys 0015" \
        python3 scripts/map-overlay.py merge --package-map "$PACKAGE_MAP" \
          --overlay corpus-map.overlay.json --out "$MERGED"; then
      MAP_OK=1
      # 0015 rule 6: the checks the overlay can change, from the restored package's own checker.
      run "packaged check-map.py --phase consumer passes on the merged map" \
          python3 "$CONSUMER_CHECKER" "$MERGED" --manifest "$PACKAGE_MANIFEST" --phase consumer || true
    else
      skipped "packaged check-map.py --phase consumer passes on the merged map"
    fi
  else
    fail "the restored map package could not be located"
  fi
else
  skipped "merge(package, overlay) obeys 0015"
  skipped "packaged check-map.py --phase consumer passes on the merged map"
fi

# rules-factory decision 0019. The declaration is read from the restored package, which the lock
# files pin by hash, never from a file this engine commits.
step "Randomness"
if [[ -n "${PACKAGE_MANIFEST:-}" ]]; then
  run "RulesKernel.Randomness is reachable only as the corpus declares" \
      "${GATE[@]}" randomness --manifest "$PACKAGE_MANIFEST" --map "$PACKAGE_MAP" || true
else
  skipped "RulesKernel.Randomness is reachable only as the corpus declares"
fi

# rules-factory decision 0013. NOT VERIFIED is its own outcome: not ok, not FAIL, named at the end.
step "Corpus verification posture"
if [[ "$MAP_OK" -eq 1 ]]; then
  posture_status=0
  "${GATE[@]}" posture --manifest "$PACKAGE_MANIFEST" --map "$MERGED" --name "$NAME" || posture_status=$?
  case "$posture_status" in
    0) printf '%sok%s   every corpus verified under its declared posture\n' "$GREEN" "$OFF" ;;
    3) printf '%sNOT VERIFIED%s a corpus could not be verified under its declared posture (not ok, not FAIL)\n' "$YEL" "$OFF"
       NOT_VERIFIED+=("corpus verification posture") ;;
    *) fail "every corpus verified under its declared posture" ;;
  esac
else
  skipped "every corpus verified under its declared posture"
fi

step "Generated files"
if [[ "$RESTORED" -eq 1 && -n "${PACKAGE_MAP:-}" ]]; then
  run "every *.g.cs matches a fresh regeneration (no hand edits)" \
      "${GATE[@]}" regenerate --package-map "$PACKAGE_MAP" --package-manifest "$PACKAGE_MANIFEST" --package-id "$PACKAGE_ID" \
        --package-version "$PACKAGE_VERSION" --name "$NAME" || true
else
  skipped "every *.g.cs matches a fresh regeneration (no hand edits)"
fi

# Not guarded on $RESTORED or $MAP_OK: it reads files in this repository and nothing else -- no
# restore, no map package, no network -- so it can never legitimately degrade to a skip.
step "The provenance record"
run "provenance.json hashes the generated files, the managed files and the overlay" \
    "${GATE[@]}" provenance || true

step "Format"
if [[ "$RESTORED" -eq 1 ]]; then
  run "dotnet format --verify-no-changes" dotnet format "$SOLUTION" --verify-no-changes --no-restore || true
else
  skipped "dotnet format --verify-no-changes"
fi

EXPECTED_RESULT_FILES="$("${GATE[@]}" expected-results)"

build_and_test() {
  local config="$1"; shift
  local results="$SCRATCH/results-$config"
  if [[ "$RESTORED" -ne 1 ]]; then
    skipped "build $config"; skipped "test $config"; skipped "every named test exists and ran ($config)"
    return
  fi
  if run "build $config (0 warnings)" env "$@" dotnet build "$SOLUTION" -c "$config" --no-restore -warnaserror; then
    local status=0
    env "$@" dotnet test "$SOLUTION" -c "$config" --no-build --nologo \
      --logger "trx" --results-directory "$results" || status=$?
    if "${GATE[@]}" tests-ran "$results" "$EXPECTED_RESULT_FILES" && [[ "$status" -eq 0 ]]; then
      printf '%sok%s   test %s\n' "$GREEN" "$OFF" "$config"
    else
      fail "test $config"
    fi
    if [[ "$MAP_OK" -eq 1 ]]; then
      run "every test an implemented entry names exists and ran ($config)" \
          "${GATE[@]}" named-tests "$results" --map "$MERGED" || true
    else
      skipped "every test an implemented entry names exists and ran ($config)"
    fi
  else
    skipped "test $config"
    skipped "every test an implemented entry names exists and ran ($config)"
  fi
}

step "Build + test (Debug)"
build_and_test Debug CI="${CI:-}"

if [[ "$MODE" != "fast" ]]; then
  step "Build + test (Release, CI=true)"
  build_and_test Release CI=true
fi

# The rails this engine is worked under, held to their own word: a reviewer charter that grants a
# tool that writes, and a rail citing a document this engine does not have, are both defects this
# project's lineage has actually shipped (rules-factory decision 0029).
step "The agent rails"
run "the rails hold: read-only reviewers, no dangling citation, a readable policy" "${GATE[@]}" rails || true

echo
if [[ "$FAILED" -eq 0 && "${#NOT_VERIFIED[@]}" -gt 0 ]]; then
  printf '%s%svalidate.sh %s: PASS, and NOT VERIFIED: %s%s\n' \
    "$BOLD" "$YEL" "$MODE" "$(IFS=,; echo "${NOT_VERIFIED[*]}")" "$OFF"
elif [[ "$FAILED" -eq 0 ]]; then
  printf '%s%svalidate.sh %s: PASS%s\n' "$BOLD" "$GREEN" "$MODE" "$OFF"
else
  printf '%s%svalidate.sh %s: FAIL%s\n' "$BOLD" "$RED" "$MODE" "$OFF"
fi
exit "$FAILED"
