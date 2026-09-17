#!/usr/bin/env python3
"""The bounded assignment for one map entry: everything an agent needs, and nothing else.

    tools/entry-packet.py <entry-id> [--out DIR] [--package-map PATH] [--stdout]

Emitted by rules-factory as a managed file (decision 0029). `AGENTS.md` is the contract this
serves; read that first.

**Why a packet rather than "read the repository".** An agent that starts by searching a corpus and
a map for what a rule means re-does the mapping, badly, every time -- and its reading, not the
published map, ends up in the engine. The map is the interface (rules-factory decision 0001), so
the assignment is one entry of it, assembled mechanically: the entry as published and merged with
this engine's overlay, its citation and the evidence verbatim, what it depends on and what those
entries are, what enables or suspends it, where its cross-references land, the owner's rulings
that apply to it, the handler the generated code declares once the entry is `implemented` -- the
one the work has to produce, not the one on disk while it is still `mapped` -- and the obligations
the gate will hold the work to.

**What this deliberately does not do.** It does not read the corpus, quote more of it than the map
quotes, summarise, paraphrase or rank anything. Every line below is the map's own bytes or a fact
computed from them, so a packet cannot introduce a reading of its own -- which is the failure it
exists to prevent, not a limitation of the implementation.

Where the packet and the corpus appear to disagree, that is an upstream map defect: report it
(`AGENTS.md`), and do not make the engine disagree with the published map.

**Ephemeral.** A packet is written outside the repository and never committed: it is derived from
the map, so committing it would create a second copy of the interface that can go stale. The
default location is `$RULES_ENGINE_PACKET_ROOT` or a directory beside the system temporary one;
a `--out` inside the repository is refused.

The map itself is a NuGet package this engine references and never copies (decision 0015), so the
merge needs the restored package. `--package-map` names it; without one, this asks MSBuild where
the restore put it, exactly as `scripts/validate.sh` does -- which needs the SDK and a restore.

Standard library only, plus the factory's own generator vendored under `scripts/factory/`, so the
entry, the handler signature and the packet cannot drift from what the build actually generates.
"""
import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import types

# model_for() imports the vendored scripts/factory modules, and an imported module leaves its
# bytecode behind: scripts/factory/__pycache__/, a path no ownership row covers, so the checkout
# that ran this goes dirty and tools/dispatch-agent.sh refuses to open a worktree for the next
# issue (#194). scripts/validate.sh and `factory verify` export PYTHONDONTWRITEBYTECODE for the
# same reason, but nothing exports it in the shell an agent runs this from. The loader reads this
# flag when the import happens, so it belongs here and not beside the import it disarms.
sys.dont_write_bytecode = True

ROOT = pathlib.Path(__file__).resolve().parents[1]
OVERLAY = "corpus-map.overlay.json"
PROVENANCE = "provenance.json"
PACKET_ROOT_VARIABLE = "RULES_ENGINE_PACKET_ROOT"


class Refused(Exception):
    """Something the packet cannot honestly assemble. Nothing is written."""


def read_json(path, what):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        raise Refused(f"{what} is missing: {path}")
    except (OSError, ValueError) as error:
        raise Refused(f"{what} cannot be read ({path}): {error}")


def engine():
    """(name, map id, map version, map nupkg sha256, randomness) from the engine's provenance."""
    record = read_json(ROOT / PROVENANCE, "provenance.json")
    try:
        return (record["engine"]["name"], record["map"]["packageId"], record["map"]["version"],
                record["map"].get("nupkgSha256", ""), record.get("randomness"))
    except (KeyError, TypeError):
        raise Refused(f"{PROVENANCE} does not name this engine and its map; run `factory produce` again")


def package_map_from_msbuild(name):
    """Where the restore put the map package's map, asked of MSBuild rather than guessed.

    The same question `scripts/validate.sh` asks, and for the same reason: the global packages
    folder is NuGet's business, and an engine that guesses at it is wrong on someone's machine.
    """
    project = ROOT / "src" / name / f"{name}.csproj"
    if not project.is_file():
        raise Refused(f"no project at {project}; pass --package-map")
    try:
        frameworks = (ROOT / "Directory.Build.props").read_text(encoding="utf-8")
        framework = frameworks.split("<TargetFrameworks>")[1].split("<")[0].split(";")[0]
    except (OSError, IndexError):
        raise Refused("cannot read the target framework from Directory.Build.props; pass --package-map")
    try:
        done = subprocess.run(["dotnet", "msbuild", str(project), "-getItem:RulesFactoryMap",
                               f"-p:TargetFramework={framework}"],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=300)
    except (OSError, subprocess.SubprocessError) as error:
        raise Refused(f"cannot ask MSBuild where the map package is ({error}). Pass --package-map, or "
                      f"restore first: dotnet restore")
    if done.returncode != 0:
        raise Refused(f"MSBuild could not answer where the map package is. Restore first "
                      f"(`dotnet restore`), or pass --package-map.\n{done.stderr.strip()}")
    try:
        items = json.loads(done.stdout)["Items"]["RulesFactoryMap"]
        (item,) = items
        path = item["FullPath"]
    except (ValueError, KeyError, TypeError):
        raise Refused("MSBuild returned no single RulesFactoryMap item; restore first, or pass --package-map")
    return path


