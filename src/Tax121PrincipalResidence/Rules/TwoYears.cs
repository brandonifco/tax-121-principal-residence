using System.Globalization;
using RulesKernel.Provenance;
using RulesKernel.Resolution;

namespace Tax121PrincipalResidence;

/// <summary>
/// <see cref="MapEntries.OwnershipAndUseAggregation"/>, § 1.121-1(c)(1): "The requirements of ownership and use
/// for periods aggregating 2 years or more may be satisfied by establishing ownership and use for 24 full months
/// or for 730 days (365 × 2)."
/// </summary>
/// <remarks>
/// A value, not a procedure: the three equivalent quantities the corpus prints. Either measure alone satisfies
/// the two years, so a count below one threshold says nothing about the other; neither predicate is a finding that
/// the requirement is not met. How ownership and use are counted from dates is not stated here, and this value does
/// not count them.
/// </remarks>
public sealed record TwoYearAggregate
{
    /// <summary>"periods aggregating 2 years or more".</summary>
    public int Years => TwoYears.Years;

    /// <summary>"24 full months".</summary>
    public int FullMonths => TwoYears.FullMonths;

    /// <summary>"730 days (365 × 2)".</summary>
    public int Days => TwoYears.Days;

    /// <summary>Where the value is stated: <c>§ 1.121-1(c)</c>.</summary>
    public SourceLocator Authority => MapEntries.OwnershipAndUseAggregation.Locator;

    /// <summary>Whether <paramref name="fullMonths"/> full months of ownership and use satisfy the two years: 24 or more.</summary>
    /// <param name="fullMonths">The full months of ownership and use established.</param>
    /// <returns>True at 24 or more; false below, which does not rule out <see cref="IsEstablishedByDays"/>.</returns>
    public bool IsEstablishedByFullMonths(int fullMonths) => fullMonths >= FullMonths;

    /// <summary>Whether <paramref name="days"/> days of ownership and use satisfy the two years: 730 or more.</summary>
    /// <param name="days">The days of ownership and use established.</param>
    /// <returns>True at 730 or more; false below, which does not rule out <see cref="IsEstablishedByFullMonths"/>.</returns>
    public bool IsEstablishedByDays(int days) => days >= Days;

    /// <inheritdoc/>
    public override string ToString() =>
        string.Create(
            CultureInfo.InvariantCulture,
            $"periods aggregating {Years} years: {FullMonths} full months or {Days} days [{Authority}]");
}

/// <summary>§ 1.121-1(c)(1): two years, as 24 full months or 730 days.</summary>
public static class TwoYears
{
    /// <summary>"2 years".</summary>
    public const int Years = 2;

    /// <summary>"24 full months".</summary>
    public const int FullMonths = 24;

    /// <summary>"730 days (365 × 2)".</summary>
    public const int Days = 365 * 2;

    /// <summary>
    /// <see cref="MapEntries.OwnershipAndUseAggregation"/> for a sale or exchange on <paramref name="saleOrExchangeDate"/>:
    /// the value, or the decline <see cref="Applicability.Gate"/> answers when this section does not apply (decision 0001).
    /// </summary>
    /// <param name="saleOrExchangeDate">The date of the sale or exchange. Required, never defaulted.</param>
    /// <returns>The value, or the decline.</returns>
    /// <exception cref="ArgumentException">No date was given; its <c>ParamName</c> is <c>SaleOrExchangeDate</c>.</exception>
    public static Resolution<TwoYearAggregate> For(DateOnly? saleOrExchangeDate) =>
        Applicability.Gate(MapEntries.OwnershipAndUseAggregation, saleOrExchangeDate) is { } decline
            ? Resolution<TwoYearAggregate>.FromUnresolved(decline)
            : Resolution<TwoYearAggregate>.FromValue(new TwoYearAggregate());
}
