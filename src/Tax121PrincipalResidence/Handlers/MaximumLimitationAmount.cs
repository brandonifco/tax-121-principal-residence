using RulesKernel.Resolution;

namespace Tax121PrincipalResidence.Requests
{
    /// <summary>The inputs <c>maximum-limitation-amount</c>'s rule reads.</summary>
    public sealed partial class MaximumLimitationAmountRequest
    {
        /// <summary>The date of the sale or exchange, as a calendar date with no time or zone. Required (decision 0001).</summary>
        public DateOnly? SaleOrExchangeDate { get; init; }

        /// <summary>
        /// Whether the return is one of the "certain joint returns" the $500,000 amount is for, as section 121(b)(2)
        /// and § 1.121-2(a)(3)(i) fix it. Required: the caller answers it, and it is never assumed.
        /// </summary>
        public bool? CertainJointReturn { get; init; }
    }
}

namespace Tax121PrincipalResidence
{
    internal static partial class Handlers
    {
        /// <summary>
        /// <c>maximum-limitation-amount</c>: <see cref="Applicability.Gate"/>, then <see cref="MaximumLimitations.For"/>.
        /// </summary>
        internal static partial Resolution<object> MaximumLimitationAmount(Requests.MaximumLimitationAmountRequest request) =>
            Applicability.Gate(MapEntries.MaximumLimitationAmount, request.SaleOrExchangeDate) is { } decline
                ? Resolution<object>.FromUnresolved(decline)
                : Answer(MaximumLimitations.For(Demand(request.CertainJointReturn, request.EntryId, nameof(request.CertainJointReturn))));
    }
}