def model_for(package_map_path, name, package_id, version, randomness):
    """The factory's own model of merge(package map, overlay), from the generator this engine vendors."""
    sys.path.insert(0, str(ROOT / "scripts" / "factory"))
    try:
        import generate  # noqa: E402  (the factory's generator, vendored by produce)
        import rulings  # noqa: E402  (the owner's rulings the overlay holds, decision 0027)
    except ImportError as error:
        raise Refused(f"scripts/factory is not importable ({error}); run `factory produce` again")
    package = read_json(package_map_path, "the map package's map")
    overlay_path = ROOT / OVERLAY
    overlay = read_json(overlay_path, "the overlay") if overlay_path.is_file() else {}
    try:
        merged = generate.merge(package, overlay, root=str(ROOT))
        model = generate.Model(types.SimpleNamespace(package_id=package_id, version=version, randomness=randomness),
                               merged, name, rulings.collect(overlay))
    except generate.GenerationError as error:
        raise Refused(f"the map and this engine's overlay do not merge: {error}")
    return generate, model, overlay


def block(value):
    """A JSON value as a fenced block: the map's bytes, not a rendering of them."""
    return "```json\n" + json.dumps(value, indent=2, ensure_ascii=False) + "\n```"


def fence(text):
    """A string the corpus wrote, in a fence, exactly as the map holds it.

    Not `block`: JSON-quoting the corpus's own sentence escapes its quotation marks and turns the
    wording an implementer has to read into something they have to decode first. The map's backlog
    items render evidence this way for the same reason. The fence is opened with as many backticks
    as it takes to contain what is inside it.
    """
    ticks = "`" * max(3, max((len(run) for run in re.findall(r"`+", text)), default=0) + 1)
    return f"{ticks}text\n{text}\n{ticks}"


def entry_line(model, entry_id):
    """`<id> -- <name> (<status>)` for an entry of the map, or a note that the map has no such entry."""
    item = model.by_id.get(entry_id)
    if item is None:
        return f"`{entry_id}` — **not an entry of this map**"
    entry = item["entry"]
    return f"`{entry_id}` — {entry.get('name', '(unnamed)')} (status: {entry.get('status', 'unstated')})"


def locators(generate, model, item):
    """Every located entry this one rests on, as (entry id, locator), in the model's own order.

    A derived entry (decision 0012) cites nothing of its own: its sources' citations are its
    citation, and they entail the fact together, so all of them are here rather than the first.
    """
    del generate
    out = []
    for member in item["locators"]:
        located = next(i for i in model.entries if i["member"] == member)
        out.append((located["entry"]["id"], model.locator_of(member)))
    return out


def as_implemented(generate, model, item):
    """This entry as the generator will see it once the overlay says `implemented` (#204).

    §7 describes the work, and the work changes the declaration: `status` decides both the
    correspondence row (`first_row`) and, through it, whether the handler is the required partial
    or the optional hook. So the status is moved and the generator is asked again, rather than the
    packet restating either rule -- the packet's whole claim is that it computes from the map with
    the factory's own generator, and a second copy of that rule here would be the first line of it
    that could drift from what the build emits.
    """
    entry = {**item["entry"], "status": "implemented"}
    entries = {entry_id: other["entry"] for entry_id, other in model.by_id.items()}
    entries[entry["id"]] = entry
    return {**item, "entry": entry, "row": generate.first_row(entry, entries)}


