/** Shared helpers for cost display across cost-tracking subcomponents. */

/**
 * Format a cost value consistently (6 decimal places, dollar sign).
 * Values below $0.000001 show "< $0.000001".
 */
export function formatCost(usd: number): string {
  if (usd < 0.000001) return "< $0.000001";
  return `$${usd.toFixed(6)}`;
}

/**
 * Background-intensity style for a cost cell — the bar's opacity is
 * proportional to `value / maxValue`, giving a heat-map effect for
 * scannable cost magnitude at a glance.
 *
 * Max opacity is capped at 0.35 so the table remains readable.
 * The bar is rendered as a right-aligned pseudo-bar via flexbox.
 */
export function costBarStyle(
  value: number,
  maxValue: number,
): React.CSSProperties {
  const ratio = maxValue > 0 ? value / maxValue : 0;
  const opacity = Math.min(ratio, 0.35);
  return {
    background: `rgba(37, 99, 235, ${opacity})`,
    borderRadius: 4,
    padding: "1px 6px",
    display: "inline-block",
    fontFamily: "monospace",
    fontSize: 11,
    textAlign: "right",
    whiteSpace: "nowrap",
  };
}
