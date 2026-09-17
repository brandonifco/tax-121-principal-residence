#!/usr/bin/env python3
"""PreToolUse guard: keep implementation work out of the primary checkout.

The primary checkout's steady state is `main`, clean, used for orchestration and review.
Implementation belongs in a worktree outside the repository (AGENTS.md section 4).

Written instructions alone do not survive a long agent session: an agent told once, forty
tool calls ago, will eventually edit a file where it is standing. This hook is the
mechanical backstop for that.

It is ACCIDENT PREVENTION, not security. A determined process bypasses it trivially, and
that is fine: the goal is to stop the unintentional commit on main, not to defend against
a hostile one.

Emitted by rules-factory as a managed file, adapted from a hand-built guard that reached this
shape over several corrections. The parsing below is what those corrections produced, and each
reason is kept because it is a bug this file already had:

  * Commands are parsed into shell segments and tokenised rather than regex-matched. The
    regex version could not see git's two-token global options at all, so
    `git -C <primary> commit` and `git -c user.name=x commit` walked straight through.
  * The whole command is tokenised once with `shlex` in `punctuation_chars` mode, which is
    quote-aware: shell operators surface as their own tokens only where the shell would
    treat them as operators, so a `>` inside a quoted argument stays part of that argument.
    Scanning raw text for `>`/`>>` blocked `git commit -m` messages carrying a
    `<noreply@...>` trailer, and `grep -E "a|b>c"`, which teaches agents to route around
    the guard -- worse than not having one.
  * Heredoc bodies are stripped before tokenising. A heredoc body is data handed to the
    command's stdin, never shell syntax, so parsing it is a category error regardless of
    how good the tokeniser is.
  * Redirect targets and file-mutator arguments are read off the token stream positionally
    per command (the mode argument to `chmod`/`chown`, the `-m` value to `install`, the
    script argument to `sed` are skipped) rather than "every token that does not start
    with `-`".
  * A target built from an unexpanded variable (`$DIR/out.txt`) or a command substitution
    cannot be resolved without expanding the shell, which this guard deliberately does not
    do. It says so by allowing the command, rather than asserting a location it cannot see.

Escape hatch, deliberately explicit and documented in AGENTS.md section 4:

    RULES_ENGINE_ALLOW_PRIMARY_MUTATION=1

The variable's name is configuration, not code: `.github/agent-policy.json`
(`worktrees.primaryMutationEscapeHatch`) is read first, and the name above is the default
this engine was produced with. A policy file that is missing or unreadable falls back to the
defaults rather than failing the session open or closed by accident.

Exit codes: 0 allow, 2 block (stderr is shown to the agent).
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

DEFAULT_ESCAPE_HATCH = "RULES_ENGINE_ALLOW_PRIMARY_MUTATION"
DEFAULT_WORKTREE_ROOT_VARIABLE = "RULES_ENGINE_WORKTREE_ROOT"
POLICY = ".github/agent-policy.json"


def policy_variables() -> tuple[str, str]:
    """(escape hatch, worktree root) variable names, from the engine's policy or the defaults.

    The policy is engine-owned: a consumer renames these without editing this file. It is read
    from the repository the hook was invoked in, and any failure to read it -- absent, malformed,
    not JSON, the wrong shape -- falls back to the defaults, because a guard that stops working
    because a configuration file has a typo in it is a guard nobody can rely on.
    """
    root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    try:
        with open(Path(root) / POLICY, encoding="utf-8") as handle:
            worktrees = json.load(handle).get("worktrees") or {}
        hatch = worktrees.get("primaryMutationEscapeHatch")
        variable = worktrees.get("rootEnvironmentVariable")
    except (OSError, ValueError, AttributeError):
        return DEFAULT_ESCAPE_HATCH, DEFAULT_WORKTREE_ROOT_VARIABLE
    return (hatch if isinstance(hatch, str) and hatch else DEFAULT_ESCAPE_HATCH,
            variable if isinstance(variable, str) and variable else DEFAULT_WORKTREE_ROOT_VARIABLE)


ESCAPE_HATCH, WORKTREE_ROOT_VARIABLE = policy_variables()

# Git subcommands that mutate history, the index-to-HEAD relationship, the working tree,
# or the remote. `merge` and `checkout` are handled separately: both have sanctioned
# forms in the primary checkout.
FORBIDDEN_VERBS = {
    "commit": "commit in the primary checkout",
    "push": "push from the primary checkout",
    "reset": "reset in the primary checkout",
    "rebase": "rebase in the primary checkout",
    "cherry-pick": "cherry-pick in the primary checkout",
    "revert": "revert in the primary checkout",
    "am": "patch application in the primary checkout",
    "apply": "patch application in the primary checkout",
    "stash": "stash in the primary checkout",
    "clean": "git clean in the primary checkout",
    "update-ref": "direct ref manipulation in the primary checkout",
    "filter-branch": "history rewriting in the primary checkout",
}

# Shell commands that mutate files in place.
FILE_MUTATORS = {"rm", "mv", "cp", "truncate", "install", "shred", "chmod", "chown", "ln"}

BULK_ADD_ARGS = {"-A", "--all", "."}

# shlex's shell-operator preset: "();<>|&". A run of these characters, outside any
# quote, comes back as one token ("&&", ">>", "&>", ...). Newline is added on top: it
# is whitespace by default (silently swallowed), but a bare newline is as much a
# command separator as ";" is, and swallowing it would hide a second command --
# "echo hi\ngit commit -m x" must not merge into one token stream that never starts
# with "git".
_PUNCTUATION = shlex.shlex("", punctuation_chars=True).punctuation_chars + "\n"

# Tokens that end a shell segment and start the next one. "(" and ")" (subshells) are
# deliberately not included: the previous regex-based splitter did not understand them
# either, and pretending to now would be worse than staying consistent about the gap.
SEGMENT_SEPARATORS = {";", "&&", "||", "|", "&", "\n"}

REDIRECT_OUT_OPS = {">", ">>", "&>", "&>>"}
REDIRECT_IN_OPS = {"<", "<<", "<<<"}

# "<<-?\s*(quote)?DELIM(quote)?" -- the start of a heredoc. Matched against raw command
# text (before tokenising) so its body can be dropped before anything tries to parse it
# as shell syntax.
HEREDOC_MARKER = re.compile(r"<<-?\s*(['\"]?)([A-Za-z0-9_-]+)\1")


def emit(reason: str, guidance: str) -> None:
    print(f"BLOCKED by primary-checkout-guard: {reason}\n\n{guidance}", file=sys.stderr)
    sys.exit(2)


def git(args: list[str], cwd: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, check=False, timeout=5
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def is_primary_checkout(path: str) -> tuple[bool, str | None]:
    """True when `path` sits in the primary checkout rather than a linked worktree.

    `git rev-parse --git-common-dir` returns a path RELATIVE to the directory git ran in
    (e.g. "../../.git" from a subdirectory) while --git-dir may return an absolute one.
    Resolving them against the process cwd instead of `path` silently compares unrelated
    paths, which made this answer False everywhere except the repository root.
    """
    if not Path(path).is_dir():
        return False, None
    top = git(["rev-parse", "--show-toplevel"], path)
    if not top:
        return False, None
    common = git(["rev-parse", "--git-common-dir"], path)
    gitdir = git(["rev-parse", "--git-dir"], path)
    if common is None or gitdir is None:
        return False, top

    base = Path(path)
    resolve = lambda p: (Path(p) if Path(p).is_absolute() else base / p).resolve()
    return resolve(common) == resolve(gitdir), top


WORKTREE_GUIDANCE = (
    "Implementation work belongs in an isolated worktree, not the primary checkout.\n"
    "See AGENTS.md section 4 for how one is created, and work there.\n\n"
    "If you are the orchestrator doing sanctioned primary-checkout work, set\n"
    f"    {ESCAPE_HATCH}=1\n"
    "for that command, and say in the pull request or the report why it was necessary."
)


def strip_heredocs(command: str) -> str:
    """Blank out heredoc bodies before any further parsing sees them.

    A heredoc body is data the shell hands to the command's stdin verbatim; the shell
    never parses it as command syntax, so `>>`, unbalanced quotes and stray parens
    inside it mean nothing. Scanning it anyway is exactly how
    `python3 - <<'PY' ... (((s >> 18) ^ s) >> 27) ... PY` got misread as "redirection
    targeting ... (18)^s))". This only needs to find the marker and its matching
    terminator line -- the body's contents never matter once found.
    """
    lines = command.split("\n")
    kept: list[str] = []
    index = 0
    total = len(lines)
    while index < total:
        line = lines[index]
        kept.append(line)
        index += 1
        for _quote, delimiter in HEREDOC_MARKER.findall(line):
            while index < total and lines[index].strip() != delimiter:
                index += 1
            if index < total:
                index += 1  # consume the terminator line too
    return "\n".join(kept)


def full_tokenize(command: str) -> list[str]:
    """Tokenise an entire (heredoc-stripped) command in one quote-aware pass.

    `punctuation_chars` makes shlex return shell operators as their own tokens --
    but only where they are actually operators. Anything inside a quoted argument,
    `>` included, stays part of that argument's single token, which is what makes
    `git commit -m "...<noreply@anthropic.com>"` tokenise as one `-m` value rather
    than a redirect: the fix is recognising it sits inside an argument, not a better
    regex on the raw text.
    """
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=_PUNCTUATION)
        lexer.whitespace_split = True
        lexer.whitespace = lexer.whitespace.replace("\n", "")
        return list(lexer)
    except ValueError:
        # Unbalanced quotes. Fall back to whitespace splitting rather than failing
        # open on a command we could not parse -- segment and redirect boundaries are
        # lost, but an obvious verb or a bare `>` token still shows up.
        return command.split()


def split_segments(tokens: list[str]) -> list[list[str]]:
    """Split a flat token stream into one token list per shell command.

    Redirect operators (`>`, `<`, ...) stay inside their segment -- a redirect does not
    end a command, it decorates one -- only SEGMENT_SEPARATORS do.
    """
    segments: list[list[str]] = [[]]
    for token in tokens:
        if token in SEGMENT_SEPARATORS:
            segments.append([])
        else:
            segments[-1].append(token)
    return [segment for segment in segments if segment]


def _is_unresolvable(raw: str) -> bool:
    """True when `raw` contains a shell variable or command substitution.

    `$SP/out.txt` and `$(mktemp)` cannot be resolved to a real location without
    expanding the shell, which this guard deliberately does not do. Asserting a
    location for a target it cannot see is worse than saying nothing.
    """
    return "$" in raw or "`" in raw


def extract_redirects(tokens: list[str]) -> tuple[list[str], list[str]]:
    """Split a segment's tokens into (command tokens, write-redirect targets).

    A redirect can appear anywhere in a simple command, not only at the end, so this
    walks the whole segment rather than assuming position. Input redirection (`<`,
    `<<`, `<<<`) is a read, not a write, and its operand -- a filename or a heredoc
    delimiter -- is not one of the command's own arguments either, so both the
    operator and its operand are dropped from the returned command tokens.
    """
    command_tokens: list[str] = []
    write_targets: list[str] = []
    index = 0
    total = len(tokens)
    while index < total:
        token = tokens[index]
        if token in REDIRECT_OUT_OPS:
            if index + 1 < total:
                write_targets.append(tokens[index + 1])
                index += 2
            else:
                index += 1
            continue
        if token in REDIRECT_IN_OPS:
            index += 2 if index + 1 < total else 1
            continue
        command_tokens.append(token)
        index += 1
    return command_tokens, write_targets


def _positional_args(args: list[str]) -> list[str]:
    return [a for a in args if not a.startswith("-")]


def chmod_paths(args: list[str]) -> list[str]:
    """`chmod [-R] MODE PATH...` -- the first positional is the mode, not a path."""
    return _positional_args(args)[1:]


def chown_paths(args: list[str]) -> list[str]:
    """`chown [-R] OWNER[:GROUP] PATH...` -- ditto for the ownership spec."""
    return _positional_args(args)[1:]


def install_paths(args: list[str]) -> list[str]:
    """`install [-m MODE] [-o OWNER] [-g GROUP] SRC... DST` -- skip option values."""
    result: list[str] = []
    skip_next = False
    for arg in args:
        if skip_next:
            skip_next = False
            continue
        if arg in {"-m", "-o", "-g"}:
            skip_next = True
            continue
        if arg.startswith("-"):
            continue
        result.append(arg)
    return result


def sed_paths(args: list[str]) -> list[str]:
    """`sed -i SCRIPT FILE...`, or `sed -i -e SCRIPT FILE...` -- the script is not a path.

    Without `-e`/`-f` the script is the first positional argument (the source of the
    original bug: `sed -i 's/.../.../ ' "$SP/f.md"` treated the script text itself as a
    candidate path). With `-e SCRIPT` or `-f FILE` the script is supplied by the flag
    instead, so every remaining positional is a real file.
    """
    positionals: list[str] = []
    skip_next = False
    has_script_flag = False
    for arg in args:
        if skip_next:
            skip_next = False
            continue
        if arg in {"-e", "-f"}:
            has_script_flag = True
            skip_next = True
            continue
        if arg.startswith("-"):
            continue
        positionals.append(arg)
    return positionals if has_script_flag else positionals[1:]


PATH_ARG_EXTRACTORS = {
    "chmod": chmod_paths,
    "chown": chown_paths,
    "install": install_paths,
}


def parse_git(tokens: list[str], cwd: str) -> tuple[str, str, list[str]] | None:
    """Return (effective_cwd, subcommand, rest) for a git invocation, else None.

    Consumes git's GLOBAL options, including the two-token forms `-C <path>` and
    `-c <key>=<value>`. The first version's regex could not match those, so
    `git -C <primary> commit` and `git -c user.name=x commit` were both invisible to it.
    """
    index = 0
    while index < len(tokens) and tokens[index] in {"sudo", "env", "command", "nohup"}:
        index += 1
    if index >= len(tokens) or Path(tokens[index]).name != "git":
        return None
    index += 1

    effective_cwd = cwd
    while index < len(tokens):
        token = tokens[index]
        if token == "-C" and index + 1 < len(tokens):
            target = tokens[index + 1]
            effective_cwd = str((Path(effective_cwd) / target).resolve())
            index += 2
        elif token == "-c" and index + 1 < len(tokens):
            index += 2
        elif token.startswith("--git-dir") or token.startswith("--work-tree"):
            index += 2 if "=" not in token else 1
        elif token.startswith("-"):
            index += 1
        else:
            return effective_cwd, token, tokens[index + 1 :]
    return None


def check_git(tokens: list[str], cwd: str) -> None:
    parsed = parse_git(tokens, cwd)
    if parsed is None:
        return
    effective_cwd, verb, rest = parsed

    # `git add -A` is blocked everywhere, worktrees included: bulk staging is how build
    # output, source packets and another task's edits reach a commit that claims to close
    # exactly one Issue.
    if verb == "add" and any(arg in BULK_ADD_ARGS for arg in rest):
        emit(
            "bulk `git add -A` / `git add .`",
            "Stage explicit paths instead:\n"
            "    git add path/to/one.cs path/to/two.cs\n\n"
            "Bulk staging is how build output, source packets and unrelated work end up\n"
            "in a commit that claims to close one Issue.",
        )

    primary, _ = is_primary_checkout(effective_cwd)
    if not primary:
        return

    if verb in FORBIDDEN_VERBS:
        emit(FORBIDDEN_VERBS[verb], WORKTREE_GUIDANCE)

    if verb in {"checkout", "switch"}:
        positional = [a for a in rest if not a.startswith("-")]
        # `git checkout -- <path>` restores files and leaves the branch alone.
        if "--" not in rest and positional and positional[0] != "main":
            emit(f"checking out '{positional[0]}' in the primary checkout", WORKTREE_GUIDANCE)
        if "--detach" in rest:
            emit("detaching HEAD in the primary checkout", WORKTREE_GUIDANCE)

    if verb == "restore" and ("--staged" in rest or "-S" in rest):
        emit("unstaging in the primary checkout", WORKTREE_GUIDANCE)

    if verb == "branch" and ("-f" in rest or "--force" in rest or "-D" in rest):
        emit("forcibly moving or deleting a branch in the primary checkout", WORKTREE_GUIDANCE)

    if verb == "merge" and not any(a == "--ff-only" for a in rest):
        emit(
            "merge in the primary checkout without --ff-only",
            "The primary checkout may only fast-forward to a new origin/main:\n"
            "    git merge --ff-only origin/main\n\n"
            "Anything else creates history in a checkout that is supposed to only follow it.",
        )

    if verb == "worktree" and rest and rest[0] == "add":
        for arg in rest[1:]:
            if arg.startswith("-"):
                continue
            target = (Path(effective_cwd) / arg).resolve()
            top = git(["rev-parse", "--show-toplevel"], effective_cwd)
            if top and _is_within(target, Path(top).resolve()):
                emit(
                    f"creating a worktree inside the repository ({arg})",
                    "Worktrees live OUTSIDE the repository. One inside it eventually gets\n"
                    "committed, scanned by a tool that did not expect it, or deleted by a\n"
                    f"clean step. Put it under ${WORKTREE_ROOT_VARIABLE}, outside the repository\n"
                    "(AGENTS.md section 4).",
                )
            break
    if verb == "worktree" and rest and rest[0] == "remove" and (
        "--force" in rest or "-f" in rest
    ):
        emit("force-removing a worktree", WORKTREE_GUIDANCE)


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def primary_root(cwd: str) -> Path | None:
    primary, top = is_primary_checkout(cwd)
    return Path(top).resolve() if primary and top else None


def check_shell_writes(tokens: list[str], cwd: str) -> None:
    """Block in-place file mutation targeting the primary checkout.

    The first version guarded only the Write/Edit tools, so every shell write path was
    open: `sed -i`, `echo >>`, `cat > file <<EOF`, `tee`, `rm -rf`. Agents edit through
    the shell routinely, which made that a large hole in a guard that reads as complete.

    `tokens` is one already-segmented, quote-aware token stream (see full_tokenize /
    split_segments) -- not raw text, so a `>` living inside a quoted argument was never
    a candidate here in the first place.
    """
    root = primary_root(cwd)
    if root is None:
        return

    def blocked_if_inside(raw: str, what: str) -> None:
        if _is_unresolvable(raw):
            return
        target = (Path(cwd) / raw).resolve()
        if _is_within(target, root):
            emit(f"{what} targeting the primary checkout ({raw})", WORKTREE_GUIDANCE)

    command_tokens, write_targets = extract_redirects(tokens)
    for raw_target in write_targets:
        blocked_if_inside(raw_target, "shell redirection")

    if not command_tokens:
        return
    command = Path(command_tokens[0]).name
    args = command_tokens[1:]

    if command == "sed" and any(a == "-i" or a.startswith("-i") for a in args):
        for arg in sed_paths(args):
            blocked_if_inside(arg, "in-place sed")

    if command == "tee":
        for arg in _positional_args(args):
            blocked_if_inside(arg, "tee")

    if command in FILE_MUTATORS:
        extractor = PATH_ARG_EXTRACTORS.get(command, _positional_args)
        for arg in extractor(args):
            blocked_if_inside(arg, f"`{command}`")


def main() -> int:
    if os.environ.get(ESCAPE_HATCH) == "1":
        return 0

    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0  # Never break the session over an unparseable payload.

    tool = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {}) or {}
    cwd = payload.get("cwd") or os.getcwd()

    if tool in {"Write", "Edit", "NotebookEdit"}:
        target = tool_input.get("file_path") or tool_input.get("notebook_path")
        if not target:
            return 0
        resolved = Path(target).expanduser()
        resolved = (Path(cwd) / resolved).resolve() if not resolved.is_absolute() else resolved.resolve()
        probe = str(resolved.parent) if resolved.parent.is_dir() else cwd
        primary, top = is_primary_checkout(probe)
        if primary and top and _is_within(resolved, Path(top).resolve()):
            emit(f"{tool} targets the primary checkout ({resolved.name})", WORKTREE_GUIDANCE)
        return 0

    if tool != "Bash":
        return 0

    command = tool_input.get("command", "") or ""
    tokens = full_tokenize(strip_heredocs(command))
    for segment in split_segments(tokens):
        check_git(segment, cwd)
        check_shell_writes(segment, cwd)

    return 0


if __name__ == "__main__":
    sys.exit(main())
