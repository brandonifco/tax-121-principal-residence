using RulesKernel.Resolution;

namespace Tax121PrincipalResidence.Requests
{
    /// <summary>The inputs <c>ownership-and-use-aggregation</c>'s rule reads.</summary>
    public sealed partial class OwnershipAndUseAggregationRequest
    {
        /// <summary>The date of the sale or exchange, as a calendar date with no time or zone. Required.</summary>
        public DateOnly? SaleOrExchangeDate { get; init; }
    }
}

namespace Tax121PrincipalResidence
{
    internal static partial class Handlers
    {
        /// <summary><c>ownership-and-use-aggregation</c>: <see cref="TwoYears.For"/>, two years as 24 full months or 730 days.</summary>
        internal static partial Resolution<object> OwnershipAndUseAggregation(Requests.OwnershipAndUseAggregationRequest request) =>
            Answer(TwoYears.For(request.SaleOrExchangeDate));
    }
}
