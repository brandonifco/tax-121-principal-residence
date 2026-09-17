#!/usr/bin/env python3
"""Record a review verdict against the exact commit it was formed on.

    tools/record-verdict.py --pr 12 --reviewer semantic --verdict pass
    tools/record-verdict.py --pr 12 --reviewer <id from the chain> --verdict fail --note "row 7 is wrong"

Emitted by rules-factory as a managed file (decision 0029).

**Why a commit status and not a comment.** A reviewer saying "pass" in a chat window is worth
nothing to the repository: the conversation ends, and what is left is a merged commit nobody can
tell was reviewed. A verdict here is a commit status on the pull request's **head SHA**, which
makes two things true at once -- the merge gate can require it, and a further commit invalidates
it automatically, because the status is on the commit that was actually read. Re-reviewing a
changed pull request is then not a discipline anybody has to remember.

**The reviewer names itself.** `--reviewer semantic` records under the policy's semantic context;
any other id must be one of the configured independent chain, and records under that link's own
context. The chain is not collapsed into one generic context on purpose: a reader of a merged
commit must be able to tell a genuinely independent verdict from a same-family fallback without
opening a transcript.

**A fail is a fail.** `tools/conformance-gate.py` treats a recorded failure at any configured
context as blocking, and a later pass at a different context does not clear it. The chain advances
when a provider is unavailable -- unreachable, rate-limited, returning no verdict at all -- never
because its verdict was unwelcome. A failure is answered by fixing the code, fixing the map, or
getting an owner's ruling.

**What this cannot check.** Which model actually produced the verdict, or that the chain was tried
in order. Those remain obligations on whoever runs this, stated here rather than implied to be
enforced.

Standard library only, plus `gh` (or `$RULES_ENGINE_GH`).
"""
import argparse
import json
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
POLICY = ".github/agent-policy.json"
SEMANTIC = "semantic"


class Refused(Exception):
    """Something that must not be recorded. Nothing is posted."""


def gh(*args, check=True):
    command = [os.environ.get("RULES_ENGINE_GH", "gh"), *args]
    done = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=ROOT, timeout=120)
    if check and done.returncode != 0:
        raise Refused(f"{' '.join(command)} failed: {done.stderr.strip() or done.stdout.strip()}")
    return done.stdout


def policy():
    try:
        with open(ROOT / POLICY, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError) as error:
        raise Refused(f"{POLICY} cannot be read ({error}); it is where the review contexts live")


def context_for(reviewer, settings):
    """The status context this reviewer records under, or a refusal naming the ones that exist."""
    review = settings.get("review") or {}
    if reviewer == SEMANTIC:
        context = review.get("semanticContext")
        if not context:
            raise Refused(f"{POLICY} sets no review.semanticContext")
        return context
    chain = review.get("independentFallback") or []
    for link in chain:
        if link.get("id") == reviewer:
            return link["context"]
    known = ", ".join([SEMANTIC] + [link.get("id", "?") for link in chain])
    raise Refused(f"{reviewer!r} is not a reviewer this engine configures. Known: {known}. "
                  f"Adding one is an edit to {POLICY}, not to this script.")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="record-verdict.py", description=__doc__.split("\n")[0])
    parser.add_argument("--pr", type=int, required=True, help="the pull request reviewed")
    parser.add_argument("--reviewer", required=True,
                        help=f"'{SEMANTIC}', or an id from review.independentFallback in {POLICY}")
    parser.add_argument("--verdict", required=True, choices=("pass", "fail"))
    parser.add_argument("--note", default="", help="one line, shown beside the status")
    parser.add_argument("--sha", help="the commit reviewed (default: the pull request's current head)")
    parser.add_argument("--dry-run", action="store_true", help="print what would be recorded, and record nothing")
    args = parser.parse_args(argv)

    try:
        settings = policy()
        context = context_for(args.reviewer, settings)
        pull = json.loads(gh("pr", "view", str(args.pr), "--json", "number,headRefOid,state"))
        head = pull.get("headRefOid")
        if not head:
            raise Refused(f"PR #{args.pr} has no head commit")
        sha = args.sha or head
        if sha != head:
            # Deliberate, and worth saying out loud: a verdict on an older commit satisfies no gate,
            # because the gate asks about the head. Recording one is allowed for the record; it is
            # never a way to pass a pull request that has moved.
            print(f"note: recording against {sha[:12]}, which is not the head ({head[:12]}). This satisfies no "
                  f"gate: the gate asks about the head commit.", file=sys.stderr)
        state = "success" if args.verdict == "pass" else "failure"
        description = (args.note or f"{args.verdict} by {args.reviewer}")[:140]
        repository = json.loads(gh("repo", "view", "--json", "nameWithOwner"))["nameWithOwner"]

        if args.dry_run:
            print(f"{repository} {sha} {context} {state} {description!r}")
            return 0
        gh("api", f"repos/{repository}/statuses/{sha}", "-X", "POST",
           "-f", f"state={state}", "-f", f"context={context}", "-f", f"description={description}")
    except Refused as error:
        print(f"record-verdict: REFUSED -- {error}", file=sys.stderr)
        return 1
    print(f"recorded {state} at {context} on {sha[:12]} (PR #{args.pr})")
    if args.verdict == "fail":
        print("A recorded failure blocks the merge outright. It is answered by fixing the code, fixing the map, or "
              "getting an owner's ruling -- never by asking another provider until one agrees.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
