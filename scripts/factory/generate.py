"""M2 of #3: scaffold a .NET engine and generate the `*.g.cs` files that tie it to its map.

Three kinds of output, one per ownership class (ownership.py holds the table, decision 0018):

  * **Managed** -- global.json, NuGet.config and Directory.Build.props (`managed_files`): the
    factory's build policy. Rewritten when the recipe version moves and the engine has not
    edited them; a hand edit is refused unless `--adopt` or `--reset` settles it.
  * **Engine-owned** -- Directory.Packages.props, the solution, both project files and an
    empty `corpus-map.overlay.json` (`engine_owned`). Written only when absent: after the first
    `produce` they belong to the engine, and a second `produce` must not undo an edit to them
    (above all to the overlay, which is the engine's own file, 0015).
    Neither managed nor engine-owned files may say anything the factory's inputs decide. A
    re-run with a different map version would leave such a file naming the old one while the
    code and provenance.json named the new (#66).
  * **Generated** -- every file named `*.g.*`: the `*.g.cs` under `Generated/`, and
    `RulesFactory.Packages.g.props` in the engine root. Rewritten on every `produce`, from the
    package map merged with the engine's overlay, and never edited by hand; provenance.json
    hashes each one. Hand-written code lives in any other file and is never touched.

`RulesFactory.Packages.g.props` holds what MSBuild reads that the inputs decide: the exact
version pins of RulesKernel and the map package, and the map's PackageReference (conditioned
on the engine project, so the test project does not take it). When the corpus declares
`randomness: seeded` (decision 0019) it also pins RulesKernel.Randomness at the kernel's version,
RulesKernel.Analyzers always,
and references nothing: whether and where to draw is the engine's to write, and the pin only
means that when it does, the version is the kernel's. Under `none` there is no pin. Directory.Packages.props imports
it, and keeps only the central-package-management switches and the test packages, which an
engine may bump on its own. Because the pins now have one home, `produce` refuses, before
writing anything, an engine whose own MSBuild files pin the kernel or the map again, reference a
map package themselves, or whose Directory.Packages.props does not import the generated file.

global.json's SDK version is the kernel's toolchain and is managed, not generated: the SDK is
not a package the build restores, and an engine that must move it adopts the file.

The corpus is copied to `corpus/` on every run; intake has already proved its bytes, and that its
licence permits committing them (decision 0028).

What the generated code states:

  * `MapEntries.g.cs` -- one static per map entry, its citation verbatim, and the baseline. A
    derived entry (0012) has no citation of its own; its `Locators` are every citation it
    rests on (see `Model._leaf_locators` for which, and in what order). An assertion's static
    also carries `AssertedBy`, the map's `assertedBy` (decision 0025), as an init property so the
    records' constructors do not change; `draws` is not generated, because its `count` is prose;
  * `Registry.g.cs` -- every entry registered with the correspondence row it matches first
    (docs/corpus-map.md, "The map and the engine agree"), and a default handler per row:
      1 `scope: out`                                  -> OutsideCurrentScope
      2 `status: mapped` or `blocked`                 -> UnsupportedRule (#47: refuse until proven)
      3 `definedElsewhere`, 4 `beyondAdapter`,
      5 an operation on an unimplemented value        -> MissingRulesData
      6 `ambiguity.fate: unresolved`                  -> RequiresInterpretation
      8 `kind: assertion`                             -> no decline: the value is demanded of the caller
      no row (a built, clear rule)                    -> nothing; a hand-written handler must answer.
    Row 7 is a fact about pairs of entries and has no single-entry handler.
    A hand-written handler (the typed partial method below, or an `[Implements("entry-id")]`
    method) replaces the default -- **only for an entry whose merged status is `implemented`**.
    A `mapped` entry declines even when its code exists (corpus-map.md, `status`), so the
    override is ignored until the overlay says so;
  * `Contracts.g.cs` and `Requests.g.cs` -- the typed contract over that registry (#76), below;
  * `Rulings.g.cs` -- only when the overlay holds an owner's ruling (decision 0027, rulings.py):
    `OwnerRuling` and `OwnerRulings`, one static per ruling and `All`, from the overlay's id, entry,
    span, answer, ruledBy, ruledOn and record, so an engine surfaces a ruling without restating
    it. Both are partial. The merge refuses a ruling that breaks 0027 before anything is written,
    and a produce with no rulings removes the file;
  * `CorrespondenceTests.g.cs` -- every entry is registered, in map order; every entry that
    is not `implemented` declines with its row's reason and its own locator, through the
    dictionary dispatch and through its typed entry point alike, and registers every locator it
    cites (all of a derived entry's premises); every `implemented` entry has a hand-written
    handler unless its row's default can serve.

The typed contract (#76). The registry dispatches on a string id and a `RuleRequest` that is a
dictionary of assertion values, and it stays: it is the one mechanism every entry shares, and the
correspondence tests read it. Over it, each entry gets

  * a request type of its own, `{Engine}.Requests.{Member}Request`, and a typed entry point,
    `EntryPoints.{Member}`, a `RuleEntry<{Member}Request, TOutput>`. Handing one entry's request to
    another entry does not compile. (`EntryPoints`, not `Rules`: an engine's hand-written code
    commonly lives in a `{Engine}.Rules` namespace, which a class of that name would collide with).
    The request type is `sealed partial` (#93): the map names no inputs, so an engine declares an
    entry's inputs itself, as `init` properties in a file of its own, and a caller sets them in an
    object initializer (`new {Member}Request { Position = p }`). The entry point hands that very
    object to the handler (`Registry.Resolve(IEntryRequest)`); only the dictionary dispatch,
    `Registry.Resolve(id, RuleRequest)`, builds one from the assertions, with every input at its
    default. The generated members are the constructors `()` and `(RuleRequest)`, `Empty`,
    `Asserting` on an assertion, `EntryId` and `Assertions`; since the generated code constructs
    requests, an engine's input may not be a C# `required` member;
  * a handler declaration, a partial method of `Handlers`, whose implementation is the
    hand-written code. For an entry whose merged status is `implemented` and whose row is not 8
    (the entries a correspondence test already requires a handler for) it is an extended partial
    method, `internal static partial Resolution<TOutput> {Member}({Member}Request request)`, so a
    missing implementation is CS8795 and one with another return type CS8817 or parameter
    CS0759: build errors, and the engine builds with warnings as errors, so a nullability
    mismatch (CS8826 and kin) is one too. Every other entry gets an optional hook,
    `static partial void {Member}({Member}Request request, ref Resolution<TOutput>? resolution)`,
    which may stay unimplemented and, when implemented with the wrong signature, is CS0759. An
    entry moving to `implemented` turns its hook into the required form, and the build names the
    handler to change.

What the types are is decided in one place, `contract()`, and the rule is: **a type comes from
the map where the map declares one, and is `object` where it does not.** Today the map declares
none. No field of an entry names an input, an output, a unit or a value type (docs/corpus-map.md,
"Fields"), and that is deliberate: *a parameter is not a rule, so it gets no entry at all*, and
`dependsOn` is explicitly not a runtime input. So what the generator can type is what the map does
say. Which entry a request belongs to is always known, and becomes the request's nominal type. A
`kind: assertion` entry is resolved from the caller's value for it (row 8), so its request has an
`Asserting(value)` constructor. The value and every output are `object`, because nothing in the
map says otherwise. A map field that did declare a type would change `contract()` and nothing
else.

Why partial methods rather than a Roslyn analyzer or source generator. An analyzer could check
`[Implements]` methods where they stand, but it is a compiled netstandard2.0 assembly referencing
Microsoft.CodeAnalysis: the factory writes source and runs no compiler, so the analyzer would have
to be a package of its own, versioned and restored and locked alongside the kernel, pinned to a
Roslyn the engine's SDK may not load, and its diagnostics would be the factory's code running
inside every engine build. A generated partial declaration costs nothing of that: it is ordinary
C# the regeneration gate already compares byte for byte, and the C# compiler itself refuses a
missing or mis-typed handler.

`[Implements]` is kept, and is the migrating part. Reflection still discovers it, as the runtime
cross-check it was: it names a map entry, has the untyped signature, and appears once, and now
also that the same entry has no typed handler as well. It can still answer an entry whose handler
is optional. An engine whose `implemented` entry was answered only by an `[Implements]` method no
longer builds until the required partial method exists (it may simply call the old method).

Deterministic: the output depends only on the package map (its id and version included), the
overlay, the corpus, the engine name and the factory's own pins. No timestamps, no machine
paths, no dictionary-order accidents.
"""
import json
import os
import re

import ownership
import rulings as rulings_step

KERNEL_VERSION = "0.3.0"
# The SDK rules-kernel pins (its global.json), so a produced engine builds with the kernel's
# toolchain. This is the kernel's pin, not this machine's: never substitute a local SDK here.
SDK_VERSION = "10.0.112"
TEST_PACKAGES = (
    ("Microsoft.NET.Test.Sdk", "17.11.1"),
    ("xunit", "2.9.2"),
    ("xunit.runner.visualstudio", "2.8.2"),
)
OVERLAY_NAME = "corpus-map.overlay.json"
PACKAGES_PROPS = "RulesFactory.Packages.g.props"
# Decision 0019: the corpus's `randomness`, carried from its manifest by intake.
RANDOMNESS_PACKAGE = "RulesKernel.Randomness"
# The kernel's compile-time determinism diagnostics (RK0001-RK0005, RK0007), pinned at the kernel's
# version like everything else the kernel ships. Referenced by the engine project alone, the way the
# map package is: a build asset, never a reference, and never part of the test project's graph.
ANALYZERS_PACKAGE = "RulesKernel.Analyzers"
RANDOMNESS = ("none", "seeded")
OWNED = ("status", "implementedIn", "tests")

