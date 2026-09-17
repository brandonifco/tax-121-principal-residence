#!/usr/bin/env python3
"""The pull request contract, checked mechanically.

    tools/pr-policy.py <pr-number>

Emitted by rules-factory as a managed file (decision 0029), and run by
`.github/workflows/pr-policy.yml` on every open, edit, push and reopen.

**What this is for.** A pull request is where a change stops being the implementer's and becomes
the repository's, and the only thing a reader six months later has is what it said. A vague pull
request is not a formatting problem: it is a change whose behavioural claim nobody stated, whose
evidence nobody can re-run, and whose scope nobody bounded -- and each of those is how a defect
gets merged with everyone's agreement.

So this checks what can be checked mechanically, and nothing it cannot:

  1. exactly one real `Closes #<n>` -- one branch closes one issue;
  2. every mandatory section is present and filled, not left as its placeholder;
  3. the evidence section shows a command and its output, not a claim that it passed;
  4. a change touching the semantic surface names an entry and a locator;
  5. agent provenance says who implemented and who reviewed;
  6. the linked issue carries exactly one risk label and exactly one state label.

**Produce mode (#193).** A `factory produce` update to this engine -- a new map version, a new
kernel pin, a new factory recipe -- is a pull request under these rails like any other, and two of
the obligations above cannot be met honestly by one: it writes no test of its own, so it can name
no mutation, and a map bump regenerates every entry, so it has no single entry id or locator. A
pull request whose body carries the `## Produced by the factory` section and its marker claims to
be one. The claim is **checked, never taken**, and it is closed on three conditions, all of which
must hold:

  1. it says so -- the section, the marker, and three declared facts: factory version, map package
     and version, kernel version;
  2. those facts equal `provenance.json` in the checked-out tree, and that record says the factory
     was not dirty. A produce from a dirty factory is not reproducible, so it is not an update
     anybody can repeat;
  3. every changed path is one the factory writes, classified through this engine's own vendored
     `scripts/factory/ownership.py` -- generated, managed, or a `packages.lock.json` a pin change
     re-locks (#94). One hand-written `.cs`, one overlay edit, one edit to `.github/agent-policy.json`
     voids the claim, by name, and the pull request is judged as the ordinary pull request it is.

The file set this can ever cover is exactly the set nobody may hand-edit anyway (AGENTS.md section
10), so it grants no new territory. Forging the bytes is caught by `./scripts/validate.sh full`,
which regenerates every `*.g.cs` and compares byte for byte; forging the declaration fails against
`provenance.json`, which is in the diff a reviewer reads.

**Produce mode changes what a pull request must say, never what it must prove.** It waives no
verdict, no `Closes #<n>`, no label rule and no gate run. It replaces the two obligations that do
not apply with two that are harder to fake: the map package and version and what moved, in place of
an entry and a locator; and the produce command, the gate's output and a `factory provenance`
recompute, in place of a named mutation.

**What it cannot check, and does not pretend to.** Whether the behavioural claim is true, whether
the evidence was really run, whether the mutation was really observed to fail, or whether the
named reviewer really reviewed. Those are a reviewer's, and the review verdict recorded against
the head commit is where they land (`tools/record-verdict.py`). A policy check that implied
otherwise would make the pull request look more verified than it is.

Label strings and the semantic surface come from `.github/agent-policy.json`, which the engine
owns. Standard library only, plus `gh` (or `$RULES_ENGINE_GH`).
"""
import argparse
import json
import os
import pathlib
import re
import subprocess
import sys

# The produce claim is classified by the engine's vendored scripts/factory/ownership.py, and an
# imported module leaves its bytecode behind: scripts/factory/__pycache__/, a path no ownership row
# covers, so the checkout that ran this goes dirty and tools/dispatch-agent.sh refuses to open a
# worktree for the next issue (#194). The loader reads this flag when the import happens, so it
# belongs here and not beside the import it disarms.
sys.dont_write_bytecode = True

