using System.Globalization;
using RulesKernel.Provenance;
using RulesKernel.Resolution;

namespace Tax121PrincipalResidence;

/// <summary>
/// What <see cref="MapEntries.UseRequiresOccupancy"/> finds for one taxpayer and one residence: "(2) Use. (i) In
/// establishing whether a taxpayer has satisfied the 2-year use requirement, occupancy of the residence is
/// required."
/// </summary>
/// <param name="Owned">The caller's fact: the taxpayer owned the residence. Carried through unchanged; it is the
/// ownership leg's fact, and it never supplies the use leg's.</param>
/// <param name="Occupied">The caller's fact: the taxpayer occupied the residence.</param>
public sealed record OccupancyFinding(bool Owned, bool Occupied)
{
    /// <summary>
    /// True when the use leg's occupancy requirement is met, which is when the taxpayer occupied the residence,
    /// owned or not. False means the use requirement is not satisfied, however long the residence was owned.
    /// </summary>
    /// <remarks>
    /// Occupancy is required, and this entry says no more than that: whether occupied time is use as a principal
    /// residence, and whether it aggregates to 2 years, are other entries' rules.
    /// </remarks>
    public bool OccupancyRequirementMet => Occupied;

    /// <summary>Where the rule is stated: <c>§ 1.121-1(c)(2)</c>.</summary>
    public SourceLocator Authority => MapEntries.UseRequiresOccupancy.Locator;

    /// <inheritdoc/>
    public override string ToString() =>
        string.Create(
            CultureInfo.InvariantCulture,
            $"a taxpayer who {(Owned ? "owned" : "did not own")} and {(Occupied ? "occupied" : "did not occupy")} the residence {(OccupancyRequirementMet ? "meets" : "does not meet")} the use requirement's occupancy requirement [{Authority}]");
}

/// <summary>§ 1.121-1(c)(2)(i): use means occupancy.</summary>
public static class Occupancy
{
    /// <summary>
    /// <see cref="MapEntries.UseRequiresOccupancy"/>: whether the occupancy the use requirement needs is there.
    /// </summary>
    /// <remarks>
    /// Short temporary absences counted as use are <c>short-temporary-absences</c>'s question, not this rule's:
    /// <paramref name="occupied"/> is the caller's fact as given.
    /// </remarks>
    /// <param name="owned">Whether the taxpayer owned the residence.</param>
    /// <param name="occupied">Whether the taxpayer occupied the residence.</param>
    /// <returns>The finding, which always resolves: the rule is clear.</returns>
    public static Resolution<OccupancyFinding> Of(bool owned, bool occupied) =>
        Resolution<OccupancyFinding>.FromValue(new OccupancyFinding(owned, occupied));
}