ROWS = {
    1: ("ScopeOut", "OutsideCurrentScope"),
    2: ("NotBuilt", "UnsupportedRule"),
    3: ("DefinedElsewhere", "MissingRulesData"),
    4: ("BeyondAdapter", "MissingRulesData"),
    5: ("ValueDependencyUnimplemented", "MissingRulesData"),
    6: ("UnresolvedAmbiguity", "RequiresInterpretation"),
    8: ("Assertion", None),
}
STATUSES = {"mapped": "Mapped", "blocked": "Blocked", "implemented": "Implemented", "declined": "Declined"}
# Names an entry's member may not take: members of MapEntries, EntryPoints and Handlers, the classes
# themselves (a member may not share its class's name), and the Requests namespace the
# generated code qualifies.
RESERVED_MEMBERS = {"SourceId", "Baseline", "Entry", "Derived", "Equals", "ReferenceEquals", "GetHashCode", "ToString",
                    "MapEntries", "EntryPoints", "Handlers", "Requests", "Dispatch", "Has", "Hooked"}


class GenerationError(Exception):
    """The map cannot be turned into an engine as it stands."""


# --- the overlay ---------------------------------------------------------------------------


def merge(document, overlay, root=None):
    """merge(package, overlay) per 0015 rules 1-4; refuses on rules 1 and 2, and on an owner's ruling
    or a decline that breaks decision 0027 (rulings.py; `root`, the engine directory, lets it check
    that each ruling's decision record is a file). A ruling never reaches the merge: the map is data."""
    if not isinstance(overlay, dict):
        raise GenerationError(f"{OVERLAY_NAME} is not an object of entry id -> {', '.join(OWNED)}")
    ids = [e.get("id") for e in document.get("entries") or []]
    for entry_id, item in overlay.items():
        if entry_id not in ids:
            raise GenerationError(f"{OVERLAY_NAME} names {entry_id!r}, which the package map has no entry for")
        if not isinstance(item, dict) or "status" not in item:
            raise GenerationError(f"{OVERLAY_NAME} item {entry_id!r} does not set status")
        extra = sorted(set(item) - set(OWNED) - set(rulings_step.KEYS))
        if extra:
            raise GenerationError(f"{OVERLAY_NAME} item {entry_id!r} sets {extra}; an engine owns only {', '.join(OWNED)}, "
                                  f"and keeps its owner's {' and '.join(rulings_step.KEYS)} beside them (0027)")
    problems = rulings_step.problems(document, overlay, root)
    if problems:
        raise GenerationError(f"{OVERLAY_NAME} breaks decision 0027: " + "; ".join(problems))
    merged = dict(document)
    entries = []
    for entry in document.get("entries") or []:
        item = overlay.get(entry.get("id"))
        if item is None:
            entries.append(entry)
        else:
            base = {k: v for k, v in entry.items() if k not in OWNED}
            base.update({k: item[k] for k in OWNED if k in item})
            entries.append(base)
    merged["entries"] = entries
    return merged


# --- the correspondence table --------------------------------------------------------------


def first_row(entry, by_id):
    """The first correspondence row the entry matches, in table order; None when it matches none."""
    if entry.get("scope") == "out":
        return 1
    if entry.get("status") in ("mapped", "blocked"):
        return 2
    if "definedElsewhere" in entry:
        return 3
    if "beyondAdapter" in entry:
        return 4
    if entry.get("kind") == "operation":
        for dep in entry.get("dependsOn") or []:
            target = by_id.get(dep)
            if isinstance(target, dict) and target.get("kind") == "value" and target.get("status") != "implemented":
                return 5
    ambiguity = entry.get("ambiguity")
    if isinstance(ambiguity, dict) and ambiguity.get("fate") == "unresolved":
        return 6
    if entry.get("kind") == "assertion":
        return 8
    return None


# --- C# text -------------------------------------------------------------------------------