ROOT = pathlib.Path(__file__).resolve().parents[1]
POLICY = ".github/agent-policy.json"
PROVENANCE = "provenance.json"

# The template's headings, and what each is for. A pull request is judged against these names, so
# the template and this list move together (both are managed rails, emitted by the same factory).
SECTIONS = (
    ("Linked issue", "which issue this closes"),
    ("Exact behavioural claim", "what the engine does now that it did not do before"),
    ("Scope, and what this deliberately does not do", "what makes the diff reviewable"),
    ("Map and rules conformance", "the entry, the map version and the locator"),
    ("Tests and evidence", "the commands, and what they printed"),
    ("Determinism", "what this change does about anything that reads the machine"),
    ("Decisions and trade-offs", "what you chose and what you rejected"),
    ("Known limitations and unresolved behaviour", "what this does not answer"),
    ("Agent provenance", "who implemented, and who reviewed"),
    ("Unrelated changes", "there are none, or they are named"),
    ("Produced by the factory", "what this run of `factory produce` moved, and from what to what"),
)
# The one heading whose absence is not a finding: almost no pull request is a factory update, and a
# section every author had to write "N/A" into would be noise. Its presence is a claim, though, so
# once it is there it is judged like any other section -- and then checked against the tree.
PRODUCE_SECTION = "Produced by the factory"
OPTIONAL = frozenset({PRODUCE_SECTION})
# Fixed, and matched in the raw body rather than in the parsed section: the template's guidance
# lives in HTML comments, which sections() strips, and so does this.
PRODUCE_MARKER = "<!-- rules-factory-produce -->"
# The three facts a produce update declares, and where provenance.json holds each. A declaration is
# only worth checking because it can be wrong: each of these is in the diff the pull request carries.
PRODUCE_FACTS = (
    ("factory version", lambda record: (record.get("factory") or {}).get("version")),
    ("map package and version",
     lambda record: f"{(record.get('map') or {}).get('packageId')} {(record.get('map') or {}).get('version')}"),
    ("kernel version", lambda record: (record.get("kernel") or {}).get("version")),
)
# Prose, compared against nothing: which of the three moved, and what a reader should expect to see
# in the diff because of it. A produce report (`factory produce --produce-report`) writes all four.
PRODUCE_PROSE = "what moved"
CLOSES = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)\b", re.I)
FENCE = re.compile(r"```.*?```", re.S)
# "tests pass", "all green", "CI is happy": a claim in the place the template asks for output.
CLAIM_NOT_EVIDENCE = re.compile(r"^\s*(?:all\s+)?(?:tests?|checks?|ci|gate|validate(?:\.sh)?)\s+"
                                r"(?:pass(?:es|ed|ing)?|are\s+green|is\s+green|green|ok)\s*\.?\s*$", re.I | re.M)


class Failed(Exception):
    """A finding a person has to act on. Every one names what to do."""


def gh(*args):
    command = [os.environ.get("RULES_ENGINE_GH", "gh"), *args]
    done = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=ROOT, timeout=120)
    if done.returncode != 0:
        raise Failed(f"{' '.join(command)} failed: {done.stderr.strip() or done.stdout.strip()}")
    return done.stdout


def policy():
    with open(ROOT / POLICY, encoding="utf-8") as handle:
        return json.load(handle)


def is_semantic(path, patterns):
    """Whether `path` is on the semantic surface. `**` spans directories; `*` does not."""
    for pattern in patterns:
        regex = re.escape(pattern).replace(r"\*\*/", "(?:.*/)?").replace(r"\*\*", ".*").replace(r"\*", "[^/]*")
        if re.fullmatch(regex, path):
            return True
    return False


def sections(body):
    """The body split into `## Heading` -> text, with HTML comments removed.

    The template's guidance lives in comments, so a section that still holds only its comment is
    empty here -- which is the point: a section is filled when somebody wrote in it.
    """
    without_comments = re.sub(r"<!--.*?-->", "", body or "", flags=re.S)
    found = {}
    current = None
    for line in without_comments.splitlines():
        heading = re.match(r"^##\s+(.*?)\s*$", line)
        if heading:
            current = heading.group(1)
            found[current] = []
        elif current is not None:
            found[current].append(line)
    return {name: "\n".join(lines).strip() for name, lines in found.items()}