def handler(generate, model, item):
    """The handler this entry will declare once it is implemented -- not the one declared today.

    While the entry is `mapped`, `Contracts.g.cs` declares the optional hook, and the regeneration
    that follows marking it `implemented` replaces that with the required partial. Rendering the
    file as it stands hands the implementer a signature that is right about the present and wrong
    about the assignment, which costs one rewrite of the handler file (#204).

    Returns the signature, what obliges it, and whether it is not what the file holds today -- an
    entry that stays on the optional hook when implemented (correspondence row 8) has the same
    declaration before and after, and saying otherwise would be the same defect the other way up.
    """
    c = generate.contract(model, as_implemented(generate, model, item))
    replaces = c["required"] != generate.contract(model, item)["required"]
    if c["required"]:
        return (f"internal static partial Resolution<{c['output']}> {item['member']}({c['request_cs']} request);",
                "required: the build does not complete without it", replaces)
    return (f"static partial void {item['member']}({c['request_cs']} request, ref Resolution<{c['output']}>? resolution);",
            "optional even then: its correspondence row answers by default, and this hook overrides that "
            "answer or leaves it", replaces)


def packet(generate, model, overlay, item, identity):
    name, package_id, version, nupkg = identity
    entry = item["entry"]
    entry_id = entry["id"]
    lines = [f"# Entry packet: `{entry_id}`\n",
             f"**{entry.get('name', '(unnamed)')}** — engine `{name}`, map `{package_id}` {version}",
             f"(`sha256:{nupkg[:16]}…`). Assembled by `tools/entry-packet.py` from the merge of that",
             "package and this engine's overlay. Every line below is the map's own bytes or a fact computed",
             "from them: nothing here is a reading of the corpus, and neither is your implementation.\n",
             "## 1. The entry, as the engine sees it\n",
             block(entry), ""]

    lines.append("## 2. Where it comes from\n")
    cited = locators(generate, model, item)
    if not cited:
        lines.append("This entry cites nothing: the map records no locator for it, and it derives from nothing.\n")
    for cited_id, locator in cited:
        held = " (its own passage)" if cited_id == entry_id else f" (through `derivedFrom`, from `{cited_id}`)"
        lines.append(f"**Locator**{held}:\n\n{block(locator)}\n")
    evidence = entry.get("evidence")
    if evidence is not None:
        lines.append("**Evidence, verbatim as the map quotes it.** This is the corpus's wording, and the only "
                     "wording you may rely on:\n")
        lines.append(fence(str(evidence)) + "\n")
    else:
        lines.append("The map quotes no evidence for this entry. That is a fact about the entry, not a gap for "
                     "you to fill from the corpus.\n")

    ambiguity = entry.get("ambiguity")
    if isinstance(ambiguity, dict):
        lines.append("**The question the map records as unsettled** — `fate` "
                     f"`{ambiguity.get('fate')}`"
                     + (f", `unresolvedReason` `{ambiguity['unresolvedReason']}`"
                        if ambiguity.get("unresolvedReason") else "") + ":\n")
        lines.append(fence(str(ambiguity.get("question", ""))) + "\n")
        lines.append("An entry whose question is unresolved is implemented as a decline that names why and cites "
                     "where. Answering it is not yours to do (`AGENTS.md`).\n")

    lines.append("## 3. What this engine records about it\n")
    row = overlay.get(entry_id)
    lines.append(f"Overlay row (`{OVERLAY}`, the three fields the engine owns under decision 0015):\n")
    lines.append(block(row) if row is not None else "This entry has no overlay row yet. Adding one is part of the "
                                                   "work: `status`, `implementedIn` and `tests`.")
    lines.append(f"\nCorrespondence row: {item['row'] if item['row'] else 'none (not plainly computable)'}\n")

    lines.append("## 4. Dependencies and reachability\n")
    depends = entry.get("dependsOn") or []
    lines.append("**`dependsOn`** — these order the work; an entry is built after what it depends on:\n"
                 if depends else "**`dependsOn`**: none.\n")
    for other in depends:
        lines.append(f"- {entry_line(model, other)}")
    for field, meaning in (("enabledBy", "this entry applies only where these hold"),
                           ("suspendedBy", "these suspend it")):
        values = entry.get(field) or []
        lines.append(f"\n**`{field}`** — {meaning}; reachability orders nothing:\n"
                     if values else f"\n**`{field}`**: none.\n")
        for other in values:
            lines.append(f"- {entry_line(model, other)}")

    lines.append("\n## 5. Cross-references\n")
    references = entry.get("crossReferences") or []
    if not references:
        lines.append("None. (A derived entry never has any.)\n")
    for reference in references:
        cites = json.dumps(reference.get("cites", ""), ensure_ascii=False)
        if reference.get("resolvedBy"):
            lines.append(f"- {cites} → resolved by {entry_line(model, reference['resolvedBy'])}")
        else:
            reason = json.dumps(reference.get("reason", ""), ensure_ascii=False)
            lines.append(f"- {cites} → **unmapped**: {reason}")

    lines.append("\n## 6. The owner's rulings that apply\n")
    applicable = [ruling for ruling in model.rulings if ruling.get("entry") == entry_id]
    if not applicable:
        lines.append("None. Where the corpus does not settle this entry, the engine declines; it does not "
                     "decide (decision 0027, and `AGENTS.md`).\n")
    for ruling in applicable:
        lines.append(block(ruling) + "\n")

    signature, obligation, replaces = handler(generate, model, item)
    lines.append("## 7. The handler you implement\n")
    lines.append(f"What `src/{name}/Generated/Contracts.g.cs` declares for this entry once it is `implemented` — "
                 f"{obligation}:\n")
    lines.append(f"```csharp\n{signature}\n```\n")
    if replaces:
        lines.append(f"That file holds a different declaration **today**: this entry is `{entry.get('status')}`, so "
                     "the generator has emitted the optional hook, and the re-produce that follows marking it "
                     "`implemented` replaces that with the signature above. Write the signature above; do not copy "
                     "the one currently in the file.\n")
    lines.append(f"The request type is `{generate.contract(model, item)['request']}` in "
                 f"`src/{name}/Generated/Requests.g.cs`. It is partial: declare the entry's inputs as `init` "
                 f"properties in a file of your own. Do not edit anything under `Generated/`.\n")

    lines.append("## 8. What the gate will ask of you\n")
    lines.append(f"- Every test you write is named in this entry's `tests`, in `{OVERLAY}`, with the mutation that "
                 "makes it fail — and you must have watched it fail. A test nobody has watched fail is not yet a "
                 "test.\n"
                 "- The whole gate, not a narrower command: `./scripts/validate.sh full`.\n"
                 "- The implementation cites this entry and its locator, and a decline names why and where.\n"
                 "- Nothing under `Generated/`, `corpus/` or `provenance.json` is edited by hand.\n"
                 "- The change closes exactly the one issue it names, and nothing else.\n")
    lines.append("## 9. If the map is wrong\n")
    lines.append("Stop. Report an upstream map defect on the issue — the entry id, the locator, what the map says "
                 "and what the corpus says — and do not implement around it. A map is corrected by a new, checked, "
                 "published map version, and this engine is then re-produced from it (`AGENTS.md`).\n")
    return "\n".join(lines)


