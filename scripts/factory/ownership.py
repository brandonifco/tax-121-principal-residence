"""Who owns each file `produce` writes (#72, decision 0018). One table, three classes.

Before this module the factory had generated files, a one-shot template scaffold and nothing
saying which was which: global.json, NuGet.config and Directory.Build.props were written once
and then belonged to the engine, so a factory change to SDK policy, package sources, analyzers
or target frameworks never reached an engine that had already been produced. `TABLE` below is
now the only place a file's class is decided; generate.py, provenance.py and the tests read it,
and the ADR's table is checked against it.

  * **generated** -- rewritten on every `produce` from the factory's inputs. A hand edit is
    overwritten, and provenance.json hashes each one in `generated`, so an edit made after the
    last `produce` is a named mismatch.
  * **managed** -- factory policy the engine should keep receiving. Each managed file has a
    recipe version, and `RECIPE_SHA256` lists the SHA-256 of the bytes every version of its
    recipe ever wrote. On each `produce` a managed file that is absent, or whose bytes are one
    of those versions, is (re)written from the current recipe: that is the migration. A managed
    file whose bytes are none of them has been edited by hand, and `produce` refuses, naming
    it, before anything is written, rather than overwrite a deliberate change or silently keep
    a stale policy. Two flags settle it: `--adopt PATH` makes the file engine-owned from then
    on (provenance.json records the adoption, so later runs remember it), and `--reset PATH`
    overwrites it with the current recipe and makes it managed again (also how an adopted file
    comes back). provenance.json hashes each managed file once, in `managed`, with its recipe
    version.
  * **engine-owned** -- written once, when absent, and never touched again: the engine's own
    choices, which no factory change should undo. provenance.json lists them in `engineOwned`
    and hashes them, as it hashes every build input the engine owns, in `buildInputs`.

Detection compares against the recipe history in code rather than against the hash the last
`produce` recorded in provenance.json. The history does not trust a file in the engine (an edited
provenance.json cannot make a hand edit look like the factory's), it works for an engine produced
before this module existed (its files are version 1), and it makes a recipe version mean fixed
bytes: tools/tests/test_factory_ownership.py fails when a recipe changes without a new version and
its hash. The cost is that a managed recipe may not depend on the engine's name or the map, and
none does.

Anything `produce` writes must match exactly one row; provenance.build refuses a written path
that matches none, so a new output cannot ship unclassified. The lock files are the one output
not written by Python: verify's first restore (verify.py) writes them in the staging copy when
none exist, and produce commits them. They are engine-owned: the engine relocks
(`scripts/validate.sh lock`) and commits them itself, and a later produce leaves them alone, with
one exception (#94, decision 0018's amendment): a produce that changes the generated pins in
RulesFactory.Packages.g.props (a map version bump) re-locks every existing lock file in its
staging copy before the gate, because lock files resolved against the old pins cannot pass the
gate's locked restore. The rewrite is the consequence of the factory's input moving, is recorded
in provenance.json, and is committed only if the gate passes. Files the engine adds itself (its
hand-written code, lock files) match no row and are not the factory's to classify.

Standard library only; vendored into every engine as scripts/factory/ownership.py because
generate.py imports it and the engine's gate imports generate.py.
"""
import collections
import fnmatch
import hashlib
import json
import os

GENERATED = "generated"
MANAGED = "managed"
ENGINE_OWNED = "engine-owned"
CLASSES = (GENERATED, MANAGED, ENGINE_OWNED)
PROVENANCE = "provenance.json"

Row = collections.namedtuple("Row", "pattern cls recipe reason")

