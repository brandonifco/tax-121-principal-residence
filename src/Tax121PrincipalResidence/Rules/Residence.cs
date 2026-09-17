using System.Collections.Immutable;
using RulesKernel.Provenance;
using RulesKernel.Resolution;

namespace Tax121PrincipalResidence;

/// <summary>A kind of property § 1.121-1(b) names as one a residence may include.</summary>
public enum ResidencePropertyKind
{
    /// <summary>"a houseboat".</summary>
    Houseboat,

    /// <summary>"a house trailer".</summary>
    HouseTrailer,
}

/// <summary>
/// The property § 1.121-1(b) says a residence may include: <see cref="MapEntries.ResidenceMayInclude"/>,
/// "A property used by the taxpayer as the taxpayer's residence may include a houseboat, a house trailer,".
/// </summary>
/// <remarks>
/// The whole of the list this entry's span prints, in the corpus's order. It is what may be a residence,
/// never that any property is one: that stays with <see cref="MapEntries.ResidenceFactsAndCircumstances"/>.
/// The co-operative apartment the sentence goes on to name is <see cref="MapEntries.ResidenceCooperativeApartment"/>'s,
/// and is not in this list.
/// </remarks>
public sealed record PropertyThatMayBeAResidence
{
    private static readonly ImmutableArray<ResidencePropertyKind> Listed =
        [ResidencePropertyKind.Houseboat, ResidencePropertyKind.HouseTrailer];

    /// <summary>The kinds of property, as the corpus lists them: a houseboat, a house trailer.</summary>
    public ImmutableArray<ResidencePropertyKind> Kinds => Listed;

    /// <summary>Where the list is stated: <c>§ 1.121-1(b)</c>.</summary>
    public SourceLocator Authority => MapEntries.ResidenceMayInclude.Locator;

    /// <summary>The corpus's words for <paramref name="kind"/>.</summary>
    /// <param name="kind">A kind of property in <see cref="Kinds"/>.</param>
    /// <returns>"a houseboat" or "a house trailer".</returns>
    public static string AsPrinted(ResidencePropertyKind kind) =>
        kind switch
        {
            ResidencePropertyKind.Houseboat => "a houseboat",
            ResidencePropertyKind.HouseTrailer => "a house trailer",
            _ => throw new ArgumentOutOfRangeException(nameof(kind), kind, "not a kind of property § 1.121-1(b) lists"),
        };

    /// <inheritdoc/>
    public override string ToString() =>
        $"a property used by the taxpayer as the taxpayer's residence may include {string.Join(", ", Kinds.Select(AsPrinted))} [{Authority}]";
}

/// <summary>§ 1.121-1(b): what a residence may include.</summary>
public static class Residence
{
    /// <summary><see cref="MapEntries.ResidenceMayInclude"/>: the list as printed. The rule is clear and always resolves.</summary>
    /// <returns>The list.</returns>
    public static Resolution<PropertyThatMayBeAResidence> MayInclude() =>
        Resolution<PropertyThatMayBeAResidence>.FromValue(new PropertyThatMayBeAResidence());
}
