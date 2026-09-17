"""M4 of #3: provenance. What an engine was produced from, recorded so it can be recomputed.

`produce` writes `provenance.json` in the engine root, last, after every other step. The
engine embeds it (`<Name>.provenance.json`, from the src project) and a generated test asserts
the embedded copy is byte-identical to the file, so a built assembly carries the record of
what it was built from.

The fields, and where each comes from:

  * `engine.name` -- the `--name` given to `produce` (recompute needs it to re-produce).
  * `factory` -- the rules-factory checkout this module is in:
      - `version`: `X.Y.Z` when HEAD carries a tag `factory/vX.Y.Z` (the highest, if several);
        otherwise `0.0.0-dev+<the first 12 hex digits of HEAD>`. Twelve is fixed rather than
        git's `--short`, whose length grows with the repository.
      - `commit`: the full SHA of HEAD.
      - `dirty`: whether `git status --porcelain` lists anything. `produce` refuses a dirty
        tree unless `--allow-dirty`, and then records `true`. A factory that is not a git
        checkout is refused outright: its commit cannot be named.
  * `map` -- the package id and version from its nuspec, the SHA-256 of the `.nupkg` bytes,
    and the SHA-256 of the map, manifest and consumer checker at the paths the package's
    props name (`map/corpus-map.json`, `map/corpus-manifest.json`, `tools/check-map.py`).
  * `corpus` -- sourceId, contentHash, hashDerivation and asOf of the one corpus, with
    `recomputed: true`: intake derived contentHash from the corpus bytes under
    hashDerivation and it matched; it was not copied from the map.
  * `kernel` -- the RulesKernel version the engine references.
  * `packs` -- `[]`: no rule packs exist yet, and the empty list says so rather than omitting it.
  * `recipes` -- every file under `tools/factory/` (the factory's templates are its Python
    modules), `__pycache__` and `*.pyc` excluded, and `tools/check-map.py` beside it (the
    checker intake runs decides whether there is any output, so it is factory code too, and a
    factory without it is refused), each with its SHA-256, sorted by
    repository-relative POSIX path in ascending byte order; and `digest`, the SHA-256 of the
    UTF-8 text made of one line `<sha256>  <path>\\n` per file in that order (`sha256sum` format).
  * `generated` -- `[{path, sha256}]`, sorted by path, for every file `produce` wrote on this
    run under the engine directory whose ownership class (ownership.py, decision 0018) is
    generated, except `provenance.json` itself. Managed and engine-owned files are not listed
    here: a re-run does not rewrite an engine-owned file, so hashing it here would make an
    engine's own edits (its overlay above all) look like tampering, and a managed file is
    recorded in `managed`. Leaving them out is only safe because neither says anything the
    inputs decide: the kernel and map pins and the map's PackageReference live in the generated
    `RulesFactory.Packages.g.props`, which is listed here like any `*.g.cs` (#66). The list is
    not hard-coded: `Recorder` notes every path opened for writing (or renamed into place) while
    `produce` runs, so a later step's output is picked up without touching this module, and a
    written path the ownership table does not classify is refused. Its root is the staging copy
    every step writes into (transaction.py), so the recorded paths, relative to that root, are
    the paths the commit puts in place under `--out`.
    Writes made by a child process are not seen; no step makes any.
  * `managed` -- `[{path, recipeVersion, sha256}]`, sorted by path, for every managed file that
    is still managed (not adopted): the recipe version it holds and the SHA-256 of its bytes,
    which are that recipe's. This is the one place a managed file is hashed.
  * `engineOwned` -- `[{path, adopted}]`, sorted by path, for every engine-owned file of the
    ownership table present in the engine (the lock files once verify's restore wrote them;
    produce's `after_restore` hook rebuilds the whole record, this section included), with `adopted: true` for a managed file the engine adopted (--adopt). The
    next `produce` reads the adoptions back from here. No hash: every engine-owned file is a
    build input, hashed once in `buildInputs`.
  * `buildInputs` -- `[{path, sha256}]`, sorted by path in ascending byte order, for every file
    under the engine directory that the .NET build reads as configuration -- or that the agent
    rails read as configuration, which is `.github/agent-policy.json` and nothing else (decision
    0029) -- and that the engine owns, as it stands when `produce` finishes. The rule is `is_build_input`, its only
    definition: at any depth, with `bin`, `obj`, `.git` and `.vs` pruned, a file named
    `global.json`, `NuGet.config` (any case, as NuGet finds it), `packages.lock.json`,
    `Directory.Build.rsp`, `.editorconfig`, `.globalconfig`, `corpus-map.overlay.json` or
    `agent-policy.json`, or
    ending in `.props`, `.targets`, `.sln`, `.slnx`, `.csproj`, `.fsproj` or `.vbproj`; minus
    `provenance.json` and every file already in `generated` or `managed` (RulesFactory.Packages.g.props
    and a managed global.json are the factory's, and are listed there, once). The section does
    not say the factory wrote these files: some are the engine-owned scaffold (or an adopted
    managed file), which the engine may have edited since, and the rest (lock files, an
    engine's own `.targets`) the factory never writes at all. It says which
    bytes were there. Rule by name rather than a list of the scaffold, so an input the engine
    adds is covered without anyone remembering to add it.
    Lock files are the one input `produce` cannot see coming: it runs no restore, so the first
    `produce` of an engine records none, and the restore after it (`validate.sh lock`) writes
    them. Holding a record to lock files it never saw would make every engine mismatch from its
    first restore until someone re-ran `produce`, and a check that always fails is ignored. So a
    record that lists no `packages.lock.json` makes no claim about lock files, and recompute
    leaves lock files out on both sides; a record that lists any is held to all of them, so
    after that a lock file changed, removed or added is a named mismatch. Re-running `produce`
    once the lock files are written is what brings them under the record.
  * `randomness` -- the corpus's declaration in its manifest (decision 0019), as intake read it:
    `"none"` (the engine's gate refuses RulesKernel.Randomness) or `"seeded"` (the engine may
    draw, through that package, pinned at the kernel's version).
  * `rulings` -- present only when the overlay holds an owner's ruling (decision 0027), so no other
    record changes: `[{id, entry, span, answer, ruledBy, ruledOn, record, recordSha256}]` in overlay
    order, which answers in the engine are its owner's and not the corpus's. `recordSha256` hashes
    the decision record as it stood when `produce` ran, so a record edited since is a mismatch named
    `rulings` until the engine is produced again.

Deterministic: no timestamps, no machine paths; two runs from the same inputs are identical.

`recompute(engine_dir, produce_into, package)` re-produces the engine in a scratch copy from
the same package and the engine's committed corpus, and returns every mismatch as a line naming
the field (`map.nupkgSha256`, `corpus.contentHash`, `recipes.files[tools/factory/generate.py]`,
`generated[src/X/Generated/MapEntries.g.cs]`, `managed[global.json]`, `buildInputs[X.slnx]`, ...).
It also hashes each recorded generated file on disk, so a hand edit to a generated file (a pin in
RulesFactory.Packages.g.props included) is caught even though re-producing would undo it; each
recorded managed file, so a hand edit is named even though re-producing refuses it; and
it applies the build-input rule to the engine on disk, so an edited, removed or added build
input is named `buildInputs[<path>]` even when the edit makes re-producing refuse.
An empty list means the record is true of the engine and the factory running the check.

What a match proves, and what it does not. The record carries two different guarantees:

  * generation provenance (`factory`, `map`, `corpus`, `kernel`, `recipes`, `generated`): the
    generated files are exactly what this factory commit makes from this package and corpus;
  * build-input provenance (`managed`, `buildInputs`): every file in the engine that the build reads as
    configuration -- the SDK pin, package sources, MSBuild props and targets, projects and
    solution, the overlay, and the lock files once recorded -- has the recorded bytes, whoever
    wrote them.

Together they say the engine's source tree is the recorded one. They do not say what a machine
did with it: which SDK is actually installed and selected (global.json names a version; nothing
hashes a toolchain), what restore fetched beyond the content hashes the lock files pin (and,
before lock files are recorded, nothing about packages beyond their versions), environment
variables and command-line properties (`CI`, `-p:...`), files outside the engine directory that
MSBuild or NuGet also read (a `Directory.Build.props` or `NuGet.config` in a parent directory,
the user-level NuGet.config), or that a given assembly was built from this tree: the embedded
copy of provenance.json ties an assembly to a record, not to a build.

Standard library only.
"""
import builtins
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import tempfile