def destination(out, entry_id):
    if out is None:
        root = os.environ.get(PACKET_ROOT_VARIABLE) or os.path.join(tempfile.gettempdir(), "rules-engine-packets")
        out = os.path.join(root, ROOT.name)
    resolved = pathlib.Path(out).expanduser().resolve()
    if resolved == ROOT or ROOT in resolved.parents:
        raise Refused(f"a packet is never written inside the repository ({resolved}). It is derived from the map, "
                      f"and a committed copy of the interface goes stale. Use --out elsewhere, or "
                      f"${PACKET_ROOT_VARIABLE}.")
    return resolved / f"entry-{entry_id}.md"


def main(argv=None):
    parser = argparse.ArgumentParser(prog="entry-packet.py", description=__doc__.split("\n")[0])
    parser.add_argument("entry", help="the map entry id to assemble a packet for")
    parser.add_argument("--out", help=f"directory to write into (default: ${PACKET_ROOT_VARIABLE}, "
                                      f"else a directory beside the system temporary one)")
    parser.add_argument("--package-map", help="the restored map package's corpus-map.json (default: ask MSBuild)")
    parser.add_argument("--stdout", action="store_true", help="write the packet to stdout and no file")
    args = parser.parse_args(argv)

    try:
        name, package_id, version, nupkg, randomness = engine()
        package_map = args.package_map or package_map_from_msbuild(name)
        generate, model, overlay = model_for(package_map, name, package_id, version, randomness)
        item = model.by_id.get(args.entry)
        if item is None:
            near = [entry_id for entry_id in model.by_id if args.entry.lower() in entry_id.lower()]
            raise Refused(f"the map has no entry {args.entry!r}"
                          + (f". Did you mean: {', '.join(sorted(near)[:5])}?" if near else
                             f" (the map has {len(model.by_id)} entries)"))
        text = packet(generate, model, overlay, item, (name, package_id, version, nupkg))
        if args.stdout:
            sys.stdout.write(text)
            return 0
        target = destination(args.out, args.entry)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    except Refused as error:
        print(f"entry-packet: REFUSED -- {error}", file=sys.stderr)
        return 1
    print(target)
    return 0


if __name__ == "__main__":
    sys.exit(main())
