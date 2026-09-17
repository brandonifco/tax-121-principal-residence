#!/usr/bin/env python3
"""Are this engine's rails actually active, or do they only exist?

    tools/agent-doctor.py [--local]

Emitted by rules-factory as a managed file (decision 0029).

**The failure this exists for is "I thought the rails were active".** Every rail in this repository
is a file, and a file is easy to have and easy to believe in. A hook that is present but not
wired into any settings, a workflow that runs but is not required, a label the scripts read and
the repository does not have, a ruleset that was created and then set to "evaluate" rather than
"active" -- each of those looks exactly like a working rail from inside the repository, and stops
anything only when somebody checks.

So this asks the questions whose answers are not visible in a file listing, and prints one row per
answer. It changes nothing, ever.

  * **Local** rows come from this checkout: the rails exist, the hook is wired to the tools it
    guards, the policy parses and configures a chain, and the gate runs the rails check.
  * **Remote** rows come from GitHub: the labels, the ruleset, and whether the three checks are
    required rather than merely present. `--local` skips them, for an offline machine; the output
    then says the remote half was not examined, because a green report that skipped the half that
    matters is the failure this repository has twice found in its own tools.

The remote half asks the same questions `factory rails --check` asks, from inside the engine and
without the factory. Where the answers would differ, the factory's is authoritative: it is the
thing that writes them.

Standard library only, plus `gh` (or `$RULES_ENGINE_GH`) for the remote rows.
"""
import argparse
import json
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
POLICY = ".github/agent-policy.json"
RULESET = "rules-factory-agent-rails"
# `verdict-requeue` is deliberately absent: it runs on the default branch's commit, where a
# required check governs nothing.
REQUIRED_CHECKS = ("validate", "pr-policy", "conformance-gate")
GUARDED_TOOLS = "Bash|Edit|Write|NotebookEdit"
RAILS = ("AGENTS.md", "CLAUDE.md", "docs/agent-team.md", POLICY,
         ".claude/agents/engine-dev.md", ".claude/agents/repo-steward.md", ".claude/agents/rules-conformance.md",
         ".claude/hooks/primary-checkout-guard.py", ".claude/settings.json",
         "tools/dispatch-agent.sh", "tools/new-issue.sh", "tools/entry-packet.py", "tools/re-produce.sh",
         "tools/review-packet.py",
         "tools/pr-policy.py", "tools/record-verdict.py", "tools/conformance-gate.py",
         "tools/requeue-gate.py",
         ".github/pull_request_template.md",
         ".github/workflows/validate.yml", ".github/workflows/pr-policy.yml",
         ".github/workflows/conformance-gate.yml", ".github/workflows/verdict-requeue.yml")
OK, MISSING, WRONG, UNKNOWN = "OK", "MISSING", "WRONG", "NOT EXAMINED"


def row(name, state, note=""):
    dots = "." * max(3, 34 - len(name))
    return f"{name} {dots} {state}" + (f"  -- {note}" if note else "")


def gh(*args):
    command = [os.environ.get("RULES_ENGINE_GH", "gh"), *args]
    try:
        done = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as error:
        return None, str(error)
    if done.returncode != 0:
        return None, (done.stderr.strip() or done.stdout.strip())
    try:
        return json.loads(done.stdout or "null"), None
    except ValueError as error:
        return None, str(error)


def local_rows():
    rows, problems = [], []

    missing = [path for path in RAILS if not (ROOT / path).is_file()]
    rows.append(row("Rail files", OK if not missing else MISSING,
                    "" if not missing else f"{len(missing)} missing: {', '.join(missing[:3])}"))
    if missing:
        problems.append(f"{len(missing)} rail(s) are not in this engine ({', '.join(missing[:3])}...); "
                        f"`factory produce` writes them")

    # A guard nothing invokes is a guard that stops nothing, and reads exactly like one that works.
    settings_path = ROOT / ".claude" / "settings.json"
    wired = False
    if settings_path.is_file():
        try:
            hooks = json.loads(settings_path.read_text(encoding="utf-8")).get("hooks") or {}
            for entry in hooks.get("PreToolUse") or []:
                command = " ".join(hook.get("command", "") for hook in entry.get("hooks") or [])
                if "primary-checkout-guard.py" in command and entry.get("matcher") == GUARDED_TOOLS:
                    wired = True
        except ValueError:
            pass
    rows.append(row("Guard wired to the tools", OK if wired else WRONG,
                    "" if wired else f"the hook exists, but no PreToolUse entry runs it for {GUARDED_TOOLS}"))
    if not wired:
        problems.append("the primary-checkout guard is not wired into .claude/settings.json, so nothing invokes it")

    chain = []
    policy_path = ROOT / POLICY
    if policy_path.is_file():
        try:
            document = json.loads(policy_path.read_text(encoding="utf-8"))
            review = document.get("review") or {}
            chain = [link.get("id") for link in review.get("independentFallback") or []]
            rows.append(row("Policy", OK, f"schemaVersion {document.get('schemaVersion')}, "
                                          f"{len(document.get('labels') or {})} labels"))
            rows.append(row("Review chain", OK if chain else WRONG,
                            f"{review.get('semanticContext')}, then {' -> '.join(chain) or 'nothing'}"))
            if not chain:
                problems.append(f"{POLICY} configures no independent reviewer, so an issue that needs one can "
                                f"never merge")
        except ValueError as error:
            rows.append(row("Policy", WRONG, f"not JSON: {error}"))
            problems.append(f"{POLICY} does not parse, and every rail reads it")

    gate = ROOT / "scripts" / "validate.sh"
    runs_rails = gate.is_file() and "rails" in gate.read_text(encoding="utf-8")
    rows.append(row("Gate checks the rails", OK if runs_rails else WRONG,
                    "" if runs_rails else "scripts/validate.sh does not run `engine-gate.py rails`"))
    if not runs_rails:
        problems.append("the gate does not check the rails, so a reviewer charter that can write would pass it")
    return rows, problems


