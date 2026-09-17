using System.Globalization;
using RulesKernel.Provenance;
using RulesKernel.Resolution;

namespace Tax121PrincipalResidence;

/// <summary>
/// Whether this section applies to one sale or exchange: <see cref="MapEntries.EffectiveDate"/>,
/// "(f) Effective date. This section is applicable for sales and exchanges on or after Decmeber 24,
/// 2002." (The misspelling is the corpus's, quoted verbatim.)
/// </summary>
/// <param name="SaleOrExchangeDate">The date of the sale or exchange the caller supplied.</param>
/// <param name="Applies">True when the sale or exchange is on or after <see cref="ApplicableFrom"/>; false when it is before.</param>
public sealed record SectionApplicability(DateOnly SaleOrExchangeDate, bool Applies)
{
    /// <summary>The first date of a sale or exchange this section is applicable for: 24 December 2002.</summary>
    public DateOnly ApplicableFrom => Applicability.ApplicableFrom;

    /// <summary>Where the rule is stated: <c>§ 1.121-1(f)</c>.</summary>
    public SourceLocator Authority => MapEntries.EffectiveDate.Locator;

    /// <inheritdoc/>
    public override string ToString() =>
        string.Create(
            CultureInfo.InvariantCulture,
            $"a sale or exchange on {SaleOrExchangeDate:yyyy-MM-dd} is {(Applies ? "within" : "outside")} this section, applicable on or after {ApplicableFrom:yyyy-MM-dd} [{Authority}]");
}

/// <summary>§ 1.121-1(f): when this section applies.</summary>
public static class Applicability
{
    /// <summary>
    /// The date the rule names, not the date the corpus is pinned to: sales and exchanges "on or after"
    /// it are within the section.
    /// </summary>
    public static readonly DateOnly ApplicableFrom = new(2002, 12, 24);

    /// <summary>
    /// <see cref="MapEntries.EffectiveDate"/>: whether this section is applicable for a sale or exchange
    /// on <paramref name="saleOrExchangeDate"/>.
    /// </summary>
    /// <remarks>
    /// The rule is clear, so both outcomes are answers: a sale before the date is outside this section,
    /// not a question the engine declines. Electing to apply the section retroactively is
    /// <c>retroactive-election</c>'s, which the map declines as out of scope (§ 1.121-4(j)); this rule
    /// does not consult it.
    /// </remarks>
    /// <param name="saleOrExchangeDate">The date of the sale or exchange.</param>
    /// <returns>The finding, which always resolves.</returns>
    public static Resolution<SectionApplicability> Of(DateOnly saleOrExchangeDate) =>
        Resolution<SectionApplicability>.FromValue(
            new SectionApplicability(saleOrExchangeDate, saleOrExchangeDate >= ApplicableFrom));
}
