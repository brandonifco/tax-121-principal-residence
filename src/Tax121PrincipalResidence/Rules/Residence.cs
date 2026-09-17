using System.Globalization;
using RulesKernel.Resolution;

namespace Tax121PrincipalResidence;

/// <summary>
/// § 1.121-1(b): <see cref="MapEntries.ResidenceFactsAndCircumstances"/>, "Whether property is used by the
/// taxpayer as the taxpayer's residence depends upon all the facts and circumstances."
/// </summary>
/// <remarks>
/// The map records this entry's question as unresolved, <c>RequiresInterpretation</c>: the corpus makes the
/// whole question turn on all the facts and circumstances, states no factor, no threshold and no weighting for
/// it, and names nobody to make it. The six factors of § 1.121-1(b)(2) are for the principal-residence
/// question, not this one. So the engine declines whatever facts it is given, and says which facts those were
/// (the map's note): weighing them would be this engine answering a question the published map says is open.
/// </remarks>
public static class Residence
{
    /// <summary>
    /// <see cref="MapEntries.ResidenceFactsAndCircumstances"/>: the entry's decline, always.
    /// </summary>
    /// <param name="factsAndCircumstances">
    /// The facts and circumstances the caller gives, each in its own words, in the caller's order. None is read
    /// as a factor; each is repeated in the decline.
    /// </param>
    /// <returns>
    /// <see cref="UnresolvedReason.RequiresInterpretation"/>, citing this entry's own locator, § 1.121-1(b), and
    /// naming the facts given.
    /// </returns>
    /// <exception cref="ArgumentException">A fact is null; its <c>ParamName</c> is <c>FactsAndCircumstances</c>.</exception>
    public static Resolution<object> Used(IReadOnlyList<string> factsAndCircumstances)
    {
        ArgumentNullException.ThrowIfNull(factsAndCircumstances);
        if (factsAndCircumstances.Any(fact => fact is null))
        {
            throw new ArgumentException(
                $"resolving the map entry '{MapEntries.ResidenceFactsAndCircumstances.Id}' needs each of its facts and circumstances to be set, and one was null",
                nameof(Requests.ResidenceFactsAndCircumstancesRequest.FactsAndCircumstances));
        }

        var given = factsAndCircumstances.Count == 0
            ? "it was given no facts"
            : "it was given these facts: " + string.Join("; ", factsAndCircumstances.Select(fact => $"\"{fact}\""));

        return Resolution<object>.FromUnresolved(new UnresolvedResult(
            UnresolvedReason.RequiresInterpretation,
            string.Create(
                CultureInfo.InvariantCulture,
                $"decide whether the map entry '{MapEntries.ResidenceFactsAndCircumstances.Id}' holds, whether property is used by the taxpayer as the taxpayer's residence: § 1.121-1(b) makes it depend upon all the facts and circumstances, and states no factor, no threshold and no weighting for it and names nobody to make it; {given}"),
            MapEntries.ResidenceFactsAndCircumstances.Locator));
    }
}
