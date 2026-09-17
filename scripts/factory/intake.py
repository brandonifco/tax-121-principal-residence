"""M1 of #3: intake. Open a map package, prove the corpus in hand is the one it was mapped from.

An engine is only as right as the correspondence between its map and its corpus, so nothing
is scaffolded until five things are shown, in this order, and any one that is not shown is a
refusal rather than a warning:

  1. **The package is a map package.** A `.nupkg` built by `tools/pack-map.py` (0015): its
     `build/<id>.props` declares exactly one `RulesFactoryMap` item, and the map, manifest and
     `ConsumerChecker` that item names are all inside the archive. A package without its
     checker (pre-2.0.0 backgammon, or a hand-built zip) is not one an engine's gate can use
     (#51), so it is refused, not tolerated. The checker's bytes are read so provenance can
     record their digest; they are never run (below).
  2. **The map is in a schemaVersion this factory reads.** The supported set is
     `SCHEMA_VERSIONS` in the factory's own `tools/check-map.py`, not a copy kept here. A map in
     any other version is refused, naming the versions that would be accepted.
  3. **The corpus may be committed and published, and is verifiable here.** The map cites
     exactly one corpus, and the manifest declares it. Its `licence` is public domain or an open
     licence the factory admits (`licence_class`, decision 0028): a corpus whose licence does not
     permit committing and publishing its text and its map is refused, whatever else it declares.
     Its `verification` is `committed-copy` (0013). A `local-copy` corpus is NOT VERIFIED: an
     engine produced from it could not re-derive its own baseline in CI.
  4. **The corpus file is the baseline.** The map's `baseline` agrees with the manifest, and
     the file given on the command line hashes to `contentHash` under `hashDerivation`. A
     derivation this module does not know is refused -- a digest computed the wrong way is
     indistinguishable from a changed corpus.
  5. **The corpus declares whether its engine may draw random values** (0019): `randomness` is
     `none` or `seeded`. A package whose manifest predates the field declares nothing, and is
     refused rather than read as `none`: the answer is the corpus's, and a default would be the
     factory's.
  6. **The factory's own checker passes, in its consumer phase**, on the packaged map and
     manifest. Before any overlay exists this is the map exactly as published, so a failure
     here means the map does not hold under the checks its engine will run, and no engine
     should be built on it.

**A package is data, never code (0016).** Nothing here executes, imports or `exec`s a byte
that came out of a package: the map and manifest are parsed as JSON, and the checker that
judges them is `tools/check-map.py` beside this factory, loaded from the factory's own
checkout and versioned with it. The package's `ConsumerChecker` is for the engine's build,
which chose that package by exact version and lock-file hash. The factory has chosen nothing
yet when it opens a package, so running what the package names would hand the package the
privileges of whoever runs the factory before a single claim in it had been checked.

**Nothing is read without a limit (#187).** All six checks above run on bytes intake already
holds, so the size of what it takes in is the one thing it must decide before it has verified
anything. A download is streamed to disk under `MAX_PACKAGE_BYTES` and hashed as it streams; a
member is refused unread when it declares more than `MAX_MEMBER_BYTES` or a compression ratio
over `MAX_COMPRESSION_RATIO`. The package the operator names is theirs, so this is about not
exhausting their machine, not about trust.

What intake cannot do: tell whether the map is *right* about the corpus (the publish gate's
locator checkers and review did that), or whether a newer version of the package exists.

Standard library only.
"""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import re
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

FLAT_CONTAINER = "https://api.nuget.org/v3-flatcontainer"

# What each `hashDerivation` covers, and how to recompute it from the file an engine commits.
#
# Both derivations in use today are SHA-256 over the file's bytes exactly as retrieved from
# the manifest's `retrievedFrom`; their names differ because the *bytes* differ from what a
# reader might assume, and that is the whole point of naming a derivation (corpus-map.md):
#
#   * ecfr-versioner-xml -- the XML document the eCFR versioner API serves for the part and
#     date, not the rendered HTML or the printed volume (examples/faa-part-107/README.md);
#   * gutenberg-plain-text-including-boilerplate -- the Project Gutenberg `.txt.utf-8`
#     including its licence header and footer, not the work text alone
#     (examples/hoyle-backgammon/README.md, finding 6).
#
# A derivation that needs normalisation (stripping boilerplate, canonicalising XML) gets its
# own function here; it must never be approximated by the raw-bytes one.
#
# This is the only table. Every engine's gate (recipe/engine-gate.py, `posture`) imports it from
# the copy of this file produce vendors at scripts/factory/intake.py, so a derivation admitted here
# is one every engine's gate can recompute (#106). Keep this module importable standalone, standard
# library only, from that directory.
def _sha256_of_bytes(data):
    return hashlib.sha256(data).hexdigest()


