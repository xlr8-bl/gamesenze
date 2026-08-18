/**
 * Combo maths — §12. Mirrors pitchside/combo.py; tests/test_combo.py is the
 * reference for the numbers.
 *
 * The independence caveat is the important part. Multiplying leg probabilities
 * assumes the legs are independent, and two picks on the same fixture are not.
 * Showing a confident combined number for a correlated combo would be exactly
 * the kind of confident-looking nonsense the sample gates exist to prevent, so
 * we detect it and say so.
 */

export const MIN_LEGS = 2;
export const MAX_LEGS = 5;

export const DISCLAIMER =
  "We don't hold funds or execute wagers; you place bets at your sportsbook.";

export type Leg = {
  pickId: string;
  fixtureId: string;
  label: string;
  market: string;
  selection: string;
  odds: number;
  bookmaker: string;
  oddsAsOf: string;
  sport: string;
};

export type Quote = {
  totalOdds: number;
  stake: number;
  payout: number;
  profit: number;
  impliedProb: number;
  warnings: string[];
  oddsAsOf: string | null;
};

export function buildQuote(legs: Leg[], stake = 100): Quote {
  const totalOdds = legs.reduce((acc, leg) => acc * leg.odds, 1);
  const payout = stake * totalOdds;
  return {
    totalOdds,
    stake,
    payout,
    profit: payout - stake,
    impliedProb: legs.length ? 1 / totalOdds : 0,
    warnings: correlationWarnings(legs),
    // Only as fresh as the stalest leg — "as of 14:23 UTC" has to be true.
    oddsAsOf: legs.length
      ? legs.map((l) => l.oddsAsOf).sort()[0]
      : null,
  };
}

export function correlationWarnings(legs: Leg[]): string[] {
  const warnings: string[] = [];
  const byFixture = new Map<string, Leg[]>();
  for (const leg of legs) {
    byFixture.set(leg.fixtureId, [...(byFixture.get(leg.fixtureId) ?? []), leg]);
  }
  for (const group of byFixture.values()) {
    if (group.length > 1) {
      const markets = group
        .map((g) => `${g.market} ${g.selection}`)
        .sort()
        .join(", ");
      warnings.push(
        `${group.length} legs on the same fixture (${markets}). These outcomes ` +
          `are correlated, so the combined probability shown is an independence ` +
          `estimate and the true chance differs. Many books will not accept ` +
          `these in one parlay.`,
      );
    }
  }
  if (new Set(legs.map((l) => l.sport)).size > 1) {
    warnings.push(
      "Mixed-sport combo — check your book accepts cross-sport parlays before " +
        "relying on the price shown.",
    );
  }
  return warnings;
}

export function formatUtc(iso: string | null): string {
  if (!iso) return "unknown";
  const d = new Date(iso);
  return `${String(d.getUTCHours()).padStart(2, "0")}:${String(
    d.getUTCMinutes(),
  ).padStart(2, "0")} UTC`;
}
