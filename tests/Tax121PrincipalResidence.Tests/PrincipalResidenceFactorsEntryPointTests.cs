using RulesKernel.Resolution;
using Tax121PrincipalResidence.Requests;
using Xunit;

namespace Tax121PrincipalResidence.Tests;

/// <summary>
/// <c>principal-residence-factors</c>, § 1.121-1(b)(2), resolved through <see cref="EntryPoints.PrincipalResidenceFactors"/>:
/// all six factors as printed, not the whole list, the effective-date gate, and no date assumed.
/// </summary>
public class PrincipalResidenceFactorsEntryPointTests
{
    private static readonly DateOnly EffectiveDate = new(2002, 12, 24);

    private static RelevantFactors Resolved(DateOnly sale) =>
        Assert.IsType<RelevantFactors>(Assert.IsType<Resolution<object>.Resolved>(
            EntryPoints.PrincipalResidenceFactors.Resolve(new PrincipalResidenceFactorsRequest { SaleOrExchangeDate = sale })).Value);

    [Fact]
    public void The_list_is_the_six_factors_as_printed_in_order_citing_1_121_1_b_2()
    {
        var factors = Resolved(EffectiveDate);

        Assert.Equal(
            new RelevantFactor[]
            {
                new("i", "The taxpayer's place of employment"),
                new("ii", "The principal place of abode of the taxpayer's family members"),
                new("iii", "The address listed on the taxpayer's federal and state tax returns, driver's license, automobile registration, and voter registration card"),
                new("iv", "The taxpayer's mailing address for bills and correspondence"),
                new("v", "The location of the taxpayer's banks"),
                new("vi", "The location of religious organizations and recreational clubs with which the taxpayer is affiliated"),
            },
            factors.Factors);
        Assert.Equal("cfr-26-1.121-1", factors.Authority.SourceId);
        Assert.Equal("§ 1.121-1(b)(2)", factors.Authority.Citation);
        Assert.Equal(EntryPoints.PrincipalResidenceFactors.Registered.Locator, factors.Authority);
    }

    [Fact]
    public void The_six_are_not_the_whole_list() =>
        Assert.False(Resolved(EffectiveDate).IsExhaustive);

    [Fact]
    public void A_sale_on_23_December_2002_declines_OutsideCurrentScope_citing_1_121_1_f_and_naming_this_entry()
    {
        var unresolved = Assert.IsType<Resolution<object>.Unresolved>(
            EntryPoints.PrincipalResidenceFactors.Resolve(
                new PrincipalResidenceFactorsRequest { SaleOrExchangeDate = new DateOnly(2002, 12, 23) })).Result;

        Assert.Equal(UnresolvedReason.OutsideCurrentScope, unresolved.Reason);
        Assert.Equal(EntryPoints.EffectiveDate.Registered.Locator, unresolved.Locator);
        Assert.Equal("§ 1.121-1(f)", unresolved.Locator.Citation);
        Assert.Contains("'principal-residence-factors'", unresolved.Attempted, StringComparison.Ordinal);
        Assert.Contains("'retroactive-election'", unresolved.Attempted, StringComparison.Ordinal);
    }

    [Fact]
    public void Without_a_sale_or_exchange_date_it_refuses_rather_than_assume_one()
    {
        var error = Assert.Throws<ArgumentException>(
            () => EntryPoints.PrincipalResidenceFactors.Resolve(new PrincipalResidenceFactorsRequest()));

        Assert.Equal(nameof(PrincipalResidenceFactorsRequest.SaleOrExchangeDate), error.ParamName);
        Assert.Contains("'principal-residence-factors'", error.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void The_dictionary_dispatch_carries_no_date_and_refuses_the_same_way()
    {
        var error = Assert.Throws<ArgumentException>(
            () => Registry.Resolve("principal-residence-factors", RuleRequest.Empty));

        Assert.Equal(nameof(PrincipalResidenceFactorsRequest.SaleOrExchangeDate), error.ParamName);
    }
}
