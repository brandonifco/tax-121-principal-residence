using RulesKernel.Resolution;
using Tax121PrincipalResidence.Requests;
using Xunit;

namespace Tax121PrincipalResidence.Tests;

/// <summary>
/// <c>ownership-and-use-aggregation</c>, § 1.121-1(c)(1), resolved through
/// <see cref="EntryPoints.OwnershipAndUseAggregation"/>: two years as 24 full months or 730 days (365 × 2), for a
/// sale on or after the effective date; a decline before it; no date assumed.
/// </summary>
public class OwnershipAndUseAggregationTests
{
    private static TwoYearAggregate Resolve(DateOnly sale)
    {
        var resolved = Assert.IsType<Resolution<object>.Resolved>(
            EntryPoints.OwnershipAndUseAggregation.Resolve(new OwnershipAndUseAggregationRequest { SaleOrExchangeDate = sale }));
        return Assert.IsType<TwoYearAggregate>(resolved.Value);
    }

    private static TwoYearAggregate Value => Resolve(new DateOnly(2002, 12, 24));

    [Fact]
    public void The_value_is_2_years_as_24_full_months_or_730_days_citing_1_121_1_c()
    {
        var value = Value;

        Assert.Equal(2, value.Years);
        Assert.Equal(24, value.FullMonths);
        Assert.Equal(730, value.Days);
        Assert.Equal("cfr-26-1.121-1", value.Authority.SourceId);
        Assert.Equal("§ 1.121-1(c)", value.Authority.Citation);
        Assert.Equal(EntryPoints.OwnershipAndUseAggregation.Registered.Locator, value.Authority);
    }

    [Fact]
    public void Twenty_four_full_months_establish_the_two_years() =>
        Assert.True(Value.IsEstablishedByFullMonths(24));

    [Fact]
    public void Twenty_three_full_months_do_not_by_months() =>
        Assert.False(Value.IsEstablishedByFullMonths(23));

    [Fact]
    public void Twenty_five_full_months_establish_the_two_years() =>
        Assert.True(Value.IsEstablishedByFullMonths(25));

    [Fact]
    public void Seven_hundred_thirty_days_establish_the_two_years() =>
        Assert.True(Value.IsEstablishedByDays(730));

    [Fact]
    public void Seven_hundred_twenty_nine_days_do_not_by_days() =>
        Assert.False(Value.IsEstablishedByDays(729));

    [Fact]
    public void Seven_hundred_thirty_one_days_establish_the_two_years() =>
        Assert.True(Value.IsEstablishedByDays(731));

    [Fact]
    public void A_sale_on_23_December_2002_declines_OutsideCurrentScope_citing_1_121_1_f()
    {
        var unresolved = Assert.IsType<Resolution<object>.Unresolved>(
            EntryPoints.OwnershipAndUseAggregation.Resolve(
                new OwnershipAndUseAggregationRequest { SaleOrExchangeDate = new DateOnly(2002, 12, 23) }));

        Assert.Equal(UnresolvedReason.OutsideCurrentScope, unresolved.Result.Reason);
        Assert.Equal(MapEntries.EffectiveDate.Locator, unresolved.Result.Locator);
        Assert.Equal("§ 1.121-1(f)", unresolved.Result.Locator.Citation);
        Assert.Contains("'ownership-and-use-aggregation'", unresolved.Result.Attempted, StringComparison.Ordinal);
        Assert.Contains("'retroactive-election'", unresolved.Result.Attempted, StringComparison.Ordinal);
    }

    [Fact]
    public void Without_a_sale_or_exchange_date_it_refuses_rather_than_assume_one()
    {
        var error = Assert.Throws<ArgumentException>(
            () => EntryPoints.OwnershipAndUseAggregation.Resolve(new OwnershipAndUseAggregationRequest()));

        Assert.Equal(nameof(OwnershipAndUseAggregationRequest.SaleOrExchangeDate), error.ParamName);
        Assert.Contains("'ownership-and-use-aggregation'", error.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void The_dictionary_dispatch_carries_no_date_and_refuses_the_same_way()
    {
        var error = Assert.Throws<ArgumentException>(() => Registry.Resolve("ownership-and-use-aggregation", RuleRequest.Empty));

        Assert.Equal(nameof(OwnershipAndUseAggregationRequest.SaleOrExchangeDate), error.ParamName);
    }
}
