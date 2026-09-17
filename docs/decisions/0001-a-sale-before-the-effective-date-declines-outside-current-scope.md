# 0001 — A sale before the effective date declines OutsideCurrentScope, naming the retroactive election

**Status:** accepted. Ruled by Brandon, 2026-09-17 (#26).

## Context

§ 1.121-1(f): *"This section is applicable for sales and exchanges on or after Decmeber 24, 2002.
For rules on electing to apply the provisions of this section retroactively, see § 1.121-4(j)."*
The map (`RulesFactory.Maps.Tax121PrincipalResidence` 2.0.0) splits it in two:

- `effective-date`, `kind: operation`, `scope: in`, `clarity: clear`. Every other `scope: in` entry
  names it in `enabledBy`.
- `retroactive-election`, `scope: out`, the same locator. Its cross-reference to § 1.121-4(j) is
  unmapped: that section is not in this engine's corpus.

`effective-date` is implemented (#24, PR #25). It resolves a sale before 24 December 2002 to the
value `SectionApplicability { Applies = false }`, and that stays as it is: for that entry the
question is settled, and a "no" is an answer.

The review of #25 found that an entry `effective-date` enables cannot read `Applies = false` as
"this section does not apply, so no exclusion". Paragraph (f) points to an election that applies the
section retroactively. For a taxpayer who made it, "no" would be wrong, and whether the election was
made, and what it does, is § 1.121-4(j)'s, which this engine does not have.

This is not an overlay `rulings[]` item. rules-factory decision 0027 rulings quote an entry's
`ambiguity.question`, and `effective-date` is `clarity: clear` with no question. The ruling is about
reachability across entries, so it is recorded here.

## Decision

**When `effective-date` does not hold, a gated entry declines `OutsideCurrentScope`.** The decline
cites § 1.121-1(f) (`effective-date`'s locator) and its `Attempted` names the retroactive election
(`retroactive-election`, see § 1.121-4(j)) as the question the engine does not answer. It does not
answer "not excludable" or anything like it, and it does not throw.

Every gated entry applies it through one helper in `Rules/Applicability.cs`:

```csharp
public static UnresolvedResult? Applicability.Gate(MapEntry entry, DateOnly? saleOrExchangeDate)
```

It returns null for a sale or exchange on or after 24 December 2002, and the entry then evaluates
its own rule. For an earlier date it returns the decline above, naming `entry`. A missing date is
refused with `ArgumentException` whose `ParamName` is `SaleOrExchangeDate`, as `effective-date` does:
a missing input is the caller's error, not a gap in the corpus, and it is never defaulted. The helper
reads `Applicability.Of`, so the date and the comparison exist once.

## What was rejected

**Answer "not applicable" (or "not excludable") for a sale before the date.** That is correct only
for a taxpayer who did not elect under § 1.121-4(j). For one who did, it is a wrong answer the engine
has no way to know is wrong, which is the answer a rules engine must not give.

**Throw.** Being unable to answer because the question sits in a section this engine does not have is
an ordinary, enumerable outcome, and a legitimate question a caller must see and handle. An exception
hides it behind an error and makes it look like the caller's mistake.

## Consequences

**The locator cannot say which entry's question it is.** `effective-date` and `retroactive-election`
both cite `§ 1.121-1(f)`, so a mutation citing `retroactive-election`'s locator left every test green.
The decline's `Attempted` is what names the election, and the test asserts it.

**Every gated entry needs the sale or exchange date.** Its request declares `DateOnly?
SaleOrExchangeDate`, as `EffectiveDateRequest` does, and its handler calls `Applicability.Gate`
before its rule.

**`effective-date` itself is unchanged.** `Applies = false` is still its value, and it does not
consult the election.