def check_closes(body, findings):
    """Exactly one `Closes #n`, outside code fences: one branch, one issue, one pull request."""
    prose = FENCE.sub("", re.sub(r"<!--.*?-->", "", body or "", flags=re.S))
    numbers = sorted({number for _, number in ((m.group(0), m.group(1)) for m in CLOSES.finditer(prose))})
    if not numbers:
        findings.append("no `Closes #<n>`: a pull request closes exactly one issue, and says which "
                        "(AGENTS.md section 4). Add it to the Linked issue section.")
    elif len(numbers) > 1:
        findings.append(f"this closes {len(numbers)} issues (#{', #'.join(numbers)}): split it, so that each "
                        f"change can be reviewed, reverted and explained on its own.")
    return numbers[0] if len(numbers) == 1 else None


# The one section a change may honestly answer "N/A": nothing it touches is on the rules surface.
# Whether that is true is not taken on the author's word -- check_conformance decides it from the
# files the pull request actually changes.
MAY_BE_NA = "Map and rules conformance"


def check_sections(body, findings):
    present = sections(body)
    filled = {}
    for name, purpose in SECTIONS:
        empty = {"", "-", "TODO"} if name == MAY_BE_NA else {"", "-", "N/A", "TODO"}
        if name not in present:
            if name in OPTIONAL:
                continue
            findings.append(f"the section `## {name}` is missing ({purpose}). The template is "
                            f".github/pull_request_template.md.")
        elif present[name] in empty:
            findings.append(f"`## {name}` is empty ({purpose}).")
        else:
            filled[name] = present[name]
    return filled


def labelled(text, field):
    """The value written after `<field>:` on its own line, or None. The labels are the template's
    bullets (`- factory version:`), so the word is looked for anywhere in the label, not at its
    start -- the same rule check_conformance and check_provenance read their fields by."""
    found = re.search(rf"(?im)^[^\n:]*\b{re.escape(field)}[^:\n]*:[ \t]*(\S.*?)[ \t]*$", text or "")
    return found.group(1) if found else None


def same_fact(declared, recorded):
    """Whether a declared fact is the recorded one. Whitespace is collapsed, and `Id@Version` is
    accepted for the map beside `Id Version`, because both spellings name the same package and
    `factory produce --package` takes the second."""
    return " ".join((declared or "").replace("@", " ").split()) == " ".join((recorded or "").split())


def engine_ownership():
    """This engine's own `scripts/factory/ownership.py`, and the engine's name (#193).

    Imported from the tree rather than restated here, so the classification a pull request is
    judged by and the one `factory produce` wrote can never disagree: they are one table. A tree
    without it, or without a readable provenance.json, cannot answer the question at all, which is
    why the caller turns that into a finding rather than into an admitted claim.
    """
    with open(ROOT / PROVENANCE, encoding="utf-8") as handle:
        record = json.load(handle)
    name = (record.get("engine") or {}).get("name")
    if not isinstance(name, str) or not name:
        raise Failed(f"{PROVENANCE} names no engine, so no path in this pull request can be classified")
    sys.path.insert(0, str(ROOT / "scripts" / "factory"))
    try:
        import ownership  # noqa: E402  (the factory's ownership table, vendored by produce)
    except ImportError as error:
        raise Failed(f"scripts/factory/ownership.py is not importable ({error}); run `factory produce` again")
    return ownership, name, record