# `{name}` is the engine name; `*` matches within one path segment only.
TABLE = (
    Row("provenance.json", GENERATED, None,
        "the record of this run; written last, from the run itself"),
    Row("RulesFactory.Packages.g.props", GENERATED, None,
        "the kernel and map pins and the map reference: facts about the inputs (#66)"),
    Row("src/{name}/Generated/*.g.cs", GENERATED, None,
        "the map, registry, typed contracts and embedded provenance, from merge(package, overlay)"),
    Row("tests/{name}.Tests/Generated/*.g.cs", GENERATED, None,
        "the correspondence and provenance tests, from the same merge"),
    Row("corpus/*", GENERATED, None,
        "the corpus copy intake proved against the map's baseline"),
    Row("backlog/*.md", GENERATED, None,
        "the entries still to build, from the merge; GitHub issues are synced from it"),
    Row("scripts/validate.sh", GENERATED, None, "the gate recipe (M3): the factory's definition of acceptable"),
    Row("scripts/map-overlay.py", GENERATED, None, "the gate recipe: 0015's merge"),
    Row("scripts/engine-gate.py", GENERATED, None, "the gate recipe: its non-dotnet checks"),
    Row("scripts/factory/*.py", GENERATED, None, "the factory's generator, vendored so the gate can regenerate"),
    Row(".github/workflows/validate.yml", GENERATED, None, "the gate recipe: CI runs validate.sh full"),
    Row("AGENTS.md", MANAGED, 7,
        "the governing contract every agent works this engine under (decision 0029)"),
    Row("CLAUDE.md", MANAGED, 1,
        "a pointer to AGENTS.md and the Claude adapters; it states no rule of its own (0029)"),
    Row("docs/agent-team.md", MANAGED, 4, "the four roles, and what each may not do (0029)"),
    Row(".claude/agents/engine-dev.md", MANAGED, 5, "the implementer's charter (0029)"),
    Row(".claude/agents/repo-steward.md", MANAGED, 1, "the structural reviewer's charter, read-only (0029)"),
    Row(".claude/agents/rules-conformance.md", MANAGED, 3, "the semantic reviewer's charter, read-only (0029)"),
    Row(".claude/hooks/primary-checkout-guard.py", MANAGED, 1,
        "the PreToolUse guard that keeps implementation work out of the primary checkout (0029)"),
    Row(".claude/settings.json", MANAGED, 1, "which tools the guard runs before (0029)"),
    Row("tools/dispatch-agent.sh", MANAGED, 2,
        "one issue, one worktree, one branch; it refuses what is not ready to work (0029)"),
    Row("tools/new-issue.sh", MANAGED, 2,
        "an issue with the shape the rails expect, a factory update's included (0029, #193)"),
    Row("tools/entry-packet.py", MANAGED, 4,
        "the bounded assignment for one entry, assembled from merge(package, overlay) (0029)"),
    Row("tools/re-produce.sh", MANAGED, 2,
        "an overlay edit is finished by a re-produce, from the factory commit the record names (#192)"),
    Row("tools/review-packet.py", MANAGED, 1,
        "everything a reviewer needs about one pull request, in the order it is read (0029)"),
    Row("tools/pr-policy.py", MANAGED, 2,
        "the pull request contract, checked mechanically; a produce update's claim is checked, not taken (#193)"),
    Row("tools/record-verdict.py", MANAGED, 1,
        "a review verdict as a commit status on the exact commit reviewed (0029)"),
    Row("tools/conformance-gate.py", MANAGED, 2,
        "whether the verdicts this change needs are recorded at the commit being merged; a truncated "
        "file list is undecidable (0029, #193)"),
    Row("tools/requeue-gate.py", MANAGED, 1,
        "asks the gate to report again at the commit a recorded verdict names (#191)"),
    Row(".github/pull_request_template.md", MANAGED, 2, "the pull request shape pr-policy.py checks (0029)"),
    Row(".github/workflows/pr-policy.yml", MANAGED, 1, "the required check that runs pr-policy.py (0029)"),
    Row(".github/workflows/conformance-gate.yml", MANAGED, 2,
        "the required check that runs conformance-gate.py (0029)"),
    Row(".github/workflows/verdict-requeue.yml", MANAGED, 1,
        "runs requeue-gate.py on the status event; deliberately not a required check (#191)"),
    Row("tools/agent-doctor.py", MANAGED, 2,
        "whether the rails are active or only present, locally and on GitHub (0029)"),
    Row(".editorconfig", MANAGED, 1,
        "the kernel determinism analyzers' severities: a build error in src, off in tests (0029)"),
    Row("global.json", MANAGED, 1,
        "the kernel's SDK pin and roll-forward policy; an engine that must move it adopts it"),
    Row("NuGet.config", MANAGED, 2,
        "package sources and source mapping: supply-chain policy; an extra feed is an adoption"),
    Row("Directory.Build.props", MANAGED, 2,
        "target frameworks, analyzers, warnings-as-errors, determinism and lock-file policy"),
    Row("Directory.Packages.props", ENGINE_OWNED, None,
        "central package management and the test packages an engine bumps; imports the generated pins"),
    Row("{name}.slnx", ENGINE_OWNED, None, "the engine adds projects to its solution"),
    Row("src/{name}/{name}.csproj", ENGINE_OWNED, None, "the engine adds references and files"),
    Row("tests/{name}.Tests/{name}.Tests.csproj", ENGINE_OWNED, None, "the engine adds test references"),
    Row("corpus-map.overlay.json", ENGINE_OWNED, None, "the engine's three fields per entry (0015)"),
    Row(".github/agent-policy.json", ENGINE_OWNED, None,
        "the engine's own rails configuration: labels, review contexts and chain, worktree "
        "variables. Written once so a factory change can never undo a consumer's choice (0029)"),
    Row("src/{name}/packages.lock.json", ENGINE_OWNED, None,
        "written by verify's first restore when absent, then reviewed, committed and relocked by the engine; "
        "re-locked by a produce that changes the generated pins (#94)"),
    Row("tests/{name}.Tests/packages.lock.json", ENGINE_OWNED, None, "the same, for the test project"),
)

