using RulesKernel.Resolution;
using Tax121PrincipalResidence.Requests;
using Xunit;

namespace Tax121PrincipalResidence.Tests;

/// <summary>
/// <c>residence-facts-and-circumstances</c>, § 1.121-1(b). The map records the entry's question as unresolved,
/// <c>RequiresInterpretation</c>, so the engine declines, citing this entry's own locator and naming the facts it
/// was given. A sale before 24 December 2002 declines through the effective-date gate instead (decision 0001).
/// </summary>
public class ResidenceFactsAndCircumstancesEntryPointTests
{
    private static UnresolvedResult Decline(Resolution<object> resolution) =>
        Assert.IsType<Resolution<object>.Unresolved>(resolution).Result;

    [Fact]
    public void A_sale_on_24_December_2002_declines_RequiresInterpretation_citing_1_121_1_b_and_names_the_facts_given()
    {
        var unresolved = Decline(EntryPoints.ResidenceFactsAndCircumstances.Resolve(new ResidenceFactsAndCircumstancesRequest
        {
            SaleOrExchangeDate = new DateOnly(2002, 12, 24),
            FactsAndCircumstances = ["lived in the house every weekend", "kept a boat docked there"],
        }));

        Assert.Equal(UnresolvedReason.RequiresInterpretation, unresolved.Reason);
        Assert.Equal("cfr-26-1.121-1", unresolved.Locator.SourceId);
        Assert.Equal("§ 1.121-1(b)", unresolved.Locator.Citation);
        Assert.Equal(EntryPoints.ResidenceFactsAndCircumstances.Registered.Locator, unresolved.Locator);
        Assert.Contains("'residence-facts-and-circumstances'", unresolved.Attempted, StringComparison.Ordinal);
        Assert.Contains("all the facts and circumstances", unresolved.Attempted, StringComparison.Ordinal);
        Assert.EndsWith(
            "it was given these facts: \"lived in the house every weekend\"; \"kept a boat docked there\"",
            unresolved.Attempted,
            StringComparison.Ordinal);
    }

    [Fact]
    public void With_no_facts_given_it_still_declines_and_says_so()
    {
        var unresolved = Decline(EntryPoints.ResidenceFactsAndCircumstances.Resolve(new ResidenceFactsAndCircumstancesRequest
        {
            SaleOrExchangeDate = new DateOnly(2026, 1, 1),
            FactsAndCircumstances = [],
        }));

        Assert.Equal(UnresolvedReason.RequiresInterpretation, unresolved.Reason);
        Assert.Equal(MapEntries.ResidenceFactsAndCircumstances.Locator, unresolved.Locator);
        Assert.EndsWith("it was given no facts", unresolved.Attempted, StringComparison.Ordinal);
    }

    [Fact]
    public void A_sale_on_23_December_2002_declines_OutsideCurrentScope_citing_1_121_1_f()
    {
        var unresolved = Decline(EntryPoints.ResidenceFactsAndCircumstances.Resolve(new ResidenceFactsAndCircumstancesRequest
        {
            SaleOrExchangeDate = new DateOnly(2002, 12, 23),
            FactsAndCircumstances = ["lived in the house every weekend"],
        }));

        Assert.Equal(UnresolvedReason.OutsideCurrentScope, unresolved.Reason);
        Assert.Equal(MapEntries.EffectiveDate.Locator, unresolved.Locator);
        Assert.Equal("§ 1.121-1(f)", unresolved.Locator.Citation);
        Assert.Contains("'residence-facts-and-circumstances'", unresolved.Attempted, StringComparison.Ordinal);
        Assert.Contains("'retroactive-election'", unresolved.Attempted, StringComparison.Ordinal);
    }

    [Fact]
    public void Without_a_sale_or_exchange_date_it_refuses_rather_than_assume_one()
    {
        var error = Assert.Throws<ArgumentException>(() => EntryPoints.ResidenceFactsAndCircumstances.Resolve(
            new ResidenceFactsAndCircumstancesRequest { FactsAndCircumstances = ["lived in the house every weekend"] }));

        Assert.Equal(nameof(ResidenceFactsAndCircumstancesRequest.SaleOrExchangeDate), error.ParamName);
    }

    [Fact]
    public void Without_the_facts_it_refuses_rather_than_assume_none()
    {
        var missing = Assert.Throws<ArgumentException>(() => EntryPoints.ResidenceFactsAndCircumstances.Resolve(
            new ResidenceFactsAndCircumstancesRequest { SaleOrExchangeDate = new DateOnly(2026, 1, 1) }));
        var nullFact = Assert.Throws<ArgumentException>(() => EntryPoints.ResidenceFactsAndCircumstances.Resolve(
            new ResidenceFactsAndCircumstancesRequest { SaleOrExchangeDate = new DateOnly(2026, 1, 1), FactsAndCircumstances = [null!] }));

        Assert.Equal(nameof(ResidenceFactsAndCircumstancesRequest.FactsAndCircumstances), missing.ParamName);
        Assert.Equal(nameof(ResidenceFactsAndCircumstancesRequest.FactsAndCircumstances), nullFact.ParamName);
    }

    [Fact]
    public void The_dictionary_dispatch_carries_no_date_and_refuses_the_same_way()
    {
        var error = Assert.Throws<ArgumentException>(() => Registry.Resolve("residence-facts-and-circumstances", RuleRequest.Empty));

        Assert.Equal(nameof(ResidenceFactsAndCircumstancesRequest.SaleOrExchangeDate), error.ParamName);
    }
}