import generate
import intake as intake_step
import ownership

FILE_NAME = "provenance.json"
FORMAT = 3  # 2: buildInputs (#69); 3: managed and engineOwned (#72)
FACTORY_DIR = os.path.dirname(os.path.abspath(__file__))
TAG = re.compile(r"^factory/v(\d+)\.(\d+)\.(\d+)$")
SHORT_SHA = 12
DIGEST_RULE = ("sha256 over UTF-8 lines '<sha256>  <path>\\n', one per recipe file, "
               "in ascending byte order of path")
SKIP_DIRS = frozenset({"bin", "obj", ".git", ".vs"})
COPY_IGNORE = shutil.ignore_patterns(*sorted(SKIP_DIRS))
# The build-input rule (`buildInputs` above; `is_build_input` applies it). Names compare casefolded.
BUILD_INPUT_NAMES = frozenset({"global.json", "nuget.config", "packages.lock.json", "directory.build.rsp",
                               ".editorconfig", ".globalconfig", generate.OVERLAY_NAME.lower(),
                               generate.AGENT_POLICY.rsplit("/", 1)[-1].lower()})
BUILD_INPUT_SUFFIXES = (".props", ".targets", ".sln", ".slnx", ".csproj", ".fsproj", ".vbproj")
LOCK_FILE = "packages.lock.json"


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    with open(path, "rb") as handle:
        return sha256(handle.read())


