using RulesKernel.Resolution;

namespace Tax121PrincipalResidence;

/// <summary>
/// The hand-written side of the typed contract rules-factory generates in
/// <c>Generated/Contracts.g.cs</c>: one partial method per <c>implemented</c> map entry, each a
/// thin adapter over the rule that implements it.
/// </summary>
/// <remarks>
/// <para>
/// Each file under <c>Handlers/</c> holds one entry's handler and the <c>init</c> properties it
/// reads, declared on the entry's generated request type. A caller resolves an entry through
/// <see cref="EntryPoints"/> with those properties set, and the handler hands them to the rule
/// unchanged. Nothing here decides a rule: every answer, and every decline, is the rule's own.
/// </para>
/// <para>
/// A request built by the dictionary dispatch (<see cref="Registry.Resolve(string, RuleRequest)"/>)
/// has every input at its default. A handler whose rule needs an input it was not given throws
/// <see cref="ArgumentException"/> naming it: a missing input is the caller's error, not a gap in
/// the corpus, so it is not an unresolved result, and it is never defaulted.
/// </para>
/// </remarks>
internal static partial class Handlers
{
    private static Resolution<object> Answer<T>(Resolution<T> resolution)
        where T : notnull =>
        resolution.Match(value => Resolution<object>.FromValue(value), Resolution<object>.FromUnresolved);

    private static T Demand<T>(T? input, string entryId, string name)
        where T : struct =>
        input ?? throw Missing(entryId, name);

    private static ArgumentException Missing(string entryId, string name) =>
        new($"resolving the map entry '{entryId}' needs its request's {name}, and it was not set", name);
}