HASH_DERIVATIONS = {
    "ecfr-versioner-xml": _sha256_of_bytes,
    "gutenberg-plain-text-including-boilerplate": _sha256_of_bytes,
    # SHA-256 over the committed page-marked text, byte for byte -- which is *not* what was
    # retrieved: WotC publishes a PDF, and examples/srd-52-combat/extract.py derives the text
    # from it with pdftotext 24.02.0 and a `{N}` marker per page. The raw-bytes function is exact
    # here because the committed file is the derivation's output; the PDF's own digest is the
    # manifest's `sourcePdf.sha256`, and `extract.py --check` holds the two together.
    "srd-5.2.1-pdftotext-24.02.0-page-marked": _sha256_of_bytes,
}

# What a manifest may declare as a corpus's `randomness` (decision 0019). `seeded`: an engine may
# draw, and only through RulesKernel.Randomness's seeded, replayable source.
RANDOMNESS = ("none", "seeded")

# Decision 0028: the factory admits a corpus only when its licence permits committing and publishing
# its text and its map. The class is read from the leading identifier of the manifest's `licence`
# (before any whitespace, `;`, `,` or closing `.`): `public-domain`, or a `public-domain-` form that
# says whose (`public-domain-us-government`), is public domain; an identifier in OPEN_LICENCES is open.
# Anything else, a missing `licence` included, is neither, and is refused. An open licence is added
# here only with a decision that admits it.
PUBLIC_DOMAIN = "public-domain"
OPEN_LICENCES = ("CC-BY-4.0", "CC0-1.0")
LICENCE_IDENTIFIER = re.compile(r"\A([A-Za-z0-9][A-Za-z0-9.-]*?)\.?(?=[\s;,]|\Z)")

# The factory's own checker: tools/check-map.py, one directory above this package. It is a
# hyphenated script rather than a module, so it is loaded by path, once, on first use.
CHECKER_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "check-map.py")
_checker_module = None

PACKAGE_REF = re.compile(r"^(?P<id>[A-Za-z0-9_.-]+)@(?P<version>[0-9A-Za-z.+-]+)$")
THIS_DIR = "$(MSBuildThisFileDirectory)"

# How much of a package intake will take in before it has verified anything (#187). Every check
# below -- the digest, the props, the schema version, the consumer phase -- happens after the
# bytes are already here, so a package or a mirror that is hostile or merely broken could
# exhaust memory or disk before a single claim in it had been read. These bound that window.
#
# The numbers are sized off what a map package this factory builds actually weighs, with room
# for maps far larger than any written yet. Packing examples/ today:
#
#   srd-52-combat  235 KB, largest member map/corpus-map.json at 108 KB
#   faa-part-107   205 KB, largest member tools/check-map.py  at 105 KB
#   hoyle-backgammon 185 KB, same checker
#
# and every member deflates by at most 5.1x (the maps; the checker 3.7x, the XML and props under
# 3x). pack-map.py stores rather than deflates, so packages built here sit at ratio 1.0; a
# package repacked by another tool will not.
#
# They are constants, not options. This is a refusal boundary, and a limit an operator can raise
# is one an attacker's README can tell them to raise ("if intake refuses, set the cap higher").
# A real map that outgrows these wants a considered change here, not a flag at the call site.
MAX_PACKAGE_BYTES = 64 * 1024 * 1024      # ~280x the largest package this factory builds
MAX_MEMBER_BYTES = 8 * 1024 * 1024        # ~75x the largest member; a map is JSON, not media
MAX_COMPRESSION_RATIO = 100               # real members reach 5.1x; a zip bomb reaches 1000x
DOWNLOAD_CHUNK = 1024 * 1024


