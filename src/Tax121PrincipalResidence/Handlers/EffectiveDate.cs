using RulesKernel.Resolution;

namespace Tax121PrincipalResidence.Requests
{
    /// <summary>The inputs <c>effective-date</c>'s rule reads.</summary>
    public sealed partial class EffectiveDateRequest
    {
        /// <summary>The date of the sale or exchange, as a calendar date with no time or zone. Required.</summary>
        public DateOnly? SaleOrExchangeDate { get; init; }
    }
}

namespace Tax121PrincipalResidence
{
    internal static partial class Handlers
    {
        /// <summary><c>effective-date</c>: <see cref="Applicability.Of"/>, whether this section applies to the sale or exchange.</summary>
        internal static partial Resolution<object> EffectiveDate(Requests.EffectiveDateRequest request) =>
            Answer(Applicability.Of(Demand(request.SaleOrExchangeDate, request.EntryId, nameof(request.SaleOrExchangeDate))));
    }
}
