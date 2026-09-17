#!/usr/bin/env python3
"""The checks scripts/validate.sh runs that are not a dotnet command.

Emitted by rules-factory tools/factory (the gate recipe, #3). Rewritten by every `factory
produce`; do not edit it here. Each subcommand prints what it examined and exits 0 when it
proved its claim, 1 when it did not; `posture` also exits 3 for NOT VERIFIED. A check that
finds nothing to examine fails: a check with no inputs has proven nothing.

  lock-files                         every project on disk has a packages.lock.json
  randomness --manifest M --map MAP  RulesKernel.Randomness is reachable only as the corpus declares
  posture --manifest M --map MAP --name N
                                     the committed corpus hashes to the baseline, under its posture
  regenerate --package-map P --package-manifest M --package-id ID --package-version V --name N [--write]
                                     every *.g.cs is exactly what the factory generates
  provenance                         provenance.json still hashes the files on disk (re-produce after
                                     an overlay edit)
  expected-results                   test projects on disk x target frameworks
  tests-ran DIR EXPECTED             the TRX files show that many result files and >0 tests
  named-tests DIR --map MAP          every test an implemented entry names exists and ran
  rails                              the agent rails hold: read-only reviewers, no dangling
                                     citation, a policy the rails can read

Run from the engine root. Standard library only.
"""
import argparse
import difflib
import glob
import hashlib
import json
import os
import pathlib
import re
import sys
import types

# derivations() and regenerate() import the vendored scripts/factory modules, and an imported
# module leaves its bytecode behind: scripts/factory/__pycache__/, a path no ownership row covers,
# so the checkout that ran this goes dirty and tools/dispatch-agent.sh refuses to open a worktree
# for the next issue (#194). scripts/validate.sh, which is what usually runs this, exports
# PYTHONDONTWRITEBYTECODE for the same reason, and so does `factory verify`; nothing exports it
# when an agent runs a subcommand directly from its shell. The loader reads this flag when the
# import happens, so it belongs here and not beside the imports it disarms.
sys.dont_write_bytecode = True

ROOT = pathlib.Path.cwd()
IGNORED = {"bin", "obj", ".git", "artifacts", "TestResults"}
OVERLAY = "corpus-map.overlay.json"
RANDOMNESS_PACKAGE = "RulesKernel.Randomness"
RANDOMNESS = ("none", "seeded")
GENERATED_PROPS = "RulesFactory.Packages.g.props"
TRX_NS = {"t": "http://microsoft.com/schemas/VisualStudio/TeamTest/2010"}


def on_disk(pattern):
    return sorted(p for p in ROOT.rglob(pattern) if not any(part in IGNORED for part in p.relative_to(ROOT).parts))


def report(problems, success):
    for p in problems:
        print(f"error: {p}", file=sys.stderr)
    if problems:
        return 1
    print(f"     {success}")
    return 0


def target_frameworks():
    props = (ROOT / "Directory.Build.props").read_text(encoding="utf-8")
    match = re.search(r"<TargetFrameworks?>([^<]+)</TargetFrameworks?>", props)
    return [f for f in match.group(1).split(";") if f] if match else []


# --- restore ---------------------------------------------------------------------------


def lock_files(_args):
    projects = on_disk("*.csproj")
    missing = [str(p.relative_to(ROOT)) for p in projects if not (p.parent / "packages.lock.json").is_file()]
    problems = [] if projects else ["no project found on disk, so no lock file was required of anything"]
    problems += [f"{m} has no packages.lock.json beside it; run `./scripts/validate.sh lock` and commit "
                 "the lock files" for m in missing]
    return report(problems, f"{len(projects)} project(s), each with its packages.lock.json")


