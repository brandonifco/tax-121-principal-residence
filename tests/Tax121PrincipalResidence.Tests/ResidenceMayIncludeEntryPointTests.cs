using RulesKernel.Resolution;
using Tax121PrincipalResidence.Requests;
using Xunit;

namespace Tax121PrincipalResidence.Tests;

/// <summary>
/// <c>residence-may-include</c>, § 1.121-1(b), resolved through <see cref="EntryPoints.ResidenceMayInclude"/>: a
/// residence may include a houseboat and a house trailer, and nothing else in this entry's span; a sale before
/// 24 December 2002 declines (decision 0001); no date is assumed.
/// </summary>
public class ResidenceMayIncludeEntryPointTests
{
    [Fact]
    public void A_sale_on_24_December_2002_resolves_a_houseboat_and_a_house_trailer_as_printed_citing_1_121_1_b()
    {
        var resolved = Assert.IsType<Resolution<object>.Resolved>(
            EntryPoints.ResidenceMayInclude.Resolve(new ResidenceMayIncludeRequest { SaleOrExchangeDate = new DateOnly(2002, 12, 24) }));

        var list = Assert.IsType<PropertyThatMayBeAResidence>(resolved.Value);
        Assert.Equal([ResidencePropertyKind.Houseboat, ResidencePropertyKind.HouseTrailer], list.Kinds.AsEnumerable());
        Assert.Equal(["a houseboat", "a house trailer"], list.Kinds.Select(PropertyThatMayBeAResidence.AsPrinted));
        Assert.Equal("cfr-26-1.121-1", list.Authority.SourceId);
        Assert.Equal("§ 1.121-1(b)", list.Authority.Citation);
        Assert.Equal(EntryPoints.ResidenceMayInclude.Registered.Locator, list.Authority);
    }

    [Fact]
    public void A_sale_on_23_December_2002_declines_OutsideCurrentScope_citing_1_121_1_f()
    {
        var unresolved = Assert.IsType<Resolution<object>.Unresolved>(
            EntryPoints.ResidenceMayInclude.Resolve(new ResidenceMayIncludeRequest { SaleOrExchangeDate = new DateOnly(2002, 12, 23) }));

        Assert.Equal(UnresolvedReason.OutsideCurrentScope, unresolved.Result.Reason);
        Assert.Equal(MapEntries.EffectiveDate.Locator, unresolved.Result.Locator);
        Assert.Equal("§ 1.121-1(f)", unresolved.Result.Locator.Citation);
        Assert.Contains("'residence-may-include'", unresolved.Result.Attempted, StringComparison.Ordinal);
    }

    [Fact]
    public void Without_a_sale_or_exchange_date_it_refuses_rather_than_assume_one()
    {
        var error = Assert.Throws<ArgumentException>(() => EntryPoints.ResidenceMayInclude.Resolve(new ResidenceMayIncludeRequest()));

        Assert.Equal(nameof(ResidenceMayIncludeRequest.SaleOrExchangeDate), error.ParamName);
    }

    [Fact]
    public void The_dictionary_dispatch_carries_no_date_and_refuses_the_same_way()
    {
        var error = Assert.Throws<ArgumentException>(() => Registry.Resolve("residence-may-include", RuleRequest.Empty));

        Assert.Equal(nameof(ResidenceMayIncludeRequest.SaleOrExchangeDate), error.ParamName);
    }
}