def cs_string(text):
    out = ['"']
    for ch in text:
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        elif ord(ch) < 0x20 or ch in "\u2028\u2029":
            out.append(f"\\u{ord(ch):04x}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def xml_text(text):
    return " ".join(str(text).split()).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def pascal(entry_id):
    parts = [p for p in re.split(r"[^A-Za-z0-9]+", entry_id) if p]
    name = "".join(p[0].upper() + p[1:] for p in parts)
    if not name or not name[0].isalpha():
        name = "Entry" + name
    if name in RESERVED_MEMBERS:
        name += "Entry"
    return name


def snake(entry_id):
    name = re.sub(r"[^A-Za-z0-9]+", "_", entry_id).strip("_")
    return name if name[:1].isalpha() else "Entry_" + name


HEADER = ("// <auto-generated>\n"
          "//   Generated by rules-factory tools/factory from {package} {version}.\n"
          "//   Every *.g.cs file is rewritten by `factory produce`; edit hand-written files instead.\n"
          "// </auto-generated>\n"
          "#nullable enable\n\n")


class Model:
    """The merged map, in the shape the templates read."""

    def __init__(self, intake, merged, name, rulings=()):
        self.name = name
        # The owner's rulings (0027), from the overlay (rulings.collect): never in `merged`, the map.
        self.rulings = list(rulings)
        self.package_id = intake.package_id
        self.version = intake.version
        self.header = HEADER.format(package=intake.package_id, version=intake.version)
        self.source_id = merged["corpus"]
        self.randomness = getattr(intake, "randomness", None)
        self.baseline = merged["baseline"]
        entries = merged.get("entries") or []
        by_id = {e["id"]: e for e in entries}
        members = {}
        self.entries = []
        for entry in entries:
            member = pascal(entry["id"])
            if member in members:
                raise GenerationError(f"entries {members[member]!r} and {entry['id']!r} both name the C# member {member}")
            members[member] = entry["id"]
            self.entries.append({"entry": entry, "member": member, "row": first_row(entry, by_id)})
        self.by_id = {item["entry"]["id"]: item for item in self.entries}
        ruling_members = {}
        for ruling in self.rulings:
            member = pascal(ruling["id"])
            if member in ("All", "OwnerRulings"):
                member += "Ruling"
            if member in ruling_members:
                raise GenerationError(f"rulings {ruling_members[member]!r} and {ruling['id']!r} both name the C# member "
                                      f"OwnerRulings.{member}")
            ruling_members[member] = ruling["id"]
            ruling["member"] = member
        for item in self.entries:
            item["locators"] = self._leaf_locators(item, frozenset())

    def _leaf_locators(self, item, seen):
        """Every located entry whose passage `item` rests on, as the located entries' members.

        A located entry cites itself. A derived one (0012) has no passage: method.md makes its
        sources' citations its citation, and the sources are premises that entail the fact
        *together*, so citing only the first would say less at runtime than the map knows (#73).
        So the set is every leaf reached through `derivedFrom`, following derived sources down
        to located ones.

        The order is depth-first, in each entry's `derivedFrom` order, and a locator reached a
        second time (two premises sharing one) keeps its first place. That makes the order a
        function of the map alone, and makes the first locator exactly the one the decline
        path cited before (the first leaf of the first source), so a decline's single kernel
        `Locator`, which the registry takes as the first of these, is unchanged.

        check-map.py refuses cycles and dangling sources before a map is packaged; they are
        refused here too, because the generator must not loop or emit a reference to nothing
        if handed a map that skipped the check.
        """
        entry = item["entry"]
        if isinstance(entry.get("locator"), dict):
            return [item["member"]]
        if entry["id"] in seen:
            raise GenerationError(f"derived entry {entry['id']!r} is derived, through a cycle, from itself")
        sources = entry.get("derivedFrom") or []
        if not sources:
            raise GenerationError(f"entry {entry['id']!r} has no locator and no derivedFrom to cite")
        found = []
        for source in sources:
            if source not in self.by_id:
                raise GenerationError(f"derived entry {entry['id']!r} is derived from {source!r}, which the map has no entry for")
            for member in self._leaf_locators(self.by_id[source], seen | {entry["id"]}):
                if member not in found:
                    found.append(member)
        return found

    def locator_of(self, member):
        """The map's locator object for the located entry whose C# member is `member`."""
        for other in self.entries:
            if other["member"] == member and self.located(other):
                return other["entry"]["locator"]
        raise GenerationError(f"no located entry {member}")

    def located(self, item):
        return isinstance(item["entry"].get("locator"), dict)


def contract(model, item):
    """The typed contract of one entry: its request type, output type and handler form.

    The one place a type is decided (see the module docstring): from the map where it declares
    one, `object` where it does not, and today it declares none. The request type is nominal, one
    per entry, because which entry is being resolved is the one thing always known; it carries an
    `Asserting` constructor on a `kind: assertion` entry, whose value is what row 8 resolves to.

    `required` is the handler a correspondence test already demands: an `implemented` entry not
    on row 8. It becomes a partial method the build cannot complete without; every other entry
    gets an optional hook.
    """
    entry = item["entry"]
    return {
        "request": f"{item['member']}Request",
        "request_cs": f"global::{model.name}.Requests.{item['member']}Request",
        "output": "object",
        "asserts": entry.get("kind") == "assertion",
        "required": entry.get("status") == "implemented" and item["row"] != 8,
    }


ASSERTED_BY_MEMBER = (
    "    /// <summary>\n"
    "    /// Who the corpus lets assert this entry, the map's <c>assertedBy</c> (rules-factory decision 0025): the\n"
    "    /// corpus's own words, or <c>caller</c> where the corpus names nobody. Empty on an entry that is not\n"
    "    /// <c>kind: assertion</c>. An engine checks an assertion's attribution against these, not its own reading.\n"
    "    /// </summary>\n"
    "    public ImmutableArray<string> AssertedBy { get; init; } = [];\n\n")


def asserted_by_init(entry):
    """The object initializer carrying `assertedBy` (0025), or nothing on an entry without one.

    An init property rather than a positional parameter, so the records' constructors and
    deconstructors, which an engine's own code may call, do not change.
    """
    names = entry.get("assertedBy")
    if not isinstance(names, list) or not names:
        return ""
    return f" {{ AssertedBy = [{', '.join(cs_string(name) for name in names)}] }}"


def locator_cs(locator):
    return f"new SourceLocator({cs_string(locator['sourceId'])}, {cs_string(locator['citation'])})"


def map_entries_cs(model):
    b = model.baseline
    as_of = b.get("asOf")
    if as_of:
        year, month, day = (int(part) for part in as_of.split("-"))
        as_of_cs = f"new DateOnly({year}, {month}, {day})"
    else:
        as_of_cs = "null"
    lines = [model.header,
             "using System.Collections.Immutable;\n",
             "using RulesKernel.Identity;\n",
             "using RulesKernel.Provenance;\n\n",
             f"namespace {model.name};\n\n",
             "/// <summary>One located entry of the map: its id, its name and its citation, verbatim.</summary>\n",
             "/// <param name=\"Id\">The map entry's stable slug.</param>\n",
             "/// <param name=\"Name\">The entry's name, as the map records it.</param>\n",
             "/// <param name=\"Locator\">Corpus id plus citation, as the map records it.</param>\n",
             "public sealed record MapEntry(string Id, string Name, SourceLocator Locator)\n{\n",
             ASSERTED_BY_MEMBER,
             "    /// <inheritdoc/>\n",
             "    public override string ToString() => $\"{Id} [{Locator}]\";\n}\n\n",
             "/// <summary>A derived entry (rules-factory decision 0012): a fact the corpus entails and never states.</summary>\n",
             "/// <param name=\"Id\">The map entry's stable slug.</param>\n",
             "/// <param name=\"Name\">The entry's name, as the map records it.</param>\n",
             "/// <param name=\"DerivedFrom\">The entry ids it is derived from, in the map's order.</param>\n",
             "/// <param name=\"Locators\">\n",
             "/// Its citation: the locator of every located entry it rests on, following derived sources down to\n",
             "/// located ones, depth-first in <paramref name=\"DerivedFrom\"/> order, each locator once, at its first place.\n",
             "/// </param>\n",
             "public sealed record DerivedMapEntry(string Id, string Name, ImmutableArray<string> DerivedFrom, ImmutableArray<SourceLocator> Locators)\n{\n",
             ASSERTED_BY_MEMBER,
             "    /// <inheritdoc/>\n",
             "    public override string ToString() => $\"{Id} [derived from {string.Join(\", \", DerivedFrom)}]\";\n}\n\n",
             f"/// <summary>The {len(model.entries)} entries of {xml_text(model.package_id)} {xml_text(model.version)}, "
             "one static per entry, citations copied verbatim from the map.</summary>\n",
             "public static class MapEntries\n{\n",
             "    /// <summary>The corpus every entry cites.</summary>\n",
             f"    public const string SourceId = {cs_string(model.source_id)};\n\n",
             "    /// <summary>The corpus baseline the map is true of.</summary>\n",
             "    public static SourceBaselineId Baseline { get; } = new(\n",
             "        sourceId: SourceId,\n",
             f"        contentHash: {cs_string(b['contentHash'])},\n",
             f"        hashDerivation: {cs_string(b['hashDerivation'])},\n",
             f"        asOf: {as_of_cs});\n"]
    for item in model.entries:
        entry = item["entry"]
        lines.append("\n")
        lines.append(f"    /// <summary>{xml_text(entry.get('name', entry['id']))} (<c>{xml_text(entry['id'])}</c>).</summary>\n")
        if model.located(item):
            locator = entry["locator"]
            lines.append(f"    public static MapEntry {item['member']} {{ get; }} = new(\n"
                         f"        {cs_string(entry['id'])},\n"
                         f"        {cs_string(entry.get('name', entry['id']))},\n"
                         f"        {locator_cs(locator)}){asserted_by_init(entry)};\n")
        else:
            sources = ", ".join(cs_string(s) for s in entry.get("derivedFrom") or [])
            # Literals, not references to the located statics: a static initializer runs in
            # textual order, and a premise may come later in the map than what it entails.
            cited = "".join(f"            {locator_cs(model.locator_of(m))},\n" for m in item["locators"])
            lines.append(f"    public static DerivedMapEntry {item['member']} {{ get; }} = new(\n"
                         f"        {cs_string(entry['id'])},\n"
                         f"        {cs_string(entry.get('name', entry['id']))},\n"
                         f"        [{sources}],\n"
                         f"        [\n{cited}        ]){asserted_by_init(entry)};\n")
    lines.append("}\n")
    return "".join(lines)


REGISTRY_SUPPORT = """
/// <summary>Whether the engine has built an entry, as the map merged with the overlay says.</summary>
public enum EntryStatus
{
    /// <summary>Enumerated and classified; not yet worked.</summary>
    Mapped,
    /// <summary>A dependency is unmet.</summary>
    Blocked,
    /// <summary>In the engine, naming the tests that prove it.</summary>
    Implemented,
    /// <summary>No implemented path at all.</summary>
    Declined,
}

/// <summary>The first row of the map-to-runtime correspondence table an entry matches (docs/corpus-map.md).</summary>
public enum CorrespondenceRow
{
    /// <summary>No row: a built, clear rule the engine simply answers.</summary>
    None = 0,
    /// <summary>Row 1, <c>scope: out</c>: OutsideCurrentScope.</summary>
    ScopeOut = 1,
    /// <summary>Row 2, <c>status: mapped</c> or <c>blocked</c>: UnsupportedRule.</summary>
    NotBuilt = 2,
    /// <summary>Row 3, <c>definedElsewhere</c>: MissingRulesData.</summary>
    DefinedElsewhere = 3,
    /// <summary>Row 4, <c>beyondAdapter</c>: MissingRulesData.</summary>
    BeyondAdapter = 4,
    /// <summary>Row 5, an operation whose value dependency is unimplemented: MissingRulesData.</summary>
    ValueDependencyUnimplemented = 5,
    /// <summary>Row 6, <c>ambiguity.fate: unresolved</c>: RequiresInterpretation.</summary>
    UnresolvedAmbiguity = 6,
    /// <summary>Row 8, <c>kind: assertion</c>: nothing; the engine demands the value.</summary>
    Assertion = 8,
}

/// <summary>What a caller supplies to resolve an entry: the values of the assertions it makes (row 8).</summary>
public sealed class RuleRequest
{
    private readonly ImmutableDictionary<string, object> assertions;

    private RuleRequest(ImmutableDictionary<string, object> assertions) => this.assertions = assertions;

    /// <summary>A request asserting nothing.</summary>
    public static RuleRequest Empty { get; } = new(ImmutableDictionary<string, object>.Empty.WithComparers(StringComparer.Ordinal));

    /// <summary>This request, also asserting <paramref name="value"/> for the assertion entry <paramref name="entryId"/>.</summary>
    /// <param name="entryId">The id of a <c>kind: assertion</c> entry.</param>
    /// <param name="value">The caller's value for it.</param>
    /// <returns>A new request.</returns>
    public RuleRequest Assert(string entryId, object value)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(entryId);
        ArgumentNullException.ThrowIfNull(value);
        return new(assertions.SetItem(entryId, value));
    }

    /// <summary>The value asserted for <paramref name="entryId"/>.</summary>
    /// <param name="entryId">The id of a <c>kind: assertion</c> entry.</param>
    /// <returns>The caller's value.</returns>
    /// <exception cref="AssertionRequiredException">The caller asserted nothing for it.</exception>
    public object Asserted(string entryId) =>
        assertions.TryGetValue(entryId, out var value) ? value : throw new AssertionRequiredException(entryId);
}

/// <summary>
/// An assertion the corpus leaves to the caller was not supplied. Not an unresolved result:
/// the corpus gave the engine the means to proceed, and the caller owes the value (row 8).
/// </summary>
public sealed class AssertionRequiredException : ArgumentException
{
    /// <summary>Creates the exception for the assertion entry <paramref name="entryId"/>.</summary>
    /// <param name="entryId">The assertion the caller did not supply.</param>
    public AssertionRequiredException(string entryId)
        : base($"the map entry '{entryId}' is an assertion; the caller must supply its value") => EntryId = entryId;

    /// <summary>The assertion the caller did not supply.</summary>
    public string EntryId { get; }
}

/// <summary>
/// Marks an untyped hand-written handler for a map entry. The method must be static, take one
/// <see cref="RuleRequest"/> and return <c>Resolution&lt;object&gt;</c>, and it is checked only at
/// runtime. It answers only once the entry's merged status is <c>implemented</c>; until then the
/// entry declines as its row says. Prefer the typed partial method <see cref="Handlers"/> declares
/// for the entry, which the compiler checks; an entry that has both is refused, and an
/// <c>implemented</c> entry whose row has no default needs the typed one to build at all.
/// </summary>
/// <param name="entryId">The map entry this method implements.</param>
[AttributeUsage(AttributeTargets.Method, AllowMultiple = true, Inherited = false)]
public sealed class ImplementsAttribute(string entryId) : Attribute
{
    /// <summary>The map entry this method implements.</summary>
    public string EntryId { get; } = entryId;
}

/// <summary>One registered map entry.</summary>
/// <param name="Id">The map entry's id.</param>
/// <param name="Status">Its merged status.</param>
/// <param name="Row">The first correspondence row it matches.</param>
/// <param name="Locators">
/// Every locator the entry cites. One, its own, for a located entry. For a derived entry
/// (rules-factory decision 0012), the locator of every located entry it rests on, following
/// derived sources down, depth-first in <c>derivedFrom</c> order, each locator once at its first
/// place: the premises entail the fact together, so a decline citing only the first says less
/// than the map knows. <see cref="Registry.Citations"/> reads them for a declined entry.
/// </param>
public sealed record RegisteredEntry(string Id, EntryStatus Status, CorrespondenceRow Row, ImmutableArray<SourceLocator> Locators)
{
    /// <summary>
    /// Who the corpus lets assert this entry, the map's <c>assertedBy</c> (rules-factory decision 0025): the
    /// corpus's own words, or <c>caller</c> where the corpus names nobody. Empty on an entry that is not
    /// <c>kind: assertion</c>. An engine checks an assertion's attribution against these, not its own reading.
    /// </summary>
    public ImmutableArray<string> AssertedBy { get; init; } = [];

    /// <summary>
    /// The locator its declines cite, the first of <see cref="Locators"/>: the kernel's
    /// <see cref="UnresolvedResult"/> holds one, and the rest are read through <see cref="Registry.Citations"/>.
    /// </summary>
    public SourceLocator Locator => Locators[0];
}
"""

REGISTRY_BODY = """
    private static readonly Lazy<ImmutableDictionary<string, Func<RuleRequest, Resolution<object>>>> Implementations =
        new(DiscoverImplementations);

    /// <summary>Every map entry, in the map's order.</summary>
    public static ImmutableArray<RegisteredEntry> Entries => All;

    /// <summary>The registered entry <paramref name="entryId"/>.</summary>
    /// <param name="entryId">A map entry id.</param>
    /// <returns>The entry.</returns>
    /// <exception cref="KeyNotFoundException">The map has no such entry.</exception>
    public static RegisteredEntry Entry(string entryId) =>
        ById.TryGetValue(entryId, out var entry) ? entry : throw new KeyNotFoundException($"the map has no entry '{entryId}'");

    /// <summary>
    /// Every locator <paramref name="entryId"/> cites, for a caller holding its decline. The
    /// kernel's <see cref="UnresolvedResult.Locator"/> is one locator, the first of these; a
    /// derived entry rests on all of them.
    /// </summary>
    /// <param name="entryId">A map entry id.</param>
    /// <returns>The entry's <see cref="RegisteredEntry.Locators"/>.</returns>
    /// <exception cref="KeyNotFoundException">The map has no such entry.</exception>
    public static ImmutableArray<SourceLocator> Citations(string entryId) => Entry(entryId).Locators;

    /// <summary>
    /// Whether a hand-written handler exists for <paramref name="entryId"/>: a typed partial method
    /// of <see cref="Handlers"/>, or an <see cref="ImplementsAttribute"/> method.
    /// </summary>
    /// <param name="entryId">A map entry id.</param>
    /// <returns>True when one exists, whether or not the entry's status lets it answer.</returns>
    /// <exception cref="InvalidOperationException">An <see cref="ImplementsAttribute"/> method is malformed or duplicates a handler.</exception>
    public static bool HasImplementation(string entryId) => Implementations.Value.ContainsKey(entryId) || Handlers.Has(entryId);

    /// <summary>
    /// Resolves <paramref name="entryId"/>: through its hand-written handler when the entry is
    /// <c>implemented</c> and has one (the typed handler first, which answers unless an optional
    /// hook leaves the resolution null), otherwise through the default its correspondence row fixes.
    /// A typed handler receives a request of its entry's type built from <paramref name="request"/>
    /// alone, so any input property an engine declares on that type has its default value; to pass
    /// inputs, resolve through <see cref="Resolve(IEntryRequest)"/> or <see cref="EntryPoints"/>.
    /// </summary>
    /// <param name="entryId">A map entry id.</param>
    /// <param name="request">What the caller asserts.</param>
    /// <returns>The resolution.</returns>
    public static Resolution<object> Resolve(string entryId, RuleRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);
        return Answer(Entry(entryId), request, null);
    }

    /// <summary>
    /// Resolves the entry <paramref name="request"/> is for, exactly as
    /// <see cref="Resolve(string, RuleRequest)"/> does for its id and assertions, except that a
    /// typed handler receives <paramref name="request"/> itself, with every input property the
    /// engine declared on its type. The typed entry points in <see cref="EntryPoints"/> resolve
    /// through here.
    /// </summary>
    /// <param name="request">A request for one map entry.</param>
    /// <returns>The resolution.</returns>
    public static Resolution<object> Resolve(IEntryRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);
        var assertions = request.Assertions ?? throw new ArgumentException("the request carries no assertions", nameof(request));
        return Answer(Entry(request.EntryId), assertions, request);
    }

    private static Resolution<object> Answer(RegisteredEntry entry, RuleRequest assertions, IEntryRequest? request)
    {
        // Discovery runs on the first resolve whatever answers it, so a malformed or duplicate
        // [Implements] handler is refused even for an entry a typed handler answers.
        var untyped = Implementations.Value;
        if (entry.Status == EntryStatus.Implemented)
        {
            if (Handlers.Dispatch(entry.Id, assertions, request) is { } typed)
            {
                return typed;
            }

            if (untyped.TryGetValue(entry.Id, out var handler))
            {
                return handler(assertions);
            }
        }

        return Default(entry, assertions);
    }

    private static Resolution<object> Default(RegisteredEntry entry, RuleRequest request) => entry.Row switch
    {
        CorrespondenceRow.ScopeOut => Decline(entry, UnresolvedReason.OutsideCurrentScope),
        CorrespondenceRow.NotBuilt => Decline(entry, UnresolvedReason.UnsupportedRule),
        CorrespondenceRow.DefinedElsewhere or CorrespondenceRow.BeyondAdapter or CorrespondenceRow.ValueDependencyUnimplemented =>
            Decline(entry, UnresolvedReason.MissingRulesData),
        CorrespondenceRow.UnresolvedAmbiguity => Decline(entry, UnresolvedReason.RequiresInterpretation),
        CorrespondenceRow.Assertion => Resolution<object>.FromValue(request.Asserted(entry.Id)),
        _ => throw new InvalidOperationException(
            $"the map entry '{entry.Id}' is {entry.Status} and matches no declining row, so a hand-written [Implements] handler must answer it"),
    };

    private static Resolution<object> Decline(RegisteredEntry entry, UnresolvedReason reason) =>
        Resolution<object>.FromUnresolved(new UnresolvedResult(reason, $"resolve the map entry '{entry.Id}'", entry.Locator));

    private static ImmutableDictionary<string, Func<RuleRequest, Resolution<object>>> DiscoverImplementations()
    {
        var found = ImmutableDictionary.CreateBuilder<string, Func<RuleRequest, Resolution<object>>>(StringComparer.Ordinal);
        const BindingFlags Everywhere = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static | BindingFlags.DeclaredOnly;
        foreach (var type in typeof(Registry).Assembly.GetTypes())
        {
            foreach (var method in type.GetMethods(Everywhere))
            {
                foreach (var implements in method.GetCustomAttributes<ImplementsAttribute>())
                {
                    var where = $"{type.FullName}.{method.Name}";
                    if (!ById.ContainsKey(implements.EntryId))
                    {
                        throw new InvalidOperationException($"{where} implements '{implements.EntryId}', which the map has no entry for");
                    }

                    var parameters = method.GetParameters();
                    if (method.ReturnType != typeof(Resolution<object>) || parameters.Length != 1 || parameters[0].ParameterType != typeof(RuleRequest))
                    {
                        throw new InvalidOperationException($"{where} must be static Resolution<object> (RuleRequest) to implement '{implements.EntryId}'");
                    }

                    if (found.ContainsKey(implements.EntryId))
                    {
                        throw new InvalidOperationException($"'{implements.EntryId}' has more than one [Implements] handler; {where} is the second");
                    }

                    if (Handlers.Has(implements.EntryId))
                    {
                        throw new InvalidOperationException($"'{implements.EntryId}' has a typed handler in Handlers and an [Implements] handler, {where}; keep one");
                    }

                    found.Add(implements.EntryId, method.CreateDelegate<Func<RuleRequest, Resolution<object>>>());
                }
            }
        }

        return found.ToImmutable();
    }
"""


def registry_cs(model):
    lines = [model.header,
             "using System.Collections.Immutable;\n",
             "using System.Reflection;\n",
             "using RulesKernel.Provenance;\n",
             "using RulesKernel.Resolution;\n\n",
             f"namespace {model.name};\n",
             REGISTRY_SUPPORT,
             "\n/// <summary>Every map entry, the correspondence row it matches first, and the handler that answers it.</summary>\n",
             "public static class Registry\n{\n",
             "    private static readonly ImmutableArray<RegisteredEntry> All =\n    [\n"]
    for item in model.entries:
        entry = item["entry"]
        row = ROWS[item["row"]][0] if item["row"] else "None"
        lines.append(f"        new({cs_string(entry['id'])}, EntryStatus.{STATUSES[entry['status']]}, "
                     f"CorrespondenceRow.{row}, "
                     f"[{', '.join(f'MapEntries.{m}.Locator' for m in item['locators'])}]){asserted_by_init(entry)},\n")
    lines.append("    ];\n\n")
    lines.append("    private static readonly ImmutableDictionary<string, RegisteredEntry> ById =\n"
                 "        All.ToImmutableDictionary(e => e.Id, StringComparer.Ordinal);\n")
    lines.append(REGISTRY_BODY)
    lines.append("}\n")
    return "".join(lines)


CONTRACTS_SUPPORT = """
/// <summary>A request for one map entry; each entry has its own type (<c>Requests</c> namespace).</summary>
public interface IEntryRequest
{
    /// <summary>The map entry this request resolves.</summary>
    string EntryId { get; }

    /// <summary>What the caller asserts, as the registry's dictionary dispatch reads it.</summary>
    RuleRequest Assertions { get; }
}

/// <summary>
/// The typed entry point of one map entry. <typeparamref name="TInput"/> is the entry's own
/// request type, so a request for another entry does not compile. <typeparamref name="TOutput"/>
/// is the type the map declares for the entry's value, and <c>object</c> where it declares none.
/// </summary>
/// <typeparam name="TInput">The entry's request type.</typeparam>
/// <typeparam name="TOutput">The entry's value type.</typeparam>
public sealed class RuleEntry<TInput, TOutput>
    where TInput : IEntryRequest
{
    private readonly Func<TInput, Resolution<TOutput>> resolve;

    internal RuleEntry(string id, Func<TInput, Resolution<TOutput>> resolve)
    {
        Id = id;
        this.resolve = resolve;
    }

    /// <summary>The map entry's id.</summary>
    public string Id { get; }

    /// <summary>The entry as the registry holds it: status, row and citations.</summary>
    public RegisteredEntry Registered => Registry.Entry(Id);

    /// <summary>Resolves the entry through <see cref="Registry.Resolve(IEntryRequest)"/>, so its handler receives <paramref name="request"/> itself.</summary>
    /// <param name="request">The entry's request.</param>
    /// <returns>The resolution.</returns>
    public Resolution<TOutput> Resolve(TInput request)
    {
        ArgumentNullException.ThrowIfNull(request);
        return resolve(request);
    }
}
"""


def contracts_cs(model):
    """`Contracts.g.cs`: the typed entry points (`EntryPoints`) and the handler declarations (`Handlers`)."""
    lines = [model.header,
             "using System.Reflection;\n",
             "using RulesKernel.Resolution;\n\n",
             f"namespace {model.name};\n",
             CONTRACTS_SUPPORT,
             "\n/// <summary>The typed entry point of every map entry, in the map's order.</summary>\n",
             "public static class EntryPoints\n{\n"]
    for index, item in enumerate(model.entries):
        entry, c = item["entry"], contract(model, item)
        lines.append("\n" if index else "")
        lines.append(f"    /// <summary>{xml_text(entry.get('name', entry['id']))} (<c>{xml_text(entry['id'])}</c>).</summary>\n"
                     f"    public static RuleEntry<{c['request_cs']}, {c['output']}> {item['member']} {{ get; }} =\n"
                     f"        new({cs_string(entry['id'])}, request => Registry.Resolve(request));\n")
    lines.append("}\n\n")
    lines.append(
        "/// <summary>\n"
        "/// The hand-written handler of every map entry, declared as partial methods the engine implements\n"
        "/// in a file of its own. An <c>implemented</c> entry whose correspondence row has no default must\n"
        "/// have one, with exactly the declared signature, or the engine does not build. Every other entry's\n"
        "/// hook may stay unimplemented; implemented, it answers once the entry is <c>implemented</c>, and a\n"
        "/// resolution it leaves null falls through to the row's default.\n"
        "/// </summary>\n"
        "internal static partial class Handlers\n{\n")
    hooks = []
    for item in model.entries:
        entry, c = item["entry"], contract(model, item)
        summary = f"    /// <summary>{xml_text(entry.get('name', entry['id']))} (<c>{xml_text(entry['id'])}</c>)"
        if c["required"]:
            lines.append(f"{summary}: required, the entry is implemented.</summary>\n"
                         f"    internal static partial Resolution<{c['output']}> {item['member']}({c['request_cs']} request);\n\n")
        else:
            hooks.append(item)
            lines.append(f"{summary}: optional.</summary>\n"
                         f"    static partial void {item['member']}({c['request_cs']} request, ref Resolution<{c['output']}>? resolution);\n\n")
    lines.append("    /// <summary>\n"
                 "    /// The typed handler's resolution of <paramref name=\"entryId\"/>, or null when it has none or leaves it null.\n"
                 "    /// The handler receives <paramref name=\"request\"/> when it is of the entry's request type, and otherwise\n"
                 "    /// (the dictionary dispatch) a request of that type built from <paramref name=\"assertions\"/>.\n"
                 "    /// </summary>\n"
                 "    internal static Resolution<object>? Dispatch(string entryId, RuleRequest assertions, IEntryRequest? request)\n"
                 "    {\n"
                 "        Resolution<object>? resolution = null;\n")
    if model.entries:
        lines.append("        switch (entryId)\n        {\n")
        for item in model.entries:
            c = contract(model, item)
            lines.append(f"            case {cs_string(item['entry']['id'])}:\n")
            if c["required"]:
                lines.append(f"                resolution = {item['member']}(request as {c['request_cs']} ?? new(assertions));\n")
            else:
                lines.append(f"                {item['member']}(request as {c['request_cs']} ?? new(assertions), ref resolution);\n")
            lines.append("                break;\n")
        lines.append("        }\n\n")
    else:
        lines.append("        _ = entryId;\n        _ = assertions;\n        _ = request;\n")
    lines.append("        return resolution;\n    }\n\n")
    lines.append("    /// <summary>Whether <paramref name=\"entryId\"/> has a typed handler: always when it is required, and an\n"
                 "    /// optional hook when the engine implemented it (an unimplemented partial method is not compiled).</summary>\n"
                 "    internal static bool Has(string entryId) => entryId switch\n    {\n")
    for item in model.entries:
        c = contract(model, item)
        if c["required"]:
            lines.append(f"        {cs_string(item['entry']['id'])} => true,\n")
        else:
            lines.append(f"        {cs_string(item['entry']['id'])} => Hooked({cs_string(item['member'])}, typeof({c['request_cs']})),\n")
    lines.append("        _ => false,\n    };\n\n")
    lines.append("    private static bool Hooked(string name, Type request) =>\n"
                 "        typeof(Handlers).GetMethod(name, BindingFlags.NonPublic | BindingFlags.Static, [request, typeof(Resolution<object>).MakeByRefType()]) is not null;\n")
    lines.append("}\n")
    return "".join(lines)


def requests_cs(model):
    """`Requests.g.cs`: one request type per entry, in a namespace of their own."""
    lines = [model.header,
             f"namespace {model.name}.Requests;\n"]
    for item in model.entries:
        entry, c = item["entry"], contract(model, item)
        eid = cs_string(entry["id"])
        lines.append(
            "\n"
            f"/// <summary>A request to resolve {xml_text(entry.get('name', entry['id']))} (<c>{xml_text(entry['id'])}</c>).</summary>\n"
            "/// <remarks>Partial: an engine declares the entry's inputs as <c>init</c> properties in a file of its own, and a\n"
            "/// caller sets them in an object initializer; the handler receives this very object through <c>EntryPoints</c>.</remarks>\n"
            f"public sealed partial class {c['request']} : IEntryRequest\n{{\n"
            f"    /// <summary>A request for <c>{xml_text(entry['id'])}</c> asserting nothing.</summary>\n"
            f"    public {c['request']}()\n"
            "        : this(RuleRequest.Empty)\n"
            "    {\n"
            "    }\n\n"
            f"    /// <summary>A request for <c>{xml_text(entry['id'])}</c> carrying <paramref name=\"assertions\"/>.</summary>\n"
            "    /// <param name=\"assertions\">What the caller asserts.</param>\n"
            f"    public {c['request']}(RuleRequest assertions)\n"
            "    {\n"
            "        ArgumentNullException.ThrowIfNull(assertions);\n"
            "        Assertions = assertions;\n"
            "    }\n\n"
            "    /// <summary>A request asserting nothing.</summary>\n"
            f"    public static {c['request']} Empty {{ get; }} = new(RuleRequest.Empty);\n\n")
        if c["asserts"]:
            lines.append(
                "    /// <summary>A request asserting <paramref name=\"value\"/> for this assertion entry, which is what it resolves to.</summary>\n"
                "    /// <param name=\"value\">The caller's value.</param>\n"
                "    /// <returns>The request.</returns>\n"
                f"    public static {c['request']} Asserting({c['output']} value) => new(RuleRequest.Empty.Assert({eid}, value));\n\n")
        lines.append(
            "    /// <inheritdoc/>\n"
            f"    public string EntryId => {eid};\n\n"
            "    /// <inheritdoc/>\n"
            "    public RuleRequest Assertions { get; }\n"
            "}\n")
    return "".join(lines)


RULINGS_FILE = "Rulings.g.cs"


def rulings_cs(model):
    """The owner's rulings the overlay holds (decision 0027), as data an engine surfaces to its callers.

    Generated only for an engine whose overlay has a ruling, so an engine with none gains no type. The
    record and the class are partial: an engine may add members (an alias, a derived property) in a
    file of its own, and never restates the metadata, which has one home, the overlay."""
    lines = [model.header,
             "using System.Collections.Immutable;\n\n",
             f"namespace {model.name};\n\n",
             "/// <summary>\n",
             "/// An owner's ruling (rules-factory decision 0027): this engine's answer to part of a question its map\n",
             "/// records as <c>fate: unresolved</c>. It is the owner's, not the corpus's, so a result that relies on it\n",
             "/// names it, and nothing presents it as what the corpus says.\n",
             "/// </summary>\n",
             "/// <param name=\"Id\">A stable id, <c>&lt;entry id&gt;/&lt;slug&gt;</c>.</param>\n",
             "/// <param name=\"EntryId\">The map entry whose <c>ambiguity.question</c> it answers part of.</param>\n",
             "/// <param name=\"Span\">The part of that question it answers, quoted verbatim from the map.</param>\n",
             "/// <param name=\"Answer\">The ruling, stated briefly.</param>\n",
             "/// <param name=\"RuledBy\">Who ruled.</param>\n",
             "/// <param name=\"RuledOn\">When.</param>\n",
             "/// <param name=\"Record\">The engine's decision record that holds the ruling, relative to the engine root.</param>\n",
             "public sealed partial record OwnerRuling(string Id, string EntryId, string Span, string Answer, string RuledBy, "
             "DateOnly RuledOn, string Record);\n\n",
             f"/// <summary>The {len(model.rulings)} owner's ruling(s) in corpus-map.overlay.json, one static each, in overlay order.</summary>\n",
             "public static partial class OwnerRulings\n{\n"]
    for ruling in model.rulings:
        year, month, day = (int(part) for part in ruling["ruledOn"].split("-"))
        lines.append(f"    /// <summary><c>{xml_text(ruling['id'])}</c>: {xml_text(ruling['answer'])}</summary>\n"
                     f"    public static OwnerRuling {ruling['member']} {{ get; }} = new(\n"
                     f"        {cs_string(ruling['id'])},\n"
                     f"        {cs_string(ruling['entry'])},\n"
                     f"        {cs_string(ruling['span'])},\n"
                     f"        {cs_string(ruling['answer'])},\n"
                     f"        {cs_string(ruling['ruledBy'])},\n"
                     f"        new DateOnly({year}, {month}, {day}),\n"
                     f"        {cs_string(ruling['record'])});\n\n")
    lines.append("    /// <summary>Every ruling, in overlay order.</summary>\n"
                 f"    public static ImmutableArray<OwnerRuling> All {{ get; }} = [{', '.join(r['member'] for r in model.rulings)}];\n"
                 "}\n")
    return "".join(lines)


def tests_cs(model):
    lines = [model.header,
             "using RulesKernel.Provenance;\n",
             "using RulesKernel.Resolution;\n",
             "using Xunit;\n\n",
             f"namespace {model.name}.Tests;\n\n",
             "public sealed class CorrespondenceTests\n{\n",
             "    private static readonly string[] MapOrder =\n    [\n"]
    for item in model.entries:
        lines.append(f"        {cs_string(item['entry']['id'])},\n")
    lines.append("    ];\n\n")
    lines.append("    [Fact]\n"
                 "    public void Every_map_entry_is_registered_in_map_order() =>\n"
                 "        Assert.Equal(MapOrder, Registry.Entries.Select(e => e.Id));\n\n")
    lines.append("    [Fact]\n"
                 "    public void Every_hand_written_handler_names_a_map_entry_once_with_the_handler_signature() =>\n"
                 "        Assert.All(MapOrder, id => _ = Registry.HasImplementation(id));\n\n")
    lines.append("    [Fact]\n"
                 "    public void Every_map_entry_has_a_typed_entry_point_in_map_order() =>\n"
                 "        Assert.Equal(MapOrder, new string[]\n"
                 "        {\n"
                 + "".join(f"            EntryPoints.{item['member']}.Id,\n" for item in model.entries) +
                 "        });\n\n")
    lines.append("    private static void AssertDeclines(string entryId, UnresolvedReason reason, Resolution<object> typed, params SourceLocator[] cited)\n"
                 "    {\n"
                 "        foreach (var resolution in new[] { Registry.Resolve(entryId, RuleRequest.Empty), typed })\n"
                 "        {\n"
                 "            var unresolved = resolution.Match<UnresolvedResult?>(_ => null, u => u);\n"
                 "            Assert.NotNull(unresolved);\n"
                 "            Assert.Equal(reason, unresolved.Reason);\n"
                 "            Assert.Equal(cited[0], unresolved.Locator);\n"
                 "        }\n\n"
                 "        Assert.Equal(cited, Registry.Citations(entryId));\n"
                 "    }\n")
    for item in model.entries:
        entry, row = item["entry"], item["row"]
        method = snake(entry["id"])
        cited = ", ".join(locator_cs(model.locator_of(m)) for m in item["locators"])
        lines.append("\n")
        if not model.located(item):
            # Whatever its row, a derived entry's citation is every premise, in the generator's
            # order, and MapEntries and the Registry must both say so.
            lines.append("    [Fact]\n"
                         f"    public void {method}__cites_every_premise()\n"
                         "    {\n"
                         f"        SourceLocator[] cited = [{cited}];\n"
                         f"        Assert.Equal(cited, MapEntries.{item['member']}.Locators);\n"
                         f"        Assert.Equal(cited, Registry.Citations({cs_string(entry['id'])}));\n"
                         "    }\n\n")
        if entry["status"] == "implemented":
            if row == 8:
                lines.append("    [Fact]\n"
                             f"    public void {method}__is_implemented_and_answers_or_demands_the_assertion()\n"
                             "    {\n"
                             f"        if (Registry.HasImplementation({cs_string(entry['id'])}))\n"
                             "        {\n            return;\n        }\n\n"
                             "        var value = new object();\n"
                             f"        var resolved = Registry.Resolve({cs_string(entry['id'])}, RuleRequest.Empty.Assert({cs_string(entry['id'])}, value))"
                             ".Match<object?>(v => v, _ => null);\n"
                             "        Assert.Same(value, resolved);\n"
                             f"        var typed = EntryPoints.{item['member']}.Resolve({contract(model, item)['request_cs']}.Asserting(value)).Match<object?>(v => v, _ => null);\n"
                             "        Assert.Same(value, typed);\n"
                             f"        Assert.Throws<AssertionRequiredException>(() => Registry.Resolve({cs_string(entry['id'])}, RuleRequest.Empty));\n"
                             "    }\n")
            else:
                lines.append("    [Fact]\n"
                             f"    public void {method}__is_implemented_so_a_hand_written_handler_answers_it() =>\n"
                             f"        Assert.True(Registry.HasImplementation({cs_string(entry['id'])}), "
                             f"{cs_string(entry['id'] + ' is implemented in the overlay and has no [Implements] handler')});\n")
        elif row in (1, 2, 3, 4, 5, 6):
            reason = ROWS[row][1]
            lines.append("    [Fact]\n"
                         f"    public void {method}__declines_{reason}_row_{row}() =>\n"
                         f"        AssertDeclines({cs_string(entry['id'])}, UnresolvedReason.{reason}, "
                         f"EntryPoints.{item['member']}.Resolve({contract(model, item)['request_cs']}.Empty), "
                         f"{cited});\n")
        else:
            raise GenerationError(f"entry {entry['id']!r} is {entry['status']!r} and matches no declining row; "
                                  f"check-map.py --phase consumer should have refused it")
    lines.append("}\n")
    return "".join(lines)



# --- scaffold ------------------------------------------------------------------------------


# No double hyphen in this text: it goes inside XML comments, where "--" is not allowed.
MANAGED_NOTE = ("Managed by rules-factory (recipe {version}): `factory produce` updates this file when its\n"
                "       recipe changes and refuses to overwrite a hand edit; adopting it makes it the engine's own.")


# The agent rails whose recipe is a file rather than a string (decision 0029): published path ->
# template under recipe/rails/. They are documents and a hook, long enough that inlining them here
# would bury the generator, and worth reading as what they are. Read lazily, inside managed_files:
# this module is vendored into every engine as scripts/factory/generate.py, where recipe/ does not
# exist and the engine's gate calls `generated` alone.
RAILS = {
    "AGENTS.md": "AGENTS.md",
    "CLAUDE.md": "CLAUDE.md",
    "docs/agent-team.md": "agent-team.md",
    ".claude/agents/engine-dev.md": "agents/engine-dev.md",
    ".claude/agents/repo-steward.md": "agents/repo-steward.md",
    ".claude/agents/rules-conformance.md": "agents/rules-conformance.md",
    ".claude/hooks/primary-checkout-guard.py": "hooks/primary-checkout-guard.py",
    ".claude/settings.json": "settings.json",
    "tools/dispatch-agent.sh": "tools/dispatch-agent.sh",
    "tools/new-issue.sh": "tools/new-issue.sh",
    "tools/entry-packet.py": "tools/entry-packet.py",
    "tools/re-produce.sh": "tools/re-produce.sh",
    "tools/review-packet.py": "tools/review-packet.py",
    "tools/pr-policy.py": "tools/pr-policy.py",
    "tools/record-verdict.py": "tools/record-verdict.py",
    "tools/conformance-gate.py": "tools/conformance-gate.py",
    "tools/requeue-gate.py": "tools/requeue-gate.py",
    ".github/pull_request_template.md": "pull_request_template.md",
    ".github/workflows/pr-policy.yml": "workflows/pr-policy.yml",
    ".github/workflows/conformance-gate.yml": "workflows/conformance-gate.yml",
    ".github/workflows/verdict-requeue.yml": "workflows/verdict-requeue.yml",
    "tools/agent-doctor.py": "tools/agent-doctor.py",
    # Named `editorconfig` in the recipe: a dotfile there would be invisible in a listing of the
    # rails, and the published path is what matters.
    ".editorconfig": "editorconfig",
}
# The rails an operator runs. `produce` writes with the default mode, so a script invoked by path
# would not run; the hook is invoked through `python3` by .claude/settings.json instead and needs
# no bit, and tools/requeue-gate.py is the same case -- .github/workflows/verdict-requeue.yml runs
# it through `python3`, and nobody runs it by hand. The mode is not part of a recipe's bytes, so it
# plays no part in hand-edit detection.
EXECUTABLE = frozenset({"tools/dispatch-agent.sh", "tools/new-issue.sh", "tools/entry-packet.py",
                        "tools/review-packet.py", "tools/pr-policy.py", "tools/record-verdict.py",
                        "tools/conformance-gate.py", "tools/agent-doctor.py", "tools/re-produce.sh"})
RAILS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "recipe", "rails")