def remote_rows(repo):
    rows, problems = [], []
    repository, error = gh("api", f"repos/{repo}")
    if repository is None:
        rows.append(row("GitHub", UNKNOWN, f"cannot read {repo}: {error}"))
        problems.append(f"the remote half was not examined ({error}); a report that skipped it proves nothing "
                        f"about what GitHub enforces")
        return rows, problems

    labels_document, _ = gh("api", f"repos/{repo}/labels", "--paginate")
    have = {item["name"] for item in labels_document or []}
    policy_path = ROOT / POLICY
    wanted = []
    if policy_path.is_file():
        try:
            wanted = sorted((json.loads(policy_path.read_text(encoding="utf-8")).get("labels") or {}).values())
        except ValueError:
            wanted = []
    absent = [name for name in wanted if name not in have]
    rows.append(row("Labels", OK if wanted and not absent else (MISSING if wanted else UNKNOWN),
                    "" if not absent else ", ".join(absent)))
    if absent:
        problems.append(f"the repository has no {', '.join(absent)} label, so an issue that needs one cannot be "
                        f"labelled or dispatched")

    rulesets, _ = gh("api", f"repos/{repo}/rulesets")
    ours = next((item for item in rulesets or [] if item.get("name") == RULESET), None)
    detail, _ = gh("api", f"repos/{repo}/rulesets/{ours['id']}") if ours else (None, None)
    active = bool(detail and detail.get("enforcement") == "active")
    rows.append(row(f"Ruleset on {repository.get('default_branch')}", OK if active else
                    (WRONG if detail else MISSING),
                    RULESET if active else (f"{RULESET} is {detail.get('enforcement')}" if detail else
                                            f"no ruleset named {RULESET}")))
    if not active:
        problems.append(f"no active {RULESET}: the default branch has no rails, whatever files this engine holds")

    required = set()
    for rule in (detail or {}).get("rules") or []:
        if rule.get("type") == "required_status_checks":
            required = {check.get("context")
                        for check in (rule.get("parameters") or {}).get("required_status_checks") or []}
    for context in REQUIRED_CHECKS:
        present = context in required
        rows.append(row(f"Required check: {context}", OK if present else MISSING,
                        "" if present else "the workflow may run; it is not required"))
        if not present:
            problems.append(f"{context} is not a required check: a workflow that exists is not one that is required")

    merge_only = (repository.get("allow_merge_commit") is True
                  and repository.get("allow_squash_merge") is False
                  and repository.get("allow_rebase_merge") is False)
    rows.append(row("Merge commits only", OK if merge_only else WRONG,
                    "" if merge_only else "squash or rebase merging is on, and a squash merge makes a commit no "
                                          "reviewer read"))
    if not merge_only:
        problems.append("squash or rebase merging is on; a verdict is pinned to the head commit, which a squash "
                        "merge discards")
    return rows, problems


def main(argv=None):
    parser = argparse.ArgumentParser(prog="agent-doctor.py", description=__doc__.split("\n")[0])
    parser.add_argument("--local", action="store_true", help="check this checkout only, and say GitHub was not examined")
    parser.add_argument("--repo", help="owner/name (default: whatever `gh` says this checkout's remote is)")
    args = parser.parse_args(argv)

    rows, problems = local_rows()
    if args.local:
        rows.append(row("GitHub", UNKNOWN, "--local: the labels, the ruleset and the required checks were not read"))
        problems.append("the remote half was not examined (--local), so this says nothing about what GitHub "
                        "enforces")
    else:
        repo = args.repo
        if not repo:
            document, error = gh("repo", "view", "--json", "nameWithOwner")
            repo = (document or {}).get("nameWithOwner")
            if not repo:
                rows.append(row("GitHub", UNKNOWN, f"cannot tell which repository this is: {error}"))
                problems.append("the remote half was not examined; pass --repo owner/name")
        if repo:
            remote, remote_problems = remote_rows(repo)
            rows.extend(remote)
            problems.extend(remote_problems)

    for line in rows:
        print(line)
    if problems:
        print()
        for problem in problems:
            print(f"  X  {problem}")
        print("\nThe factory puts the remote half in place: "
              "`factory rails --repo <owner/name> --dir <this engine> --apply`.")
        return 1
    print("\nThe rails are active, not merely present.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
