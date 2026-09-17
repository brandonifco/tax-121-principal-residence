using RulesKernel.Resolution;

namespace Tax121PrincipalResidence.Requests
{
    /// <summary>The inputs <c>principal-residence-factors</c>' rule reads.</summary>
    public sealed partial class PrincipalResidenceFactorsRequest
    {
        /// <summary>The date of the sale or exchange, as a calendar date with no time or zone. Required.</summary>
        public DateOnly? SaleOrExchangeDate { get; init; }
    }
}

namespace Tax121PrincipalResidence
{
    internal static partial class Handlers
    {
        /// <summary>
        /// <c>principal-residence-factors</c>: <see cref="RelevantFactors.AsPrinted"/>, once
        /// <see cref="Applicability.Gate"/> lets the sale or exchange through (decision 0001).
        /// </summary>
        internal static partial Resolution<object> PrincipalResidenceFactors(Requests.PrincipalResidenceFactorsRequest request) =>
            Applicability.Gate(MapEntries.PrincipalResidenceFactors, request.SaleOrExchangeDate) is { } decline
                ? Resolution<object>.FromUnresolved(decline)
                : Resolution<object>.FromValue(RelevantFactors.AsPrinted);
    }
}