def rails_files():
    """The rails recipes: published path -> text, read from recipe/rails/.

    Each is read in binary and decoded, so the bytes written are the bytes on disk: a recipe
    version means one fixed sequence of bytes (ownership.py), and a newline translated on the way
    through would silently make an engine's copy a hand edit.
    """
    out = {}
    for relative, template in RAILS.items():
        with open(os.path.join(RAILS_DIR, *template.split("/")), "rb") as handle:
            out[relative] = handle.read().decode("utf-8")
    return out


def managed_files():
    """The managed recipes (ownership.py): path -> text. Independent of the engine and the map, so
    each recipe version is one fixed sequence of bytes."""
    versions = {row.pattern: row.recipe for row in ownership.managed_rows("")}
    return {
        **rails_files(),
        "global.json": json.dumps({"sdk": {"version": SDK_VERSION, "rollForward": "disable"}}, indent=2) + "\n",
        "NuGet.config": (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            "<!-- Restore talks to nuget.org and nothing else; packages.lock.json pins every content hash.\n"
            f"     {MANAGED_NOTE.format(version=versions['NuGet.config'])} -->\n"
            "<configuration>\n"
            "  <packageSources>\n"
            "    <clear />\n"
            '    <add key="nuget.org" value="https://api.nuget.org/v3/index.json" />\n'
            "  </packageSources>\n"
            "  <packageSourceMapping>\n"
            '    <packageSource key="nuget.org">\n'
            '      <package pattern="*" />\n'
            "    </packageSource>\n"
            "  </packageSourceMapping>\n"
            "</configuration>\n"),
        "Directory.Build.props": (
            "<Project>\n\n"
            "  <!-- Zero-warning, deterministic builds.\n"
            f"       {MANAGED_NOTE.format(version=versions['Directory.Build.props'])} -->\n"
            "  <PropertyGroup>\n"
            "    <TargetFrameworks>net8.0;net10.0</TargetFrameworks>\n"
            "    <LangVersion>latest</LangVersion>\n"
            "    <Nullable>enable</Nullable>\n"
            "    <ImplicitUsings>enable</ImplicitUsings>\n"
            "    <TreatWarningsAsErrors>true</TreatWarningsAsErrors>\n"
            "    <AnalysisLevel>latest</AnalysisLevel>\n"
            "    <EnableNETAnalyzers>true</EnableNETAnalyzers>\n"
            "    <EnforceCodeStyleInBuild>true</EnforceCodeStyleInBuild>\n"
            "    <Deterministic>true</Deterministic>\n"
            "    <ContinuousIntegrationBuild Condition=\"'$(CI)' == 'true'\">true</ContinuousIntegrationBuild>\n"
            "    <InvariantGlobalization>true</InvariantGlobalization>\n"
            "    <GenerateDocumentationFile>true</GenerateDocumentationFile>\n"
            "  </PropertyGroup>\n\n"
            "  <!-- Every package, the map included, is pinned by content hash in packages.lock.json;\n"
            "       CI restores in locked mode. -->\n"
            "  <PropertyGroup>\n"
            "    <RestorePackagesWithLockFile>true</RestorePackagesWithLockFile>\n"
            "    <RestoreLockedMode Condition=\"'$(CI)' == 'true'\">true</RestoreLockedMode>\n"
            "  </PropertyGroup>\n\n"
            "</Project>\n"),
    }