def factory_written(path, ownership, name):
    """Whether `path` is one a `factory produce` run writes, by the engine's own table.

    Generated and managed files are the factory's on every run. The two `packages.lock.json` are
    engine-owned, and are here for the one case 0018's amendment (#94) admits: a produce that moved
    the generated pins re-locks them, because lock files resolved against the old pins cannot pass
    the gate. Everything else an engine owns -- its overlay, its projects, its rails configuration,
    its hand-written code -- is a decision the factory did not make, and is what voids a claim.
    """
    row = ownership.classify(path, name)
    if row is None:
        return False
    if row.cls in (ownership.GENERATED, ownership.MANAGED):
        return True
    return row.cls == ownership.ENGINE_OWNED and row.pattern.endswith("/packages.lock.json")


def check_produce(body, filled, changed, findings):
    """Whether this pull request is a factory update, by the closed predicate #193 decided.

    Returns True only when the section says so, the declared facts are the tree's, and every changed
    path is one the factory writes. A claim that fails any part of that produces a finding naming
    which part: an author who wrote the section meant it, and a silent downgrade would leave them
    reading findings about a mutation they could not have named and wondering which rule they hit.

    `body` is a parameter and not a module global on purpose. This predicate decides what two other
    checks may relax, and a value it read from somewhere else in the process is a value a reader
    cannot follow to its source.
    """
    if PRODUCE_SECTION not in filled and f"## {PRODUCE_SECTION}" not in (body or ""):
        return False
    claim = f"`## {PRODUCE_SECTION}` claims this is a `factory produce` update"
    declared = filled.get(PRODUCE_SECTION) or ""
    if PRODUCE_MARKER not in (body or ""):
        findings.append(f"{claim}, and carries no `{PRODUCE_MARKER}`. The marker is what the section is "
                        f"recognised by; the template writes it, and a section written by hand must keep it.")
        return False

    try:
        ownership, name, record = engine_ownership()
    except (Failed, OSError, ValueError) as error:
        findings.append(f"{claim}, and that claim cannot be checked here: {error}. A claim this check cannot "
                        f"examine is not admitted.")
        return False

    problems = []
    for field, recorded_by in PRODUCE_FACTS:
        value = labelled(declared, field)
        recorded = recorded_by(record)
        if value is None:
            problems.append(f"it declares no {field}")
        elif not same_fact(value, recorded):
            problems.append(f"it declares {field} {value!r}, and {PROVENANCE} in this tree records {recorded!r}")
    if labelled(declared, PRODUCE_PROSE) is None:
        problems.append(f"it does not say {PRODUCE_PROSE}: which of the three moved, and what a reader should "
                        f"therefore expect to find in the diff")
    if (record.get("factory") or {}).get("dirty") is not False:
        problems.append(f"{PROVENANCE} records the factory as dirty, so this engine was produced from a factory "
                        f"checkout with uncommitted changes. Nobody can reproduce that run, so it is not a "
                        f"factory update -- re-produce from a clean factory")

    smuggled = []
    for path in sorted(changed):
        try:
            if not factory_written(path, ownership, name):
                smuggled.append(path)
        except ownership.OwnershipError as error:
            smuggled.append(f"{path} ({error})")
    if smuggled:
        problems.append(f"{len(smuggled)} changed file(s) are not files a produce writes: "
                        f"{', '.join(smuggled[:5])}{'...' if len(smuggled) > 5 else ''}. A produce writes the "
                        f"generated and managed files and re-locks the lock files; anything else in this diff is "
                        f"somebody's decision, and it is reviewed as one")

    if problems:
        findings.append(f"{claim}, and it is not one: {'; '.join(problems)}. The claim is void and this pull "
                        f"request is judged as the ordinary pull request it is. Nothing here is waived by the "
                        f"section being present.")
        return False
    return True


