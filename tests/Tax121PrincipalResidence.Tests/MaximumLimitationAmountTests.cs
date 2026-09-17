using RulesKernel.Resolution;
using Tax121PrincipalResidence.Requests;
using Xunit;

namespace Tax121PrincipalResidence.Tests;

/// <summary>
/// <c>maximum-limitation-amount</c>, § 1.121-1(b)(3)(ii), resolved through
/// <see cref="EntryPoints.MaximumLimitationAmount"/>: $250,000, or $500,000 for certain joint returns, for a sale
/// or exchange within this section; a decline before the effective date; and no input assumed.
/// </summary>
public class MaximumLimitationAmountTests
{
    private static MaximumLimitation Resolved(MaximumLimitationAmountRequest request)
    {
        var resolved = Assert.IsType<Resolution<object>.Resolved>(EntryPoints.MaximumLimitationAmount.Resolve(request));
        return Assert.IsType<MaximumLimitation>(resolved.Value);
    }

    [Fact]
    public void A_sale_on_24_December_2002_not_on_a_certain_joint_return_is_limited_to_250000_citing_1_121_1_b_3_ii()
    {
        var limitation = Resolved(new MaximumLimitationAmountRequest
        {
            SaleOrExchangeDate = new DateOnly(2002, 12, 24),
            CertainJointReturn = false,
        });

        Assert.Equal(250_000m, limitation.Amount);
        Assert.False(limitation.CertainJointReturn);
        Assert.Equal("cfr-26-1.121-1", limitation.Authority.SourceId);
        Assert.Equal("§ 1.121-1(b)(3)(ii)", limitation.Authority.Citation);
    }

    [Fact]
    public void A_sale_on_a_certain_joint_return_is_limited_to_500000_citing_1_121_1_b_3_ii()
    {
        var limitation = Resolved(new MaximumLimitationAmountRequest
        {
            SaleOrExchangeDate = new DateOnly(2026, 1, 1),
            CertainJointReturn = true,
        });

        Assert.Equal(500_000m, limitation.Amount);
        Assert.True(limitation.CertainJointReturn);
        Assert.Equal("§ 1.121-1(b)(3)(ii)", limitation.Authority.Citation);
    }

    [Fact]
    public void A_sale_on_23_December_2002_declines_OutsideCurrentScope_citing_1_121_1_f()
    {
        var unresolved = Assert.IsType<Resolution<object>.Unresolved>(
            EntryPoints.MaximumLimitationAmount.Resolve(new MaximumLimitationAmountRequest
            {
                SaleOrExchangeDate = new DateOnly(2002, 12, 23),
                CertainJointReturn = false,
            }));

        Assert.Equal(UnresolvedReason.OutsideCurrentScope, unresolved.Result.Reason);
        Assert.Equal("§ 1.121-1(f)", unresolved.Result.Locator.Citation);
        Assert.Contains("'maximum-limitation-amount'", unresolved.Result.Attempted, StringComparison.Ordinal);
        Assert.Contains("'retroactive-election'", unresolved.Result.Attempted, StringComparison.Ordinal);
    }

    [Fact]
    public void Without_a_sale_or_exchange_date_it_refuses_rather_than_assume_one()
    {
        var error = Assert.Throws<ArgumentException>(() =>
            EntryPoints.MaximumLimitationAmount.Resolve(new MaximumLimitationAmountRequest { CertainJointReturn = false }));

        Assert.Equal(nameof(MaximumLimitationAmountRequest.SaleOrExchangeDate), error.ParamName);
    }

    [Fact]
    public void Without_whether_the_return_is_a_certain_joint_return_it_refuses_rather_than_assume_one()
    {
        var error = Assert.Throws<ArgumentException>(() =>
            EntryPoints.MaximumLimitationAmount.Resolve(new MaximumLimitationAmountRequest { SaleOrExchangeDate = new DateOnly(2026, 1, 1) }));

        Assert.Equal(nameof(MaximumLimitationAmountRequest.CertainJointReturn), error.ParamName);
    }

    [Fact]
    public void The_dictionary_dispatch_carries_no_inputs_and_refuses()
    {
        var error = Assert.Throws<ArgumentException>(() => Registry.Resolve("maximum-limitation-amount", RuleRequest.Empty));

        Assert.Equal(nameof(MaximumLimitationAmountRequest.SaleOrExchangeDate), error.ParamName);
    }
}