AGENT_POLICY = ".github/agent-policy.json"
# The five labels the issue state machine is written in: three states and two risks, in the order
# `agent_policy` writes them.
LABEL_KEYS = ("ready", "blocked", "needsDecision", "normalRisk", "independentRisk")


class PolicyError(ValueError):
    """An `.github/agent-policy.json` the rails cannot act on. Callers raise their own error type."""


def policy_labels(document, where=AGENT_POLICY):
    """The five label strings, or a refusal. The one place the label vocabulary is judged (#188).

    Two keys may not share a string. `backlog.label_plan` computes a state set and a risk set from
    these five, and two keys that collapse into one label make those sets lie: with `ready` equal
    to `blocked` an issue is in two states at once and neither can be removed, and with a state
    label equal to a risk label, moving the state strips the risk. Either way the issues reach
    GitHub undispatchable, and `rails --check` said OK, because each key was non-empty.

    It lives here because this module writes that file (`agent_policy` below), so what the rails
    demand of it cannot drift from what the factory ships in it; `rails.py` and `backlog.py` both
    read it through here and neither states the rule itself.
    """
    labels = document.get("labels") or {}
    missing = [key for key in LABEL_KEYS if not labels.get(key)]
    if missing:
        raise PolicyError(f"{where} names no {', '.join(sorted(missing))} label; the rails read every label "
                          f"from it, so a missing one would silently go unapplied")
    taken = {}
    for key in LABEL_KEYS:
        taken.setdefault(labels[key], []).append(key)
    shared = sorted((name, keys) for name, keys in taken.items() if len(keys) > 1)
    if shared:
        collisions = "; ".join(f"{' and '.join(keys)} are both {name!r}" for name, keys in shared)
        raise PolicyError(f"{where} gives one label to more than one key ({collisions}); the five are a state "
                          f"machine and a risk axis, so an issue would be in two states at once, or lose its "
                          f"risk label when its state changed")
    return {key: labels[key] for key in LABEL_KEYS}


