# CLAUDE.md

**[`AGENTS.md`](AGENTS.md) is the governing contract for this repository. Read it first.**

It applies to every agent regardless of vendor. This file states no rule of its own, on purpose:
mirrored governing documents drift, and a drifted contract is worse than no contract. If you want
to know what you may do, what the gate is, how work is dispatched, or what to do when the map and
the corpus disagree, it is in `AGENTS.md`.

Claude-specific adapters, which say how a role is invoked rather than what it may do:

| Path | What it is |
|---|---|
| `.claude/agents/engine-dev.md` | the engine developer's charter |
| `.claude/agents/repo-steward.md` | the structural reviewer's charter (read-only) |
| `.claude/agents/rules-conformance.md` | the semantic reviewer's charter (read-only) |
| `.claude/hooks/primary-checkout-guard.py` | the `PreToolUse` guard that keeps implementation work out of the primary checkout |
| `.claude/settings.json` | which tools the guard runs before |

The guard's escape hatch is `RULES_ENGINE_ALLOW_PRIMARY_MUTATION=1`, documented in `AGENTS.md`
§4, and its name is configuration in `.github/agent-policy.json`.

This file is managed by rules-factory: `factory produce` updates it when its recipe changes and
refuses to overwrite a hand edit.