# Every version of every managed recipe: path -> {recipe version: SHA-256 of the bytes it wrote}.
# Version 1 of each is what the write-once scaffold wrote before #72. Never remove a version: an
# engine still carrying those bytes is unedited, and is migrated rather than refused.
RECIPE_SHA256 = {
    ".claude/agents/engine-dev.md": {
        1: "22dbac892b04903992d13516e5a08ac04d92d02b0d8d4ce5e4bfa9ef53543287",
        2: "5f0dd905e2b3857115d93196a66a168e17b505f87dda13a7d200f2bc12572bdb",
        3: "c8569477e58633f6e807a4b9be9a00b37a6f315d5b0f1fa8b0a7bc1f36b24b06",
        4: "f2b21c791a783f828f8d4dc3fa17407f6557a15923be9b0b67ce5a94ba69f926",
        5: "3491f1a0bbdd6b4fcb7b0d1e8d3827dfe5f4a19199d8da6ddcdc2b5bc9921521",
    },
    ".claude/agents/repo-steward.md": {
        1: "6a2662ac958da76bb02263914d4e3b293a8dc15837e8a6ffccb14177b013bde7",
    },
    ".claude/agents/rules-conformance.md": {
        1: "95eac2e802b474bdefad5a6053528dceda7465bbacfc946a0dd3c52a09705e78",
        2: "034cc0af3ecb98e9af60a65931102c69546f22ddadfea9c82961bb71fbbf96c2",
        3: "7f91ed4187d6d87621873266741f972a5b9bc8a27e16a248e78eb4de69789a64",
    },
    ".claude/hooks/primary-checkout-guard.py": {
        1: "a263531db502dfad98b38bf1dd90df7b1bec5f22133db016b6f30dc38509d16d",
    },
    ".claude/settings.json": {
        1: "4d410acd10ba5b6ed2d3c6a016cc2cfde1cf8e621da54424755376a80da30aa0",
    },
    "AGENTS.md": {
        1: "06594a3207634553a28ca057ecb53225082e4f111890961e27589c544353e740",
        2: "81f5756c1bff7ca2f1f9091087138fed0204a43e2f30a1e6f05ad4430e2efd48",
        3: "c3576d1cea769505a43794b8f2d42797f230f058b238eda09230f1fd3105ab50",
        4: "b615fbea821a0171f3b7cdc503da561a7f385504da48395fa1efef934c0fc833",
        5: "0bf3bb0f7519ac6cdccf4c03fd11bf65d8b3c0a4e5580917dd5bc7e8f81b1257",
        6: "7da4642b702c6a8f527b043e4cf1d8f54f5ac6efc8840df250e998c40ac152c3",
        7: "d141aa496491ab4eb6702fbdba803f82a4a0e11163c56289be404d9a7eeea8d9",
    },
    "CLAUDE.md": {
        1: "04c07ad36e742fa60efafeca54d20bd96d16b6e338a44e46fad2b679ab8dfd9f",
    },
    "docs/agent-team.md": {
        1: "48baa22a5f1b6bb3f26d6aaed5715782462430b8b5524e1f0737ad627fae219d",
        2: "2972f4cdb30b4549639dc34de2fd47b8b06e0c680ef41e88de701ccfa66abb4d",
        3: "ae9c54d7236adca8507e673d77b51e6431a48f4a3c29af40d7420ea2810e8521",
        4: "1806e2679578deb3f6b59c920e1c209fb5c5606f36a07d1b8b9a942994103379",
    },
    "tools/dispatch-agent.sh": {
        1: "868ce983b51d784a83a6a0fcac7456608b31f0af025c75ac5eeac64a373dca2b",
        2: "5e66ff9229bf31ed43d4a70c957e774696462dba3ff4e7f75b566132a6858cb5",
    },
    "tools/new-issue.sh": {
        1: "382a2f516f81f593e74ed9e57262080c25edbac1a16d542ffb235eb772b10e88",
        2: "2830ba6458df4c34378538d73eadc4d522fb5f5cb7dbb945ef89097d66c9b9ee",
    },
    "tools/entry-packet.py": {
        1: "6e413d4e4143d888e00c1570358c5f6c7404347a173cd023b821f4d2f781835a",
        2: "59f112154a77a8cf574bd8d1ee1e43d39399025308c8f4eb2371d99081e49b20",
        3: "58791e5a923a50c591ef35325a7f45ec8db652f1b09179f5fc28c874b44d230f",
        4: "5ae5e226e92b0f1fe6ce227d58db2987173659d644e4a89667a984c9faee54af",
    },
    "tools/re-produce.sh": {
        1: "2a281f94f81ce141733494a94744caa96c88af3cd9fa848cec21c13e73739499",
        2: "259e860a06e1407b38ff2f302bd657056eb601955e5363b19d30b705f74b7d8e",
    },
    "tools/review-packet.py": {
        1: "2e989c02c1827bf6d3da8fce9a35874e25ea4baf14f62eeb64aab78c30b1f392",
    },
    "tools/pr-policy.py": {
        1: "79a33c7fe1ea8d888e4d6912a43ac60afe285c7a8bf43fbe9f7be87d6947b76e",
        2: "4a0c6677913decb13c8e9499840d5da4935c1725559dd6514d67dd72c8d849bd",
    },
    "tools/record-verdict.py": {
        1: "48f7b11f7fc829cdaebd776a3eb5db04e27cade97c427c6806b72f58805d83db",
    },
    "tools/conformance-gate.py": {
        1: "567972b60f16d1f86c661e97efa56fa2878c9a5aa92fb820c4aea07a402cbd24",
        2: "6e4a57468144caf4eaf74dce4d178a582322235ba37eb04d92bd72ddb929e58a",
    },
    "tools/requeue-gate.py": {
        1: "a4315a5fa76a696ee616e5ef190d6bbec0d023c04e22086082d4031c460aec8d",
    },
    ".github/pull_request_template.md": {
        1: "e2cebc6419d62e2df3b218d76462caf807d6637f2b305ac2aa11153f13304a92",
        2: "8b679be11d7a53d3df4ee29fa687bff03042da01efa46a639da1d70e5dfe4234",
    },
    ".github/workflows/pr-policy.yml": {
        1: "caa3394a473d5fdd45b274176d8e28c48d9f5425176318194ba68fbea8453fa2",
    },
    ".github/workflows/conformance-gate.yml": {
        1: "851d64e8705363b70711b74fe1b25306c3fac1c1e26c88a9805defc3a03042a8",
        2: "d66ae8a37a37874369ac962fbecbf9ac1b98cf0246541a61ea5089b23f8ea702",
    },
    ".github/workflows/verdict-requeue.yml": {
        1: "b1a48c75587dcbcf15638f83a703025c08f5449d9e2611550c4f15a448fcb178",
    },
    "tools/agent-doctor.py": {
        1: "1b6fced99797d165ab0216523bddae183d6e7254f41d5d5f51cdb1d1c3b8913d",
        2: "340004575c29918f4dcbdacc7c1aef7f970e60bb270832901ae501bcb61b0b30",
    },
    ".editorconfig": {
        1: "4109d1ef55053ef656e536d7818934deb73016fbe950f153bae6b2a163591cb2",
    },
    "global.json": {
        1: "12f1cf1c3eef038f55de570dc8f5e321f4ff5306a9281106c43cc60a1f78a371",
    },
    "NuGet.config": {
        1: "b6475c7eb5334ba07f88ad900e82da0ebda9f269733c1c09237a72796c8d77f2",
        2: "e53f00efe0e550fb452b2e1d8d3b1e2f0cdd1de86628eff7d60a813ebfa1818f",
    },
    "Directory.Build.props": {
        1: "1392b57192cfe16ac70aa847f932c52f136765c9ce60ed94254d73dafd0d14ef",
        2: "73c373b1457e4149eb7ab7da1aed49314536ca8945dea8022c1efbd49c7a1a8f",
    },
}