def agent_policy():
    """The engine's rails configuration (decision 0029): every choice the rails read.

    Engine-owned, so the factory writes it once and never again: a consumer changes the review
    chain, the label vocabulary or the worktree variables by editing this file, and no emitted
    script names a provider. The chain below is the default the factory ships, which is why it is
    here and not in a script.
    """
    return json.dumps({
        "schemaVersion": 1,
        "labels": {
            "ready": "state:ready",
            "blocked": "state:blocked",
            "needsDecision": "state:needs-decision",
            "normalRisk": "risk:normal",
            "independentRisk": "risk:independent-review",
        },
        "review": {
            "semanticContext": "rules-verdict/semantic",
            "semanticPaths": ["src/**", "tests/**", OVERLAY_NAME, PACKAGES_PROPS,
                              "corpus/**", "docs/decisions/**"],
            "independentFallback": [
                {"id": "codex", "context": "rules-verdict/codex"},
                {"id": "gemini", "context": "rules-verdict/gemini"},
                {"id": "in-house-independent", "context": "rules-verdict/in-house-independent"},
            ],
        },
        "worktrees": {
            "rootEnvironmentVariable": "RULES_ENGINE_WORKTREE_ROOT",
            "primaryMutationEscapeHatch": "RULES_ENGINE_ALLOW_PRIMARY_MUTATION",
        },
    }, indent=2) + "\n"


