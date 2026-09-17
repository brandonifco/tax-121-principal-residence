using RulesKernel.Resolution;
using Tax121PrincipalResidence.Requests;
using Xunit;

namespace Tax121PrincipalResidence.Tests;

/// <summary>
/// <c>use-requires-occupancy</c>, § 1.121-1(c)(2)(i), resolved through <see cref="EntryPoints.UseRequiresOccupancy"/>:
/// occupancy of the residence is required for the use requirement, so owning without occupying fails the use leg
/// while the ownership leg's fact holds. A sale before the effective date declines (decision 0001), and no input is
/// assumed.
/// </summary>
public class UseRequiresOccupancyTests
{
    private static readonly DateOnly InScopeSale = new(2020, 6, 30);

    private static OccupancyFinding Resolve(bool owned, bool occupied)
    {
        var resolved = Assert.IsType<Resolution<object>.Resolved>(
            EntryPoints.UseRequiresOccupancy.Resolve(new UseRequiresOccupancyRequest
            {
                SaleOrExchangeDate = InScopeSale,
                TaxpayerOwned = owned,
                TaxpayerOccupied = occupied,
            }));

        return Assert.IsType<OccupancyFinding>(resolved.Value);
    }

    [Fact]
    public void Owning_without_occupying_fails_the_use_leg_while_the_ownership_leg_holds_citing_1_121_1_c_2()
    {
        var finding = Resolve(owned: true, occupied: false);

        Assert.True(finding.Owned);
        Assert.False(finding.OccupancyRequirementMet);
        Assert.Equal("cfr-26-1.121-1", finding.Authority.SourceId);
        Assert.Equal("§ 1.121-1(c)(2)", finding.Authority.Citation);
        Assert.Equal(EntryPoints.UseRequiresOccupancy.Registered.Locator, finding.Authority);
    }

    [Fact]
    public void Occupying_meets_the_occupancy_requirement_whether_or_not_the_taxpayer_owned()
    {
        var occupiedNotOwned = Resolve(owned: false, occupied: true);
        Assert.False(occupiedNotOwned.Owned);
        Assert.True(occupiedNotOwned.OccupancyRequirementMet);

        var occupiedAndOwned = Resolve(owned: true, occupied: true);
        Assert.True(occupiedAndOwned.Owned);
        Assert.True(occupiedAndOwned.OccupancyRequirementMet);
    }

    [Fact]
    public void A_sale_on_23_December_2002_declines_OutsideCurrentScope_citing_1_121_1_f()
    {
        var unresolved = Assert.IsType<Resolution<object>.Unresolved>(
            EntryPoints.UseRequiresOccupancy.Resolve(new UseRequiresOccupancyRequest
            {
                SaleOrExchangeDate = new DateOnly(2002, 12, 23),
                TaxpayerOwned = true,
                TaxpayerOccupied = false,
            }));

        Assert.Equal(UnresolvedReason.OutsideCurrentScope, unresolved.Result.Reason);
        Assert.Equal(MapEntries.EffectiveDate.Locator, unresolved.Result.Locator);
        Assert.Equal("§ 1.121-1(f)", unresolved.Result.Locator.Citation);
        Assert.Contains("'use-requires-occupancy'", unresolved.Result.Attempted, StringComparison.Ordinal);
        Assert.Contains("'retroactive-election'", unresolved.Result.Attempted, StringComparison.Ordinal);
    }

    [Fact]
    public void Without_a_sale_or_exchange_date_it_refuses_rather_than_assume_one()
    {
        var error = Assert.Throws<ArgumentException>(() => EntryPoints.UseRequiresOccupancy.Resolve(
            new UseRequiresOccupancyRequest { TaxpayerOwned = true, TaxpayerOccupied = true }));

        Assert.Equal(nameof(UseRequiresOccupancyRequest.SaleOrExchangeDate), error.ParamName);
    }

    [Fact]
    public void Without_whether_the_taxpayer_occupied_it_refuses_rather_than_assume_either_answer()
    {
        var error = Assert.Throws<ArgumentException>(() => EntryPoints.UseRequiresOccupancy.Resolve(
            new UseRequiresOccupancyRequest { SaleOrExchangeDate = InScopeSale, TaxpayerOwned = true }));

        Assert.Equal(nameof(UseRequiresOccupancyRequest.TaxpayerOccupied), error.ParamName);
    }

    [Fact]
    public void Without_whether_the_taxpayer_owned_it_refuses_rather_than_assume_either_answer()
    {
        var error = Assert.Throws<ArgumentException>(() => EntryPoints.UseRequiresOccupancy.Resolve(
            new UseRequiresOccupancyRequest { SaleOrExchangeDate = InScopeSale, TaxpayerOccupied = false }));

        Assert.Equal(nameof(UseRequiresOccupancyRequest.TaxpayerOwned), error.ParamName);
    }
}