class OwnershipError(Exception):
    """A managed file cannot be written without discarding an edit, or a flag names no managed file."""


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def rows(name):
    """TABLE with `{name}` replaced by the engine name."""
    return tuple(row._replace(pattern=row.pattern.replace("{name}", name)) for row in TABLE)


def _matches(pattern, relative):
    wanted, parts = pattern.split("/"), relative.split("/")
    return len(wanted) == len(parts) and all(fnmatch.fnmatchcase(p, w) for p, w in zip(parts, wanted))


def matching(relative, name):
    """Every row of the table that `relative` (an engine-relative POSIX path) matches."""
    return [row for row in rows(name) if _matches(row.pattern, relative)]


def classify(relative, name):
    """The one row `relative` matches, or None when it matches none. More than one is a table bug."""
    found = matching(relative, name)
    if len(found) > 1:
        raise OwnershipError(f"{relative} matches {len(found)} rows of the ownership table "
                             f"({', '.join(r.pattern for r in found)}); it must match exactly one")
    return found[0] if found else None


def managed_rows(name):
    return [row for row in rows(name) if row.cls == MANAGED]


def adopted(out):
    """Managed paths the engine's provenance.json records as adopted (engine-owned).

    An unreadable or absent record adopts nothing. That is the safe direction: an adopted file
    that has been edited is then refused, naming --adopt, rather than overwritten.
    """
    try:
        with open(os.path.join(out, PROVENANCE), encoding="utf-8") as handle:
            record = json.load(handle)
        items = record.get("engineOwned") or []
        return {item["path"] for item in items if isinstance(item, dict) and item.get("adopted") is True
                and isinstance(item.get("path"), str)}
    except (OSError, ValueError, AttributeError, TypeError, KeyError):
        return set()