def declared_randomness(manifest_path, map_path):
    """The `randomness` the package manifest declares for the corpus the package map cites (0019).

    Read from the restored map package, not from anything the engine commits. The package is
    pinned to one version in the generated RulesFactory.Packages.g.props (the regenerate step holds
    that file to a fresh regeneration) and to one content hash in the lock files (restore runs in
    locked mode), so the engine cannot change the declaration without changing which package it is
    built from. provenance.json records the same value, but it is a file in the engine's tree, and
    only `factory provenance` recomputes it; a check that read it could be escaped by editing it.
    Returns (value, problem): exactly one is None.
    """
    try:
        manifest = json.loads(pathlib.Path(manifest_path).read_text(encoding="utf-8"))
        mapped = json.loads(pathlib.Path(map_path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return None, f"cannot read the package manifest or map: {error}"
    source_id = mapped.get("corpus") if isinstance(mapped, dict) else None
    corpora = [c for c in (manifest.get("corpora") if isinstance(manifest, dict) else None) or []
               if isinstance(c, dict) and c.get("sourceId") == source_id]
    if len(corpora) != 1:
        return None, f"the package manifest declares the map's corpus {source_id!r} {len(corpora)} times, not once"
    value = corpora[0].get("randomness")
    if isinstance(value, bool) or value not in RANDOMNESS:
        return None, (f"{source_id} declares randomness {value!r}; it must be one of {', '.join(RANDOMNESS)} "
                      "(rules-factory decision 0019), and nothing is assumed when it is missing")
    return value, None


def randomness(args):
    """rules-factory decision 0019: whether an engine may draw random values is the corpus's to say.

    `none`: a rule-bound engine for a corpus with no chance in it draws no random value, so the
    kernel's randomness package must not be reachable, directly or transitively. Lock files list
    every package restore resolves, so they are the evidence; project files are read too, so a
    reference is found even before a lock file records it.

    `seeded`: the engine may reference RulesKernel.Randomness, and its version has one home, the
    generated RulesFactory.Packages.g.props, at the kernel's version. An engine-owned MSBuild file
    that pins it again or overrides its version is refused, so the version cannot drift where no
    regeneration looks."""
    declared, problem = declared_randomness(args.manifest, args.map)
    if problem:
        return report([problem], "")
    locks = on_disk("packages.lock.json")
    problems = [] if locks else ["no packages.lock.json found, so nothing shows what restore resolves"]
    resolved, referenced = [], []
    for lock in locks:
        try:
            document = json.loads(lock.read_text(encoding="utf-8"))
        except ValueError as error:
            problems.append(f"{lock.relative_to(ROOT)} is not JSON: {error}")
            continue
        for framework, packages in (document.get("dependencies") or {}).items():
            for name in packages or {}:
                if name.lower() == RANDOMNESS_PACKAGE.lower():
                    resolved.append(f"{lock.relative_to(ROOT)} ({framework}) resolves {name}")
    pattern = re.escape(RANDOMNESS_PACKAGE)
    for project in on_disk("*.csproj") + on_disk("*.props") + on_disk("*.targets"):
        relative = str(project.relative_to(ROOT)).replace(os.sep, "/")
        text = project.read_text(encoding="utf-8", errors="replace")
        generated_props = relative == GENERATED_PROPS
        if re.search(r'Include\s*=\s*"' + pattern + r'"', text, re.IGNORECASE):
            if declared == "none" or not generated_props:
                referenced.append(f"{relative} references {RANDOMNESS_PACKAGE}")
        if declared == "seeded" and not generated_props:
            if re.search(r'<PackageVersion\b[^>]*?\bInclude\s*=\s*"' + pattern + r'"', text, re.IGNORECASE):
                problems.append(f"{relative} pins {RANDOMNESS_PACKAGE}; its version belongs in {GENERATED_PROPS}, "
                                "at the kernel's version")
            if re.search(r'<PackageReference\b[^>]*?\bInclude\s*=\s*"' + pattern + r'"[^>]*?\bVersion(Override)?\s*=',
                         text, re.IGNORECASE):
                problems.append(f"{relative} gives {RANDOMNESS_PACKAGE} a version of its own; it belongs in "
                                f"{GENERATED_PROPS}, at the kernel's version")
    if declared == "none":
        problems += resolved + referenced
        return report(problems, f"randomness: none -- {len(locks)} lock file(s) and the project files resolve no "
                                f"{RANDOMNESS_PACKAGE}")
    return report(problems, f"randomness: seeded -- {RANDOMNESS_PACKAGE} may be referenced, pinned only in "
                            f"{GENERATED_PROPS} ({len(resolved)} lock-file resolution(s) of it)")


# --- the corpus --------------------------------------------------------------------------

def derivations():
    """The hashDerivations this gate can recompute: intake's HASH_DERIVATIONS, from the copy of the
    factory's intake.py that `factory produce` vendored under scripts/factory/ beside this file.

    There is one table, not two. This gate once kept its own, and a derivation the factory admitted
    (#108, the SRD's) was missing from it, so every engine of that corpus failed here (#106). The
    vendored intake.py is already what `regenerate` imports its siblings from, and its bytes are in
    provenance.json's `generated`. A declared derivation not in the table is a failure: a digest
    nobody re-derived is unchecked."""
    sys.path.insert(0, str(ROOT / "scripts" / "factory"))
    try:
        import intake  # noqa: E402  (the factory's intake, vendored by produce)
    except ImportError as error:
        return None, f"scripts/factory/intake.py cannot be imported ({error}); run `factory produce` again"
    table = getattr(intake, "HASH_DERIVATIONS", None)
    if not isinstance(table, dict) or not table:
        return None, "scripts/factory/intake.py declares no HASH_DERIVATIONS; run `factory produce` again"
    return table, None


def posture(args):
    """rules-factory decision 0013: how a baseline is verified is a property of the corpus.

    committed-copy: the bytes are under corpus/; hashed here and in CI.
    local-copy: the bytes are not in the repository; hashed from $envVar when it is set, and
    otherwise NOT VERIFIED (exit 3) -- neither ok nor FAIL, and never silent.
    """
    manifest = json.loads(pathlib.Path(args.manifest).read_text(encoding="utf-8"))
    mapped = json.loads(pathlib.Path(args.map).read_text(encoding="utf-8"))
    entries_cs = ROOT / "src" / args.name / "Generated" / "MapEntries.g.cs"
    cited = re.search(r'contentHash: "([0-9a-f]{64})"', entries_cs.read_text(encoding="utf-8")) if entries_cs.is_file() else None

    table, problem = derivations()
    if problem:
        return report([problem], "")
    problems, verified, unverified = [], [], []
    corpora = [c for c in manifest.get("corpora") or [] if isinstance(c, dict)]
    if not corpora:
        problems.append("the package manifest declares no corpora, so nothing was verified")
    for corpus in corpora:
        sid = corpus.get("sourceId", "?")
        kind = corpus.get("verification")
        boundary = corpus.get("boundaryPolicy")
        expected = corpus.get("contentHash")
        derive = table.get(corpus.get("hashDerivation"))
        if sid == mapped.get("corpus"):
            if (mapped.get("baseline") or {}).get("contentHash") != expected:
                problems.append(f"{sid}: the map's baseline is {(mapped.get('baseline') or {}).get('contentHash')}, "
                                f"the manifest's is {expected}")
            if cited is None or cited.group(1) != expected:
                problems.append(f"{sid}: MapEntries.Baseline cites {cited.group(1) if cited else 'no contentHash'}, "
                                f"the manifest says {expected}")
        if kind not in ("committed-copy", "local-copy"):
            problems.append(f"{sid}: verification is {kind!r}; it must be committed-copy or local-copy")
            continue
        if boundary == "never-commit" and kind == "committed-copy":
            problems.append(f"{sid}: a never-commit corpus cannot be committed-copy")
            continue
        if derive is None:
            problems.append(f"{sid}: this gate cannot recompute hashDerivation {corpus.get('hashDerivation')!r}, "
                            f"so the baseline is unchecked (known: {', '.join(sorted(table))})")
            continue
        if kind == "committed-copy":
            name = os.path.basename(str(corpus.get("committedPath") or ""))
            path = ROOT / "corpus" / name if name else None
            if path is None or not path.is_file():
                problems.append(f"{sid}: committed-copy, and corpus/{name} is not a file")
                continue
            where = f"committed at corpus/{name}"
        else:
            var = corpus.get("envVar")
            if not var:
                problems.append(f"{sid}: local-copy names no envVar")
                continue
            if not os.environ.get(var):
                unverified.append(f"{sid} (local-copy, {boundary}): ${var} is not set, so the corpus bytes "
                                  "are not here to hash. Set it to a legal copy to verify.")
                continue
            path = pathlib.Path(os.environ[var])
            if not path.is_file():
                problems.append(f"{sid}: ${var} is {str(path)!r}, which is not a file")
                continue
            where = f"local copy at ${var}"
        digest = derive(path.read_bytes())
        if digest != expected:
            problems.append(f"{sid}: the {where} hashes to {digest}, the manifest pins {expected}")
        else:
            verified.append(f"{sid} ({kind}, {boundary}): {where} hashes to the pinned baseline")

    for p in problems:
        print(f"error: {p}", file=sys.stderr)
    for v in verified:
        print(f"     verified: {v}")
    for u in unverified:
        print(f"     NOT VERIFIED: {u}")
    return 1 if problems else 3 if unverified else 0


# --- the generated files ----------------------------------------------------------------


def regenerate(args):
    """Every *.g.cs, and RulesFactory.Packages.g.props with the kernel and map pins, is what the
    factory's generator makes of merge(package, overlay) and the package id and version, byte for byte.

    The generator (generate.py, and provenance.py for the files that embed provenance.json) is the
    copy under scripts/factory/, written by the same `factory produce` that wrote the files; that
    its bytes are the factory's is provenance's to show (every recipe file is in provenance.json's
    `generated`), not this step's."""
    sys.path.insert(0, str(ROOT / "scripts" / "factory"))
    import generate  # noqa: E402  (the factory's generator, vendored by produce)
    import provenance  # noqa: E402  (its generated C# that embeds provenance.json)
    import rulings  # noqa: E402  (the owner's rulings the overlay holds, rules-factory decision 0027)

    package = json.loads(pathlib.Path(args.package_map).read_text(encoding="utf-8"))
    declared, problem = declared_randomness(args.package_manifest, args.package_map)
    if problem:
        return report([problem], "")
    overlay_path = ROOT / OVERLAY
    overlay = json.loads(overlay_path.read_text(encoding="utf-8")) if overlay_path.is_file() else {}
    try:
        model = generate.Model(types.SimpleNamespace(package_id=args.package_id, version=args.package_version,
                                                     randomness=declared),
                               generate.merge(package, overlay, root=str(ROOT)), args.name, rulings.collect(overlay))
        expected = {**generate.generated(model), **provenance.embedding(model)}
    except generate.GenerationError as error:
        return report([f"the generator refuses merge(package, overlay): {error}"], "")

    if args.write:
        for relative, text in expected.items():
            target = ROOT / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(text.encode("utf-8"))
        print(f"     wrote {len(expected)} generated file(s)")
        return 0

    problems = []
    for relative, text in sorted(expected.items()):
        target = ROOT / relative
        if not target.is_file():
            problems.append(f"{relative} is missing")
            continue
        actual = target.read_bytes()
        if actual != text.encode("utf-8"):
            diff = list(difflib.unified_diff(actual.decode("utf-8", "replace").splitlines(), text.splitlines(),
                                             f"{relative} (on disk)", f"{relative} (regenerated)", n=0, lineterm=""))
            shown = "\n".join(diff[:12]) + ("\n..." if len(diff) > 12 else "")
            problems.append(f"{relative} differs from a fresh regeneration -- a hand edit, or an overlay "
                            f"changed without re-running `factory produce`:\n{shown}")
    stray = sorted({str(p.relative_to(ROOT)).replace(os.sep, "/") for p in on_disk("*.g.cs")} - set(expected))
    problems += [f"{s} is a *.g.cs file the factory does not generate; hand-written code goes in any other file"
                 for s in stray]
    return report(problems, f"{len(expected)} generated file(s) match a fresh regeneration from "
                            f"{args.package_id}@{args.package_version} + {OVERLAY}")


# --- the record -------------------------------------------------------------------------

RECORD = "provenance.json"
RE_PRODUCE = "tools/re-produce.sh"


def record_matches(_args):
    """provenance.json still hashes the bytes on disk: the derived files are not older than the
    overlay they were derived from (#192).

    This compares and nothing else. It re-derives nothing and writes nothing, because **an engine
    cannot author this record.** `factory produce` writes it from a rules-factory checkout: it
    names that checkout's commit, hashes every one of the factory's recipe files, and lists what
    the run itself wrote. An engine has five vendored modules and no run to observe. Decisively, an
    engine can re-derive its `*.g.cs` but not scripts/validate.sh, this file, scripts/map-overlay.py,
    scripts/factory/*.py or the CI workflow -- all recorded as generated, all hashed here. An
    engine-side rewrite would hash whatever is on disk and hand a fresh matching SHA-256 to a
    hand-edited gate, and a gate that re-blesses its own bytes proves nothing.

    **What is compared, and what deliberately is not.** Every `generated` entry, every `managed`
    entry, and `buildInputs[corpus-map.overlay.json]` -- and no other build input. Adding a
    PackageReference, a project to the solution or a version to Directory.Packages.props are
    engine-owned acts (decision 0018); making each of them require a re-produce before this goes
    green would produce a gate people route around. Holding the whole of `buildInputs` is
    `factory provenance`'s job, where a real re-produce can tell a legitimate addition from drift.
    The overlay is different in kind: it is the *input to generation*, and appears in `buildInputs`
    only because it happens to be engine-owned. That single comparison is what catches a stale
    record, because hashing the recorded backlog files cannot: a backlog item file that still lists
    an implemented entry is unchanged, so its hash matches. The overlay moved, so everything derived
    from it is older than the overlay, and that is the fact this names.
    """
    sys.path.insert(0, str(ROOT / "scripts" / "factory"))
    try:
        import provenance  # noqa: E402  (the factory's own record module, vendored by produce)
    except ImportError as error:
        return report([f"scripts/factory/provenance.py cannot be imported ({error}); run `{RE_PRODUCE}`"], "")

    path = ROOT / RECORD
    if not path.is_file():
        return report([f"{RECORD} is not here, so nothing says what this engine was produced from; "
                       f"run `{RE_PRODUCE}`"], "")
    raw = path.read_bytes()
    try:
        recorded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        return report([f"{RECORD} is not readable JSON ({error})"], "")
    if not isinstance(recorded, dict):
        return report([f"{RECORD} is not a JSON object"], "")

    problems, examined = [], 0
    # The factory's own serialisation, so a hand edit shows up even when it kept every hash true.
    if raw != provenance.serialize(recorded):
        problems.append(f"{RECORD} is not in the factory's canonical form; only `factory produce` writes it, "
                        f"and this file has been through another hand")

    for section in ("generated", "managed"):
        for item in recorded.get(section) or []:
            if not (isinstance(item, dict) and isinstance(item.get("path"), str)):
                problems.append(f"{section}: {item!r} is not a recorded path and hash")
                continue
            examined += 1
            where = ROOT / pathlib.Path(*item["path"].split("/"))
            if not where.is_file():
                problems.append(f"{section}[{item['path']}]: recorded, missing on disk")
            else:
                actual = hashlib.sha256(where.read_bytes()).hexdigest()
                if actual != item.get("sha256"):
                    problems.append(f"{section}[{item['path']}].sha256: recorded {item.get('sha256')}, "
                                    f"on disk {actual}")

    entry = next((item for item in recorded.get("buildInputs") or []
                  if isinstance(item, dict) and item.get("path") == OVERLAY), None)
    overlay_path = ROOT / OVERLAY
    if entry is not None or overlay_path.is_file():
        examined += 1
    if entry is None and overlay_path.is_file():
        problems.append(f"buildInputs[{OVERLAY}]: not recorded, and the engine has one; the record predates the "
                        f"overlay it was generated from")
    elif entry is not None and not overlay_path.is_file():
        problems.append(f"buildInputs[{OVERLAY}]: recorded, missing on disk")
    elif entry is not None:
        actual = hashlib.sha256(overlay_path.read_bytes()).hexdigest()
        if actual != entry.get("sha256"):
            problems.append(f"buildInputs[{OVERLAY}].sha256: recorded {entry.get('sha256')}, on disk {actual}. "
                            f"The overlay is the input the generated files and the backlog are made from, so "
                            f"everything derived from it is older than it is")

    if not examined:
        print(f"error: {RECORD} lists no generated file, no managed file and no {OVERLAY}, so this check examined "
              f"nothing -- and a check that examines nothing is a failure, never an ok", file=sys.stderr)
        return 1
    if problems:
        source = recorded.get("map") or {}
        name = (recorded.get("engine") or {}).get("name")
        for problem in problems:
            print(f"error: {problem}", file=sys.stderr)
        print(f"error: one command fixes all of the above: `{RE_PRODUCE}`. It clones rules-factory at the commit "
              f"{RECORD} names and runs `factory produce --package {source.get('packageId')}@{source.get('version')} "
              f"--corpus <this engine's corpus> --name {name} --out <this engine>` -- which is the only thing that "
              f"writes {RECORD} and backlog/. Editing either by hand is the defect this step exists to catch.",
              file=sys.stderr)
        return 1
    return report([], f"{examined} recorded file(s) hash as {RECORD} records, {OVERLAY} among them")


# --- tests ------------------------------------------------------------------------------


def expected_results(_args):
    """`dotnet test` exits 0 when it finds nothing, so the expectation comes from the projects on
    disk, not the solution: a project dropped from the solution would drop out of both counts."""
    count = sum(1 for p in on_disk("*.csproj")
                if re.search(r"<IsTestProject>\s*true\s*</IsTestProject>", p.read_text(encoding="utf-8"), re.I))
    print(count * max(1, len(target_frameworks())))
    return 0


def _trx(results_dir):
    return sorted(glob.glob(os.path.join(results_dir, "**", "*.trx"), recursive=True))


def tests_ran(args):
    import xml.etree.ElementTree as ET
    files, total = _trx(args.results_dir), 0
    for f in files:
        counters = ET.parse(f).getroot().find(".//t:ResultSummary/t:Counters", TRX_NS)
        if counters is not None:
            total += int(counters.get("total", "0"))
    problems = []
    if len(files) != args.expected:
        problems.append(f"expected {args.expected} result file(s) (test projects on disk x target frameworks), "
                        f"found {len(files)}. A test project silently stopped running.")
    if total == 0:
        problems.append("zero tests were discovered or executed across all test projects")
    return report(problems, f"{total} test(s) across {len(files)} result file(s) actually ran")


def named_tests(args):
    """rules-factory#2: an `implemented` entry names the tests that prove it. The map cannot show a
    named test exists or ran, so every one must have an executed result (Passed or Failed; a
    failure is the suite's to report) in every target framework. Names are `Class.Method`; a short
    class name that resolves to two classes is refused rather than guessed."""
    import xml.etree.ElementTree as ET
    frameworks = max(1, len(target_frameworks()))
    ran, classes = {}, {}
    for f in _trx(args.results_dir):
        root = ET.parse(f).getroot()
        names = {}
        for unit in root.iterfind(".//t:UnitTest", TRX_NS):
            method = unit.find("t:TestMethod", TRX_NS)
            full = method.get("className")
            short = full.rsplit(".", 1)[-1]
            classes.setdefault(short, set()).add(full)
            names[unit.get("id")] = f"{short}.{method.get('name')}"
        for name in {names[r.get("testId")] for r in root.iterfind(".//t:UnitTestResult", TRX_NS)
                     if r.get("outcome") in ("Passed", "Failed") and r.get("testId") in names}:
            ran[name] = ran.get(name, 0) + 1

    mapped = json.loads(pathlib.Path(args.map).read_text(encoding="utf-8"))
    problems, named, implemented = [], 0, 0
    for entry in mapped.get("entries") or []:
        tests = entry.get("tests") or []
        if entry.get("status") == "implemented":
            implemented += 1
            if not tests:
                problems.append(f"{entry.get('id')}: implemented, and names no test")
        for item in tests:
            named += 1
            test = item.get("test", "") if isinstance(item, dict) else ""
            short = test.rsplit(".", 1)[0] if "." in test else ""
            if len(classes.get(short, ())) > 1:
                problems.append(f"{entry.get('id')}: {test!r} is ambiguous; class {short} is {sorted(classes[short])}")
            elif ran.get(test, 0) == 0:
                problems.append(f"{entry.get('id')}: names {test!r}, which no result file shows running -- "
                                "renamed, deleted, skipped, or never a test")
            elif ran[test] != frameworks:
                problems.append(f"{entry.get('id')}: {test!r} ran in {ran[test]} result file(s), expected one per "
                                f"target framework ({frameworks})")
    if not problems and implemented == 0:
        print("     no entry is implemented, so no named test was required (nothing here to prove yet)")
        return 0
    return report(problems, f"{named} test(s) named by {implemented} implemented entries, every one found and "
                            f"executed in all {frameworks} target framework(s)")


# --- the rails (rules-factory decision 0029) -------------------------------------------------

POLICY = ".github/agent-policy.json"
# A charter that grants any of these can edit what it reviews. The predecessor's own check caught a
# charter claiming read-only while granting `Bash`, which is why this is a check and not a rule.
MUTATING_TOOLS = {"bash", "edit", "write", "notebookedit", "multiedit", "task", "webfetch", "websearch"}
REVIEWER_CHARTERS = (".claude/agents/repo-steward.md", ".claude/agents/rules-conformance.md")
RAIL_DOCUMENTS = ("AGENTS.md", "CLAUDE.md", "docs/agent-team.md")
LINK = re.compile(r"\[[^\]]*\]\(([^)#\s]+)(?:#[^)\s]*)?\)")


def charter_tools(text):
    """The `tools:` line of a charter's front matter, as a set, or None when it grants no list."""
    if not text.startswith("---\n"):
        return None
    for line in text.split("---\n", 2)[1].splitlines():
        if line.startswith("tools:"):
            return {tool.strip().lower() for tool in line.split(":", 1)[1].split(",") if tool.strip()}
    return None


def rails(_args):
    """The rails hold together: read-only means read-only, and nothing cites what is not here.

    Two failures this repository's lineage has actually shipped, turned into checks:

      * a charter that described a reviewer as read-only while granting it a tool that writes. A
        reviewer that can edit what it reviews is not a reviewer, and prose saying otherwise is
        worse than nothing because it is believed;
      * enforcement machinery shipped beside documents it cited and did not have -- sixty-one
        references to files that did not exist, several inside runtime error messages, and a
        pre-armed hook whose escape hatch was documented in a file that had been deleted. Rails
        and their manual ship together or neither ships.
    """
    problems = []
    examined = 0

    for relative in REVIEWER_CHARTERS:
        path = ROOT / relative
        if not path.is_file():
            problems.append(f"{relative} is missing: a reviewer role with no charter is a reviewer with no limits")
            continue
        examined += 1
        granted = charter_tools(path.read_text(encoding="utf-8"))
        if granted is None:
            problems.append(f"{relative} grants no explicit `tools:` list, so it inherits every tool. A reviewer "
                            f"that can edit what it reviews is not a reviewer.")
        elif granted & MUTATING_TOOLS:
            problems.append(f"{relative} grants {', '.join(sorted(granted & MUTATING_TOOLS))}, which can write. "
                            f"A read-only charter that grants a writing tool is the predecessor's own bug.")

    for relative in RAIL_DOCUMENTS + REVIEWER_CHARTERS + (".claude/agents/engine-dev.md",):
        path = ROOT / relative
        if not path.is_file():
            problems.append(f"{relative} is missing, and other rails cite it")
            continue
        for target in LINK.findall(path.read_text(encoding="utf-8")):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            examined += 1
            if not (path.parent / target).resolve().exists():
                problems.append(f"{relative} cites {target}, which does not exist in this engine")

    # Every path a rail names in running text, checked the same way: a command an agent is told to
    # run that is not here is the same defect as a broken link, and reads as more authoritative.
    for relative in RAIL_DOCUMENTS:
        path = ROOT / relative
        if not path.is_file():
            continue
        for named in set(re.findall(r"`((?:tools|scripts)/[A-Za-z0-9_.\-/]+\.(?:py|sh))`",
                                    path.read_text(encoding="utf-8"))):
            examined += 1
            if not (ROOT / named).is_file():
                problems.append(f"{relative} tells an agent to run {named}, which this engine does not have")

    policy_path = ROOT / POLICY
    if not policy_path.is_file():
        problems.append(f"{POLICY} is missing: every rail reads its labels, contexts and chain from it")
    else:
        examined += 1
        try:
            document = json.loads(policy_path.read_text(encoding="utf-8"))
        except ValueError as error:
            problems.append(f"{POLICY} is not JSON ({error}); the rails cannot read their own configuration")
            document = None
        if isinstance(document, dict):
            if document.get("schemaVersion") != 1:
                problems.append(f"{POLICY} has schemaVersion {document.get('schemaVersion')!r}; this engine's rails "
                                f"read version 1")
            review = document.get("review") or {}
            if not review.get("semanticContext"):
                problems.append(f"{POLICY} sets no review.semanticContext, so no semantic verdict can be recorded")
            chain = review.get("independentFallback") or []
            if not chain:
                problems.append(f"{POLICY} configures no independent reviewer, so an issue classified as needing "
                                f"one can never be merged")
            for link in chain:
                if not (isinstance(link, dict) and link.get("id") and link.get("context")):
                    problems.append(f"{POLICY}: every review.independentFallback link needs an id and a context "
                                    f"(got {link!r}). A verdict recorded under a generic context cannot be told "
                                    f"from a same-family fallback.")
            for field in ("ready", "blocked", "needsDecision", "normalRisk", "independentRisk"):
                if not (document.get("labels") or {}).get(field):
                    problems.append(f"{POLICY} names no {field} label, and the rails read every label from here")

    if not examined:
        print("no rails found to examine -- this check proved nothing", file=sys.stderr)
        return 1
    return report(problems, f"the rails hold: {len(REVIEWER_CHARTERS)} read-only charter(s), {examined} citation(s) "
                            f"and path(s) that resolve, and a policy the rails can read")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("lock-files").set_defaults(run=lock_files)
    m = sub.add_parser("randomness")
    m.add_argument("--manifest", required=True)
    m.add_argument("--map", required=True)
    m.set_defaults(run=randomness)
    p = sub.add_parser("posture")
    p.add_argument("--manifest", required=True)
    p.add_argument("--map", required=True)
    p.add_argument("--name", required=True)
    p.set_defaults(run=posture)
    r = sub.add_parser("regenerate")
    for flag in ("--package-map", "--package-manifest", "--package-id", "--package-version", "--name"):
        r.add_argument(flag, required=True)
    r.add_argument("--write", action="store_true")
    r.set_defaults(run=regenerate)
    sub.add_parser("provenance").set_defaults(run=record_matches)
    sub.add_parser("expected-results").set_defaults(run=expected_results)
    t = sub.add_parser("tests-ran")
    t.add_argument("results_dir")
    t.add_argument("expected", type=int)
    t.set_defaults(run=tests_ran)
    n = sub.add_parser("named-tests")
    n.add_argument("results_dir")
    n.add_argument("--map", required=True)
    n.set_defaults(run=named_tests)
    sub.add_parser("rails").set_defaults(run=rails)
    args = parser.parse_args(argv)
    return args.run(args)


if __name__ == "__main__":
    sys.exit(main())
