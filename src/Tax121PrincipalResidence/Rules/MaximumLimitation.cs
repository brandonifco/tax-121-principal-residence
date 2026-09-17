using System.Globalization;
using RulesKernel.Provenance;
using RulesKernel.Resolution;

namespace Tax121PrincipalResidence;

/// <summary>
/// The one maximum limitation amount that applies to the combined sales or exchanges of vacant land and the
/// dwelling unit: <see cref="MapEntries.MaximumLimitationAmount"/>, "Therefore, only one maximum limitation amount
/// of $250,000 ($500,000 for certain joint returns) applies to the combined sales or exchanges of vacant land and
/// the dwelling unit."
/// </summary>
/// <param name="Amount">The maximum limitation amount, in US dollars: $250,000, or $500,000 for a certain joint return.</param>
/// <param name="CertainJointReturn">Whether the caller said the return is one of the "certain joint returns".</param>
public sealed record MaximumLimitation(decimal Amount, bool CertainJointReturn)
{
    /// <summary>Where the value is stated: <c>§ 1.121-1(b)(3)(ii)</c>.</summary>
    public SourceLocator Authority => MapEntries.MaximumLimitationAmount.Locator;

    /// <inheritdoc/>
    public override string ToString() =>
        string.Create(
            CultureInfo.InvariantCulture,
            $"one maximum limitation amount of ${Amount:#,0} applies to the combined sales or exchanges of vacant land and the dwelling unit{(CertainJointReturn ? " (a certain joint return)" : string.Empty)} [{Authority}]");
}

/// <summary>§ 1.121-1(b)(3)(ii): the maximum limitation amount for the combined sale of vacant land and the dwelling unit.</summary>
public static class MaximumLimitations
{
    /// <summary>The maximum limitation amount the evidence prints: $250,000.</summary>
    public static readonly decimal Amount = 250_000m;

    /// <summary>The maximum limitation amount the evidence prints for certain joint returns: $500,000.</summary>
    public static readonly decimal CertainJointReturnAmount = 500_000m;

    /// <summary>
    /// <see cref="MapEntries.MaximumLimitationAmount"/>: the one maximum limitation amount for the combined sales or
    /// exchanges of vacant land and the dwelling unit.
    /// </summary>
    /// <remarks>
    /// Which returns are "certain joint returns" is fixed by section 121(b)(2) and § 1.121-2(a)(3)(i), neither of
    /// them in this engine's corpus. The map makes it a caller-supplied fact, so the caller answers it and this rule
    /// does not.
    /// </remarks>
    /// <param name="certainJointReturn">Whether the return is one of the "certain joint returns".</param>
    /// <returns>The value, which always resolves.</returns>
    public static Resolution<MaximumLimitation> For(bool certainJointReturn) =>
        Resolution<MaximumLimitation>.FromValue(
            new MaximumLimitation(certainJointReturn ? CertainJointReturnAmount : Amount, certainJointReturn));
}
