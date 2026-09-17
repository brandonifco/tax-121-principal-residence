using System.Collections.ObjectModel;
using System.Globalization;
using RulesKernel.Provenance;

namespace Tax121PrincipalResidence;

/// <summary>One factor § 1.121-1(b)(2) lists, with the numeral it is printed under.</summary>
/// <param name="Numeral">The printed numeral, without its parentheses: <c>i</c> to <c>vi</c>.</param>
/// <param name="Text">The factor's printed words, without the numeral and the punctuation that joins the list.</param>
public sealed record RelevantFactor(string Numeral, string Text)
{
    /// <inheritdoc/>
    public override string ToString() => string.Create(CultureInfo.InvariantCulture, $"({Numeral}) {Text}");
}

/// <summary>
/// The relevant factors in determining a taxpayer's principal residence, as § 1.121-1(b)(2) lists them:
/// <see cref="MapEntries.PrincipalResidenceFactors"/>, "relevant factors in determining a taxpayer's principal
/// residence, include, but are not limited to— (i) ... (vi) ...".
/// </summary>
/// <remarks>
/// The whole printed list, all six, in the printed order. The corpus names them "in addition to the taxpayer's
/// use of the property", says they "include, but are not limited to" these (<see cref="IsExhaustive"/> is
/// false), and gives no weighting. Which residence is the principal residence is
/// <c>principal-residence-facts-and-circumstances</c>'s question; this value does not answer it.
/// </remarks>
public sealed class RelevantFactors
{
    private RelevantFactors()
    {
    }

    /// <summary>The list as printed.</summary>
    public static RelevantFactors AsPrinted { get; } = new();

    /// <summary>The six factors, (i) to (vi), in the printed order.</summary>
    public IReadOnlyList<RelevantFactor> Factors { get; } = new ReadOnlyCollection<RelevantFactor>(
    [
        new("i", "The taxpayer's place of employment"),
        new("ii", "The principal place of abode of the taxpayer's family members"),
        new("iii", "The address listed on the taxpayer's federal and state tax returns, driver's license, automobile registration, and voter registration card"),
        new("iv", "The taxpayer's mailing address for bills and correspondence"),
        new("v", "The location of the taxpayer's banks"),
        new("vi", "The location of religious organizations and recreational clubs with which the taxpayer is affiliated"),
    ]);

    /// <summary>False: the relevant factors "include, but are not limited to" the six listed.</summary>
    public bool IsExhaustive => false;

    /// <summary>Where the list is printed: <c>§ 1.121-1(b)(2)</c>.</summary>
    public SourceLocator Authority => MapEntries.PrincipalResidenceFactors.Locator;

    /// <inheritdoc/>
    public override string ToString() =>
        string.Create(
            CultureInfo.InvariantCulture,
            $"relevant factors include, but are not limited to: {string.Join("; ", Factors)} [{Authority}]");
}
