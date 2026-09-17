using RulesKernel.Resolution;

namespace Tax121PrincipalResidence.Requests
{
    /// <summary>The inputs <c>use-requires-occupancy</c>'s rule reads.</summary>
    public sealed partial class UseRequiresOccupancyRequest
    {
        /// <summary>The date of the sale or exchange, as a calendar date with no time or zone. Required (decision 0001).</summary>
        public DateOnly? SaleOrExchangeDate { get; init; }

        /// <summary>Whether the taxpayer owned the residence. Required, never defaulted.</summary>
        public bool? TaxpayerOwned { get; init; }

        /// <summary>Whether the taxpayer occupied the residence. Required, never defaulted.</summary>
        public bool? TaxpayerOccupied { get; init; }
    }
}

namespace Tax121PrincipalResidence
{
    internal static partial class Handlers
    {
        /// <summary>
        /// <c>use-requires-occupancy</c>: the effective-date gate (decision 0001), then <see cref="Occupancy.Of"/>.
        /// </summary>
        internal static partial Resolution<object> UseRequiresOccupancy(Requests.UseRequiresOccupancyRequest request) =>
            Applicability.Gate(MapEntries.UseRequiresOccupancy, request.SaleOrExchangeDate) is { } decline
                ? Resolution<object>.FromUnresolved(decline)
                : Answer(Occupancy.Of(
                    Demand(request.TaxpayerOwned, request.EntryId, nameof(request.TaxpayerOwned)),
                    Demand(request.TaxpayerOccupied, request.EntryId, nameof(request.TaxpayerOccupied))));
    }
}