def engine_owned(model):
    """The engine-owned scaffold (ownership.py): path -> text, written only when absent."""
    name = model.name
    packages = "\n".join(f'    <PackageVersion Include="{p}" Version="{v}" />' for p, v in TEST_PACKAGES)
    return {
        "Directory.Packages.props": (
            "<Project>\n\n"
            "  <PropertyGroup>\n"
            "    <ManagePackageVersionsCentrally>true</ManagePackageVersionsCentrally>\n"
            "    <CentralPackageTransitivePinningEnabled>true</CentralPackageTransitivePinningEnabled>\n"
            "  </PropertyGroup>\n\n"
            "  <!-- The kernel and map pins, and the reference to the map, are rewritten by every\n"
            "       `factory produce`: they are facts about what the engine was produced from. -->\n"
            f'  <Import Project="$(MSBuildThisFileDirectory){PACKAGES_PROPS}" />\n\n'
            "  <ItemGroup>\n"
            f"{packages}\n"
            "  </ItemGroup>\n\n"
            "</Project>\n"),
        f"{name}.slnx": (
            "<Solution>\n"
            f'  <Project Path="src/{name}/{name}.csproj" />\n'
            f'  <Project Path="tests/{name}.Tests/{name}.Tests.csproj" />\n'
            "</Solution>\n"),
        f"src/{name}/{name}.csproj": (
            '<Project Sdk="Microsoft.NET.Sdk">\n\n'
            "  <ItemGroup>\n"
            '    <PackageReference Include="RulesKernel" />\n'
            f"    <!-- The map package is referenced from {PACKAGES_PROPS}, which `factory produce`\n"
            "         rewrites, so the reference always names the package the code was generated from. -->\n"
            "  </ItemGroup>\n\n"
            "  <ItemGroup>\n"
            "    <!-- What this engine was produced from (tools/factory/provenance.py); a generated test\n"
            "         asserts the embedded copy is the file. -->\n"
            f'    <EmbeddedResource Include="../../provenance.json" LogicalName="{name}.provenance.json" Link="provenance.json" />\n'
            "  </ItemGroup>\n\n"
            "</Project>\n"),
        f"tests/{name}.Tests/{name}.Tests.csproj": (
            '<Project Sdk="Microsoft.NET.Sdk">\n\n'
            "  <PropertyGroup>\n"
            "    <IsPackable>false</IsPackable>\n"
            "    <IsTestProject>true</IsTestProject>\n"
            "    <!-- Test names are the documentation here. -->\n"
            "    <GenerateDocumentationFile>false</GenerateDocumentationFile>\n"
            "  </PropertyGroup>\n\n"
            "  <ItemGroup>\n"
            + "".join(f'    <PackageReference Include="{p}" />\n' for p, _ in TEST_PACKAGES) +
            "  </ItemGroup>\n\n"
            "  <ItemGroup>\n"
            f'    <ProjectReference Include="../../src/{name}/{name}.csproj" />\n'
            "  </ItemGroup>\n\n"
            "</Project>\n"),
        OVERLAY_NAME: "{}\n",
        AGENT_POLICY: agent_policy(),
    }


