using RulesKernel.Resolution;
using Tax121PrincipalResidence.Requests;
using Xunit;

namespace Tax121PrincipalResidence.Tests;

/// <summary>
/// <c>effective-date</c>, § 1.121-1(f), resolved through <see cref="EntryPoints.EffectiveDate"/>: a sale on
/// 24 December 2002 is within this section, a sale the day before is outside it, and no date is assumed.
/// </summary>
public class EffectiveDateEntryPointTests
{
    [Fact]
    public void A_sale_on_24_December_2002_is_within_this_section_citing_1_121_1_f()
    {
        var sale = new DateOnly(2002, 12, 24);

        var resolved = Assert.IsType<Resolution<object>.Resolved>(
            EntryPoints.EffectiveDate.Resolve(new EffectiveDateRequest { SaleOrExchangeDate = sale }));

        var finding = Assert.IsType<SectionApplicability>(resolved.Value);
        Assert.True(finding.Applies);
        Assert.Equal(sale, finding.SaleOrExchangeDate);
        Assert.Equal(new DateOnly(2002, 12, 24), finding.ApplicableFrom);
        Assert.Equal("cfr-26-1.121-1", finding.Authority.SourceId);
        Assert.Equal("§ 1.121-1(f)", finding.Authority.Citation);
        Assert.Equal(EntryPoints.EffectiveDate.Registered.Locator, finding.Authority);
    }

    [Fact]
    public void A_sale_on_23_December_2002_is_outside_this_section_citing_1_121_1_f()
    {
        var sale = new DateOnly(2002, 12, 23);

        var resolved = Assert.IsType<Resolution<object>.Resolved>(
            EntryPoints.EffectiveDate.Resolve(new EffectiveDateRequest { SaleOrExchangeDate = sale }));

        var finding = Assert.IsType<SectionApplicability>(resolved.Value);
        Assert.False(finding.Applies);
        Assert.Equal(sale, finding.SaleOrExchangeDate);
        Assert.Equal(EntryPoints.EffectiveDate.Registered.Locator, finding.Authority);
    }

    [Fact]
    public void Without_a_sale_or_exchange_date_it_refuses_rather_than_assume_one()
    {
        var error = Assert.Throws<ArgumentException>(() => EntryPoints.EffectiveDate.Resolve(new EffectiveDateRequest()));

        Assert.Equal(nameof(EffectiveDateRequest.SaleOrExchangeDate), error.ParamName);
    }

    [Fact]
    public void The_dictionary_dispatch_carries_no_date_and_refuses_the_same_way()
    {
        var error = Assert.Throws<ArgumentException>(() => Registry.Resolve("effective-date", RuleRequest.Empty));

        Assert.Equal(nameof(EffectiveDateRequest.SaleOrExchangeDate), error.ParamName);
    }
}