def plan_managed(out, name, recipes, adopt=(), reset=()):
    """Decide every managed file for a run into `out`.

    `recipes` maps each managed path to the current recipe's bytes. Returns (writes, managed,
    adopted_now, notes): the bytes to write per path, {path: recipe version} for the files that
    stay managed, the set that is engine-owned by adoption, and a line per decision worth
    logging. Raises OwnershipError, before anything is written, for a flag that names no managed
    file and for every hand-edited managed file neither flag settles.
    """
    table = {row.pattern: row for row in managed_rows(name)}
    if set(recipes) != set(table):
        raise OwnershipError(f"the managed recipes ({sorted(recipes)}) are not the managed rows of the "
                             f"ownership table ({sorted(table)})")
    unknown = sorted(p for p in set(adopt) | set(reset) if p not in table)
    if unknown:
        raise OwnershipError(f"--adopt and --reset name managed files only ({', '.join(sorted(table))}); "
                             f"{', '.join(unknown)} is not one")
    both = sorted(set(adopt) & set(reset))
    if both:
        raise OwnershipError(f"{', '.join(both)} is given to both --adopt and --reset")
    recorded = adopted(out)
    writes, managed, adopted_now, notes, refused = {}, {}, set(), [], []
    for path, row in sorted(table.items()):
        target = os.path.join(out, *path.split("/"))
        current = recipes[path]
        if sha256(current) != RECIPE_SHA256.get(path, {}).get(row.recipe):
            raise OwnershipError(f"the {path} recipe's bytes are not recipe version {row.recipe}'s recorded "
                                 f"hash; a changed recipe needs a new version in the ownership table")
        on_disk = None
        if os.path.isfile(target):
            with open(target, "rb") as handle:
                on_disk = handle.read()
        if path in reset:
            writes[path] = current
            managed[path] = row.recipe
            notes.append(f"reset {path} to managed recipe {row.recipe}")
        elif path in adopt or path in recorded:
            adopted_now.add(path)
            if on_disk is None:
                writes[path] = current
            if path in adopt and path not in recorded:
                notes.append(f"adopted {path}: engine-owned from now on")
        elif on_disk is None:
            writes[path] = current
            managed[path] = row.recipe
        else:
            versions = [v for v, digest in RECIPE_SHA256[path].items() if digest == sha256(on_disk)]
            if not versions:
                refused.append(path)
                continue
            managed[path] = row.recipe
            if on_disk != current:
                writes[path] = current
                notes.append(f"updated managed {path} from recipe {max(versions)} to {row.recipe}")
    if refused:
        raise OwnershipError(
            f"{', '.join(refused)} {'is a managed file' if len(refused) == 1 else 'are managed files'} "
            f"edited by hand: the bytes are no version of the factory's recipe, so produce will neither "
            f"overwrite the edit nor leave a stale policy unnoticed. Pass --adopt <path> to make it the "
            f"engine's own from now on, or --reset <path> to replace it with the current recipe")
    return writes, managed, adopted_now, notes
