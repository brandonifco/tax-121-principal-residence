using RulesKernel.Resolution;
using Tax121PrincipalResidence.Requests;
using Xunit;

namespace Tax121PrincipalResidence.Tests;

/// <summary>
/// <see cref="Applicability.Gate"/>: how an entry <c>effective-date</c> enables reads it (decision 0001). A sale
/// before 24 December 2002 declines <see cref="UnresolvedReason.OutsideCurrentScope"/>, citing § 1.121-1(f) and
/// naming the retroactive election; a sale on or after it proceeds; no date is assumed.
/// </summary>
public class EffectiveDateGateTests
{
    private static readonly MapEntry Gated = MapEntries.ExclusionOfGain;

    [Fact]
    public void A_sale_on_23_December_2002_declines_OutsideCurrentScope_citing_1_121_1_f_and_naming_the_retroactive_election()
    {
        var decline = Applicability.Gate(Gated, new DateOnly(2002, 12, 23));

        Assert.NotNull(decline);
        Assert.Equal(UnresolvedReason.OutsideCurrentScope, decline.Reason);
        Assert.Equal(MapEntries.EffectiveDate.Locator, decline.Locator);
        Assert.Equal("§ 1.121-1(f)", decline.Locator.Citation);
        Assert.Contains("'exclusion-of-gain'", decline.Attempted, StringComparison.Ordinal);
        Assert.Contains("2002-12-23", decline.Attempted, StringComparison.Ordinal);
        Assert.Contains("'retroactive-election'", decline.Attempted, StringComparison.Ordinal);
        Assert.Contains("§ 1.121-4(j)", decline.Attempted, StringComparison.Ordinal);
    }

    [Fact]
    public void A_sale_on_24_December_2002_proceeds() =>
        Assert.Null(Applicability.Gate(Gated, new DateOnly(2002, 12, 24)));

    [Fact]
    public void A_sale_on_25_December_2002_proceeds() =>
        Assert.Null(Applicability.Gate(Gated, new DateOnly(2002, 12, 25)));

    [Fact]
    public void Without_a_sale_or_exchange_date_the_gate_refuses_rather_than_assume_one()
    {
        var error = Assert.Throws<ArgumentException>(() => Applicability.Gate(Gated, null));

        Assert.Equal(nameof(EffectiveDateRequest.SaleOrExchangeDate), error.ParamName);
        Assert.Contains("'exclusion-of-gain'", error.Message, StringComparison.Ordinal);
    }
}
