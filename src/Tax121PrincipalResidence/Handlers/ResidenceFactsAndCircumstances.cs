using RulesKernel.Resolution;

namespace Tax121PrincipalResidence.Requests
{
    /// <summary>The inputs <c>residence-facts-and-circumstances</c>'s rule reads.</summary>
    public sealed partial class ResidenceFactsAndCircumstancesRequest
    {
        /// <summary>The date of the sale or exchange, as a calendar date with no time or zone. Required (decision 0001).</summary>
        public DateOnly? SaleOrExchangeDate { get; init; }

        /// <summary>
        /// The facts and circumstances the caller gives, each in its own words. Required: an empty list says there
        /// are none, and is not assumed for a missing one.
        /// </summary>
        public IReadOnlyList<string>? FactsAndCircumstances { get; init; }
    }
}

namespace Tax121PrincipalResidence
{
    internal static partial class Handlers
    {
        /// <summary>
        /// <c>residence-facts-and-circumstances</c>: the effective-date gate (decision 0001), then
        /// <see cref="Residence.Used"/>, the rule's decline naming the facts given.
        /// </summary>
        internal static partial Resolution<object> ResidenceFactsAndCircumstances(Requests.ResidenceFactsAndCircumstancesRequest request) =>
            Applicability.Gate(MapEntries.ResidenceFactsAndCircumstances, request.SaleOrExchangeDate) is { } decline
                ? Resolution<object>.FromUnresolved(decline)
                : Residence.Used(request.FactsAndCircumstances ?? throw Missing(request.EntryId, nameof(request.FactsAndCircumstances)));
    }
}