def check_evidence(filled, findings, produce=False):
    evidence = filled.get("Tests and evidence")
    if evidence is None:
        return
    fences = FENCE.findall(evidence)
    body = "\n".join(fences)
    if not fences:
        findings.append("`## Tests and evidence` shows no command and no output. Paste what you ran and what it "
                        "printed: a claim is not evidence, and a reviewer cannot re-run a summary.")
    elif not re.search(r"(?m)^\s*(?:\$\s*)?\S*(?:validate\.sh|dotnet|python3|pytest)\b", body):
        findings.append("`## Tests and evidence` shows no command that was run. The gate is "
                        "`./scripts/validate.sh full`; show it, and what it printed.")
    if CLAIM_NOT_EVIDENCE.search(evidence) and len(body.strip().splitlines()) < 3:
        findings.append("`## Tests and evidence` says the tests pass rather than showing them passing. "
                        "This repository has twice shipped a check that counted work it had not done.")
    # Asked whatever the fences hold: the mutation obligation is about the tests, not the formatting.
    if produce:
        # A produce writes no test of its own, so there is no mutation it could honestly name -- and a
        # rule met by writing the word is worse than no rule. What replaces it is not lighter: the
        # command that made these bytes, and a recompute saying the committed record is the one a
        # re-produce writes. Both are re-runnable by a reviewer; "mutation" is not.
        for command, why in (("factory produce", "the command that wrote these bytes"),
                             ("factory provenance", "the recompute showing the committed record is the one a "
                                                    "re-produce writes")):
            if command not in evidence:
                findings.append(f"`## Tests and evidence` shows no `{command}`, and this is a factory update: "
                                f"show {why}, and what it printed. A produce update names no mutation because it "
                                f"writes no test; this is what it shows instead.")
    elif "mutation" not in evidence.lower():
        findings.append("`## Tests and evidence` names no mutation. Every test records the mutation that makes it "
                        "fail, and you must have watched it fail -- a test nobody has watched fail is not yet a test.")


def check_conformance(filled, semantic_files, findings, produce=False):
    conformance = filled.get("Map and rules conformance")
    if conformance is None or not semantic_files:
        return
    # A map version bump regenerates every entry, so a factory update has no single entry id and no
    # single locator: the honest answers are "all of them" and "the whole map", which name nothing.
    # What it does have is the map package and the version it moved to, which is the fact the diff
    # can be read against -- and that is required here, not waived.
    fields = ((("map", "the map package and version this engine was produced from"),) if produce else
              (("entry", "the entry id, which is what ties this to the map"),
               ("map", "the map package and version this was implemented against"),
               ("locator", "the locator, which is where the rule is")))
    if re.fullmatch(r"(?i)\s*n/?a\.?\s*", conformance):
        findings.append(f"`## Map and rules conformance` says N/A, but this change touches the semantic surface "
                        f"({', '.join(sorted(semantic_files)[:3])}...). Name {', '.join(w for _, w in fields)}: "
                        f"an implementation of an unnamed rule cannot be reviewed against one.")
        return
    for field, what in fields:
        # The template's bullets read "entry id(s):", "map package and version:", "source
        # locator(s):" -- so the word is looked for anywhere in the label, not at its start.
        if labelled(conformance, field) is None:
            findings.append(f"`## Map and rules conformance` does not name {what}.")


def check_provenance(filled, findings):
    provenance = filled.get("Agent provenance")
    if provenance is None:
        return
    for field in ("implemented by", "structurally reviewed by", "semantically reviewed by"):
        if not re.search(rf"(?im)^[^\n:]*\b{re.escape(field)}[ \t]*:[ \t]*\S", provenance):
            findings.append(f"`## Agent provenance` does not say who this was {field.replace(' by', '')} by. "
                            f"A merged commit must say who did what without opening a transcript.")


def check_issue_labels(number, settings, findings):
    issue = json.loads(gh("issue", "view", str(number), "--json", "number,state,labels"))
    names = {label["name"] for label in issue.get("labels") or []}
    labels = settings.get("labels") or {}
    risks = names & {labels.get("normalRisk"), labels.get("independentRisk")}
    states = names & {labels.get("ready"), labels.get("blocked"), labels.get("needsDecision")}
    if len(risks) != 1:
        findings.append(f"issue #{number} carries {len(risks)} risk labels ({', '.join(sorted(risks)) or 'none'}); "
                        f"exactly one is required, because it decides whether an independent verdict is needed.")
    if len(states) != 1:
        findings.append(f"issue #{number} carries {len(states)} state labels ({', '.join(sorted(states)) or 'none'}); "
                        f"exactly one is required.")
    if labels.get("needsDecision") in names:
        findings.append(f"issue #{number} is {labels['needsDecision']}: the question it raises is not answered, and "
                        f"an implementation cannot answer it for itself (AGENTS.md section 6).")
    return issue