def packages_props(model):
    """The pins and the map reference: everything MSBuild reads that the factory's inputs decide."""
    if model.randomness not in RANDOMNESS:
        raise GenerationError(f"the corpus's randomness is {model.randomness!r}, not one of {', '.join(RANDOMNESS)} "
                              f"(decision 0019), so whether to pin {RANDOMNESS_PACKAGE} is undecided")
    randomness = "" if model.randomness == "none" else (
        "    <!-- The corpus declares randomness: seeded (rules-factory decision 0019), so the engine may\n"
        "         reference RulesKernel.Randomness. It is pinned here, at the kernel's version, and the\n"
        "         factory references it nowhere: whether and where to draw is the engine's code. -->\n"
        f'    <PackageVersion Include="{RANDOMNESS_PACKAGE}" Version="{KERNEL_VERSION}" />\n')
    return (
        "<Project>\n\n"
        "  <!-- <auto-generated>\n"
        f"       Generated by rules-factory tools/factory from {xml_text(model.package_id)} {xml_text(model.version)}.\n"
        "       Rewritten by every `factory produce`; recorded in provenance.json. Do not edit.\n"
        "       </auto-generated> -->\n\n"
        "  <ItemGroup>\n"
        "    <!-- The kernel is referenced, never copied. -->\n"
        f'    <PackageVersion Include="RulesKernel" Version="{KERNEL_VERSION}" />\n'
        "    <!-- The kernel's determinism analyzers, at the kernel's version. An engine that copied a\n"
        "         list of forbidden constructs into itself would diverge from every other engine's copy,\n"
        "         which is what the kernel exists to end (rules-factory decision 0029). -->\n"
        f'    <PackageVersion Include="{ANALYZERS_PACKAGE}" Version="{KERNEL_VERSION}" />\n'
        f"{randomness}"
        "    <!-- The map is referenced, never copied (rules-factory decision 0015), at an exact\n"
        "         version. The engine's own build facts live in corpus-map.overlay.json. -->\n"
        f'    <PackageVersion Include="{model.package_id}" Version="[{model.version}]" />\n'
        "  </ItemGroup>\n\n"
        "  <!-- The map this engine is built from, referenced by the engine project only. It carries no\n"
        "       assemblies; its build props add one RulesFactoryMap item naming the restored map,\n"
        "       manifest and checker. -->\n"
        f"  <ItemGroup Condition=\"'$(MSBuildProjectName)' == '{model.name}'\">\n"
        f'    <PackageReference Include="{model.package_id}" PrivateAssets="all" />\n'
        "    <!-- The analyzers, on the engine project only: a determinism defect in the rules is a build\n"
        "         error, and a test that fakes a clock or iterates a set is not the engine doing it.\n"
        "         .editorconfig states each severity rather than leaving it to the package's defaults. -->\n"
        f'    <PackageReference Include="{ANALYZERS_PACKAGE}" PrivateAssets="all" />\n'
        "  </ItemGroup>\n\n"
        "</Project>\n")


def generated(model):
    name = model.name
    files = {
        PACKAGES_PROPS: packages_props(model),
        f"src/{name}/Generated/MapEntries.g.cs": map_entries_cs(model),
        f"src/{name}/Generated/Registry.g.cs": registry_cs(model),
        f"src/{name}/Generated/Contracts.g.cs": contracts_cs(model),
        f"src/{name}/Generated/Requests.g.cs": requests_cs(model),
        f"tests/{name}.Tests/Generated/CorrespondenceTests.g.cs": tests_cs(model),
    }
    if model.rulings:
        files[f"src/{name}/Generated/{RULINGS_FILE}"] = rulings_cs(model)
    return files


def _write(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(data)


MSBUILD_FILES = (".props", ".targets", ".csproj")
ENGINE_BUILD_SKIP = {"bin", "obj", ".git", ".vs", "corpus", "backlog", "Generated"}


def refuse_split_pins(model, out):
    """Refuse an engine whose own MSBuild files would contradict the generated pins.

    The kernel and map versions, and the reference to the map package, have exactly one home:
    PACKAGES_PROPS, rewritten every run. An engine-owned file that pins either package again, or
    references a map package itself, or a Directory.Packages.props that does not import the
    generated file (an engine scaffolded before the pins moved there), would let the build use a
    version provenance does not name. Refused before anything is written, rather than repaired:
    those files are the engine's, and the factory does not edit them.
    """
    pinned = {"RulesKernel", model.package_id} | ({RANDOMNESS_PACKAGE} if model.randomness == "seeded" else set())
    found = []
    for directory, dirs, names in os.walk(out):
        dirs[:] = sorted(d for d in dirs if d not in ENGINE_BUILD_SKIP)
        for file_name in sorted(names):
            if not file_name.endswith(MSBUILD_FILES) or file_name == PACKAGES_PROPS:
                continue
            path = os.path.join(directory, file_name)
            relative = os.path.relpath(path, out).replace(os.sep, "/")
            try:
                with open(path, encoding="utf-8") as handle:
                    text = handle.read()
            except (OSError, UnicodeDecodeError) as error:
                raise GenerationError(f"cannot read {path}: {error}")
            for element, package in re.findall(r'<(PackageVersion|PackageReference)\b[^>]*?\bInclude="([^"]+)"', text):
                if element == "PackageVersion" and package in pinned:
                    found.append(f"{relative} pins {package}")
                elif element == "PackageReference" and (package == model.package_id or package.startswith("RulesFactory.Maps.")):
                    found.append(f"{relative} references the map package {package}")
            if re.search(r'\bVersionOverride="', text):
                for package in re.findall(r'<PackageReference\b[^>]*?\bInclude="([^"]+)"[^>]*?\bVersionOverride="', text):
                    if package in pinned:
                        found.append(f"{relative} overrides the version of {package}")
            if relative == "Directory.Packages.props" and PACKAGES_PROPS not in text:
                found.append(f"{relative} does not import {PACKAGES_PROPS}")
    if found:
        raise GenerationError("the engine's own build files would pin a different kernel or map than the one "
                              f"generated ({'; '.join(found)}); the pins and the map reference belong in "
                              f"{PACKAGES_PROPS}, which every produce rewrites, so remove them from those files")


def produce(intake, name, out, log=None, adopt=(), reset=()):
    """Write an engine for `intake` under `out`, each file as its ownership class says.

    Engine-owned files are written when absent; managed files as ownership.plan_managed decides
    (`adopt` and `reset` are the managed paths given to --adopt and --reset); generated files
    always. The returned model carries `managed` ({path: recipe version}) and `adopted` (managed
    paths now engine-owned) for provenance to record. Every refusal is raised before any write.
    """
    overlay_path = os.path.join(out, OVERLAY_NAME)
    overlay = {}
    if os.path.isfile(overlay_path):
        try:
            with open(overlay_path, encoding="utf-8") as handle:
                overlay = json.load(handle)
        except (OSError, ValueError) as error:
            raise GenerationError(f"cannot read {overlay_path}: {error}")
    model = Model(intake, merge(intake.map, overlay, root=out), name, rulings_step.collect(overlay))
    refuse_split_pins(model, out)
    try:
        managed_writes, model.managed, model.adopted, notes = ownership.plan_managed(
            out, name, {p: t.encode("utf-8") for p, t in managed_files().items()}, adopt, reset)
    except ownership.OwnershipError as error:
        raise GenerationError(str(error))
    corpus_file = os.path.basename(str(intake.corpus.get("committedPath") or intake.corpus_name))

    written = []
    for relative, text in engine_owned(model).items():
        path = os.path.join(out, *relative.split("/"))
        if not os.path.exists(path):
            _write(path, text.encode("utf-8"))
            written.append(relative)
    for relative, data in sorted(managed_writes.items()):
        path = os.path.join(out, *relative.split("/"))
        _write(path, data)
        if relative in EXECUTABLE:
            os.chmod(path, 0o755)
        written.append(relative)
    _write(os.path.join(out, "corpus", corpus_file), intake.corpus_bytes)
    written.append(f"corpus/{corpus_file}")
    for relative, text in generated(model).items():
        _write(os.path.join(out, *relative.split("/")), text.encode("utf-8"))
        written.append(relative)
    # An engine whose last ruling was withdrawn no longer generates the rulings file (0027); left in
    # place, it would be a stray *.g.cs the gate refuses.
    stale_rulings = os.path.join(out, "src", name, "Generated", RULINGS_FILE)
    if not model.rulings and os.path.isfile(stale_rulings):
        os.remove(stale_rulings)
        written.append(f"(removed) src/{name}/Generated/{RULINGS_FILE}")
    if log is not None:
        rows = {}
        for item in model.entries:
            rows[item["row"]] = rows.get(item["row"], 0) + 1
        summary = ", ".join(f"row {r}: {n}" if r else f"no row: {n}" for r, n in sorted(rows.items(), key=lambda kv: kv[0] or 0))
        print(f"--- produce: {len(model.entries)} entries registered ({summary})", file=log)
        for line in rulings_step.describe(overlay):
            print(f"--- {line}", file=log)
        for note in notes:
            print(note, file=log)
        for relative in written:
            print(f"wrote {relative}", file=log)
    return model