class Refused(Exception):
    """Intake did not pass. Nothing is produced."""


class Usage(Exception):
    """The inputs are not usable at all (missing file, unreadable archive)."""


class Intake:
    """Everything later milestones read, established as true of each other."""

    def __init__(self, **fields):
        self.__dict__.update(fields)


def _note(log, message):
    if log is not None:
        print(message, file=log, flush=True)


# --- locating the package ----------------------------------------------------------------


def _global_packages_folder():
    return os.environ.get("NUGET_PACKAGES") or os.path.join(os.path.expanduser("~"), ".nuget", "packages")


def sha256_of_file(path):
    """The file's SHA-256, read a chunk at a time: a .nupkg is never held whole in memory."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(DOWNLOAD_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(url, target):
    """Stream `url` to `target`, hashing as it goes; refuse past MAX_PACKAGE_BYTES (#187).

    Hashed while streaming rather than re-read afterwards, and capped while streaming rather
    than checked afterwards: by the time a whole `response.read()` had returned, the memory or
    the disk is already spent. What is written before the cap is reached is removed, so a
    refusal leaves no half a package behind for anything else to pick up.
    """
    digest, total = hashlib.sha256(), 0
    try:
        with urllib.request.urlopen(url, timeout=60) as response, open(target, "wb") as handle:
            for chunk in iter(lambda: response.read(DOWNLOAD_CHUNK), b""):
                total += len(chunk)
                if total > MAX_PACKAGE_BYTES:
                    raise Refused(f"{url} is larger than {MAX_PACKAGE_BYTES} bytes, the most intake will "
                                  f"download; nothing in a package is verified until it is here, so the "
                                  f"download is stopped and the partial file removed")
                digest.update(chunk)
                handle.write(chunk)
    except BaseException as error:
        with contextlib.suppress(OSError):
            os.remove(target)
        if isinstance(error, OSError):
            raise Usage(f"cannot fetch {url}: {error}")
        raise
    return digest.hexdigest()


def resolve_package(spec, download_dir, log=None):
    """(`.nupkg` path, its SHA-256) for `spec`: a file path, or `Id@Version` from the cache or nuget.org."""
    if os.path.isfile(spec):
        path = os.path.abspath(spec)
        return path, sha256_of_file(path)
    match = PACKAGE_REF.match(spec)
    if not match:
        raise Usage(f"--package {spec!r} is neither a .nupkg file nor Id@Version")
    lower_id, version = match["id"].lower(), match["version"].lower()
    name = f"{lower_id}.{version}.nupkg"
    cached = os.path.join(_global_packages_folder(), lower_id, version, name)
    if os.path.isfile(cached):
        _note(log, f"package {spec} from the NuGet global packages folder: {cached}")
        return cached, sha256_of_file(cached)
    url = f"{FLAT_CONTAINER}/{lower_id}/{version}/{name}"
    target = os.path.join(download_dir, name)
    _note(log, f"package {spec} from {url}")
    return target, _download(url, target)


# --- reading the package -----------------------------------------------------------------


def _props_path(ref):
    """`$(MSBuildThisFileDirectory)../map/x.json` -> `map/x.json`, relative to the archive root."""
    if not isinstance(ref, str) or not ref.startswith(THIS_DIR):
        raise Refused(f"RulesFactoryMap path {ref!r} is not relative to $(MSBuildThisFileDirectory)")
    joined = os.path.normpath(os.path.join("build", ref[len(THIS_DIR):].replace("\\", "/")))
    if joined.startswith(".."):
        raise Refused(f"RulesFactoryMap path {ref!r} leaves the package")
    return joined.replace(os.sep, "/")


def _read_member(archive, name):
    """One member's bytes, refusing an oversized or over-compressed one *before* reading it (#187).

    This runs on every member intake reads, whatever the package's provenance: a downloaded one
    is capped on the way in, but one named on the command line or taken from the NuGet cache is
    not, and either can carry a member that decompresses to more memory than the machine has.

    Two checks, then the read:

      * the declared uncompressed size, against MAX_MEMBER_BYTES;
      * the declared ratio, against MAX_COMPRESSION_RATIO -- a member can sit under the size cap
        and still be a bomb relative to the bytes intake paid for it.

    Both read the archive's own declarations, which the package controls, so checking them looks
    like trusting the attacker. What makes it sound is the reader underneath: `ZipFile.open`
    stops at the declared `file_size` and verifies the member's CRC-32, so a member that declares
    less than it holds does not hand back the extra -- it fails, and that failure is a refusal
    here rather than a traceback. A declaration can therefore only be an *over*statement, and an
    overstatement is refused above. The read is still asked for one byte past the declared size
    and checked, so the bound is stated here and does not rest on that reader's internals.
    """
    info = archive.getinfo(name)
    if info.file_size > MAX_MEMBER_BYTES:
        raise Refused(f"{name} declares {info.file_size} uncompressed bytes, over the {MAX_MEMBER_BYTES} "
                      f"a package member may be; it is refused unread")
    ratio = info.file_size / info.compress_size if info.compress_size else info.file_size
    if ratio > MAX_COMPRESSION_RATIO:
        raise Refused(f"{name} declares {info.file_size} bytes from {info.compress_size} compressed, a ratio "
                      f"of {ratio:.0f} over the {MAX_COMPRESSION_RATIO} a package member may be; it is "
                      f"refused unread")
    try:
        with archive.open(name) as member:
            data = member.read(info.file_size + 1)
    except (OSError, zipfile.BadZipFile) as error:
        raise Refused(f"{name} cannot be read as the {info.file_size} bytes it declares: {error}")
    if len(data) > info.file_size:
        raise Refused(f"{name} decompresses to more than the {info.file_size} bytes it declares; the size "
                      f"intake checked was not the size the member has")
    return data


def read_package(nupkg):
    try:
        archive = zipfile.ZipFile(nupkg)
    except (OSError, zipfile.BadZipFile) as error:
        raise Usage(f"{nupkg} is not a readable .nupkg: {error}")
    with archive:
        names = set(archive.namelist())
        nuspecs = [n for n in names if "/" not in n and n.endswith(".nuspec")]
        if len(nuspecs) != 1:
            raise Refused(f"{nupkg}: expected one root .nuspec, found {sorted(nuspecs) or 'none'}")
        metadata = ET.fromstring(_read_member(archive, nuspecs[0])).find("{*}metadata")
        package_id = metadata.findtext("{*}id") if metadata is not None else None
        version = metadata.findtext("{*}version") if metadata is not None else None
        if not package_id or not version:
            raise Refused(f"{nupkg}: the nuspec names no id and version")

        props_name = f"build/{package_id}.props"
        # NuGet matches the props name case-insensitively; so does this.
        props = [n for n in names if n.lower() == props_name.lower()]
        if not props:
            raise Refused(f"{package_id} {version} has no {props_name}, so it declares no "
                          f"RulesFactoryMap item and is not a map package (0015)")
        items = [e for e in ET.fromstring(_read_member(archive, props[0])).iter() if e.tag.endswith("RulesFactoryMap")]
        if len(items) != 1:
            raise Refused(f"{props_name} declares {len(items)} RulesFactoryMap items; a map package declares one")
        item = items[0].attrib
        for field in ("Include", "Manifest", "ConsumerChecker"):
            if not item.get(field):
                raise Refused(f"{props_name}: the RulesFactoryMap item has no {field}")
        if item.get("PackageId") != package_id or item.get("PackageVersion") != version:
            raise Refused(f"{props_name} says {item.get('PackageId')} {item.get('PackageVersion')}; "
                          f"the nuspec says {package_id} {version}")

        parts = {}
        for field, label in (("Include", "map"), ("Manifest", "manifest"), ("ConsumerChecker", "checker")):
            path = _props_path(item[field])
            if path not in names:
                what = ("the consumer-phase checker (#51), so an engine built on it could not run the "
                        "checks its own overlay can change" if label == "checker" else f"its {label}")
                raise Refused(f"{package_id} {version} names {path} as {what}, and the package does not contain it")
            parts[label] = (path, _read_member(archive, path))
    return package_id, version, parts


def _json(label, raw):
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        raise Refused(f"the packaged {label} is not JSON: {error}")


# --- the corpus --------------------------------------------------------------------------


def licence_class(licence):
    """`public-domain` or `open` for a manifest `licence` the factory admits (0028); None for any other."""
    found = LICENCE_IDENTIFIER.match(licence) if isinstance(licence, str) else None
    identifier = found.group(1) if found else ""
    if identifier == PUBLIC_DOMAIN or identifier.startswith(PUBLIC_DOMAIN + "-"):
        return "public-domain"
    if identifier in OPEN_LICENCES:
        return "open"
    return None


def refuse_unadmitted_licence(corpus):
    """Refused unless the manifest corpus's `licence` is public domain or open (0028)."""
    licence = corpus.get("licence") if isinstance(corpus, dict) else None
    if licence_class(licence) is None:
        source_id = corpus.get("sourceId") if isinstance(corpus, dict) else None
        raise Refused(f"{source_id}'s manifest `licence` is {licence!r}, which is neither public domain "
                      f"(`{PUBLIC_DOMAIN}`, or `{PUBLIC_DOMAIN}-<whose>`) nor an open licence the factory admits "
                      f"({', '.join(OPEN_LICENCES)}): the factory admits only corpora whose licence permits "
                      f"committing and publishing their text and maps (docs/decisions/0028)")


def verify_corpus(document, manifest, corpus_path):
    """(corpus, bytes) once the corpus is proved admissible (0028) and to be the map's baseline."""
    if not isinstance(document, dict) or not isinstance(manifest, dict):
        raise Refused("the packaged map or manifest is not a JSON object")
    source_id = document.get("corpus")
    cited = {source_id}
    for entry in document.get("entries") or []:
        locator = entry.get("locator") if isinstance(entry, dict) else None
        if isinstance(locator, dict) and locator.get("sourceId"):
            cited.add(locator["sourceId"])
    if len(cited) != 1:
        raise Refused(f"the map cites {sorted(map(str, cited))}; an engine is produced from exactly one corpus")
    corpora = [c for c in manifest.get("corpora") or [] if isinstance(c, dict) and c.get("sourceId") == source_id]
    if len(corpora) != 1:
        raise Refused(f"the packaged manifest declares {source_id!r} {len(corpora)} times; it must declare it once")
    corpus = corpora[0]
    refuse_unadmitted_licence(corpus)

    posture = corpus.get("verification")
    if posture != "committed-copy":
        raise Refused(f"NOT VERIFIED -- {source_id} is {posture!r}, not `committed-copy` (0013): an engine "
                      f"produced from it could not re-derive its baseline wherever it is built")

    baseline = document.get("baseline") or {}
    for field in ("contentHash", "hashDerivation"):
        if baseline.get(field) != corpus.get(field):
            raise Refused(f"the map's baseline.{field} is {baseline.get(field)!r} and the manifest's is "
                          f"{corpus.get(field)!r}; the map is not of the corpus the manifest declares")
    if baseline.get("asOf") != corpus.get("asOf"):
        raise Refused(f"the map's baseline.asOf is {baseline.get('asOf')!r} and the manifest's is {corpus.get('asOf')!r}")

    randomness = corpus.get("randomness")
    if isinstance(randomness, bool) or randomness not in RANDOMNESS:
        raise Refused(f"{source_id} declares randomness {randomness!r}; a corpus declares `none` or `seeded` "
                      f"(0019), and a manifest without the field is refused, not read as `none`")

    derivation = corpus.get("hashDerivation")
    derive = HASH_DERIVATIONS.get(derivation)
    if derive is None:
        raise Refused(f"NOT VERIFIED -- no way to compute hashDerivation {derivation!r}; known: "
                      f"{', '.join(sorted(HASH_DERIVATIONS))}")
    try:
        with open(corpus_path, "rb") as handle:
            corpus_bytes = handle.read()
    except OSError as error:
        raise Usage(f"cannot read corpus {corpus_path}: {error}")
    actual = derive(corpus_bytes)
    if actual != corpus.get("contentHash"):
        raise Refused(f"{corpus_path} is not {source_id} at the map's baseline: {derivation} gives {actual}, "
                      f"the map was made of {corpus.get('contentHash')}")
    return corpus, corpus_bytes


# --- the factory's checker ---------------------------------------------------------------


def checker():
    """The factory's own `tools/check-map.py`, imported in-process.

    In-process rather than as a child process: it is the factory's own code, standard library
    only, and a subprocess would add an interpreter, a timeout to choose and an exit code to
    translate. A factory checkout without it is broken rather than refusing a package, so its
    absence is a usage error.
    """
    global _checker_module
    if _checker_module is None:
        if not os.path.isfile(CHECKER_PATH):
            raise Usage(f"the factory's checker {CHECKER_PATH} is missing; intake cannot run without it")
        spec = importlib.util.spec_from_file_location("factory_check_map", CHECKER_PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _checker_module = module
    return _checker_module


def check_contract(document):
    """The package's contract is declarative: a `schemaVersion` the factory's checker reads.

    There is no fallback to the package's own checker for a version the factory does not know.
    That fallback is exactly the path by which a package would become code again (0016).
    """
    supported = checker().SCHEMA_VERSIONS
    version = document.get("schemaVersion") if isinstance(document, dict) else None
    if isinstance(version, bool) or version not in supported:
        raise Refused(f"the map is schemaVersion {version!r}, and this factory's check-map.py reads "
                      f"schemaVersion {', '.join(map(str, supported))}; a map in another version needs a "
                      f"factory that reads it, not the package's own checker (0016)")
    return version


# --- the consumer phase ------------------------------------------------------------------


def run_consumer_checks(parts, log=None):
    """The factory's `check-map.py --phase consumer` on the packaged map and manifest.

    Only the map and manifest are written to the scratch directory. The checker is the
    factory's, so the package's `ConsumerChecker` bytes never reach the filesystem as a
    script, let alone an interpreter. The checker's report is captured and passed to `log`, so
    a refusal shows which check failed.
    """
    module = checker()
    output = io.StringIO()
    with tempfile.TemporaryDirectory(prefix="factory-intake-") as scratch:
        paths = {}
        for label in ("map", "manifest"):
            path, data = parts[label]
            target = os.path.join(scratch, *path.split("/"))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "wb") as handle:
                handle.write(data)
            paths[label] = target
        argv = [paths["map"], "--manifest", paths["manifest"], "--repo-root", scratch, "--phase", "consumer"]
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            try:
                code = module.main(argv)
            except SystemExit as stop:  # argparse exits rather than returning
                code = stop.code if isinstance(stop.code, int) else 2
    _note(log, output.getvalue().rstrip("\n"))
    if code != 0:
        raise Refused(f"the factory's check-map.py --phase consumer exited {code} on the packaged map")


# --- the whole of intake -----------------------------------------------------------------


def intake(package_spec, corpus_path, log=None):
    with tempfile.TemporaryDirectory(prefix="factory-download-") as downloads:
        nupkg, nupkg_sha256 = resolve_package(package_spec, downloads, log)
        package_id, version, parts = read_package(nupkg)
    _note(log, f"--- intake: {package_id} {version}")
    document = _json("map", parts["map"][1])
    manifest = _json("manifest", parts["manifest"][1])
    schema_version = check_contract(document)
    _note(log, f"map schemaVersion {schema_version}: read by this factory's check-map.py")
    corpus, corpus_bytes = verify_corpus(document, manifest, corpus_path)
    _note(log, f"corpus {corpus['sourceId']}: {corpus['hashDerivation']} {corpus['contentHash']} matches {corpus_path}")
    _note(log, f"corpus {corpus['sourceId']}: randomness {corpus['randomness']} (0019)")
    _note(log, "--- intake: the factory's check-map.py --phase consumer (the package's checker is not run)")
    run_consumer_checks(parts, log)
    return Intake(
        package_id=package_id, version=version, nupkg_sha256=nupkg_sha256,
        map=document, map_raw=parts["map"][1],
        manifest=manifest, manifest_raw=parts["manifest"][1],
        checker_raw=parts["checker"][1],  # hashed for provenance, never executed (0016)
        part_paths={label: path for label, (path, _) in parts.items()},
        corpus=corpus, corpus_bytes=corpus_bytes, corpus_name=os.path.basename(corpus_path),
        randomness=corpus["randomness"],
    )