def truncation(pull, changed, findings):
    """Whether `gh pr view --json files` gave a partial list (#193). True means decide nothing from it.

    The cap is real and silent: `gh pr view --json files` returns at most 100 files, with no error
    and no warning, whatever `changedFiles` says. Every rule below reads the changed paths -- what
    is on the semantic surface, and whether a produce claim covers the whole diff -- so a pull
    request with more than a hundred changed files whose rule-bearing ones sort past the first
    hundred would be judged on a diff that is not the diff. A map version bump regenerates hundreds
    of files, which is exactly the case this check is for. So the count is asked for alongside the
    list, and a short list refuses rather than deciding on the half it was given: a check that
    examines some of what it is for is not a pass either.
    """
    count = pull.get("changedFiles")
    if not isinstance(count, int) or len(changed) == count:
        return False
    findings.append(f"GitHub returned {len(changed)} of this pull request's {count} changed files: the list is "
                    f"truncated, and the semantic surface and the ownership of this diff cannot be decided from "
                    f"a partial list. Nothing below was judged against the files that are missing. Read the diff "
                    f"(`gh pr diff {pull.get('number')} --name-only`) and split the change, or say on the issue "
                    f"why one pull request this large is the reviewable unit.")
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(prog="pr-policy.py", description=__doc__.split("\n")[0])
    parser.add_argument("pr", type=int, help="the pull request number")
    args = parser.parse_args(argv)

    findings = []
    try:
        settings = policy()
        pull = json.loads(gh("pr", "view", str(args.pr), "--json", "number,title,body,files,changedFiles"))
        body = pull.get("body") or ""
        changed = [f["path"] for f in pull.get("files") or []]
        truncated = truncation(pull, changed, findings)
        semantic_files = {path for path in changed
                          if is_semantic(path, (settings.get("review") or {}).get("semanticPaths") or [])}

        linked = check_closes(body, findings)
        filled = check_sections(body, findings)
        # Never on a truncated list: the produce predicate says every changed path is one the
        # factory writes, and a list that is missing some cannot say that about the ones it lost.
        produce = False if truncated else check_produce(body, filled, changed, findings)
        check_evidence(filled, findings, produce=produce)
        check_conformance(filled, semantic_files, findings, produce=produce)
        check_provenance(filled, findings)
        if linked is not None:
            check_issue_labels(linked, settings, findings)
    except Failed as error:
        print(f"pr-policy: cannot check PR #{args.pr} -- {error}", file=sys.stderr)
        return 2
    except (OSError, ValueError) as error:
        print(f"pr-policy: cannot check PR #{args.pr} -- {error}", file=sys.stderr)
        return 2

    if findings:
        print(f"pr-policy: PR #{args.pr} does not satisfy the contract ({len(findings)} finding(s)):\n")
        for finding in findings:
            print(f"  X  {finding}\n")
        print("The contract is .github/pull_request_template.md and AGENTS.md. None of this is about form: each "
              "line above is something a reviewer would otherwise have to take on trust.")
        return 1
    print(f"pr-policy: PR #{args.pr} satisfies the contract "
          f"({len(SECTIONS) - len(OPTIONAL)} required sections, one linked issue, evidence and provenance present).")
    if produce:
        print(f"The `## {PRODUCE_SECTION}` claim was admitted: the declared factory, map and kernel are "
              f"{PROVENANCE}'s, that record is not dirty, and every changed file is one a produce writes. "
              f"It replaced the mutation and the entry, and waived no verdict.")
    print("What this does not say: that the claim is true, that the evidence was run, or that the named reviewers "
          "reviewed. Those are the review verdict's, recorded against the head commit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
