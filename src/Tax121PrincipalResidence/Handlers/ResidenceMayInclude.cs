using RulesKernel.Resolution;

namespace Tax121PrincipalResidence.Requests
{
    /// <summary>The inputs <c>residence-may-include</c>'s rule reads.</summary>
    public sealed partial class ResidenceMayIncludeRequest
    {
        /// <summary>The date of the sale or exchange, as a calendar date with no time or zone. Required (decision 0001).</summary>
        public DateOnly? SaleOrExchangeDate { get; init; }
    }
}

namespace Tax121PrincipalResidence
{
    internal static partial class Handlers
    {
        /// <summary>
        /// <c>residence-may-include</c>: <see cref="Applicability.Gate"/> first (decision 0001), then
        /// <see cref="Residence.MayInclude"/>, the list as printed.
        /// </summary>
        internal static partial Resolution<object> ResidenceMayInclude(Requests.ResidenceMayIncludeRequest request) =>
            Applicability.Gate(MapEntries.ResidenceMayInclude, request.SaleOrExchangeDate) is { } decline
                ? Resolution<object>.FromUnresolved(decline)
                : Answer(Residence.MayInclude());
    }
}