# --- the factory -----------------------------------------------------------------------------


def _git(factory_dir, *args):
    try:
        done = subprocess.run(["git", "-C", factory_dir, *args], stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise intake_step.Refused(f"cannot run git to identify the factory: {error}")
    if done.returncode != 0:
        raise intake_step.Refused(f"the factory at {factory_dir} is not a git checkout whose commit can be "
                                  f"named (git {' '.join(args)}: {done.stderr.strip()})")
    return done.stdout


def factory_state(factory_dir=FACTORY_DIR):
    commit = _git(factory_dir, "rev-parse", "HEAD").strip()
    tags = []
    for line in _git(factory_dir, "tag", "--points-at", "HEAD").splitlines():
        match = TAG.match(line.strip())
        if match:
            tags.append(tuple(int(part) for part in match.groups()))
    version = ".".join(map(str, max(tags))) if tags else f"0.0.0-dev+{commit[:SHORT_SHA]}"
    dirty = bool(_git(factory_dir, "status", "--porcelain").strip())
    top = os.path.realpath(_git(factory_dir, "rev-parse", "--show-toplevel").strip())
    return {"version": version, "commit": commit, "dirty": dirty, "_top": top}


def require_clean(state, allow_dirty):
    if state["dirty"] and not allow_dirty:
        raise intake_step.Refused(f"the factory working tree ({state['_top']}) has uncommitted changes, so "
                                  f"provenance could not name what produced the engine; commit them, or "
                                  f"pass --allow-dirty to produce anyway and record dirty: true")


# Factory code outside tools/factory that decides the output, relative to tools/factory's parent.
RECIPES_BESIDE = ("check-map.py",)


def recipes(factory_dir, top):
    files = []
    for name in RECIPES_BESIDE:
        path = os.path.join(os.path.dirname(os.path.abspath(factory_dir)), name)
        if not os.path.isfile(path):
            raise intake_step.Refused(f"the factory has no {path}, so provenance could not name the checker "
                                      f"intake runs")
        files.append({"path": os.path.relpath(os.path.realpath(path), top).replace(os.sep, "/"),
                      "sha256": sha256_file(path)})
    for directory, dirs, names in os.walk(factory_dir):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in names:
            if name.endswith(".pyc"):
                continue
            path = os.path.join(directory, name)
            files.append({"path": os.path.relpath(os.path.realpath(path), top).replace(os.sep, "/"),
                          "sha256": sha256_file(path)})
    files.sort(key=lambda f: f["path"].encode("utf-8"))
    text = "".join(f"{f['sha256']}  {f['path']}\n" for f in files)
    return {"files": files, "digestRule": DIGEST_RULE, "digest": sha256(text.encode("utf-8"))}


# --- what produce writes ---------------------------------------------------------------------


class Recorder:
    """Notes every file opened for writing, or renamed into place, under `out` while active."""

    WRITE_MODES = set("wax+")

    def __init__(self, out):
        self.root = os.path.realpath(os.path.abspath(out))
        self.paths = set()

    def _note(self, target):
        if isinstance(target, (str, bytes, os.PathLike)):
            path = os.path.realpath(os.path.abspath(os.fsdecode(target)))
            if path.startswith(self.root + os.sep):
                self.paths.add(os.path.relpath(path, self.root).replace(os.sep, "/"))

    def __enter__(self):
        self._saved = (builtins.open, io.open, os.replace, os.rename)
        real_open, _, real_replace, real_rename = self._saved

        def recording_open(file, mode="r", *args, **kwargs):
            if self.WRITE_MODES & set(mode):
                self._note(file)
            return real_open(file, mode, *args, **kwargs)

        def recording_replace(src, dst, *args, **kwargs):
            self._note(dst)
            return real_replace(src, dst, *args, **kwargs)

        def recording_rename(src, dst, *args, **kwargs):
            self._note(dst)
            return real_rename(src, dst, *args, **kwargs)

        builtins.open = io.open = recording_open
        os.replace, os.rename = recording_replace, recording_rename
        return self

    def __exit__(self, *exc):
        builtins.open, io.open, os.replace, os.rename = self._saved
        return False


# --- build inputs ----------------------------------------------------------------------------


def is_build_input(relative):
    """Whether the engine-relative POSIX path `relative` is a build input: the one rule.

    `agent-policy.json` is here for the reason the others are: it is configuration the engine owns
    and something reads at face value, so what it held at a commit has to be recoverable from the
    record. The reader is the rails rather than MSBuild (0029).
    """
    parts = relative.split("/")
    if any(part in SKIP_DIRS for part in parts[:-1]):
        return False
    name = parts[-1].lower()
    return name in BUILD_INPUT_NAMES or name.endswith(BUILD_INPUT_SUFFIXES)


def is_lock_file(relative):
    return relative.split("/")[-1].lower() == LOCK_FILE


def build_inputs(root, exclude=()):
    """`[{path, sha256}]` of every build input under `root`, sorted, minus `exclude` and provenance.json.

    Symlinked directories are followed, as transaction.py follows them when staging, so what is
    hashed is what the build would read.
    """
    exclude = set(exclude) | {FILE_NAME}
    found = []
    for directory, dirs, names in os.walk(root, followlinks=True):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in names:
            path = os.path.join(directory, name)
            relative = os.path.relpath(path, root).replace(os.sep, "/")
            if relative in exclude or not is_build_input(relative) or not os.path.isfile(path):
                continue
            found.append({"path": relative, "sha256": sha256_file(path)})
    found.sort(key=lambda f: f["path"].encode("utf-8"))
    return found


def claimed(recorded_inputs, inputs):
    """`inputs` as far as the record makes a claim: without lock files when it lists none (above)."""
    if any(isinstance(item, dict) and is_lock_file(str(item.get("path", ""))) for item in recorded_inputs):
        return inputs
    return [item for item in inputs if not is_lock_file(item["path"])]


# --- the embedded copy -----------------------------------------------------------------------


PROVENANCE_CS = """namespace @NAME@;

/// <summary>The engine's provenance.json (rules-factory #3, M4), embedded when the assembly was built.</summary>
public static class EngineProvenance
{
    /// <summary>The manifest resource name provenance.json is embedded under.</summary>
    public const string ResourceName = "@NAME@.provenance.json";

    /// <summary>The embedded provenance.json, byte for byte.</summary>
    /// <returns>The file's bytes.</returns>
    /// <exception cref="InvalidOperationException">The assembly was built without it.</exception>
    public static byte[] ReadBytes()
    {
        using var stream = typeof(EngineProvenance).Assembly.GetManifestResourceStream(ResourceName)
            ?? throw new InvalidOperationException($"the assembly has no embedded {ResourceName}");
        using var copy = new MemoryStream();
        stream.CopyTo(copy);
        return copy.ToArray();
    }
}
"""

PROVENANCE_TESTS_CS = """using Xunit;

namespace @NAME@.Tests;

public sealed class ProvenanceTests
{
    [Fact]
    public void The_embedded_provenance_is_byte_identical_to_provenance_json_in_the_engine_root() =>
        Assert.Equal(File.ReadAllBytes(EngineRootFile("provenance.json")), EngineProvenance.ReadBytes());

    private static string EngineRootFile(string name)
    {
        for (var directory = new DirectoryInfo(AppContext.BaseDirectory); directory is not null; directory = directory.Parent)
        {
            var candidate = Path.Combine(directory.FullName, name);
            if (File.Exists(candidate) && File.Exists(Path.Combine(directory.FullName, "@NAME@.slnx")))
            {
                return candidate;
            }
        }

        throw new FileNotFoundException($"no {name} beside @NAME@.slnx above {AppContext.BaseDirectory}");
    }
}
"""


def embedding(model):
    """The generated C# that reads and tests the embedded copy (the src project embeds the file)."""
    name = model.name
    return {
        f"src/{name}/Generated/Provenance.g.cs": model.header + PROVENANCE_CS.replace("@NAME@", name),
        f"tests/{name}.Tests/Generated/ProvenanceTests.g.cs": model.header + PROVENANCE_TESTS_CS.replace("@NAME@", name),
    }


def emit(model, out):
    for relative, text in embedding(model).items():
        path = os.path.join(out, *relative.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(text.encode("utf-8"))


# --- the record ------------------------------------------------------------------------------


def build(state, result, model, recorder, factory_dir=FACTORY_DIR):
    corpus = result.corpus
    root = recorder.root
    generated_files = []
    for relative in sorted(recorder.paths, key=lambda p: p.encode("utf-8")):
        try:
            row = ownership.classify(relative, model.name)
        except ownership.OwnershipError as error:
            raise generate.GenerationError(str(error))
        if row is None:
            raise generate.GenerationError(f"produce wrote {relative}, which the ownership table "
                                           f"(tools/factory/ownership.py) does not classify; add it to the table")
        if relative == FILE_NAME or row.cls != ownership.GENERATED:
            continue
        generated_files.append({"path": relative, "sha256": sha256_file(os.path.join(root, *relative.split("/")))})
    managed = [{"path": path, "recipeVersion": version, "sha256": sha256_file(os.path.join(root, *path.split("/")))}
               for path, version in sorted(model.managed.items(), key=lambda kv: kv[0].encode("utf-8"))]
    # Only those present: the lock files exist once verify's restore has written them.
    owned = sorted({row.pattern for row in ownership.rows(model.name) if row.cls == ownership.ENGINE_OWNED
                    and os.path.isfile(os.path.join(root, *row.pattern.split("/")))}
                   | set(model.adopted), key=lambda p: p.encode("utf-8"))
    return {
        "provenanceFormat": FORMAT,
        "engine": {"name": model.name},
        "factory": {"version": state["version"], "commit": state["commit"], "dirty": state["dirty"]},
        "map": {
            "packageId": result.package_id,
            "version": result.version,
            "nupkgSha256": result.nupkg_sha256,
            "files": [{"role": role, "path": result.part_paths[role], "sha256": sha256(raw)}
                      for role, raw in (("map", result.map_raw), ("manifest", result.manifest_raw),
                                        ("checker", result.checker_raw))],
        },
        "corpus": {
            "sourceId": corpus["sourceId"],
            "contentHash": corpus["contentHash"],
            "hashDerivation": corpus["hashDerivation"],
            "asOf": corpus.get("asOf"),
            "recomputed": True,
        },
        "kernel": {"packageId": "RulesKernel", "version": generate.KERNEL_VERSION},
        "packs": [],
        "recipes": recipes(factory_dir, state["_top"]),
        "generated": generated_files,
        "managed": managed,
        "engineOwned": [{"path": path, "adopted": path in model.adopted} for path in owned],
        "buildInputs": build_inputs(root, {g["path"] for g in generated_files} | set(model.managed)),
        "randomness": result.randomness,
        **({"rulings": [{"id": r["id"], "entry": r["entry"], "span": r["span"], "answer": r["answer"],
                         "ruledBy": r["ruledBy"], "ruledOn": r["ruledOn"], "record": r["record"],
                         "recordSha256": sha256_file(os.path.join(root, *r["record"].split("/")))}
                        for r in model.rulings]} if getattr(model, "rulings", None) else {}),
    }


def serialize(document):
    return (json.dumps(document, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def write(out, document):
    with open(os.path.join(out, FILE_NAME), "wb") as handle:
        handle.write(serialize(document))


# --- recompute -------------------------------------------------------------------------------


def _keyed(items):
    """A list of objects keyed by path (or role) compares by that key, not by position."""
    if items and all(isinstance(i, dict) and ("path" in i or "role" in i) for i in items):
        return {str(i.get("path", i.get("role"))): {k: v for k, v in i.items() if k not in ("path",)} for i in items}
    return None


def diff(recorded, actual, field=""):
    if isinstance(recorded, dict) and isinstance(actual, dict):
        out = []
        for key in list(recorded) + [k for k in actual if k not in recorded]:
            name = f"{field}.{key}" if field else key
            if key not in actual:
                out.append(f"{name}: recorded {json.dumps(recorded[key])}, recomputed nothing")
            elif key not in recorded:
                out.append(f"{name}: recorded nothing, recomputed {json.dumps(actual[key])}")
            else:
                out.extend(diff(recorded[key], actual[key], name))
        return out
    if isinstance(recorded, list) and isinstance(actual, list):
        left, right = _keyed(recorded), _keyed(actual)
        if left is not None and right is not None:
            out = []
            for key in sorted(set(left) | set(right)):
                name = f"{field}[{key}]"
                if key not in right:
                    out.append(f"{name}: recorded, recomputed nothing")
                elif key not in left:
                    out.append(f"{name}: not recorded, recomputed {json.dumps(right[key])}")
                else:
                    out.extend(diff(left[key], right[key], name))
            if [str(i.get("path", i.get("role"))) for i in recorded] != [str(i.get("path", i.get("role"))) for i in actual] \
                    and set(left) == set(right):
                out.append(f"{field}: recorded in a different order")
            return out
    if recorded != actual:
        return [f"{field}: recorded {json.dumps(recorded)}, recomputed {json.dumps(actual)}"]
    return []


def recompute(engine_dir, produce_into, package=None):
    """Every way `engine_dir/provenance.json` is not what re-producing gives; [] when it is.

    `produce_into(package, corpus, name, out)` runs the whole of `produce` with --allow-dirty and
    returns the provenance document it wrote (raising intake.Refused or GenerationError).
    """
    path = os.path.join(engine_dir, FILE_NAME)
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
        recorded = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as error:
        return [f"{FILE_NAME}: cannot be read ({error})"]
    if not isinstance(recorded, dict):
        return [f"{FILE_NAME}: not a JSON object"]
    mismatches = []
    if raw != serialize(recorded):
        mismatches.append(f"{FILE_NAME}: not in the factory's canonical form (edited by hand?)")

    # Generated files on disk: re-producing rewrites them, so a hand edit is only visible here.
    for item in recorded.get("generated") or []:
        where = os.path.join(engine_dir, *str(item.get("path")).split("/"))
        if not os.path.isfile(where):
            mismatches.append(f"generated[{item.get('path')}]: recorded, missing on disk")
        elif sha256_file(where) != item.get("sha256"):
            mismatches.append(f"generated[{item.get('path')}].sha256: recorded {item.get('sha256')}, "
                              f"on disk {sha256_file(where)}")

    # Managed files on disk: a hand edit makes re-producing refuse, so it is only named here.
    for item in recorded.get("managed") or []:
        if not isinstance(item, dict):
            continue
        where = os.path.join(engine_dir, *str(item.get("path")).split("/"))
        if not os.path.isfile(where):
            mismatches.append(f"managed[{item.get('path')}]: recorded, missing on disk")
        elif sha256_file(where) != item.get("sha256"):
            mismatches.append(f"managed[{item.get('path')}].sha256: recorded {item.get('sha256')}, "
                              f"on disk {sha256_file(where)}")

    # Build inputs on disk, by the same rule, so an edit that makes re-producing refuse is still
    # named. Re-producing below hashes the scratch copy, which gives the same lines (not repeated).
    recorded_inputs = recorded.get("buildInputs")
    recorded_generated = {str(g.get("path")) for key in ("generated", "managed")
                          for g in recorded.get(key) or [] if isinstance(g, dict)}
    if isinstance(recorded_inputs, list):
        on_disk = claimed(recorded_inputs, build_inputs(engine_dir, recorded_generated))
        mismatches.extend(diff(recorded_inputs, on_disk, "buildInputs"))

    corpus = recorded.get("corpus") or {}
    corpus_files = [g["path"] for g in recorded.get("generated") or [] if str(g.get("path", "")).startswith("corpus/")]
    if len(corpus_files) != 1:
        return mismatches + [f"generated: names {len(corpus_files)} corpus/ files; exactly one is the corpus"]
    corpus_path = os.path.join(engine_dir, *corpus_files[0].split("/"))
    derive = intake_step.HASH_DERIVATIONS.get(corpus.get("hashDerivation"))
    if derive is None:
        mismatches.append(f"corpus.hashDerivation: {corpus.get('hashDerivation')!r} cannot be computed")
    elif os.path.isfile(corpus_path):
        with open(corpus_path, "rb") as handle:
            actual = derive(handle.read())
        if actual != corpus.get("contentHash"):
            mismatches.append(f"corpus.contentHash: recorded {corpus.get('contentHash')}, {corpus_files[0]} "
                              f"gives {actual} under {corpus.get('hashDerivation')}")

    source = recorded.get("map") or {}
    name = (recorded.get("engine") or {}).get("name")
    spec = package or f"{source.get('packageId')}@{source.get('version')}"
    with tempfile.TemporaryDirectory(prefix="factory-recompute-") as scratch:
        copy = os.path.join(scratch, "engine")
        shutil.copytree(engine_dir, copy, ignore=COPY_IGNORE)
        try:
            actual = produce_into(spec, os.path.join(copy, *corpus_files[0].split("/")), name, copy)
        except (intake_step.Refused, intake_step.Usage, generate.GenerationError) as error:
            return mismatches + [f"produce refused to re-produce the engine, so nothing else was compared: {error}"]
    if isinstance(recorded_inputs, list) and isinstance(actual.get("buildInputs"), list):
        actual = {**actual, "buildInputs": claimed(recorded_inputs, actual["buildInputs"])}
        # engineOwned names the lock files too; the same no-claim rule applies to it (#72).
        if isinstance(actual.get("engineOwned"), list):
            actual["engineOwned"] = claimed(recorded_inputs, actual["engineOwned"])
    for line in diff(recorded, actual):
        if line not in mismatches:
            mismatches.append(line)
    return mismatches
